#!/usr/bin/env python
"""
Простой запуск автокомментирования для инфобизнеса.

Использует 4 аккаунта с ротацией:
- Лёша Лаймов (@lemonlime192)
- Карина (@karinko_o)
- Люба (@lyuba_ok)
- Кира (@kirushka_94)

Запуск:
    python run_auto_comments.py

Остановка:
    Ctrl+C
"""

import asyncio
import sys
from loguru import logger

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant
from traffic_engine.main import TrafficEngine


async def main():
    """Запустить автокомментирование для инфобизнеса."""

    # Настройка логирования
    logger.remove()  # Убираем дефолтный handler
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "logs/auto_comments_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        level="DEBUG"
    )

    logger.info("=" * 60)
    logger.info("TRAFFIC ENGINE - АВТОКОММЕНТИРОВАНИЕ")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Аккаунты для ротации:")
    logger.info("  1. Лёша Лаймов (@lemonlime192)")
    logger.info("  2. Карина (@karinko_o)")
    logger.info("  3. Люба (@lyuba_ok)")
    logger.info("  4. Кира (@kirushka_94)")
    logger.info("")
    logger.info("Для остановки нажмите Ctrl+C")
    logger.info("=" * 60)
    logger.info("")

    # Инициализируем БД
    await init_db()
    logger.info("База данных инициализирована")

    # Проверяем, есть ли тенант infobusiness
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            logger.error("Тенант 'infobusiness' не найден в БД!")
            logger.info("Запустите: python scripts/init_db.py")
            return

    logger.info(f"Запускаю Traffic Engine для тенанта: {tenant.display_name}")
    logger.info("")

    # Создаём и запускаем движок
    engine = TrafficEngine()

    try:
        # Запускаем только для infobusiness
        await engine.start(tenant_names=["infobusiness"])
    except KeyboardInterrupt:
        logger.info("\n\nПолучен сигнал остановки...")
        await engine.stop()
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await engine.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершено пользователем")
