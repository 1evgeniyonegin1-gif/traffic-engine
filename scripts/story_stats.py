#!/usr/bin/env python
"""Быстрая статистика Story Viewing."""
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, cast, Date
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import TrafficAction, UserBotAccount


async def main():
    await init_db()

    async with get_session() as session:
        # Сегодня
        result = await session.execute(
            select(TrafficAction.status, func.count(TrafficAction.id))
            .where(
                TrafficAction.action_type == "story_view",
                cast(TrafficAction.created_at, Date) == date.today()
            )
            .group_by(TrafficAction.status)
        )

        stats = dict(result)
        total = sum(stats.values())
        success = stats.get("success", 0)

        print(f"\n📊 Story Views Today: {total}")
        print(f"   ✅ Success: {success} ({success/total*100 if total else 0:.0f}%)")
        print(f"   ⏭️  Skipped: {stats.get('skipped', 0)}")
        print(f"   ❌ Failed: {stats.get('failed', 0)}\n")


if __name__ == "__main__":
    asyncio.run(main())
