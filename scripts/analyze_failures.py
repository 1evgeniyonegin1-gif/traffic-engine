#!/usr/bin/env python
"""
Анализ причин неудачных комментариев
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text


async def main():
    async with get_session() as db:
        print("\n" + "="*80)
        print("АНАЛИЗ НЕУДАЧНЫХ КОММЕНТАРИЕВ")
        print("="*80)

        # Статистика по ошибкам
        print("\nПРИЧИНЫ НЕУДАЧ:")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                status,
                error_message,
                COUNT(*) as count
            FROM traffic_actions
            WHERE action_type = 'comment' AND status != 'success'
            GROUP BY status, error_message
            ORDER BY count DESC
            LIMIT 20
        """))

        for row in result:
            status, error, count = row
            error_clean = error.encode('ascii', 'ignore').decode('ascii') if error else 'No message'
            # Обрезать длинное сообщение
            error_short = error_clean[:80] + "..." if len(error_clean) > 80 else error_clean
            print(f"\n[{status}] ({count} раз)")
            print(f"  {error_short}")

        # По каналам - где больше всего неудач
        print("\n" + "="*80)
        print("КАНАЛЫ С НАИБОЛЬШИМ КОЛИЧЕСТВОМ НЕУДАЧ:")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                tc.title,
                tc.username,
                COUNT(*) as total,
                SUM(CASE WHEN ta.status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN ta.status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM traffic_target_channels tc
            LEFT JOIN traffic_actions ta ON ta.target_channel_id = tc.channel_id AND ta.action_type = 'comment'
            WHERE tc.is_active = true
            GROUP BY tc.title, tc.username
            HAVING COUNT(ta.id) > 0
            ORDER BY failed DESC
            LIMIT 10
        """))

        for row in result:
            title, username, total, success, failed = row
            title_clean = title.encode('ascii', 'ignore').decode('ascii') if title else 'Unknown'
            success_rate = (success / total * 100) if total > 0 else 0
            print(f"\n{title_clean} (@{username})")
            print(f"  Всего: {total}, Успешных: {success} ({success_rate:.1f}%), Неудачных: {failed}")

        # Последние ошибки с деталями
        print("\n" + "="*80)
        print("ПОСЛЕДНИЕ 10 ОШИБОК (детально):")
        print("-"*80)

        result = await db.execute(text("""
            SELECT
                ta.created_at,
                uba.first_name,
                tc.title,
                ta.status,
                ta.error_message,
                ta.content
            FROM traffic_actions ta
            JOIN traffic_userbot_accounts uba ON uba.id = ta.account_id
            LEFT JOIN traffic_target_channels tc ON tc.channel_id = ta.target_channel_id
            WHERE ta.action_type = 'comment' AND ta.status != 'success'
            ORDER BY ta.created_at DESC
            LIMIT 10
        """))

        for row in result:
            created_at, name, channel, status, error, content = row
            channel_clean = channel.encode('ascii', 'ignore').decode('ascii') if channel else 'Unknown'
            error_clean = error.encode('ascii', 'ignore').decode('ascii') if error else 'No message'

            print(f"\n[{created_at.strftime('%Y-%m-%d %H:%M:%S')}] {name} -> {channel_clean}")
            print(f"  Статус: {status}")
            print(f"  Ошибка: {error_clean[:150]}")

        # Рекомендации
        print("\n" + "="*80)
        print("РЕКОМЕНДАЦИИ:")
        print("="*80)

        # Проверить настройки каналов
        result = await db.execute(text("""
            SELECT COUNT(*) FROM traffic_target_channels WHERE is_active = true
        """))
        active_channels = result.scalar()

        result = await db.execute(text("""
            SELECT COUNT(DISTINCT tc.id)
            FROM traffic_target_channels tc
            JOIN traffic_actions ta ON ta.target_channel_id = tc.channel_id
            WHERE ta.action_type = 'comment' AND ta.status = 'failed'
            AND ta.error_message LIKE '%comment%disabled%'
        """))
        disabled_comments = result.scalar()

        print(f"\n1. Активных каналов: {active_channels}")
        if disabled_comments > 0:
            print(f"   [!] {disabled_comments} каналов с отключенными комментариями")
            print(f"   Решение: Отключить эти каналы (is_active=false)")

        print(f"\n2. Проверить что комментарии разрешены в каналах")
        print(f"   Решение: python scripts/verify_channels.py")

        print(f"\n3. Возможные причины низкого success rate:")
        print(f"   - Комментарии отключены в канале")
        print(f"   - Канал приватный/закрытый")
        print(f"   - Бот не подписан на канал")
        print(f"   - Пост удалён/недоступен")
        print(f"   - Ограничения Telegram на новые аккаунты")

        print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
