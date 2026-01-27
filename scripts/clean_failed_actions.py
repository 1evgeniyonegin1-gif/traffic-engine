#!/usr/bin/env python
"""
Очистка старых failed actions из базы данных.

Удаляет записи со status='failed' старше указанного количества дней.
"""

import asyncio
import sys
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import delete, select, func

# Добавляем корень проекта в путь
sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0].rstrip("\\").rstrip("/"))

from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import TrafficAction


async def show_stats():
    """Показать статистику actions по статусам."""
    async with get_session() as session:
        result = await session.execute(
            select(
                TrafficAction.status,
                func.count(TrafficAction.id).label("count")
            ).group_by(TrafficAction.status)
        )
        stats = result.all()

        logger.info("Текущая статистика actions:")
        for status, count in stats:
            logger.info(f"  {status}: {count}")


async def clean_failed_actions(days_old: int = 7, dry_run: bool = True):
    """
    Удалить старые failed actions.

    Args:
        days_old: Удалять записи старше N дней
        dry_run: Только показать, не удалять
    """
    cutoff_date = datetime.now() - timedelta(days=days_old)

    async with get_session() as session:
        # Считаем, сколько будет удалено
        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.status == "failed",
                TrafficAction.created_at < cutoff_date
            )
        )
        count = result.scalar()

        logger.info(f"Найдено {count} failed actions старше {days_old} дней")

        if count == 0:
            logger.info("Нечего удалять")
            return

        if dry_run:
            logger.info("Режим dry-run: записи НЕ удалены")
            logger.info("Для удаления запустите с параметром --delete")
            return

        # Удаляем
        result = await session.execute(
            delete(TrafficAction).where(
                TrafficAction.status == "failed",
                TrafficAction.created_at < cutoff_date
            )
        )
        await session.commit()

        logger.info(f"Удалено {result.rowcount} записей")


async def main():
    """Основная функция."""
    import argparse

    parser = argparse.ArgumentParser(description="Очистка старых failed actions")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Удалять записи старше N дней (default: 7)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Реально удалить записи (без этого флага - только показ)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Показать статистику и выйти"
    )
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, format="{time:HH:mm:ss} | {level} | {message}", level="INFO")

    await init_db()

    if args.stats:
        await show_stats()
        return

    await show_stats()
    logger.info("")
    await clean_failed_actions(days_old=args.days, dry_run=not args.delete)
    logger.info("")
    await show_stats()


if __name__ == "__main__":
    asyncio.run(main())
