#!/usr/bin/env python
"""Analyze failed comments and their reasons."""

import asyncio
from collections import Counter

from sqlalchemy import select

from traffic_engine.database import get_session
from traffic_engine.database.models import TrafficAction


async def analyze_failures():
    """Analyze failed comments."""
    async with get_session() as session:
        # Get all failed comments
        result = await session.execute(
            select(TrafficAction)
            .where(
                TrafficAction.action_type == "comment",
                TrafficAction.status == "failed"
            )
            .order_by(TrafficAction.created_at.desc())
            .limit(50)
        )
        failed_actions = result.scalars().all()

        if not failed_actions:
            print("No failed comments found!")
            return

        print(f"Found {len(failed_actions)} failed comments\n")

        # Count error reasons
        error_counter = Counter()
        channel_errors = {}

        for action in failed_actions:
            error_msg = action.error_message or "Unknown error"
            error_counter[error_msg] += 1

            channel_id = action.target_channel_id
            if channel_id not in channel_errors:
                channel_errors[channel_id] = []
            channel_errors[channel_id].append(error_msg)

        # Print error distribution
        print("Error reasons:")
        for error, count in error_counter.most_common(10):
            print(f"  {count:3}x | {error[:100]}")

        # Print channels with most errors
        print(f"\nChannels with errors:")
        for channel_id, errors in sorted(
            channel_errors.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]:
            print(f"  Channel {channel_id}: {len(errors)} errors")
            # Show unique error types
            unique_errors = set(errors)
            for err in list(unique_errors)[:3]:
                print(f"    - {err[:80]}")


if __name__ == "__main__":
    asyncio.run(analyze_failures())
