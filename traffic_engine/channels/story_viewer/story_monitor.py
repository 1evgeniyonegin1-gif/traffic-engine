"""
Story Monitor - Мониторинг и просмотр stories целевой аудитории.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from sqlalchemy import select, func

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import TargetAudience
from traffic_engine.core import AccountManager, HumanSimulator
from traffic_engine.notifications import TelegramNotifier

from .story_viewer import StoryViewer


class StoryMonitor:
    """
    Мониторинг и просмотр stories целевой аудитории.

    Функции:
    - Выбор пользователей из ЦА с высоким quality_score
    - Просмотр stories через StoryViewer
    - Контроль лимитов и рабочих часов
    - Обработка FloodWait ошибок
    """

    def __init__(
        self,
        tenant_id: int,
        account_manager: AccountManager,
        notifier: Optional[TelegramNotifier] = None,
    ):
        """
        Initialize story monitor.

        Args:
            tenant_id: ID тенанта
            account_manager: Менеджер аккаунтов
            notifier: Telegram notifier для алертов
        """
        self.tenant_id = tenant_id
        self.account_manager = account_manager
        self.notifier = notifier

        self.human_sim = HumanSimulator()
        self.story_viewer = StoryViewer()

        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._no_users_warning_shown = False  # Флаг для однократного предупреждения

    async def initialize(self) -> None:
        """Initialize monitor."""
        logger.info("Story monitor initialized")

    async def start(self) -> None:
        """Запустить мониторинг и просмотр stories с автоперезапуском."""
        if self._running:
            logger.warning("Story monitor already running")
            return

        self._running = True
        logger.info("Starting story monitor...")

        while self._running:
            try:
                await self._monitoring_loop()

            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                # Сетевые ошибки - пробуем переподключиться
                self._reconnect_attempts += 1
                delay = min(30 * (2 ** self._reconnect_attempts), 600)  # Max 10 min

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error(f"❌ Max reconnect attempts ({self._max_reconnect_attempts}) reached. Stopping story monitor.")
                    self._running = False
                    break

                logger.warning(
                    f"🔌 Connection lost: {e}. "
                    f"Attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}. "
                    f"Reconnecting in {delay}s..."
                )
                await asyncio.sleep(delay)

            except Exception as e:
                import traceback
                logger.error(f"❌ Story monitor error: {e}\n{traceback.format_exc()}")
                self._reconnect_attempts += 1
                delay = 60

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error("❌ Max reconnect attempts reached. Stopping story monitor.")
                    self._running = False
                    break

                logger.info(f"Restarting story monitor in {delay}s...")
                await asyncio.sleep(delay)

        logger.info("Story monitor stopped")

    async def _monitoring_loop(self) -> None:
        """
        Основной цикл мониторинга и просмотра stories.

        Алгоритм:
        1. Проверка рабочих часов
        2. Получение доступного аккаунта
        3. Выбор пользователя из ЦА
        4. Просмотр story
        5. Задержка 5-15 минут
        """
        consecutive_errors = 0

        while self._running:
            try:
                # 1. Проверка рабочих часов
                if not self.human_sim.is_working_hours():
                    logger.debug("Outside working hours for story viewing, sleeping...")
                    await asyncio.sleep(300)  # 5 минут
                    continue

                # 2. Получить доступный аккаунт
                account = await self.account_manager.get_available_account("story_view")
                if not account:
                    logger.debug("No accounts available for story viewing")
                    await asyncio.sleep(60)
                    continue

                # 3. Выбрать пользователя из ЦА
                target_user = await self._select_target_user()
                if not target_user:
                    if not self._no_users_warning_shown:
                        logger.warning(
                            "⚠️ No target users available for story viewing! "
                            f"Need users with quality_score >= {getattr(settings, 'story_view_min_quality_score', 70)}. "
                            "System will retry every 5 minutes."
                        )
                        self._no_users_warning_shown = True
                    await asyncio.sleep(300)  # 5 минут
                    continue

                # Сбросить флаг если пользователи появились
                self._no_users_warning_shown = False

                # 4. Получить клиент аккаунта
                client = await self.account_manager.get_client(account.id)
                if not client:
                    logger.error(f"Failed to get client for account {account.id}")
                    await asyncio.sleep(60)
                    continue

                # 5. Просмотреть story
                try:
                    success = await self.story_viewer.view_user_story(
                        client=client,
                        user_id=target_user.user_id,
                        account_id=account.id,
                        tenant_id=self.tenant_id,
                    )

                    if success:
                        logger.info(
                            f"✅ Account {account.phone} viewed story of user {target_user.user_id} "
                            f"(quality_score={target_user.quality_score})"
                        )
                        # Отмечаем действие в AccountManager
                        await self.account_manager.mark_action(account.id, "story_view")
                    else:
                        logger.debug(f"⏭️ User {target_user.user_id} has no active stories, skipping")

                    consecutive_errors = 0  # Сбрасываем при успехе

                except FloodWaitError as e:
                    logger.warning(f"⚠️ FloodWait {e.seconds}s for account {account.id}")

                    # Устанавливаем cooldown для аккаунта
                    await self.account_manager.set_cooldown(account.id, e.seconds)

                    # Ждём указанное время + буфер
                    await asyncio.sleep(e.seconds + 10)

                    # Отправляем алерт админу
                    if self.notifier:
                        await self.notifier.notify_flood_wait(
                            account_phone=account.phone,
                            wait_seconds=e.seconds,
                            action_type="story_view",
                        )

                    consecutive_errors = 0  # Не считаем FloodWait как ошибку

                # 6. Задержка перед следующим просмотром (5-15 минут)
                delay = self.human_sim.get_random_pause(
                    settings.min_story_interval_sec,
                    settings.max_story_interval_sec,
                )
                logger.debug(f"⏳ Waiting {delay/60:.1f} min before next story view...")
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                logger.info("Story monitoring cancelled")
                break

            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                # Сетевые ошибки - пробрасываем наверх для переподключения
                logger.warning(f"🔌 Network error in story monitoring: {e}")
                raise

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Story monitoring error ({consecutive_errors}): {e}")

                if consecutive_errors >= 5:
                    logger.error("Too many consecutive errors, triggering reconnect")
                    raise ConnectionError(f"Too many errors: {e}")

                await asyncio.sleep(60)

    async def _select_target_user(self) -> Optional[TargetAudience]:
        """
        Выбрать случайного пользователя из ЦА с высоким quality_score.

        Критерии:
        - tenant_id = self.tenant_id
        - quality_score >= story_view_min_quality_score (default 70)
        - status in ['new', 'contacted']

        Returns:
            TargetAudience или None если нет подходящих пользователей
        """
        try:
            min_quality = getattr(settings, "story_view_min_quality_score", 70)

            async with get_session() as session:
                result = await session.execute(
                    select(TargetAudience)
                    .where(
                        TargetAudience.tenant_id == self.tenant_id,
                        TargetAudience.quality_score >= min_quality,
                        TargetAudience.status.in_(["new", "contacted"]),
                    )
                    .order_by(func.random())  # Случайный выбор
                    .limit(1)
                )
                user = result.scalar_one_or_none()

                if user:
                    logger.debug(
                        f"📍 Selected target user {user.user_id} "
                        f"(quality={user.quality_score}, source={user.source_type})"
                    )

                return user

        except Exception as e:
            logger.error(f"Failed to select target user: {e}")
            return None

    async def stop(self) -> None:
        """Остановить мониторинг."""
        logger.info("Stopping story monitor...")
        self._running = False
        logger.info("Story monitor stopped")
