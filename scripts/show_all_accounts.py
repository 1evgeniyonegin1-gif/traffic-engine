"""Показать все аккаунты"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text


async def main():
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT phone, status, first_name, daily_comments, daily_story_views "
            "FROM traffic_userbot_accounts ORDER BY phone"
        ))

        print("\n=== ВСЕ АККАУНТЫ ===\n")
        for row in result:
            phone, status, name, comments, stories = row
            print(f"{phone} ({name})")
            print(f"  Статус: {status}")
            print(f"  Комментариев сегодня: {comments}")
            print(f"  Story views сегодня: {stories}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
