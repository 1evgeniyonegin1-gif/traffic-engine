"""
Human Simulator - Имитация человеческого поведения.

Функции:
- Определение "рабочих часов"
- Симуляция времени печати
- Симуляция времени чтения
- Рандомные паузы
"""

import random
from datetime import datetime, time as dt_time
from typing import Optional

from loguru import logger

from traffic_engine.config import settings


class HumanSimulator:
    """
    Имитация человеческого поведения для избежания детекта ботов.

    Паттерны:
    - Случайные задержки между действиями
    - "Рабочие часы" (9:00-23:00 по умолчанию)
    - Паузы на "обед", "сон"
    - Иногда просто читать без действий
    """

    def __init__(
        self,
        work_start_hour: int = settings.work_start_hour,
        work_end_hour: int = settings.work_end_hour,
    ):
        """
        Initialize human simulator.

        Args:
            work_start_hour: Час начала "работы" (0-23)
            work_end_hour: Час окончания "работы" (1-24)
        """
        self.work_start = work_start_hour
        self.work_end = work_end_hour

    def is_working_hours(self) -> bool:
        """
        Проверить, сейчас рабочие часы.

        Returns:
            True если сейчас можно работать
        """
        current_hour = datetime.now().hour
        return self.work_start <= current_hour < self.work_end

    def should_act_now(self, action_probability: float = 0.8) -> bool:
        """
        Решить, выполнять ли действие сейчас.

        Имитирует человека, который не всегда сразу реагирует.

        Args:
            action_probability: Базовая вероятность действия (0-1)

        Returns:
            True если нужно действовать
        """
        # Ночью не работаем
        if not self.is_working_hours():
            logger.debug("Outside working hours, skipping action")
            return False

        # Случайно пропускаем действия для естественности
        if random.random() > action_probability:
            logger.debug("Random skip for human-like behavior")
            return False

        # В "обеденное время" (12-14) снижаем активность
        current_hour = datetime.now().hour
        if 12 <= current_hour <= 14:
            if random.random() > 0.5:  # 50% пропуск
                logger.debug("Lunch time, reduced activity")
                return False

        return True

    def get_typing_delay(self, text: str) -> float:
        """
        Получить время на "печатание" текста.

        Args:
            text: Текст который "печатаем"

        Returns:
            Время в секундах
        """
        # Средняя скорость печати: 3-6 символов в секунду
        chars_per_second = random.uniform(3, 6)
        base_time = len(text) / chars_per_second

        # Добавляем время на "подумать"
        thinking_time = random.uniform(1, 5)

        # Иногда делаем паузы (имитация исправления опечаток)
        if random.random() < 0.2:  # 20% шанс
            pause = random.uniform(2, 5)
            base_time += pause

        return base_time + thinking_time

    def get_reading_delay(self, text: str) -> float:
        """
        Получить время на "прочтение" текста.

        Args:
            text: Текст для чтения

        Returns:
            Время в секундах
        """
        # Средняя скорость чтения: 200-400 слов в минуту
        words = len(text.split())
        words_per_minute = random.uniform(200, 400)
        base_time = (words / words_per_minute) * 60

        # Минимум 2 секунды даже для коротких текстов
        base_time = max(base_time, 2)

        # Добавляем время на "осмысление"
        if words > 50:
            thinking_time = random.uniform(2, 8)
            base_time += thinking_time

        return base_time

    def get_scroll_delay(self) -> float:
        """
        Получить время на прокрутку/переход.

        Returns:
            Время в секундах
        """
        return random.uniform(0.5, 2.0)

    def get_random_pause(
        self,
        min_seconds: float = 1,
        max_seconds: float = 10
    ) -> float:
        """
        Получить случайную паузу.

        Args:
            min_seconds: Минимальная пауза
            max_seconds: Максимальная пауза

        Returns:
            Время в секундах
        """
        return random.uniform(min_seconds, max_seconds)

    def get_session_duration(self) -> float:
        """
        Получить длительность "сессии" активности.

        Имитирует то, что человек не сидит в телеграме постоянно.

        Returns:
            Время активной сессии в минутах
        """
        # Сессия от 10 до 60 минут
        return random.uniform(10, 60)

    def get_break_duration(self) -> float:
        """
        Получить длительность перерыва между сессиями.

        Returns:
            Время перерыва в минутах
        """
        # Перерыв от 15 до 120 минут
        return random.uniform(15, 120)

    def should_take_break(self, actions_count: int) -> bool:
        """
        Решить, нужен ли перерыв.

        Args:
            actions_count: Количество выполненных действий в текущей сессии

        Returns:
            True если нужен перерыв
        """
        # После 20-40 действий делаем перерыв
        threshold = random.randint(20, 40)
        return actions_count >= threshold

    def get_reaction_emoji(self) -> str:
        """
        Получить случайный эмодзи для реакции на сторис.

        Returns:
            Эмодзи
        """
        # Популярные реакции
        reactions = ["👍", "🔥", "❤️", "😍", "👏", "💪", "🙌", "✨"]

        # Взвешенный выбор (первые более популярны)
        weights = [30, 25, 20, 10, 5, 5, 3, 2]

        return random.choices(reactions, weights=weights, k=1)[0]

    def should_react_to_story(self, probability: float = 0.3) -> bool:
        """
        Решить, ставить ли реакцию на сторис.

        Не все сторис требуют реакции - это выглядит подозрительно.

        Args:
            probability: Вероятность реакции (0-1)

        Returns:
            True если стоит поставить реакцию
        """
        return random.random() < probability


# Global human simulator instance
human_simulator = HumanSimulator()


def get_human_simulator() -> HumanSimulator:
    """Get human simulator instance."""
    return human_simulator
