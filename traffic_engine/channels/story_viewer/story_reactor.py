"""
Story Reactor - Реакции на stories пользователей.

Техника "обратного просмотра":
1. Смотрим сторис людей из ЦА
2. Ставим реакции (огонь, лайк и т.д.)
3. Человек видит кто посмотрел и отреагировал
4. Заходит в наш профиль → видит био → переходит в воронку
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.stories import (
    GetPeerStoriesRequest,
    ReadStoriesRequest,
    SendReactionRequest,
)
from telethon.tl.types import ReactionEmoji
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    PeerIdInvalidError,
    ReactionInvalidError,
)

try:
    from telethon.errors import StoryNotModifiedError
except ImportError:
    StoryNotModifiedError = Exception

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import TrafficAction, UserBotAccount
from traffic_engine.core import HumanSimulator


class StoryReactor:
    """
    Просмотр stories + реакции для техники "обратного просмотра".

    Что делает:
    1. Получает список сторис пользователя из ЦА
    2. Смотрит случайную сторис
    3. Ставит реакцию (🔥, ❤️, 👍 и т.д.)
    4. Логирует действие
    """

    def __init__(self):
        """Initialize story reactor."""
        self.human_sim = HumanSimulator()

    async def view_and_react(
        self,
        client: TelegramClient,
        user_id: int,
        account_id: int,
        tenant_id: int,
        force_reaction: bool = False,
    ) -> dict:
        """
        Просмотреть сторис и поставить реакцию.

        Args:
            client: Telethon клиент
            user_id: ID пользователя из ЦА
            account_id: ID нашего аккаунта
            tenant_id: ID тенанта
            force_reaction: Всегда ставить реакцию (иначе 30% шанс)

        Returns:
            dict с результатами: {viewed: bool, reacted: bool, story_id: int}
        """
        result = {"viewed": False, "reacted": False, "story_id": None}

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
                    action_type="story_reaction",
                    status="failed",
                    error_message=f"Invalid peer: {e}",
                )
                return result

            # 2. Получить список stories
            try:
                stories_result = await client(GetPeerStoriesRequest(peer=user_entity))
            except UserPrivacyRestrictedError:
                logger.debug(f"⏭️ User {user_id} has private stories")
                return result
            except FloodWaitError:
                raise
            except Exception as e:
                logger.warning(f"⚠️ Failed to get stories for user {user_id}: {e}")
                return result

            # 3. Проверить наличие stories
            if not stories_result or not hasattr(stories_result, "stories"):
                logger.debug(f"⏭️ User {user_id} has no stories object")
                return result

            stories_list = (
                stories_result.stories.stories
                if hasattr(stories_result.stories, "stories")
                else []
            )

            if not stories_list:
                logger.debug(f"⏭️ User {user_id} has no active stories")
                return result

            # 4. Выбрать рандомную story
            story = random.choice(stories_list)
            story_id = story.id
            result["story_id"] = story_id

            logger.info(f"👁️ Viewing story {story_id} from user {user_id}...")

            # 5. Имитация просмотра (3-8 секунд)
            delay = self.human_sim.get_reading_delay("visual content")
            logger.debug(f"⏱️ Simulating view delay: {delay:.1f}s")
            await asyncio.sleep(delay)

            # 6. Отметить как просмотренную
            try:
                await client(ReadStoriesRequest(peer=user_entity, max_id=story_id))
                result["viewed"] = True
                logger.info(f"✅ Viewed story {story_id} from user {user_id}")
            except StoryNotModifiedError:
                result["viewed"] = True
                logger.debug(f"Story {story_id} already viewed")
            except FloodWaitError:
                raise
            except Exception as e:
                logger.warning(f"⚠️ Failed to mark story as viewed: {e}")

            # 7. Обновить счётчик просмотров
            await self._increment_story_views(account_id)

            # 8. Логируем просмотр
            await self._log_action(
                tenant_id=tenant_id,
                account_id=account_id,
                user_id=user_id,
                story_id=story_id,
                action_type="story_view",
                status="success",
            )

            # 9. Решаем ставить ли реакцию
            should_react = force_reaction or self.human_sim.should_react_to_story(0.3)

            if not should_react:
                logger.debug(f"⏭️ Skipping reaction (random decision)")
                return result

            # 10. Пауза перед реакцией (1-3 сек)
            await asyncio.sleep(random.uniform(1, 3))

            # 11. Ставим реакцию
            emoji = self.human_sim.get_reaction_emoji()

            try:
                await client(SendReactionRequest(
                    peer=user_entity,
                    story_id=story_id,
                    reaction=ReactionEmoji(emoticon=emoji),
                ))
                result["reacted"] = True

                logger.info(f"🔥 Reacted with {emoji} to story {story_id} from user {user_id}")

                # Логируем реакцию
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=story_id,
                    action_type="story_reaction",
                    status="success",
                    reaction=emoji,
                )

                # Обновить счётчик реакций
                await self._increment_story_reactions(account_id)

            except ReactionInvalidError:
                logger.warning(f"⚠️ Reaction {emoji} not allowed for story {story_id}")
            except FloodWaitError:
                raise
            except Exception as e:
                logger.warning(f"⚠️ Failed to react to story {story_id}: {e}")
                await self._log_action(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    user_id=user_id,
                    story_id=story_id,
                    action_type="story_reaction",
                    status="failed",
                    error_message=str(e),
                )

            return result

        except FloodWaitError:
            raise
        except Exception as e:
            logger.error(f"❌ Error in view_and_react for user {user_id}: {e}")
            return result

    async def _log_action(
        self,
        tenant_id: int,
        account_id: int,
        user_id: int,
        story_id: Optional[int],
        action_type: str,
        status: str,
        error_message: Optional[str] = None,
        reaction: Optional[str] = None,
    ) -> None:
        """Залогировать действие в БД."""
        try:
            async with get_session() as session:
                action = TrafficAction(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    action_type=action_type,
                    target_user_id=user_id,
                    target_story_id=story_id,
                    status=status,
                    error_message=error_message,
                    reaction=reaction,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(action)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {e}")

    async def _increment_story_views(self, account_id: int) -> None:
        """Увеличить счётчик просмотров."""
        try:
            async with get_session() as session:
                account = await session.get(UserBotAccount, account_id)
                if account:
                    account.daily_story_views += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to increment story views: {e}")

    async def _increment_story_reactions(self, account_id: int) -> None:
        """Увеличить счётчик реакций."""
        try:
            async with get_session() as session:
                account = await session.get(UserBotAccount, account_id)
                if account:
                    account.daily_story_reactions += 1
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to increment story reactions: {e}")
