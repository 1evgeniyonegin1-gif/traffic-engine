#!/usr/bin/env python
"""Disable channels where we can't comment (admin privileges required)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update

from traffic_engine.database import get_session
from traffic_engine.database.models import TargetChannel, TrafficAction


async def disable_restricted_channels():
    """Disable channels with 'admin privileges required' errors."""
    async with get_session() as session:
        # Find channels with admin privilege errors
        result = await session.execute(
            select(TrafficAction.target_channel_id)
            .where(
                TrafficAction.action_type == "comment",
                TrafficAction.status == "failed",
                TrafficAction.error_message.like("%admin privileges are required%")
            )
            .group_by(TrafficAction.target_channel_id)
        )

        restricted_channel_ids = [row[0] for row in result.all()]

        if not restricted_channel_ids:
            print("No restricted channels found!")
            return

        print(f"Found {len(restricted_channel_ids)} channels with admin restrictions:")

        # Get channel details
        channels_result = await session.execute(
            select(TargetChannel)
            .where(TargetChannel.channel_id.in_(restricted_channel_ids))
        )
        channels = channels_result.scalars().all()

        for channel in channels:
            username = f"@{channel.username}" if channel.username else f"ID:{channel.channel_id}"
            try:
                print(f"  - {username} ({channel.title})")
            except UnicodeEncodeError:
                print(f"  - {username}")

        # Ask for confirmation
        response = input("\nDisable these channels? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Cancelled.")
            return

        # Disable channels
        await session.execute(
            update(TargetChannel)
            .where(TargetChannel.channel_id.in_(restricted_channel_ids))
            .values(is_active=False)
        )
        await session.commit()

        print(f"\nDisabled {len(restricted_channel_ids)} channels")

        # Show remaining active channels
        active_result = await session.execute(
            select(TargetChannel)
            .where(TargetChannel.is_active == True)
        )
        active_channels = active_result.scalars().all()

        print(f"\nRemaining active channels: {len(active_channels)}")
        for ch in active_channels[:10]:
            username = f"@{ch.username}" if ch.username else f"ID:{ch.channel_id}"
            try:
                print(f"  - {username} ({ch.title})")
            except UnicodeEncodeError:
                print(f"  - {username}")


if __name__ == "__main__":
    asyncio.run(disable_restricted_channels())
