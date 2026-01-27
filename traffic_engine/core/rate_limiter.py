"""
Rate Limiter - Контроль частоты действий для избежания бана.

Функции:
- Отслеживание лимитов по аккаунтам
- Генерация рандомных задержек
- Автоматический cooldown при FloodWait
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from loguru import logger

from traffic_engine.config import settings


class RateLimiter:
    """
    Контроль частоты действий для избежания бана Telegram.

    Лимиты (рекомендуемые):
    - Комментарии: 50-80/день на аккаунт, 30-180 сек между
    - Инвайты: 30-50/день на аккаунт, 60-300 сек между
    - Просмотр сторис: 200-300/день, 2-10 сек между
    - Реакции на сторис: 80-100/день, 10-30 сек между
    """

    # Конфигурация лимитов по типам действий
    ACTION_LIMITS: Dict[str, Dict[str, int]] = {
        "comment": {
            "daily": settings.max_comments_per_day,
            "min_interval": settings.min_comment_interval_sec,
            "max_interval": settings.max_comment_interval_sec,
        },
        "invite": {
            "daily": settings.max_invites_per_day,
            "min_interval": settings.min_invite_interval_sec,
            "max_interval": settings.max_invite_interval_sec,
        },
        "story_view": {
            "daily": settings.max_story_views_per_day,
            "min_interval": settings.min_story_interval_sec,
            "max_interval": settings.max_story_interval_sec,
        },
        "story_react": {
            "daily": settings.max_story_reactions_per_day,
            "min_interval": 10,
            "max_interval": 30,
        },
    }

    # Множитель интервалов (увеличивается при FloodWait)
    _interval_multiplier: float = 1.0

    # Время последнего действия по типам
    _last_action_time: Dict[str, datetime] = {}

    def __init__(self):
        """Initialize rate limiter."""
        self._interval_multiplier = 1.0
        self._last_action_time = {}

    def get_daily_limit(self, action_type: str) -> int:
        """
        Получить дневной лимит для типа действия.

        Args:
            action_type: Тип действия (comment, invite, story_view, story_react)

        Returns:
            Максимальное количество действий в день
        """
        if action_type not in self.ACTION_LIMITS:
            logger.warning(f"Unknown action type: {action_type}, using default limit 50")
            return 50

        return self.ACTION_LIMITS[action_type]["daily"]

    def get_delay(self, action_type: str) -> float:
        """
        Получить рандомную задержку перед действием.

        Args:
            action_type: Тип действия

        Returns:
            Время задержки в секундах
        """
        if action_type not in self.ACTION_LIMITS:
            return random.uniform(30, 60)

        config = self.ACTION_LIMITS[action_type]
        base_delay = random.uniform(
            config["min_interval"],
            config["max_interval"]
        )

        # Применяем множитель (увеличивается после FloodWait)
        delay = base_delay * self._interval_multiplier

        # Добавляем небольшой шум для естественности
        noise = random.uniform(-0.1, 0.1) * delay
        delay += noise

        return max(delay, config["min_interval"])

    def can_perform_now(self, action_type: str) -> Tuple[bool, float]:
        """
        Проверить, можно ли выполнить действие сейчас.

        Args:
            action_type: Тип действия

        Returns:
            Tuple (можно ли, сколько ждать если нельзя)
        """
        if action_type not in self._last_action_time:
            return True, 0

        last_time = self._last_action_time[action_type]
        min_interval = self.ACTION_LIMITS.get(action_type, {}).get("min_interval", 30)

        elapsed = (datetime.now() - last_time).total_seconds()
        required_wait = (min_interval * self._interval_multiplier) - elapsed

        if required_wait <= 0:
            return True, 0

        return False, required_wait

    def record_action(self, action_type: str) -> None:
        """
        Записать выполненное действие.

        Args:
            action_type: Тип действия
        """
        self._last_action_time[action_type] = datetime.now()

    def handle_flood_wait(self, wait_seconds: int) -> None:
        """
        Обработать FloodWait ошибку.

        При FloodWait увеличиваем интервалы для всех типов действий.

        Args:
            wait_seconds: Сколько секунд ждать (из ошибки Telegram)
        """
        logger.warning(f"FloodWait received: {wait_seconds} seconds")

        # Увеличиваем множитель интервалов на 20-50%
        increase = random.uniform(1.2, 1.5)
        self._interval_multiplier *= increase

        # Ограничиваем максимальный множитель
        self._interval_multiplier = min(self._interval_multiplier, 3.0)

        logger.info(f"Interval multiplier increased to {self._interval_multiplier:.2f}")

    def reset_multiplier(self) -> None:
        """Сбросить множитель интервалов (после успешной серии действий)."""
        if self._interval_multiplier > 1.0:
            # Плавно уменьшаем
            self._interval_multiplier = max(1.0, self._interval_multiplier * 0.9)
            logger.debug(f"Interval multiplier decreased to {self._interval_multiplier:.2f}")

    def get_status(self) -> Dict:
        """Получить текущий статус rate limiter."""
        return {
            "interval_multiplier": self._interval_multiplier,
            "last_actions": {
                action_type: time.isoformat()
                for action_type, time in self._last_action_time.items()
            },
            "limits": self.ACTION_LIMITS,
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get rate limiter instance."""
    return rate_limiter
