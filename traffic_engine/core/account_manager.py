"""
Account Manager - Управление пулом userbot аккаунтов.

Функции:
- Ротация аккаунтов для распределения нагрузки
- Отслеживание лимитов и cooldown
- Автоматический прогрев новых аккаунтов
- Получение доступных аккаунтов для действий

Использует Telethon для работы с Telegram API.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, Tenant
from .rate_limiter import RateLimiter, get_rate_limiter


class AccountManager:
    """
    Управление пулом userbot аккаунтов.

    Обеспечивает:
    - Ротацию между аккаунтами
    - Контроль лимитов
    - Автоматический cooldown при ошибках
    - Прогрев новых аккаунтов

    Использует Telethon для работы с Telegram API.
    """

    def __init__(self, tenant_id: int):
        """
        Initialize account manager for a specific tenant.

        Args:
            tenant_id: ID тенанта
        """
        self.tenant_id = tenant_id
        self.rate_limiter = get_rate_limiter()
        self._clients: Dict[int, TelegramClient] = {}  # account_id -> TelegramClient
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize all active accounts for the tenant.

        Создаёт Telethon клиенты для всех активных аккаунтов.
        """
        if self._initialized:
            return

        async with get_session() as session:
            result = await session.execute(
                select(UserBotAccount).where(
                    UserBotAccount.tenant_id == self.tenant_id,
                    UserBotAccount.status.in_(["active", "warming"])
                )
            )
            accounts = result.scalars().all()

            for account in accounts:
                try:
                    # Настройка прокси если есть
                    proxy = None
                    if account.proxy_host and account.proxy_port:
                        proxy_type = account.proxy_type or "socks5"
                        # Telethon proxy format: (type, host, port, rdns, username, password)
                        if proxy_type == "socks5":
                            import socks
                            proxy = (
                                socks.SOCKS5,
                                account.proxy_host,
                                account.proxy_port,
                                True,  # rdns
                                account.proxy_username,
                                account.proxy_password,
                            )
                        elif proxy_type == "http":
                            import socks
                            proxy = (
                                socks.HTTP,
                                account.proxy_host,
                                account.proxy_port,
                                True,
                                account.proxy_username,
                                account.proxy_password,
                            )
                        logger.info(f"Using proxy {account.proxy_host}:{account.proxy_port} for {account.phone}")

                    # Создаём Telethon клиент с session string
                    client = TelegramClient(
                        StringSession(account.session_string),
                        settings.telegram_api_id,
                        settings.telegram_api_hash,
                        proxy=proxy,
                    )
                    self._clients[account.id] = client
                    logger.info(f"Initialized Telethon client for account {account.phone}")
                except Exception as e:
                    logger.error(f"Failed to initialize account {account.phone}: {e}")

        self._initialized = True
        logger.info(f"Account manager initialized with {len(self._clients)} accounts")

    async def get_available_account(
        self,
        action_type: str,
        exclude_ids: Optional[List[int]] = None
    ) -> Optional[UserBotAccount]:
        """
        Получить доступный аккаунт для выполнения действия.

        Алгоритм:
        1. Фильтруем аккаунты без cooldown
        2. Фильтруем по дневному лимиту
        3. Сортируем по времени последнего использования
        4. Добавляем рандом

        Args:
            action_type: Тип действия (comment, invite, story_view, story_react)
            exclude_ids: ID аккаунтов для исключения

        Returns:
            UserBotAccount или None если нет доступных
        """
        exclude_ids = exclude_ids or []

        async with get_session() as session:
            # Получаем активные и прогреваемые аккаунты
            result = await session.execute(
                select(UserBotAccount).where(
                    UserBotAccount.tenant_id == self.tenant_id,
                    UserBotAccount.status.in_(["active", "warming"]),
                    UserBotAccount.id.notin_(exclude_ids),
                )
            )
            accounts = result.scalars().all()

            if not accounts:
                logger.warning("No active/warming accounts available")
                return None

            # Фильтруем по доступности
            available = []
            now = datetime.now()

            for account in accounts:
                # Проверяем cooldown
                if account.cooldown_until and account.cooldown_until > now:
                    continue

                # Проверяем дневной лимит (с учётом прогрева)
                daily_count = self._get_daily_count(account, action_type)
                daily_limit = self._get_warmup_limit(account, action_type)

                if daily_count >= daily_limit:
                    continue

                # Проверяем флаги возможностей
                if action_type == "comment" and not account.can_comment:
                    continue
                if action_type == "invite" and not account.can_invite:
                    continue
                if action_type in ["story_view", "story_react"] and not account.can_view_stories:
                    continue

                available.append(account)

            if not available:
                logger.warning(f"No accounts available for {action_type}")
                return None

            # Сортируем по времени последнего использования (давно не использованные первыми)
            available.sort(
                key=lambda a: a.last_used_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=False
            )

            # Выбираем из топ-3 с рандомом (если есть)
            top_accounts = available[:min(3, len(available))]
            selected = random.choice(top_accounts)

            logger.debug(f"Selected account {selected.phone} for {action_type}")
            return selected

    def _get_daily_count(self, account: UserBotAccount, action_type: str) -> int:
        """Получить количество действий за сегодня."""
        # Проверяем, нужно ли сбросить счётчики
        if account.limits_reset_at:
            if account.limits_reset_at.date() < datetime.now().date():
                # Счётчики устарели, будут сброшены при следующем обновлении
                return 0

        if action_type == "comment":
            return account.daily_comments
        elif action_type == "invite":
            return account.daily_invites
        elif action_type == "story_view":
            return account.daily_story_views
        elif action_type == "story_react":
            return account.daily_story_reactions
        return 0

    def _get_warmup_limit(self, account: UserBotAccount, action_type: str) -> int:
        """
        Получить лимит для аккаунта с учётом прогрева.

        Логика:
        - День 1-2: минимальная активность
        - День 3-4: увеличенная активность
        - День 5-6: почти полная активность
        - День 7+: полные лимиты (прогрев завершён)
        """
        # Если прогрев завершён — полные лимиты
        if account.warmup_completed:
            return self.rate_limiter.get_daily_limit(action_type)

        # Если прогрев не начинался — начинаем
        if not account.warmup_started_at:
            return self._get_warmup_limit_for_day(1, action_type)

        # Вычисляем день прогрева
        days_warming = (datetime.now() - account.warmup_started_at).days + 1

        # Если прогрев завершён по времени
        if days_warming > settings.warmup_days:
            return self.rate_limiter.get_daily_limit(action_type)

        return self._get_warmup_limit_for_day(days_warming, action_type)

    def _get_warmup_limit_for_day(self, day: int, action_type: str) -> int:
        """Получить лимит для конкретного дня прогрева."""
        if action_type == "comment":
            if day <= 2:
                return settings.warmup_day1_comments
            elif day <= 4:
                return settings.warmup_day3_comments
            elif day <= 6:
                return settings.warmup_day5_comments
            else:
                return settings.max_comments_per_day

        elif action_type == "invite":
            if day <= 2:
                return settings.warmup_day1_invites  # 0 - инвайты отключены
            elif day <= 4:
                return settings.warmup_day3_invites
            elif day <= 6:
                return settings.warmup_day5_invites
            else:
                return settings.max_invites_per_day

        elif action_type in ["story_view", "story_react"]:
            if day <= 2:
                return settings.warmup_day1_stories
            elif day <= 4:
                return settings.warmup_day3_stories
            elif day <= 6:
                return settings.warmup_day5_stories
            else:
                return settings.max_story_views_per_day

        return 10  # fallback

    async def mark_action(
        self,
        account_id: int,
        action_type: str,
        success: bool = True
    ) -> None:
        """
        Записать выполненное действие.

        Args:
            account_id: ID аккаунта
            action_type: Тип действия
            success: Успешно ли выполнено
        """
        async with get_session() as session:
            account = await session.get(UserBotAccount, account_id)
            if not account:
                return

            # Обновляем время последнего использования
            account.last_used_at = datetime.now()

            # Проверяем и сбрасываем дневные счётчики если нужно
            today = datetime.now().date()
            if not account.limits_reset_at or account.limits_reset_at.date() < today:
                account.daily_comments = 0
                account.daily_invites = 0
                account.daily_story_views = 0
                account.daily_story_reactions = 0
                account.limits_reset_at = datetime.now()

            # Увеличиваем счётчик
            if success:
                if action_type == "comment":
                    account.daily_comments += 1
                elif action_type == "invite":
                    account.daily_invites += 1
                elif action_type == "story_view":
                    account.daily_story_views += 1
                elif action_type == "story_react":
                    account.daily_story_reactions += 1

            await session.commit()
            logger.debug(f"Marked {action_type} for account {account.phone}")

    async def set_cooldown(
        self,
        account_id: int,
        seconds: int,
        reason: str
    ) -> None:
        """
        Поставить аккаунт на cooldown.

        Args:
            account_id: ID аккаунта
            seconds: Длительность cooldown в секундах
            reason: Причина cooldown
        """
        # Добавляем буфер к времени cooldown
        buffer = random.randint(60, 300)
        total_seconds = seconds + buffer

        async with get_session() as session:
            account = await session.get(UserBotAccount, account_id)
            if not account:
                return

            account.cooldown_until = datetime.now() + timedelta(seconds=total_seconds)
            account.cooldown_reason = reason

            await session.commit()

            logger.warning(
                f"Account {account.phone} on cooldown for {total_seconds}s: {reason}"
            )

        # Уведомляем rate_limiter об ошибке
        self.rate_limiter.handle_flood_wait(seconds)

    async def set_account_status(
        self,
        account_id: int,
        status: str,
        reason: Optional[str] = None
    ) -> None:
        """
        Изменить статус аккаунта.

        Args:
            account_id: ID аккаунта
            status: Новый статус (active, warming, banned, disabled)
            reason: Причина изменения
        """
        async with get_session() as session:
            account = await session.get(UserBotAccount, account_id)
            if not account:
                return

            old_status = account.status
            account.status = status

            if status == "banned":
                account.can_comment = False
                account.can_invite = False
                account.can_view_stories = False

            await session.commit()

            logger.info(
                f"Account {account.phone} status changed: {old_status} -> {status}"
                + (f" ({reason})" if reason else "")
            )

    async def get_client(self, account_id: int) -> Optional[TelegramClient]:
        """
        Получить Telethon клиент для аккаунта.

        Args:
            account_id: ID аккаунта

        Returns:
            Telethon TelegramClient или None
        """
        if not self._initialized:
            await self.initialize()

        return self._clients.get(account_id)

    async def get_stats(self) -> Dict:
        """Получить статистику по аккаунтам."""
        async with get_session() as session:
            result = await session.execute(
                select(UserBotAccount).where(
                    UserBotAccount.tenant_id == self.tenant_id
                )
            )
            accounts = result.scalars().all()

            stats = {
                "total": len(accounts),
                "active": 0,
                "warming": 0,
                "cooldown": 0,
                "banned": 0,
                "disabled": 0,
                "today_comments": 0,
                "today_invites": 0,
                "today_story_views": 0,
            }

            now = datetime.now()
            for account in accounts:
                stats[account.status] = stats.get(account.status, 0) + 1

                # Проверяем cooldown
                if account.cooldown_until and account.cooldown_until > now:
                    stats["cooldown"] += 1

                # Суммируем действия за сегодня
                if account.limits_reset_at and account.limits_reset_at.date() == now.date():
                    stats["today_comments"] += account.daily_comments
                    stats["today_invites"] += account.daily_invites
                    stats["today_story_views"] += account.daily_story_views

            return stats

    async def reset_daily_limits(self) -> None:
        """Сбросить дневные лимиты всех аккаунтов (вызывать в полночь)."""
        async with get_session() as session:
            await session.execute(
                update(UserBotAccount)
                .where(UserBotAccount.tenant_id == self.tenant_id)
                .values(
                    daily_comments=0,
                    daily_invites=0,
                    daily_story_views=0,
                    daily_story_reactions=0,
                    limits_reset_at=datetime.now(),
                )
            )
            await session.commit()

        logger.info(f"Daily limits reset for tenant {self.tenant_id}")

    async def close(self) -> None:
        """Закрыть все клиенты."""
        for account_id, client in self._clients.items():
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Error closing client {account_id}: {e}")

        self._clients.clear()
        self._initialized = False
        logger.info("Account manager closed")
