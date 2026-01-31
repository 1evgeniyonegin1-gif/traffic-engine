"""
Telegram Notifier - Отправка уведомлений об ошибках в Telegram.

Функции:
- Уведомления о критических ошибках
- Throttling для предотвращения спама
- Разные категории ошибок с разными интервалами
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
from enum import Enum

from loguru import logger

try:
    from aiogram import Bot
    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False
    logger.warning("aiogram not installed - notifications disabled")


class ErrorType(str, Enum):
    """Типы ошибок для уведомлений."""
    ACCOUNT_BANNED = "account_banned"
    ALL_ACCOUNTS_COOLDOWN = "all_accounts_cooldown"
    CHANNEL_UNAVAILABLE = "channel_unavailable"
    FLOOD_WAIT_LONG = "flood_wait_long"
    AI_ERROR = "ai_error"
    DB_ERROR = "db_error"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    # Новые типы для модулей
    INVITE_FAILED = "invite_failed"
    STORY_REACT_FAILED = "story_react_failed"
    DASHBOARD_ERROR = "dashboard_error"


# Интервалы throttling для каждого типа ошибки (в секундах)
THROTTLE_INTERVALS = {
    ErrorType.ACCOUNT_BANNED: 0,  # Сразу, без throttling
    ErrorType.ALL_ACCOUNTS_COOLDOWN: 1800,  # 30 минут
    ErrorType.CHANNEL_UNAVAILABLE: 3600,  # 1 час
    ErrorType.FLOOD_WAIT_LONG: 1800,  # 30 минут
    ErrorType.AI_ERROR: 3600,  # 1 час
    ErrorType.DB_ERROR: 300,  # 5 минут
    ErrorType.SYSTEM_START: 0,  # Сразу
    ErrorType.SYSTEM_STOP: 0,  # Сразу
    # Новые типы
    ErrorType.INVITE_FAILED: 1800,  # 30 минут
    ErrorType.STORY_REACT_FAILED: 1800,  # 30 минут
    ErrorType.DASHBOARD_ERROR: 300,  # 5 минут
}


class TelegramNotifier:
    """
    Отправка уведомлений в Telegram.

    Использует aiogram для отправки сообщений.
    Включает throttling для предотвращения спама.
    """

    def __init__(
        self,
        bot_token: str,
        admin_id: int,
        enabled: bool = True,
    ):
        """
        Initialize notifier.

        Args:
            bot_token: Токен Telegram бота
            admin_id: ID администратора для уведомлений
            enabled: Включены ли уведомления
        """
        self.bot_token = bot_token
        self.admin_id = admin_id
        self.enabled = enabled and AIOGRAM_AVAILABLE

        self._bot: Optional["Bot"] = None
        self._last_notifications: Dict[str, datetime] = {}
        self._error_counts: Dict[str, int] = {}

        if self.enabled:
            self._bot = Bot(token=bot_token)
            logger.info(f"TelegramNotifier initialized for admin {admin_id}")
        else:
            logger.warning("TelegramNotifier disabled")

    def _should_throttle(self, error_type: ErrorType, context: str = "") -> bool:
        """
        Проверить, нужно ли throttle уведомление.

        Args:
            error_type: Тип ошибки
            context: Дополнительный контекст (например, название канала)

        Returns:
            True если нужно пропустить уведомление
        """
        key = f"{error_type.value}:{context}"
        interval = THROTTLE_INTERVALS.get(error_type, 3600)

        if interval == 0:
            return False

        last_time = self._last_notifications.get(key)
        if last_time is None:
            return False

        time_since = (datetime.now() - last_time).total_seconds()
        return time_since < interval

    def _record_notification(self, error_type: ErrorType, context: str = "") -> None:
        """Записать время последнего уведомления."""
        key = f"{error_type.value}:{context}"
        self._last_notifications[key] = datetime.now()

    async def notify(
        self,
        error_type: ErrorType,
        message: str,
        context: str = "",
    ) -> bool:
        """
        Отправить уведомление.

        Args:
            error_type: Тип ошибки
            message: Текст сообщения
            context: Дополнительный контекст для throttling

        Returns:
            True если уведомление отправлено
        """
        if not self.enabled or not self._bot:
            return False

        # Проверяем throttling
        if self._should_throttle(error_type, context):
            logger.debug(f"Throttled notification: {error_type.value}")
            return False

        # Формируем сообщение
        emoji_map = {
            ErrorType.ACCOUNT_BANNED: "🚫",
            ErrorType.ALL_ACCOUNTS_COOLDOWN: "⏸️",
            ErrorType.CHANNEL_UNAVAILABLE: "📢",
            ErrorType.FLOOD_WAIT_LONG: "🐌",
            ErrorType.AI_ERROR: "🤖",
            ErrorType.DB_ERROR: "💾",
            ErrorType.SYSTEM_START: "🚀",
            ErrorType.SYSTEM_STOP: "🛑",
            # Новые типы
            ErrorType.INVITE_FAILED: "📨",
            ErrorType.STORY_REACT_FAILED: "👁️",
            ErrorType.DASHBOARD_ERROR: "📊",
        }

        emoji = emoji_map.get(error_type, "⚠️")
        full_message = f"{emoji} <b>Traffic Engine Alert</b>\n\n{message}"

        try:
            await self._bot.send_message(
                chat_id=self.admin_id,
                text=full_message,
                parse_mode="HTML",
            )
            self._record_notification(error_type, context)
            logger.info(f"Sent notification: {error_type.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def notify_account_banned(self, account_phone: str, channel: str = "") -> bool:
        """Уведомление о бане аккаунта."""
        message = f"Аккаунт <code>{account_phone}</code> забанен"
        if channel:
            message += f" в канале @{channel}"
        return await self.notify(ErrorType.ACCOUNT_BANNED, message)

    async def notify_all_accounts_cooldown(self) -> bool:
        """Уведомление что все аккаунты на cooldown."""
        message = "Все аккаунты на cooldown!\nКомментирование приостановлено."
        return await self.notify(ErrorType.ALL_ACCOUNTS_COOLDOWN, message)

    async def notify_channel_unavailable(self, channel: str, error: str = "") -> bool:
        """Уведомление о недоступном канале."""
        message = f"Канал @{channel} недоступен"
        if error:
            message += f"\nОшибка: {error}"
        return await self.notify(ErrorType.CHANNEL_UNAVAILABLE, message, context=channel)

    async def notify_flood_wait(self, account_phone: str, seconds: int) -> bool:
        """Уведомление о длинном FloodWait."""
        if seconds < 3600:  # Уведомляем только если больше часа
            return False
        hours = seconds / 3600
        message = f"FloodWait {hours:.1f} часов на аккаунте <code>{account_phone}</code>"
        return await self.notify(ErrorType.FLOOD_WAIT_LONG, message)

    async def notify_ai_error(self, error: str) -> bool:
        """Уведомление об ошибке AI."""
        message = f"Ошибка генерации комментария:\n<code>{error[:200]}</code>"
        return await self.notify(ErrorType.AI_ERROR, message)

    async def notify_system_start(self, accounts_count: int, channels_count: int) -> bool:
        """Уведомление о запуске системы."""
        message = (
            f"Система запущена!\n"
            f"• Аккаунтов: {accounts_count}\n"
            f"• Каналов: {channels_count}"
        )
        return await self.notify(ErrorType.SYSTEM_START, message)

    async def notify_system_stop(self, reason: str = "") -> bool:
        """Уведомление об остановке системы."""
        message = "Система остановлена"
        if reason:
            message += f"\nПричина: {reason}"
        return await self.notify(ErrorType.SYSTEM_STOP, message)

    async def notify_invite_failed(self, account_phone: str, chat: str, error: str = "") -> bool:
        """Уведомление об ошибке инвайта."""
        message = f"Ошибка инвайта с <code>{account_phone}</code>\nГруппа: {chat}"
        if error:
            message += f"\nОшибка: {error[:100]}"
        return await self.notify(ErrorType.INVITE_FAILED, message, context=chat)

    async def notify_story_react_failed(self, account_phone: str, error: str = "") -> bool:
        """Уведомление об ошибке реакции на сторис."""
        message = f"Ошибка реакции на сторис с <code>{account_phone}</code>"
        if error:
            message += f"\nОшибка: {error[:100]}"
        return await self.notify(ErrorType.STORY_REACT_FAILED, message)

    async def notify_dashboard_error(self, error: str) -> bool:
        """Уведомление об ошибке дашборда."""
        message = f"Ошибка дашборда:\n<code>{error[:200]}</code>"
        return await self.notify(ErrorType.DASHBOARD_ERROR, message)

    async def close(self) -> None:
        """Закрыть сессию бота."""
        if self._bot:
            await self._bot.session.close()


# Singleton instance
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> Optional[TelegramNotifier]:
    """Получить singleton instance notifier."""
    return _notifier


def init_notifier(bot_token: str, admin_id: int, enabled: bool = True) -> TelegramNotifier:
    """
    Инициализировать глобальный notifier.

    Args:
        bot_token: Токен бота
        admin_id: ID администратора
        enabled: Включены ли уведомления

    Returns:
        TelegramNotifier instance
    """
    global _notifier
    _notifier = TelegramNotifier(bot_token, admin_id, enabled)
    return _notifier
