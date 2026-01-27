#!/usr/bin/env python
"""Check comment statistics from PostgreSQL."""

import asyncio
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from traffic_engine.database import get_session
from traffic_engine.database.models import TrafficAction


async def check_stats():
    """Check comment statistics."""
    async with get_session() as session:
        # Comments today
        today_count = await session.scalar(
            select(func.count())
            .select_from(TrafficAction)
            .where(
                TrafficAction.action_type == "comment",
                func.date(TrafficAction.created_at) == func.date(func.now())
            )
        )
        print(f"Comments today: {today_count or 0}")

        # Successful comments (all time)
        success_count = await session.scalar(
            select(func.count())
            .select_from(TrafficAction)
            .where(
                TrafficAction.action_type == "comment",
                TrafficAction.status == "success"
            )
        )
        print(f"Successful comments (all time): {success_count or 0}")

        # Last 5 comments
        result = await session.execute(
            select(TrafficAction)
            .where(TrafficAction.action_type == "comment")
            .order_by(TrafficAction.created_at.desc())
            .limit(5)
        )
        actions = result.scalars().all()

        print("\nLast 5 comments:")
        for action in actions:
            content = (
                action.content[:50] + "..."
                if action.content and len(action.content) > 50
                else action.content or "(no content)"
            )
            created = action.created_at.strftime("%Y-%m-%d %H:%M:%S")
            print(f"{created} | {action.status:8} | Channel: {action.target_channel_id} | {content}")


if __name__ == "__main__":
    asyncio.run(check_stats())
