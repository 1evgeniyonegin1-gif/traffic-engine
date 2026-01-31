"""
Invite Monitor - Мониторинг и инвайт пользователей в группы-мероприятия.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from telethon.errors import FloodWaitError

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.core import AccountManager, HumanSimulator
from traffic_engine.notifications import TelegramNotifier

from .chat_inviter import ChatInviter


class InviteMonitor:
    """
    Мониторинг и инвайт пользователей в группы-мероприятия.

    Функции:
    - Выбор пользователей из ЦА с высоким quality_score
    - Инвайт в группу через ChatInviter
    - Контроль лимитов и рабочих часов
    - Публикация оффера при достижении порога
    """

    def __init__(
        self,
        tenant_id: int,
        account_manager: AccountManager,
        notifier: Optional[TelegramNotifier] = None,
    ):
        """
        Initialize invite monitor.

        Args:
            tenant_id: ID тенанта
            account_manager: Менеджер аккаунтов
            notifier: Telegram notifier для алертов
        """
        self.tenant_id = tenant_id
        self.account_manager = account_manager
        self.notifier = notifier

        self.human_sim = HumanSimulator()
        self.chat_inviter = ChatInviter()

        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._no_users_warning_shown = False
        self._no_chat_warning_shown = False

    async def initialize(self) -> None:
        """Initialize monitor."""
        # Проверяем есть ли активные чаты для инвайтов
        chat = await self.chat_inviter.get_active_chat(self.tenant_id)
        if chat:
            logger.info(f"Invite monitor initialized. Active chat: {chat.title}")
        else:
            logger.warning("Invite monitor initialized, but no active chats found!")

    async def start(self) -> None:
        """Запустить мониторинг и инвайты с автоперезапуском."""
        if self._running:
            logger.warning("Invite monitor already running")
            return

        self._running = True
        logger.info("Starting invite monitor...")

        while self._running:
            try:
                await self._monitoring_loop()

            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                self._reconnect_attempts += 1
                delay = min(30 * (2 ** self._reconnect_attempts), 600)

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error(f"❌ Max reconnect attempts reached. Stopping invite monitor.")
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
                logger.error(f"❌ Invite monitor error: {e}\n{traceback.format_exc()}")
                self._reconnect_attempts += 1
                delay = 60

                if self._reconnect_attempts > self._max_reconnect_attempts:
                    logger.error("❌ Max reconnect attempts reached. Stopping invite monitor.")
                    self._running = False
                    break

                logger.info(f"Restarting invite monitor in {delay}s...")
                await asyncio.sleep(delay)

        logger.info("Invite monitor stopped")

    async def _monitoring_loop(self) -> None:
        """
        Основной цикл мониторинга и инвайтов.

        Алгоритм:
        1. Проверка рабочих часов
        2. Проверка лимита инвайтов (MAX_INVITES_PER_DAY)
        3. Получение доступного аккаунта
        4. Получение активного чата
        5. Выбор пользователя из ЦА
        6. Инвайт
        7. Проверка порога для оффера
        8. Задержка 5-15 минут
        """
        consecutive_errors = 0
        max_invites = getattr(settings, "max_invites_per_day", 0)

        # Если инвайты отключены
        if max_invites <= 0:
            logger.info("Invites disabled (MAX_INVITES_PER_DAY=0). Invite monitor sleeping.")
            while self._running:
                await asyncio.sleep(300)  # Проверяем каждые 5 минут
                max_invites = getattr(settings, "max_invites_per_day", 0)
                if max_invites > 0:
                    logger.info(f"Invites enabled (MAX_INVITES_PER_DAY={max_invites}). Resuming...")
                    break
            return

        while self._running:
            try:
                # 1. Проверка рабочих часов
                if not self.human_sim.is_working_hours():
                    logger.debug("Outside working hours for invites, sleeping...")
                    await asyncio.sleep(300)
                    continue

                # 2. Получить доступный аккаунт
                account = await self.account_manager.get_available_account("invite")
                if not account:
                    logger.debug("No accounts available for invites")
                    await asyncio.sleep(60)
                    continue

                # 3. Получить активный чат
                chat = await self.chat_inviter.get_active_chat(self.tenant_id)
                if not chat:
                    if not self._no_chat_warning_shown:
                        logger.warning(
                            "⚠️ No active chats for invites! "
                            "Create one with: python scripts/create_event_group.py"
                        )
                        self._no_chat_warning_shown = True
                    await asyncio.sleep(300)
                    continue

                self._no_chat_warning_shown = False

                # 4. Выбрать пользователей из ЦА
                users = await self.chat_inviter.get_users_to_invite(
                    tenant_id=self.tenant_id,
                    limit=1,
                    min_quality=getattr(settings, "invite_min_quality_score", 50),
                )
                if not users:
                    if not self._no_users_warning_shown:
                        logger.warning(
                            "⚠️ No users available for invites! "
                            "System will retry every 5 minutes."
                        )
                        self._no_users_warning_shown = True
                    await asyncio.sleep(300)
                    continue

                self._no_users_warning_shown = False
                target_user = users[0]

                # 5. Получить клиент аккаунта
                client = await self.account_manager.get_client(account.id)
                if not client:
                    logger.error(f"Failed to get client for account {account.id}")
                    await asyncio.sleep(60)
                    continue

                # 6. Инвайтим
                try:
                    result = await self.chat_inviter.invite_user(
                        client=client,
                        user_id=target_user.user_id,
                        chat_id=chat.chat_id,
                        account_id=account.id,
                        tenant_id=self.tenant_id,
                    )

                    if result["invited"]:
                        logger.info(
                            f"✅ Account {account.phone} invited user {target_user.user_id} "
                            f"to {chat.title} (quality={target_user.quality_score})"
                        )
                        await self.account_manager.mark_action(account.id, "invite")

                        # 7. Проверяем порог для оффера
                        await self.chat_inviter.check_and_publish_offer(client, chat)

                    else:
                        logger.debug(f"⏭️ Failed to invite user {target_user.user_id}: {result.get('error')}")

                    consecutive_errors = 0

                except FloodWaitError as e:
                    logger.warning(f"⚠️ FloodWait {e.seconds}s for account {account.id}")
                    await self.account_manager.set_cooldown(account.id, e.seconds)
                    await asyncio.sleep(e.seconds + 10)

                    if self.notifier and e.seconds >= 3600:
                        await self.notifier.notify_flood_wait(
                            account_phone=account.phone,
                            seconds=e.seconds,
                        )

                    consecutive_errors = 0

                # 8. Задержка перед следующим инвайтом (5-15 минут)
                delay = self.human_sim.get_random_pause(
                    getattr(settings, "min_invite_interval_sec", 300),
                    getattr(settings, "max_invite_interval_sec", 900),
                )
                logger.debug(f"⏳ Waiting {delay/60:.1f} min before next invite...")
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                logger.info("Invite monitoring cancelled")
                break

            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                logger.warning(f"🔌 Network error in invite monitoring: {e}")
                raise

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Invite monitoring error ({consecutive_errors}): {e}")

                # Уведомляем об ошибке
                if self.notifier and consecutive_errors >= 3:
                    await self.notifier.notify_invite_failed(
                        account_phone="system",
                        chat="",
                        error=str(e),
                    )

                if consecutive_errors >= 5:
                    logger.error("Too many consecutive errors, triggering reconnect")
                    raise ConnectionError(f"Too many errors: {e}")

                await asyncio.sleep(60)

    async def stop(self) -> None:
        """Остановить мониторинг."""
        logger.info("Stopping invite monitor...")
        self._running = False
        logger.info("Invite monitor stopped")
