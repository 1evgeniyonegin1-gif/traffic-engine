#!/usr/bin/env python
"""
Статистика комментариев - показывает все комментарии с деталями.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text


async def main():
    async with get_session() as db:
        print("\n" + "="*80)
        print("СТАТИСТИКА КОММЕНТАРИЕВ")
        print("="*80)

        # Общая статистика
        result = await db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'flood_wait' THEN 1 ELSE 0 END) as flood_wait
            FROM traffic_actions
            WHERE action_type = 'comment'
        """))
        stats = result.fetchone()

        print(f"\nВсего комментариев: {stats[0]}")
        print(f"  Успешных: {stats[1]} ({stats[1]*100/stats[0] if stats[0] > 0 else 0:.1f}%)")
        print(f"  Неудачных: {stats[2]}")
        print(f"  FloodWait: {stats[3]}")

        # По аккаунтам
        print("\n" + "-"*80)
        print("ПО АККАУНТАМ:")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                uba.phone,
                uba.first_name,
                COUNT(ta.id) as total,
                SUM(CASE WHEN ta.status = 'success' THEN 1 ELSE 0 END) as success
            FROM traffic_userbot_accounts uba
            LEFT JOIN traffic_actions ta ON ta.account_id = uba.id AND ta.action_type = 'comment'
            GROUP BY uba.phone, uba.first_name
            ORDER BY total DESC
        """))

        for row in result:
            phone, name, total, success = row
            print(f"\n{name} ({phone}):")
            print(f"  Всего: {total}, Успешных: {success}")

        # По каналам
        print("\n" + "-"*80)
        print("ПО КАНАЛАМ (топ 10):")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                tc.title,
                tc.username,
                COUNT(ta.id) as total,
                SUM(CASE WHEN ta.status = 'success' THEN 1 ELSE 0 END) as success
            FROM traffic_target_channels tc
            LEFT JOIN traffic_actions ta ON ta.target_channel_id = tc.channel_id AND ta.action_type = 'comment'
            GROUP BY tc.title, tc.username
            HAVING COUNT(ta.id) > 0
            ORDER BY total DESC
            LIMIT 10
        """))

        for row in result:
            title, username, total, success = row
            # Убрать emoji из названия канала
            title_clean = title.encode('ascii', 'ignore').decode('ascii') if title else 'Unknown'
            print(f"\n{title_clean} (@{username}):")
            print(f"  Всего: {total}, Успешных: {success}")

        # Последние 10 комментариев
        print("\n" + "-"*80)
        print("ПОСЛЕДНИЕ 10 КОММЕНТАРИЕВ:")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                ta.created_at,
                uba.first_name,
                tc.title,
                ta.content,
                ta.status
            FROM traffic_actions ta
            JOIN traffic_userbot_accounts uba ON uba.id = ta.account_id
            LEFT JOIN traffic_target_channels tc ON tc.channel_id = ta.target_channel_id
            WHERE ta.action_type = 'comment'
            ORDER BY ta.created_at DESC
            LIMIT 10
        """))

        for row in result:
            created_at, name, channel, content, status = row
            # Убрать emoji
            channel_clean = channel.encode('ascii', 'ignore').decode('ascii') if channel else 'Unknown'
            print(f"\n[{created_at.strftime('%Y-%m-%d %H:%M:%S')}] {name} -> {channel_clean}")
            print(f"  Статус: {status}")
            if content:
                # Обрезать длинный текст и убрать emoji
                content_clean = content.encode('ascii', 'ignore').decode('ascii')
                preview = content_clean[:100] + "..." if len(content_clean) > 100 else content_clean
                print(f"  Текст: {preview}")

        # За последние 24 часа
        print("\n" + "-"*80)
        print("ЗА ПОСЛЕДНИЕ 24 ЧАСА:")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
            FROM traffic_actions
            WHERE action_type = 'comment'
            AND created_at > NOW() - INTERVAL '24 hours'
        """))
        stats = result.fetchone()

        print(f"\nВсего: {stats[0]}, Успешных: {stats[1]}")

        print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
