"""
Comment Poster - Публикация комментариев в Telegram.

Использует Telethon для отправки комментариев
с обработкой ошибок и FloodWait.
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional, Any

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.types import Channel
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    ChannelPrivateError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChatAdminRequiredError,
)

from traffic_engine.core import AccountManager, RateLimiter, HumanSimulator
from traffic_engine.database import get_session
from traffic_engine.database.models import TrafficAction
from traffic_engine.notifications import TelegramNotifier


class CommentPoster:
    """
    Публикация комментариев в Telegram каналы.

    Функции:
    - Отправка комментариев через Telethon
    - Обработка FloodWait и других ошибок
    - Логирование действий в БД
    - Кэширование entity каналов
    """

    def __init__(
        self,
        account_manager: AccountManager,
        notifier: Optional[TelegramNotifier] = None,
    ):
        """
        Initialize comment poster.

        Args:
            account_manager: Менеджер аккаунтов
            notifier: Telegram notifier для алертов (опционально)
        """
        self.account_manager = account_manager
        self.rate_limiter = RateLimiter()
        self.human_sim = HumanSimulator()
        self.notifier = notifier

        # Кэш entity каналов: username -> entity
        self._entity_cache: Dict[str, Any] = {}
        # Кэш групп обсуждения: username -> discussion_entity
        self._discussion_cache: Dict[str, Any] = {}

    async def post_comment(
        self,
        channel_id: int,
        message_id: int,
        comment_text: str,
        strategy: str = "smart",
        channel_username: Optional[str] = None,
    ) -> bool:
        """
        Опубликовать комментарий под постом.

        Args:
            channel_id: ID канала (для логирования)
            message_id: ID поста (сообщения)
            comment_text: Текст комментария
            strategy: Стратегия (для логирования)
            channel_username: Username канала (для Telethon)

        Returns:
            True если успешно
        """
        # Получаем доступный аккаунт
        account = await self.account_manager.get_available_account("comment")
        if not account:
            logger.warning("No available accounts for commenting")
            # Уведомляем админа
            if self.notifier:
                await self.notifier.notify_all_accounts_cooldown()
            return False

        # Получаем Telethon клиент
        client = await self.account_manager.get_client(account.id)
        if not client:
            logger.error(f"Failed to get client for account {account.phone}")
            return False

        # Проверяем rate limit
        can_perform, wait_time = self.rate_limiter.can_perform_now("comment")
        if not can_perform:
            logger.debug(f"Rate limited, waiting {wait_time:.0f}s")
            await asyncio.sleep(wait_time)

        # Получаем задержку
        delay = self.rate_limiter.get_delay("comment")

        # Симуляция печати
        typing_delay = self.human_sim.get_typing_delay(comment_text)
        total_delay = max(delay, typing_delay)

        logger.debug(f"Waiting {total_delay:.0f}s before posting...")
        await asyncio.sleep(total_delay)

        # Отправляем комментарий
        try:
            # Подключаемся если нужно
            if not client.is_connected():
                await client.connect()

            # Получаем entity канала (с кэшированием)
            entity = await self._get_channel_entity(
                client=client,
                channel_username=channel_username,
                channel_id=channel_id,
            )

            if not entity:
                logger.error(f"Failed to get entity for channel {channel_username or channel_id}")
                await self._log_action(
                    account_id=account.id,
                    tenant_id=self.account_manager.tenant_id,
                    action_type="comment",
                    target_channel_id=channel_id,
                    target_message_id=message_id,
                    content=comment_text,
                    status="failed",
                    error_message="Failed to get channel entity",
                )
                return False

            # Получаем группу обсуждения (linked chat) для комментирования
            discussion_entity = await self._get_discussion_entity(
                client=client,
                channel_entity=entity,
                channel_username=channel_username,
            )

            if discussion_entity:
                # Отправляем в группу обсуждения
                await client.send_message(
                    entity=discussion_entity,
                    message=comment_text,
                    reply_to=message_id,
                )
            else:
                # Fallback: пробуем отправить напрямую в канал
                logger.warning(f"No discussion group found for {channel_username}, trying direct send")
                await client.send_message(
                    entity=entity,
                    message=comment_text,
                    reply_to=message_id,
                )

            # Записываем успешное действие
            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="success",
            )

            # Обновляем счётчики
            await self.account_manager.mark_action(account.id, "comment", success=True)
            self.rate_limiter.record_action("comment")

            # Периодически сбрасываем множитель
            self.rate_limiter.reset_multiplier()

            logger.info(
                f"Posted comment to channel {channel_id}, post {message_id} "
                f"via account {account.phone}"
            )
            return True

        except FloodWaitError as e:
            # Обрабатываем FloodWait
            logger.warning(f"FloodWait: {e.seconds}s for account {account.phone}")

            # Уведомляем если FloodWait больше часа
            if self.notifier and e.seconds >= 3600:
                await self.notifier.notify_flood_wait(account.phone, e.seconds)

            await self.account_manager.set_cooldown(
                account.id,
                e.seconds,
                reason="flood_wait"
            )

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="flood_wait",
                error_message=f"FloodWait: {e.seconds}s",
                flood_wait_seconds=e.seconds,
            )

            return False

        except SlowModeWaitError as e:
            # Slowmode в канале
            logger.warning(f"SlowModeWait: {e.seconds}s for channel {channel_id}")

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message=f"SlowModeWait: {e.seconds}s",
            )

            return False

        except (ChatWriteForbiddenError, ChatAdminRequiredError) as e:
            # Нет прав на комментарии - попробуем подписаться на группу обсуждения
            error_type = type(e).__name__
            logger.warning(f"{error_type} for channel {channel_id} - trying to join discussion group...")

            # Попытка подписаться на группу обсуждения
            try:
                if entity and isinstance(entity, Channel):
                    full_channel = await client(GetFullChannelRequest(entity))
                    linked_chat_id = full_channel.full_chat.linked_chat_id
                    if linked_chat_id:
                        discussion = await client.get_entity(linked_chat_id)
                        await client(JoinChannelRequest(discussion))
                        logger.info(f"✅ Joined discussion group for @{channel_username} - retry on next post")
                    else:
                        logger.warning(f"Channel @{channel_username} has no discussion group")
            except Exception as join_error:
                logger.error(f"Failed to join discussion group: {join_error}")

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message=f"{error_type} - attempted to join discussion",
            )

            return False

        except UserBannedInChannelError:
            # Аккаунт забанен в канале
            logger.error(f"Account {account.phone} banned in channel {channel_id}")

            # Уведомляем админа
            if self.notifier:
                await self.notifier.notify_account_banned(
                    account.phone,
                    channel_username or str(channel_id)
                )

            await self.account_manager.set_account_status(
                account.id,
                status="banned",
                reason=f"Banned in channel {channel_id}"
            )

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="banned",
                error_message="UserBannedInChannel",
            )

            return False

        except ChannelPrivateError:
            # Канал приватный
            logger.warning(f"Channel {channel_id} is private")

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message="ChannelPrivate",
            )

            return False

        except Exception as e:
            # Другие ошибки
            logger.error(f"Failed to post comment: {e}")

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message=str(e),
            )

            return False

    async def _get_channel_entity(
        self,
        client: TelegramClient,
        channel_username: Optional[str],
        channel_id: int,
    ) -> Optional[Any]:
        """
        Получить entity канала с кэшированием.

        Args:
            client: Telethon клиент
            channel_username: Username канала (без @)
            channel_id: ID канала

        Returns:
            Entity канала или None при ошибке
        """
        # Формируем ключ кэша
        cache_key = channel_username or str(channel_id)

        # Проверяем кэш
        if cache_key in self._entity_cache:
            return self._entity_cache[cache_key]

        try:
            # Пробуем получить по username (с @)
            if channel_username:
                username_with_at = f"@{channel_username}" if not channel_username.startswith("@") else channel_username
                entity = await client.get_entity(username_with_at)
                self._entity_cache[cache_key] = entity
                logger.debug(f"Cached entity for @{channel_username}")
                return entity

            # Пробуем по ID
            entity = await client.get_entity(channel_id)
            self._entity_cache[cache_key] = entity
            logger.debug(f"Cached entity for channel_id {channel_id}")
            return entity

        except ValueError as e:
            logger.error(f"Entity not found: {e}")
            return None
        except ChannelPrivateError:
            logger.error(f"Channel {channel_username or channel_id} is private")
            return None
        except Exception as e:
            logger.error(f"Failed to get entity: {e}")
            return None

    async def _get_discussion_entity(
        self,
        client: TelegramClient,
        channel_entity: Any,
        channel_username: Optional[str],
    ) -> Optional[Any]:
        """
        Получить entity группы обсуждения (linked chat) канала.

        Комментарии в Telegram отправляются не в канал, а в его
        linked chat (группу обсуждения). Без этого будет ошибка
        "Chat admin privileges required".

        Args:
            client: Telethon клиент
            channel_entity: Entity канала
            channel_username: Username канала (для кэширования)

        Returns:
            Entity группы обсуждения или None если её нет
        """
        cache_key = channel_username or str(getattr(channel_entity, 'id', 'unknown'))

        # Проверяем кэш
        if cache_key in self._discussion_cache:
            cached = self._discussion_cache[cache_key]
            if cached is None:
                return None  # Уже проверяли, нет группы
            return cached

        try:
            # Получаем полную информацию о канале
            if not isinstance(channel_entity, Channel):
                logger.debug(f"Entity {cache_key} is not a Channel, skipping discussion lookup")
                self._discussion_cache[cache_key] = None
                return None

            full_channel = await client(GetFullChannelRequest(channel_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                logger.debug(f"Channel {cache_key} has no discussion group (comments disabled)")
                self._discussion_cache[cache_key] = None
                return None

            # Получаем entity группы обсуждения
            discussion = await client.get_entity(linked_chat_id)
            self._discussion_cache[cache_key] = discussion
            logger.info(f"Found discussion group for @{cache_key}: {getattr(discussion, 'title', linked_chat_id)}")
            return discussion

        except Exception as e:
            logger.error(f"Failed to get discussion group for {cache_key}: {e}")
            self._discussion_cache[cache_key] = None
            return None

    async def _log_action(
        self,
        account_id: int,
        tenant_id: int,
        action_type: str,
        target_channel_id: Optional[int] = None,
        target_message_id: Optional[int] = None,
        content: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        flood_wait_seconds: Optional[int] = None,
    ) -> None:
        """Записать действие в БД."""
        async with get_session() as session:
            action = TrafficAction(
                tenant_id=tenant_id,
                account_id=account_id,
                action_type=action_type,
                target_channel_id=target_channel_id,
                target_message_id=target_message_id,
                content=content,
                status=status,
                error_message=error_message,
                flood_wait_seconds=flood_wait_seconds,
                ai_model="yandexgpt",  # YandexGPT используется
            )
            session.add(action)
            await session.commit()
