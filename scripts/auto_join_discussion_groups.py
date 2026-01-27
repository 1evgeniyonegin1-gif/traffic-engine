#!/usr/bin/env python
"""
Auto-join discussion groups for all active channels across all accounts.
"""

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    InviteRequestSentError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount, TargetChannel


async def join_discussion_groups():
    """Join discussion groups for all active channels."""
    await init_db()

    print("=" * 70)
    print("AUTO JOIN DISCUSSION GROUPS")
    print("=" * 70)

    # Get all active channels
    async with get_session() as session:
        channels_result = await session.execute(
            select(TargetChannel).where(TargetChannel.is_active == True)
        )
        channels = channels_result.scalars().all()

        accounts_result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.status == "active")
        )
        accounts = accounts_result.scalars().all()

    print(f"\nChannels: {len(channels)}")
    print(f"Accounts: {len(accounts)}\n")

    if not channels:
        print("No active channels found!")
        return

    if not accounts:
        print("No active accounts found!")
        return

    # Process each account
    for account in accounts:
        print(f"\n{'='*70}")
        print(f"Account: {account.first_name} ({account.phone})")
        print(f"{'='*70}\n")

        # Connect
        client = TelegramClient(
            StringSession(account.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print(f"  ERROR: Account not authorized!")
                continue

            joined_count = 0
            skipped_count = 0
            error_count = 0

            for channel in channels:
                username = channel.username or str(channel.channel_id)

                try:
                    # Get channel
                    try:
                        entity = await client.get_entity(username)
                    except Exception as e:
                        print(f"  SKIP @{username}: Can't get entity ({e})")
                        skipped_count += 1
                        continue

                    # Get full channel info
                    full_channel = await client(GetFullChannelRequest(entity))
                    linked_chat_id = full_channel.full_chat.linked_chat_id

                    if not linked_chat_id:
                        print(f"  SKIP @{username}: No discussion group")
                        skipped_count += 1
                        continue

                    # Get discussion group entity
                    try:
                        discussion_entity = await client.get_entity(linked_chat_id)
                    except Exception as e:
                        print(f"  ERROR @{username}: Can't get discussion group ({e})")
                        error_count += 1
                        continue

                    # Try to join
                    try:
                        await client(JoinChannelRequest(discussion_entity))
                        print(f"  JOIN @{username} -> discussion group")
                        joined_count += 1

                        # Human-like delay
                        await asyncio.sleep(random.uniform(3, 8))

                    except FloodWaitError as e:
                        print(f"  FLOOD @{username}: Wait {e.seconds}s")
                        await asyncio.sleep(e.seconds)
                        continue

                    except (ChannelPrivateError, UserBannedInChannelError) as e:
                        print(f"  BANNED @{username}: {e}")
                        error_count += 1

                    except InviteRequestSentError:
                        print(f"  REQUEST @{username}: Invite request sent")
                        joined_count += 1

                except Exception as e:
                    print(f"  ERROR @{username}: {e}")
                    error_count += 1

            print(f"\n  Summary: {joined_count} joined, {skipped_count} skipped, {error_count} errors")

        finally:
            await client.disconnect()

        # Delay between accounts
        if account != accounts[-1]:
            delay = random.uniform(30, 60)
            print(f"\n  Waiting {delay:.0f}s before next account...")
            await asyncio.sleep(delay)

    print(f"\n{'='*70}")
    print("DONE!")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(join_discussion_groups())
