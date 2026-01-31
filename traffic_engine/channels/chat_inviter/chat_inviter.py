"""
Chat Inviter - Инвайт пользователей в группы-мероприятия.

Техника "мероприятий":
1. Создаём группу "Новая профессия 2026" или подобную
2. Инвайтим людей из ЦА
3. Когда набирается N человек — публикуем оффер
4. Люди переходят в воронку
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import AddChatUserRequest
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    UserNotMutualContactError,
    UserChannelsTooMuchError,
    ChatAdminRequiredError,
    UserAlreadyParticipantError,
    PeerIdInvalidError,
    UserKickedError,
    InputUserDeactivatedError,
    UserBannedInChannelError,
)
from sqlalchemy import select, and_

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import (
    TrafficAction,
    UserBotAccount,
    TargetAudience,
    InviteChat,
)
from traffic_engine.core import HumanSimulator


class ChatInviter:
    """
    Инвайт пользователей из ЦА в группы-мероприятия.

    Логика:
    1. Берём пользователей из TargetAudience (status='new' или 'processed')
    2. Инвайтим в активную группу из InviteChat
    3. Логируем результат
    4. Когда группа заполнена — публикуем оффер
    """

    def __init__(self):
        """Initialize chat inviter."""
        self.human_sim = HumanSimulator()

    async def invite_user(
        self,
        client: TelegramClient,
        user_id: int,
        chat_id: int,
        account_id: int,
        tenant_id: int,
    ) -> dict:
        """
        Пригласить пользователя в группу.

        Args:
            client: Telethon клиент
            user_id: ID пользователя для инвайта
            chat_id: ID группы
            account_id: ID нашего аккаунта
            tenant_id: ID тенанта

        Returns:
            dict с результатами: {invited: bool, error: str}
        """
        result = {"invited": False, "error": None}

        try:
            # 1. Получить entity пользователя
            try:
                user_entity = await client.get_entity(user_id)
            except (ValueError, PeerIdInvalidError) as e:
                result["error"] = f"Invalid user: {e}"
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    status="failed",
                    error_message=result["error"],
                )
                return result

            # 2. Получить entity группы
            try:
                chat_entity = await client.get_entity(chat_id)
            except (ValueError, PeerIdInvalidError) as e:
                result["error"] = f"Invalid chat: {e}"
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    status="failed",
                    error_message=result["error"],
                )
                return result

            # 3. Имитация задержки перед инвайтом
            delay = self.human_sim.get_random_pause(2, 5)
            await asyncio.sleep(delay)

            # 4. Инвайтим
            # Для супергрупп/каналов
            if hasattr(chat_entity, "megagroup") or hasattr(chat_entity, "broadcast"):
                await client(InviteToChannelRequest(
                    channel=chat_entity,
                    users=[user_entity]
                ))
            else:
                # Для обычных групп
                await client(AddChatUserRequest(
                    chat_id=chat_id,
                    user_id=user_entity,
                    fwd_limit=0  # Не пересылать историю
                ))

            result["invited"] = True
            logger.info(f"✅ Invited user {user_id} to chat {chat_id}")

            # 5. Логируем успех
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                chat_id=chat_id,
                status="success",
            )

            # 6. Обновляем счётчик инвайтов аккаунта
            await self._increment_invites(account_id)

            # 7. Обновляем статус пользователя в ЦА
            await self._mark_user_invited(tenant_id, user_id)

            # 8. Обновляем статистику чата
            await self._increment_chat_invited(chat_id)

            return result

        except UserAlreadyParticipantError:
            result["error"] = "Already in chat"
            logger.debug(f"User {user_id} already in chat {chat_id}")
            return result

        except UserPrivacyRestrictedError:
            result["error"] = "Privacy restricted"
            logger.debug(f"User {user_id} has privacy settings")
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                chat_id=chat_id,
                status="skipped",
                error_message="Privacy restricted",
            )
            return result

        except UserNotMutualContactError:
            result["error"] = "Not mutual contact"
            logger.debug(f"User {user_id} requires mutual contact")
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                chat_id=chat_id,
                status="skipped",
                error_message="Not mutual contact",
            )
            return result

        except (UserKickedError, UserBannedInChannelError):
            result["error"] = "User banned from chat"
            logger.debug(f"User {user_id} is banned from chat {chat_id}")
            return result

        except (InputUserDeactivatedError,):
            result["error"] = "User deactivated"
            logger.debug(f"User {user_id} is deactivated")
            # Помечаем как заблокированного
            await self._mark_user_blocked(tenant_id, user_id)
            return result

        except UserChannelsTooMuchError:
            result["error"] = "User in too many channels"
            logger.debug(f"User {user_id} in too many channels")
            return result

        except ChatAdminRequiredError:
            result["error"] = "Need admin rights"
            logger.error(f"Need admin rights in chat {chat_id}")
            return result

        except FloodWaitError as e:
            result["error"] = f"FloodWait {e.seconds}s"
            logger.warning(f"FloodWait: {e.seconds}s")
            raise

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error inviting user {user_id}: {e}")
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                chat_id=chat_id,
                status="failed",
                error_message=str(e),
            )
            return result

    async def get_users_to_invite(
        self,
        tenant_id: int,
        limit: int = 10,
        min_quality: int = 50,
    ) -> List[TargetAudience]:
        """
        Получить список пользователей для инвайта.

        Args:
            tenant_id: ID тенанта
            limit: Максимум пользователей
            min_quality: Минимальный quality_score

        Returns:
            Список пользователей из ЦА
        """
        async with get_session() as session:
            result = await session.execute(
                select(TargetAudience)
                .where(and_(
                    TargetAudience.tenant_id == tenant_id,
                    TargetAudience.invited_to_chat == False,
                    TargetAudience.status.in_(["new", "processed"]),
                    TargetAudience.quality_score >= min_quality,
                ))
                .order_by(TargetAudience.quality_score.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_active_chat(self, tenant_id: int) -> Optional[InviteChat]:
        """
        Получить активный чат для инвайтов.

        Args:
            tenant_id: ID тенанта

        Returns:
            Активный чат или None
        """
        async with get_session() as session:
            result = await session.execute(
                select(InviteChat)
                .where(and_(
                    InviteChat.tenant_id == tenant_id,
                    InviteChat.is_active == True,
                ))
                .order_by(InviteChat.total_invited.asc())  # Меньше заполненные первыми
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def check_and_publish_offer(
        self,
        client: TelegramClient,
        chat: InviteChat,
    ) -> bool:
        """
        Проверить и опубликовать оффер если достигнут порог.

        Args:
            client: Telethon клиент
            chat: Чат

        Returns:
            True если оффер опубликован
        """
        if chat.offer_published:
            return False

        if chat.total_joined < chat.publish_offer_at_members:
            return False

        if not chat.offer_message:
            logger.warning(f"No offer message for chat {chat.title}")
            return False

        try:
            chat_entity = await client.get_entity(chat.chat_id)
            message = await client.send_message(chat_entity, chat.offer_message)

            # Закрепляем сообщение
            await client.pin_message(chat_entity, message.id)

            # Обновляем в БД
            async with get_session() as session:
                db_chat = await session.get(InviteChat, chat.id)
                if db_chat:
                    db_chat.offer_published = True
                    db_chat.offer_published_at = datetime.now(timezone.utc)
                    db_chat.offer_message_id = message.id
                    await session.commit()

            logger.info(f"✅ Published offer in chat {chat.title}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish offer: {e}")
            return False

    async def _log_action(
        self,
        tenant_id: int,
        account_id: int,
        user_id: int,
        chat_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Залогировать действие."""
        try:
            async with get_session() as session:
                action = TrafficAction(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    action_type="invite",
                    target_user_id=user_id,
                    target_channel_id=chat_id,
                    status=status,
                    error_message=error_message,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(action)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log invite action: {e}")

    async def _increment_invites(self, account_id: int) -> None:
        """Увеличить счётчик инвайтов."""
        try:
            async with get_session() as session:
                account = await session.get(UserBotAccount, account_id)
                if account:
                    account.daily_invites += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to increment invites: {e}")

    async def _mark_user_invited(self, tenant_id: int, user_id: int) -> None:
        """Пометить пользователя как приглашённого."""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(TargetAudience)
                    .where(and_(
                        TargetAudience.tenant_id == tenant_id,
                        TargetAudience.user_id == user_id,
                    ))
                )
                user = result.scalar_one_or_none()
                if user:
                    user.invited_to_chat = True
                    user.invited_at = datetime.now(timezone.utc)
                    user.status = "invited"
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to mark user invited: {e}")

    async def _mark_user_blocked(self, tenant_id: int, user_id: int) -> None:
        """Пометить пользователя как заблокированного."""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(TargetAudience)
                    .where(and_(
                        TargetAudience.tenant_id == tenant_id,
                        TargetAudience.user_id == user_id,
                    ))
                )
                user = result.scalar_one_or_none()
                if user:
                    user.status = "blocked"
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to mark user blocked: {e}")

    async def _increment_chat_invited(self, chat_id: int) -> None:
        """Увеличить счётчик инвайтов в чате."""
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(InviteChat)
                    .where(InviteChat.chat_id == chat_id)
                )
                chat = result.scalar_one_or_none()
                if chat:
                    chat.total_invited += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to increment chat invited: {e}")
