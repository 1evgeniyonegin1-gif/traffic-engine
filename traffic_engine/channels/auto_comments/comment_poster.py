"""
Comment Poster - Публикация комментариев в Telegram.

Использует Telethon для отправки комментариев
с обработкой ошибок и FloodWait.

ИСПРАВЛЕНЫ ОШИБКИ (31.01.2026):
1. "Failed to get channel entity" - автоподписка на канал
2. "Invalid channel object" - правильная передача entity
3. "You join the discussion group before commenting" - автовступление в discussion group
4. "authorization key used under two different IP" - обработка конфликта сессий
"""

import asyncio
from datetime import datetime
from typing import Dict, Optional, Any

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.types import Channel, InputPeerChannel
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    ChannelPrivateError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChatAdminRequiredError,
    AuthKeyDuplicatedError,
    UserNotParticipantError,
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
    - Автоматическое вступление в каналы и группы обсуждения
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

        # Кэш entity каналов: (account_id, username) -> entity
        self._entity_cache: Dict[tuple, Any] = {}
        # Кэш групп обсуждения: (account_id, username) -> discussion_entity
        self._discussion_cache: Dict[tuple, Any] = {}
        # Каналы, на которые уже подписались: (account_id, username)
        self._joined_channels: set = set()
        # Группы обсуждения, в которые уже вступили: (account_id, discussion_id)
        self._joined_discussions: set = set()

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
        entity = None
        try:
            # Подключаемся если нужно
            if not client.is_connected():
                await client.connect()

            # ШАГ 1: Получаем entity канала (с автоподпиской)
            entity = await self._get_channel_entity(
                client=client,
                account_id=account.id,
                channel_username=channel_username,
                channel_id=channel_id,
            )

            if not entity:
                error_msg = f"Failed to get entity for channel @{channel_username or channel_id}"
                logger.error(error_msg)
                await self._log_action(
                    account_id=account.id,
                    tenant_id=self.account_manager.tenant_id,
                    action_type="comment",
                    target_channel_id=channel_id,
                    target_message_id=message_id,
                    content=comment_text,
                    status="failed",
                    error_message=error_msg,
                )
                return False

            # ШАГ 2: Получаем группу обсуждения И ВСТУПАЕМ в неё
            discussion_entity = await self._get_and_join_discussion(
                client=client,
                account_id=account.id,
                channel_entity=entity,
                channel_username=channel_username,
            )

            # ШАГ 3: Отправляем комментарий
            if discussion_entity:
                # Отправляем в группу обсуждения (reply_to = ID поста в канале)
                await client.send_message(
                    entity=discussion_entity,
                    message=comment_text,
                    reply_to=message_id,
                )
                logger.info(f"Comment sent to discussion group of @{channel_username}")
            else:
                # Нет группы обсуждения - комментарии отключены в канале
                logger.warning(f"Channel @{channel_username} has no discussion group - comments disabled")
                await self._log_action(
                    account_id=account.id,
                    tenant_id=self.account_manager.tenant_id,
                    action_type="comment",
                    target_channel_id=channel_id,
                    target_message_id=message_id,
                    content=comment_text,
                    status="failed",
                    error_message="Channel has no discussion group (comments disabled)",
                )
                return False

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
            self.rate_limiter.reset_multiplier()

            logger.info(
                f"Posted comment to @{channel_username}, post {message_id} "
                f"via account {account.phone}"
            )
            return True

        except FloodWaitError as e:
            logger.warning(f"FloodWait: {e.seconds}s for account {account.phone}")

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
            logger.warning(f"SlowModeWait: {e.seconds}s for channel @{channel_username}")
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
            error_type = type(e).__name__
            logger.warning(f"{error_type} for @{channel_username} - need to join discussion group")

            # Пробуем вступить в группу обсуждения
            joined = await self._force_join_discussion(client, account.id, entity, channel_username)

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message=f"{error_type} - {'joined discussion, retry next time' if joined else 'failed to join'}",
            )
            return False

        except UserBannedInChannelError:
            logger.error(f"Account {account.phone} banned in channel @{channel_username}")

            if self.notifier:
                await self.notifier.notify_account_banned(
                    account.phone,
                    channel_username or str(channel_id)
                )

            # НЕ баним весь аккаунт - только помечаем что он забанен в этом канале
            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="banned",
                error_message=f"Banned in @{channel_username}",
            )
            return False

        except ChannelPrivateError:
            logger.warning(f"Channel @{channel_username} is private - trying to join")

            # Пробуем подписаться на приватный канал
            try:
                if channel_username:
                    await client(JoinChannelRequest(channel_username))
                    logger.info(f"Joined private channel @{channel_username} - retry next time")
            except Exception as join_err:
                logger.error(f"Cannot join private channel: {join_err}")

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message="ChannelPrivate - attempted to join",
            )
            return False

        except AuthKeyDuplicatedError:
            # КРИТИЧНО: сессия используется с другого IP
            logger.error(f"AuthKeyDuplicated for account {account.phone} - session conflict!")

            if self.notifier:
                await self.notifier.notify_account_banned(
                    account.phone,
                    "SESSION_CONFLICT"
                )

            # Ставим аккаунт на паузу на 1 час
            await self.account_manager.set_cooldown(
                account.id,
                3600,
                reason="session_conflict"
            )

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message="AuthKeyDuplicated - session used from different IP",
            )
            return False

        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to post comment: {error_str}")

            # Проверяем специфичные ошибки
            if "join the discussion group" in error_str.lower():
                # Ошибка "You must join the discussion group before commenting"
                joined = await self._force_join_discussion(client, account.id, entity, channel_username)
                error_str = f"Must join discussion - {'joined, retry next time' if joined else 'failed to join'}"

            await self._log_action(
                account_id=account.id,
                tenant_id=self.account_manager.tenant_id,
                action_type="comment",
                target_channel_id=channel_id,
                target_message_id=message_id,
                content=comment_text,
                status="failed",
                error_message=error_str[:500],  # Ограничиваем длину
            )
            return False

    async def _get_channel_entity(
        self,
        client: TelegramClient,
        account_id: int,
        channel_username: Optional[str],
        channel_id: int,
    ) -> Optional[Any]:
        """
        Получить entity канала с автоподпиской.

        Если канал недоступен - подписывается на него.
        """
        cache_key = (account_id, channel_username or str(channel_id))

        # Проверяем кэш
        if cache_key in self._entity_cache:
            return self._entity_cache[cache_key]

        entity = None

        try:
            # Пробуем получить по username
            if channel_username:
                username = channel_username if channel_username.startswith("@") else f"@{channel_username}"
                entity = await client.get_entity(username)
            else:
                # По ID - нужен InputPeerChannel с access_hash
                # Но access_hash неизвестен, поэтому это может не работать
                entity = await client.get_entity(channel_id)

        except (ValueError, ChannelPrivateError) as e:
            # Канал не найден или приватный - пробуем подписаться
            logger.info(f"Channel not accessible, trying to join: {e}")

            if channel_username and cache_key not in self._joined_channels:
                try:
                    await client(JoinChannelRequest(channel_username))
                    self._joined_channels.add(cache_key)
                    logger.info(f"Joined channel @{channel_username}")

                    # Повторно получаем entity
                    await asyncio.sleep(1)  # Небольшая пауза после подписки
                    username = channel_username if channel_username.startswith("@") else f"@{channel_username}"
                    entity = await client.get_entity(username)

                except FloodWaitError as fw:
                    logger.warning(f"FloodWait on join: {fw.seconds}s")
                    await asyncio.sleep(fw.seconds + 5)
                except Exception as join_err:
                    logger.error(f"Failed to join channel @{channel_username}: {join_err}")
                    return None

        except Exception as e:
            logger.error(f"Failed to get entity for @{channel_username}: {e}")
            return None

        if entity:
            self._entity_cache[cache_key] = entity

        return entity

    async def _get_and_join_discussion(
        self,
        client: TelegramClient,
        account_id: int,
        channel_entity: Any,
        channel_username: Optional[str],
    ) -> Optional[Any]:
        """
        Получить группу обсуждения И АВТОМАТИЧЕСКИ вступить в неё.

        Это исправляет ошибку "You must join the discussion group before commenting".
        """
        cache_key = (account_id, channel_username or str(getattr(channel_entity, 'id', 'unknown')))

        # Проверяем кэш
        if cache_key in self._discussion_cache:
            cached = self._discussion_cache[cache_key]
            if cached is None:
                return None
            return cached

        try:
            if not isinstance(channel_entity, Channel):
                self._discussion_cache[cache_key] = None
                return None

            # Получаем информацию о linked chat
            full_channel = await client(GetFullChannelRequest(channel_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                logger.debug(f"Channel @{channel_username} has no discussion group")
                self._discussion_cache[cache_key] = None
                return None

            # Получаем entity группы обсуждения
            discussion = await client.get_entity(linked_chat_id)

            # АВТОВСТУПЛЕНИЕ в группу обсуждения
            discussion_key = (account_id, linked_chat_id)
            if discussion_key not in self._joined_discussions:
                try:
                    await client(JoinChannelRequest(discussion))
                    self._joined_discussions.add(discussion_key)
                    logger.info(f"Joined discussion group for @{channel_username}: {getattr(discussion, 'title', linked_chat_id)}")
                    await asyncio.sleep(1)  # Пауза после вступления
                except UserNotParticipantError:
                    # Уже в группе
                    self._joined_discussions.add(discussion_key)
                except Exception as e:
                    # Логируем но продолжаем - может уже в группе
                    logger.warning(f"Join discussion warning: {e}")
                    self._joined_discussions.add(discussion_key)

            self._discussion_cache[cache_key] = discussion
            return discussion

        except Exception as e:
            logger.error(f"Failed to get/join discussion for @{channel_username}: {e}")
            self._discussion_cache[cache_key] = None
            return None

    async def _force_join_discussion(
        self,
        client: TelegramClient,
        account_id: int,
        channel_entity: Any,
        channel_username: Optional[str],
    ) -> bool:
        """
        Принудительно вступить в группу обсуждения.
        Вызывается при ошибках ChatWriteForbidden и т.д.
        """
        try:
            if not channel_entity or not isinstance(channel_entity, Channel):
                return False

            full_channel = await client(GetFullChannelRequest(channel_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                logger.warning(f"@{channel_username} has no discussion group")
                return False

            discussion = await client.get_entity(linked_chat_id)
            await client(JoinChannelRequest(discussion))

            # Обновляем кэши
            cache_key = (account_id, channel_username or str(channel_entity.id))
            self._discussion_cache[cache_key] = discussion
            self._joined_discussions.add((account_id, linked_chat_id))

            logger.info(f"Force joined discussion group for @{channel_username}")
            return True

        except Exception as e:
            logger.error(f"Force join discussion failed: {e}")
            return False

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
                ai_model="yandexgpt",
            )
            session.add(action)
            await session.commit()

    def clear_cache(self) -> None:
        """Очистить все кэши (полезно при переподключении)."""
        self._entity_cache.clear()
        self._discussion_cache.clear()
        logger.debug("Caches cleared")
