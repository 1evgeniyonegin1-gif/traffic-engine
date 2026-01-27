"""
Быстрая проверка целевой аудитории
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text


async def main():
    async with get_session() as db:
        # Всего пользователей
        result = await db.execute(text("SELECT COUNT(*) FROM traffic_target_audience"))
        total = result.scalar()
        print(f"\nВсего пользователей в ЦА: {total}")

        if total == 0:
            print("\nПРОБЛЕМА: В базе нет целевой аудитории!")
            print("   Решение: запустите скрипты для сбора ЦА из каналов")
            return

        # По качеству
        result = await db.execute(text(
            "SELECT quality_score, COUNT(*) FROM traffic_target_audience "
            "GROUP BY quality_score ORDER BY quality_score DESC"
        ))
        rows = result.fetchall()
        print("\nПо quality_score:")
        for score, count in rows:
            print(f"  Score {score}: {count} чел")

        # Подходящие для story viewing
        result = await db.execute(text(
            "SELECT COUNT(*) FROM traffic_target_audience WHERE quality_score >= 70"
        ))
        suitable = result.scalar()
        print(f"\nПодходят для story viewing (score >= 70): {suitable}")

        if suitable == 0:
            print("\nПРОБЛЕМА: Нет пользователей с quality_score >= 70")
            print("   Решение 1: Понизить порог в .env (STORY_VIEW_MIN_QUALITY_SCORE)")
            print("   Решение 2: Улучшить качество ЦА (собрать из более активных каналов)")

        # Последние 10 пользователей
        result = await db.execute(text(
            "SELECT username, quality_score FROM traffic_target_audience "
            "ORDER BY created_at DESC LIMIT 10"
        ))
        recent = result.fetchall()
        print("\nПоследние 10 добавленных:")
        for username, score in recent:
            print(f"  @{username or 'no_username'} (score: {score})")


if __name__ == "__main__":
    asyncio.run(main())
