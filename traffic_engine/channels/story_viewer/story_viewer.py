"""
Story Viewer - Просмотр stories пользователей через Telethon API.
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.stories import GetPeerStoriesRequest, ReadStoriesRequest
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    PeerIdInvalidError,
)
# StoryNotModifiedError может не существовать в старых версиях Telethon
try:
    from telethon.errors import StoryNotModifiedError
except ImportError:
    StoryNotModifiedError = Exception  # Fallback

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import TrafficAction, UserBotAccount
from traffic_engine.core import HumanSimulator


class StoryViewer:
    """
    Просмотр stories пользователей из ЦА.

    Использует Telethon API для:
    - Получения списка stories пользователя
    - Просмотра случайной story
    - Логирования действий
    """

    def __init__(self):
        """Initialize story viewer."""
        self.human_sim = HumanSimulator()

    async def view_user_story(
        self,
        client: TelegramClient,
        user_id: int,
        account_id: int,
        tenant_id: int,
    ) -> bool:
        """
        Просмотреть 1 рандомную story пользователя.

        Args:
            client: Telethon клиент аккаунта
            user_id: ID пользователя чью story смотрим
            account_id: ID аккаунта который смотрит
            tenant_id: ID тенанта

        Returns:
            True если story успешно просмотрена, False если нет stories

        Raises:
            FloodWaitError: Если нужно подождать перед следующим запросом
        """
        try:
            # 1. Получить entity пользователя
            try:
                user_entity = await client.get_entity(user_id)
            except (ValueError, PeerIdInvalidError) as e:
                logger.warning(f"⚠️ Cannot get entity for user {user_id}: {e}")
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=None,
                    status="failed",
                    error_message=f"Invalid peer: {e}",
                )
                return False

            # 2. Получить список stories пользователя
            try:
                stories_result = await client(GetPeerStoriesRequest(peer=user_entity))
            except UserPrivacyRestrictedError:
                logger.debug(f"⏭️ User {user_id} has private stories (not visible)")
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=None,
                    status="skipped",
                    error_message="Private stories",
                )
                return False
            except FloodWaitError:
                # Пробрасываем FloodWait наверх
                raise
            except Exception as e:
                logger.warning(f"⚠️ Failed to get stories for user {user_id}: {e}")
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=None,
                    status="failed",
                    error_message=str(e),
                )
                return False

            # 3. Проверить наличие stories
            if not stories_result or not hasattr(stories_result, "stories"):
                logger.debug(f"⏭️ User {user_id} has no stories object")
                return False

            stories_list = stories_result.stories.stories if hasattr(stories_result.stories, "stories") else []

            if not stories_list:
                logger.debug(f"⏭️ User {user_id} has no active stories")
                return False

            # 4. Выбрать рандомную story
            story = random.choice(stories_list)
            story_id = story.id

            logger.info(f"👁️ Viewing story {story_id} from user {user_id}...")

            # 5. Имитация просмотра (задержка 3-8 секунд)
            # Для визуального контента используем get_reading_delay
            delay = self.human_sim.get_reading_delay("visual content")
            logger.debug(f"⏱️ Simulating view delay: {delay:.1f}s")
            await asyncio.sleep(delay)

            # 6. Отметить story как просмотренную
            try:
                await client(ReadStoriesRequest(peer=user_entity, max_id=story_id))
            except StoryNotModifiedError:
                # Story уже просмотрена - это OK
                logger.debug(f"Story {story_id} already viewed (not modified)")
            except FloodWaitError:
                # Пробрасываем FloodWait наверх
                raise
            except Exception as e:
                logger.warning(f"⚠️ Failed to mark story {story_id} as viewed: {e}")
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=story_id,
                    status="failed",
                    error_message=f"Mark failed: {e}",
                )
                return False

            # 7. Залогировать успешный просмотр
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                story_id=story_id,
                status="success",
            )

            # 8. Обновить счётчик просмотров аккаунта
            await self._increment_story_views(account_id)

            logger.info(f"✅ Successfully viewed story {story_id} from user {user_id}")
            return True

        except FloodWaitError:
            # Пробрасываем FloodWait наверх для обработки в StoryMonitor
            raise

        except Exception as e:
            logger.error(f"❌ Error viewing story from user {user_id}: {e}")
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                story_id=None,
                status="failed",
                error_message=str(e),
            )
            return False

    async def _log_action(
        self,
        tenant_id: int,
        account_id: int,
        user_id: int,
        story_id: Optional[int],
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Залогировать действие в БД.

        Args:
            tenant_id: ID тенанта
            account_id: ID аккаунта
            user_id: ID пользователя
            story_id: ID story (если есть)
            status: Статус (success, failed, skipped)
            error_message: Сообщение об ошибке (опционально)
        """
        try:
            async with get_session() as session:
                action = TrafficAction(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    action_type="story_view",
                    target_user_id=user_id,
                    target_story_id=story_id,
                    status=status,
                    error_message=error_message,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(action)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log story view action: {e}")

    async def _increment_story_views(self, account_id: int) -> None:
        """
        Увеличить счётчик просмотров stories для аккаунта.

        Args:
            account_id: ID аккаунта
        """
        try:
            async with get_session() as session:
                account = await session.get(UserBotAccount, account_id)
                if account:
                    account.daily_story_views += 1
                    await session.commit()
                    logger.debug(f"📊 Account {account_id} story views: {account.daily_story_views}")
        except Exception as e:
            logger.error(f"Failed to increment story views for account {account_id}: {e}")
