#!/usr/bin/env python
"""
Быстрое добавление тестовой ЦА для Story Viewing.

ВНИМАНИЕ: Этот скрипт создаёт ФЕЙКОВЫЕ записи для теста!
Для реальной ЦА используйте collect_target_audience.py
"""

import asyncio
import sys
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from traffic_engine.database import get_session
from traffic_engine.database.models import TargetAudience, TargetChannel
from sqlalchemy import select


async def main():
    """Добавить тестовую ЦА на основе существующих каналов."""
    logger.info("=== Добавление тестовой ЦА ===")

    async with get_session() as db:
        # Получить первые 5 каналов
        result = await db.execute(
            select(TargetChannel).where(TargetChannel.is_active == True).limit(5)
        )
        channels = result.scalars().all()

        if not channels:
            logger.error("Нет активных каналов!")
            return

        # Создать тестовые записи ЦА (имитация подписчиков)
        added = 0
        for channel in channels:
            # Добавить 20 фейковых юзеров на канал
            for i in range(20):
                # Генерируем рандомный user_id (от 100000000 до 999999999)
                user_id = random.randint(100000000, 999999999)

                audience = TargetAudience(
                    tenant_id=channel.tenant_id,
                    user_id=user_id,
                    username=f"user_{user_id % 10000}",
                    first_name=f"Test User {i+1}",
                    source_type="channel_subscribers",
                    source_id=channel.channel_id,
                    source_name=channel.title,
                    quality_score=random.randint(50, 95),  # Хороший рандомный скор
                    status="new"
                )
                db.add(audience)
                added += 1

        await db.commit()
        logger.success(f"Добавлено {added} тестовых пользователей в ЦА")

        # Статистика
        result = await db.execute(
            select(TargetAudience)
            .where(TargetAudience.quality_score >= 50)
        )
        suitable = len(result.scalars().all())
        logger.info(f"Пользователей с quality_score >= 50: {suitable}")

    logger.success("=== Готово! ===")
    logger.warning("ВНИМАНИЕ: Это тестовые данные! Для реального сбора ЦА используйте collect_target_audience.py")


if __name__ == "__main__":
    asyncio.run(main())
