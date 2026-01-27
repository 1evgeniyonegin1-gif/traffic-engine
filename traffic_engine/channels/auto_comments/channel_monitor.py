"""
Channel Monitor - Мониторинг каналов для автокомментирования.

Использует Telethon для подписки на обновления каналов
и обработки новых постов.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Set

from loguru import logger
from telethon import TelegramClient
from telethon.tl.types import Message, Channel
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
)
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import TargetChannel, Tenant
from traffic_engine.core import AccountManager, HumanSimulator
from traffic_engine.notifications import TelegramNotifier

from .comment_generator import CommentGenerator
from .comment_poster import CommentPoster


class ChannelMonitor:
    """
    Мониторинг каналов для автокомментирования.

    Функции:
    - Подписка на обновления целевых каналов
    - Фильтрация постов (реклама, репосты, короткие)
    - Вызов генератора и постера комментариев

    Использует Telethon для работы с Telegram API.
    """

    def __init__(
        self,
        tenant_id: int,
        account_manager: AccountManager,
        notifier: Optional[TelegramNotifier] = None,
        on_new_post: Optional[Callable] = None,
    ):
        """
        Initialize channel monitor.

        Args:
            tenant_id: ID тенанта
            account_manager: Менеджер аккаунтов
            notifier: Telegram notifier для алертов
            on_new_post: Callback для новых постов (опционально)
        """
        self.tenant_id = tenant_id
        self.account_manager = account_manager
        self.notifier = notifier
        self.on_new_post = on_new_post

        self.human_sim = HumanSimulator()
        self.comment_generator: Optional[CommentGenerator] = None
        self.comment_poster: Optional[CommentPoster] = None

        self._running = False
        self._client: Optional[TelegramClient] = None
        self._channels: Dict[int, TargetChannel] = {}  # channel_id -> TargetChannel
        self._subscribed_channels: Set[int] = set()  # Каналы, на которые уже подписаны
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 30  # Начальная задержка в секундах

    async def initialize(self, tenant_name: str = "infobusiness") -> None:
        """
        Initialize monitor with generators and poster.

        Args:
            tenant_name: Название тенанта для контекста
        """
        self.comment_generator = CommentGenerator(tenant_name=tenant_name)
        self.comment_poster = CommentPoster(self.account_manager, self.notifier)

        # Загружаем каналы из БД
        await self._load_channels()

        logger.info(f"Channel monitor initialized with {len(self._channels)} channels")

    async def _load_channels(self) -> None:
        """Загрузить активные каналы из БД."""
        async with get_session() as session:
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.tenant_id == self.tenant_id,
                    TargetChannel.is_active == True,
                )
            )
            channels = result.scalars().all()

            self._channels = {ch.channel_id: ch for ch in channels}

    async def start(self) -> None:
        """Запустить мониторинг каналов с автоперезапуском."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info("Starting channel monitor...")

        while self._running:
            try:
                # Получаем клиент от первого доступного аккаунта
                account = await self.account_manager.get_available_account("comment")
                if not account:
                    logger.error("No accounts available for monitoring")
                    await asyncio.sleep(60)
                    continue

                self._client = await self.account_manager.get_client(account.id)
                if not self._client:
                    logger.error("Failed to get client")
                    await asyncio.sleep(60)
                    continue

                await self._client.connect()
                if not await self._client.is_user_authorized():
                    logger.error("Client not authorized!")
                    await asyncio.sleep(60)
                    continue

                logger.info("✅ Telethon client connected")
                self._reconnect_attempts = 0  # Сбрасываем счётчик при успешном подключении

                # Медленная подписка на каналы (1-2 за запуск)
                await self._slow_join_channels()

                # Запускаем polling
                await self._polling_loop()

            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                # Ошибки сети — пробуем переподключиться
                self._reconnect_attempts += 1
                delay = min(self._reconnect_delay * (2 ** self._reconnect_attempts), 600)  # Max 10 min

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error(f"❌ Max reconnect attempts ({self._max_reconnect_attempts}) reached. Stopping.")
                    self._running = False
                    break

                logger.warning(
                    f"🔌 Connection lost: {e}. "
                    f"Attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}. "
                    f"Reconnecting in {delay}s..."
                )
                await self._safe_disconnect()
                await asyncio.sleep(delay)

            except Exception as e:
                import traceback
                logger.error(f"❌ Monitor error: {e}\n{traceback.format_exc()}")
                self._reconnect_attempts += 1
                delay = 60

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error(f"❌ Max reconnect attempts reached. Stopping.")
                    self._running = False
                    break

                logger.info(f"Restarting in {delay}s...")
                await self._safe_disconnect()
                await asyncio.sleep(delay)

        await self._safe_disconnect()
        logger.info("Channel monitor stopped")

    async def _safe_disconnect(self) -> None:
        """Безопасно отключить клиент."""
        try:
            if self._client and self._client.is_connected():
                await self._client.disconnect()
        except Exception as e:
            logger.debug(f"Disconnect error (ignored): {e}")

    async def _slow_join_channels(self) -> None:
        """
        Медленная подписка на каналы (1-2 за запуск).

        Безопасная стратегия:
        - Подписываемся только на 1-2 канала за цикл запуска
        - Пауза 5-10 минут между подписками
        - Пропускаем каналы, на которые уже подписаны
        """
        # Находим каналы, на которые нужно подписаться
        channels_to_join = [
            ch for ch_id, ch in self._channels.items()
            if ch_id not in self._subscribed_channels and ch.username
        ]

        if not channels_to_join:
            logger.debug("All channels already subscribed or no username")
            return

        # Выбираем 1-2 случайных канала
        num_to_join = min(random.randint(1, 2), len(channels_to_join))
        selected = random.sample(channels_to_join, num_to_join)

        logger.info(f"📢 Slow join: {num_to_join} channel(s) this session")

        for channel in selected:
            try:
                # Проверяем, можем ли читать без подписки
                try:
                    entity = await self._client.get_entity(channel.username)
                    self._subscribed_channels.add(channel.channel_id)
                    logger.debug(f"Can read @{channel.username} without subscription")
                    continue
                except ChannelPrivateError:
                    pass  # Нужна подписка

                # Подписываемся
                await self._client(JoinChannelRequest(channel.username))
                self._subscribed_channels.add(channel.channel_id)
                logger.info(f"✅ Joined @{channel.username}")

                # Большая пауза между подписками (5-10 минут)
                if channel != selected[-1]:
                    delay = random.randint(300, 600)
                    logger.info(f"⏳ Waiting {delay // 60} min before next join...")
                    await asyncio.sleep(delay)

            except FloodWaitError as e:
                logger.warning(f"⚠️ FloodWait for {e.seconds}s on @{channel.username}")
                await asyncio.sleep(e.seconds + 10)
            except (ChannelPrivateError, UserBannedInChannelError) as e:
                logger.warning(f"⚠️ Cannot join @{channel.username}: {e}")
            except Exception as e:
                logger.error(f"❌ Failed to join @{channel.username}: {e}")

    async def _join_channels(self) -> None:
        """Вступить в целевые каналы (если ещё не вступили). DEPRECATED - use _slow_join_channels."""
        for channel_id, channel in self._channels.items():
            try:
                # Проверяем, вступили ли уже
                entity = await self._client.get_entity(channel_id)
                logger.debug(f"Already in channel: {getattr(entity, 'title', channel_id)}")
            except Exception:
                # Пробуем вступить
                try:
                    if channel.username:
                        await self._client(JoinChannelRequest(channel.username))
                        logger.info(f"Joined channel: @{channel.username}")
                except Exception as e:
                    logger.error(f"Failed to join {channel.username}: {e}")

    async def _polling_loop(self) -> None:
        """
        Основной цикл polling новых постов.

        Каждые 30-60 секунд проверяем каналы на новые посты.
        При сетевых ошибках пробрасываем их наверх для автоперезапуска.
        """
        consecutive_errors = 0

        while self._running:
            try:
                # Проверяем рабочие часы
                if not self.human_sim.is_working_hours():
                    logger.debug("Outside working hours, sleeping...")
                    await asyncio.sleep(300)  # 5 минут
                    continue

                # Проверяем каналы
                await self._check_channels()
                consecutive_errors = 0  # Сбрасываем при успехе

                # Случайная пауза между проверками
                delay = self.human_sim.get_random_pause(30, 90)
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                logger.info("Polling cancelled")
                break
            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                # Сетевые ошибки — пробрасываем наверх для переподключения
                logger.warning(f"🔌 Network error in polling: {e}")
                raise
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Polling error ({consecutive_errors}): {e}")

                if consecutive_errors >= 5:
                    logger.error("Too many consecutive errors, triggering reconnect")
                    raise ConnectionError(f"Too many errors: {e}")

                await asyncio.sleep(60)

    async def _check_channels(self) -> None:
        """Проверить все каналы на новые посты."""
        for channel_id, channel in self._channels.items():
            try:
                await self._check_channel(channel)
            except Exception as e:
                logger.error(f"Error checking channel {channel.username}: {e}")

    async def _check_channel(self, channel: TargetChannel) -> None:
        """
        Проверить один канал на новые посты.

        Args:
            channel: Канал для проверки
        """
        # Получаем последние сообщения через Telethon
        # Используем username для публичных каналов (не требует подписки)
        messages: List[Message] = []
        channel_ref = channel.username if channel.username else channel.channel_id
        async for message in self._client.iter_messages(
            channel_ref,
            limit=5  # Последние 5 постов
        ):
            messages.append(message)

        if not messages:
            return

        # Фильтруем новые посты (которые ещё не обрабатывали)
        new_posts = [
            msg for msg in messages
            if msg.id > (channel.last_post_id or 0)
        ]

        if not new_posts:
            logger.debug(f"No new posts in @{channel.username} (last_post_id={channel.last_post_id})")
            return

        logger.info(f"✨ Found {len(new_posts)} NEW posts in @{channel.username}!")

        # Обрабатываем каждый новый пост
        for post in sorted(new_posts, key=lambda m: m.id):
            await self._process_post(channel, post)

        # Обновляем last_post_id
        await self._update_last_post_id(channel.id, messages[0].id)

    async def _process_post(self, channel: TargetChannel, post: Message) -> None:
        """
        Обработать новый пост.

        Args:
            channel: Канал
            post: Сообщение (пост) - Telethon Message
        """
        # Извлекаем текст (Telethon использует post.message вместо post.text)
        post_text = post.message or ""

        # Проверяем, нужно ли комментировать
        should_comment = await self.comment_generator.should_comment(
            post_text=post_text,
            is_ad=self._is_ad(post),
            is_repost=post.fwd_from is not None,  # Telethon использует fwd_from
        )

        if not should_comment:
            logger.info(f"⏭️  Skipping post {post.id} in @{channel.username} (ad or repost)")
            return

        # Ждём перед действием (имитация человека)
        if not self.human_sim.should_act_now():
            logger.info(f"⏭️  Random skip post {post.id} in @{channel.username} (human-like behavior)")
            return

        logger.info(f"📝 Generating comment for post {post.id} in @{channel.username}...")

        # Генерируем комментарий
        strategy = self.comment_generator.get_random_strategy()
        comment = await self.comment_generator.generate(
            post_text=post_text,
            strategy=strategy,
            channel_title=channel.title,
        )

        if not comment:
            logger.warning(f"❌ Failed to generate comment for post {post.id}")
            return

        logger.info(f"✅ Generated comment ({len(comment)} chars): {comment[:50]}...")

        # Ждём случайное время (5-10 минут после поста)
        # Telethon: post.date может быть offset-aware или naive
        now = datetime.now(timezone.utc)
        post_date = post.date
        if post_date.tzinfo is None:
            post_date = post_date.replace(tzinfo=timezone.utc)
        post_age = (now - post_date).total_seconds()

        # ВСЕГДА ждём 5-10 минут (безопаснее для прогрева)
        delay = self.human_sim.get_random_pause(300, 600)  # 5-10 минут
        logger.info(f"Post is {post_age/60:.1f} min old. Waiting {delay/60:.1f} min before commenting...")
        await asyncio.sleep(delay)

        # Публикуем комментарий
        success = await self.comment_poster.post_comment(
            channel_id=channel.channel_id,
            message_id=post.id,
            comment_text=comment,
            strategy=strategy,
            channel_username=channel.username,
        )

        if success:
            # Обновляем статистику канала
            await self._update_channel_stats(channel.id)

    def _is_ad(self, post: Message) -> bool:
        """Определить, является ли пост рекламой."""
        # Telethon использует post.message вместо post.text
        text = (post.message or "").lower()

        ad_markers = [
            "реклама", "#реклама", "erid:", "promo", "#ad",
            "рекламный пост", "на правах рекламы",
        ]

        for marker in ad_markers:
            if marker in text:
                return True

        return False

    async def _update_last_post_id(self, channel_db_id: int, post_id: int) -> None:
        """Обновить ID последнего обработанного поста."""
        async with get_session() as session:
            channel = await session.get(TargetChannel, channel_db_id)
            if channel:
                channel.last_post_id = post_id
                channel.last_processed_at = datetime.now(timezone.utc)
                await session.commit()

    async def _update_channel_stats(self, channel_db_id: int) -> None:
        """Обновить статистику канала."""
        async with get_session() as session:
            channel = await session.get(TargetChannel, channel_db_id)
            if channel:
                channel.posts_processed += 1
                channel.comments_posted += 1
                await session.commit()

    async def stop(self) -> None:
        """Остановить мониторинг."""
        logger.info("Stopping channel monitor...")
        self._running = False
        await self._safe_disconnect()
        logger.info("Channel monitor stopped")

    async def add_channel(
        self,
        channel_id: int,
        username: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        Добавить канал для мониторинга.

        Args:
            channel_id: ID канала
            username: Username канала (без @)
            title: Название канала
        """
        async with get_session() as session:
            # Проверяем, есть ли уже
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.channel_id == channel_id
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(f"Channel {channel_id} already exists")
                return

            # Создаём новый
            channel = TargetChannel(
                tenant_id=self.tenant_id,
                channel_id=channel_id,
                username=username,
                title=title or f"Channel {channel_id}",
                is_active=True,
            )
            session.add(channel)
            await session.commit()

            # Добавляем в память
            self._channels[channel_id] = channel

            logger.info(f"Added channel @{username or channel_id}")

    async def remove_channel(self, channel_id: int) -> None:
        """Удалить канал из мониторинга."""
        async with get_session() as session:
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.channel_id == channel_id
                )
            )
            channel = result.scalar_one_or_none()

            if channel:
                channel.is_active = False
                await session.commit()

                # Удаляем из памяти
                self._channels.pop(channel_id, None)

                logger.info(f"Removed channel {channel_id}")
