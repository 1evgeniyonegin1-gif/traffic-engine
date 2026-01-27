#!/usr/bin/env python
"""
Отключить проблемные каналы автоматически.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text
from loguru import logger


async def main():
    logger.info("=== Поиск и отключение проблемных каналов ===")

    async with get_session() as db:
        # Найти каналы с частыми ошибками "admin required"
        result = await db.execute(text("""
            SELECT DISTINCT tc.id, tc.title, tc.username,
                   COUNT(*) as error_count
            FROM traffic_target_channels tc
            JOIN traffic_actions ta ON ta.target_channel_id = tc.channel_id
            WHERE ta.action_type = 'comment'
            AND ta.status = 'failed'
            AND (
                ta.error_message LIKE '%admin privileges%'
                OR ta.error_message LIKE '%Invalid channel%'
                OR ta.error_message LIKE '%Failed to get channel%'
            )
            AND tc.is_active = true
            GROUP BY tc.id, tc.title, tc.username
            HAVING COUNT(*) >= 2
            ORDER BY error_count DESC
        """))

        channels_to_disable = result.fetchall()

        if not channels_to_disable:
            logger.success("Проблемных каналов не найдено!")
            return

        logger.info(f"Найдено {len(channels_to_disable)} проблемных каналов:")

        disabled = 0
        for row in channels_to_disable:
            channel_id, title, username, errors = row
            title_clean = title.encode('ascii', 'ignore').decode('ascii') if title else 'Unknown'

            logger.warning(f"  {title_clean} (@{username}) - {errors} ошибок")

            # Отключить канал
            await db.execute(text("""
                UPDATE traffic_target_channels
                SET is_active = false
                WHERE id = :channel_id
            """), {"channel_id": channel_id})

            disabled += 1

        await db.commit()

        logger.success(f"Отключено {disabled} проблемных каналов")

        # Показать оставшиеся активные каналы
        result = await db.execute(text("""
            SELECT COUNT(*) FROM traffic_target_channels WHERE is_active = true
        """))
        active = result.scalar()

        logger.info(f"Осталось {active} активных каналов")

        # Показать каналы с лучшим success rate
        logger.info("\nЛучшие каналы (оставлены активными):")

        result = await db.execute(text("""
            SELECT
                tc.title,
                tc.username,
                COUNT(*) as total,
                SUM(CASE WHEN ta.status = 'success' THEN 1 ELSE 0 END) as success
            FROM traffic_target_channels tc
            LEFT JOIN traffic_actions ta ON ta.target_channel_id = tc.channel_id AND ta.action_type = 'comment'
            WHERE tc.is_active = true
            GROUP BY tc.title, tc.username
            HAVING COUNT(ta.id) > 0
            ORDER BY success DESC
            LIMIT 5
        """))

        for row in result:
            title, username, total, success = row
            title_clean = title.encode('ascii', 'ignore').decode('ascii') if title else 'Unknown'
            rate = (success / total * 100) if total > 0 else 0
            logger.info(f"  {title_clean} (@{username}) - {success}/{total} ({rate:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
