#!/usr/bin/env python
"""
Безопасная подписка всех аккаунтов на приоритетные каналы.

Стратегия:
- 5 каналов для каждого аккаунта (безопасно)
- Пауза 45-90 сек между подписками
- Пауза 5-7 минут между аккаунтами
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
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest, GetFullChannelRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount

# Топ-5 каналов (с частыми постами)
PRIORITY_CHANNELS = [
    "mspiridonov",      # Максим Спиридонов
    "Oskar_Hartmann",   # Оскар Хартманн
    "portnyaginlive",   # Портнягин
    "Theedinorogblog",  # Единорог
    "sberstartup",      # Сбер Стартап
]


async def is_subscribed(client: TelegramClient, channel_username: str) -> bool:
    """Check if subscribed to channel."""
    try:
        entity = await client.get_entity(channel_username)
        me = await client.get_me()
        await client(GetParticipantRequest(channel=entity, participant=me))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        return False


async def join_discussion_group(client: TelegramClient, channel_username: str) -> bool:
    """Join discussion group (linked chat) of the channel."""
    try:
        channel = await client.get_entity(channel_username)
        full = await client(GetFullChannelRequest(channel))
        linked_chat_id = full.full_chat.linked_chat_id

        if not linked_chat_id:
            return False

        discussion = await client.get_entity(linked_chat_id)

        # Check if already in discussion
        try:
            me = await client.get_me()
            await client(GetParticipantRequest(channel=discussion, participant=me))
            return True  # Already in
        except UserNotParticipantError:
            pass

        # Join discussion group
        await client(JoinChannelRequest(discussion))
        return True

    except Exception:
        return False


async def subscribe_account(account: UserBotAccount):
    """Subscribe one account to priority channels."""
    print(f"\n{'=' * 60}")
    print(f"Account: {account.first_name} ({account.phone})")
    print(f"{'=' * 60}")

    # Connect
    client = TelegramClient(
        StringSession(account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )
    await client.connect()

    if not await client.is_user_authorized():
        print(f"  [X] Account not authorized!")
        await client.disconnect()
        return 0, 0, len(PRIORITY_CHANNELS)

    channel_ok = 0
    discussion_ok = 0
    failed = 0

    for i, username in enumerate(PRIORITY_CHANNELS, 1):
        print(f"  [{i}/{len(PRIORITY_CHANNELS)}] @{username}")

        try:
            # 1. Subscribe to channel
            print(f"    Channel: ", end="", flush=True)
            if await is_subscribed(client, username):
                print("[OK] already")
                channel_ok += 1
            else:
                await client(JoinChannelRequest(username))
                print("[+] JOINED")
                channel_ok += 1
                await asyncio.sleep(random.randint(10, 20))

            # 2. Subscribe to discussion group
            print(f"    Discussion: ", end="", flush=True)
            if await join_discussion_group(client, username):
                print("[+] JOINED")
                discussion_ok += 1
            else:
                print("[-] no group")

            # Pause between channels
            if i < len(PRIORITY_CHANNELS):
                delay = random.randint(45, 90)
                print(f"    Wait {delay}s...\n")
                await asyncio.sleep(delay)

        except FloodWaitError as e:
            print(f"    [X] FloodWait {e.seconds}s")
            failed += 1
            await asyncio.sleep(e.seconds + 10)
        except ChannelPrivateError:
            print(f"    [X] Private channel")
            failed += 1
        except UserBannedInChannelError:
            print(f"    [X] BANNED!")
            failed += 1
        except Exception as e:
            print(f"    [X] Error: {str(e)[:40]}")
            failed += 1

    await client.disconnect()
    return channel_ok, discussion_ok, failed


async def main():
    await init_db()

    print("=" * 60)
    print("SAFE SUBSCRIPTION - ALL ACCOUNTS")
    print("=" * 60)
    print(f"Channels: {len(PRIORITY_CHANNELS)}")
    print()

    # Get accounts to subscribe (disabled ones)
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.status == "disabled")
        )
        accounts = result.scalars().all()

    if not accounts:
        print("No disabled accounts found!")
        return

    print(f"Accounts to subscribe: {len(accounts)}")
    print()

    total_channels = 0
    total_discussions = 0
    total_failed = 0

    for idx, account in enumerate(accounts, 1):
        ch_ok, disc_ok, failed = await subscribe_account(account)
        total_channels += ch_ok
        total_discussions += disc_ok
        total_failed += failed

        # Pause between accounts (5-7 min)
        if idx < len(accounts):
            delay = random.randint(300, 420)
            print(f"\n{'=' * 60}")
            print(f"Pause between accounts: {delay // 60} min {delay % 60} sec")
            print(f"{'=' * 60}\n")
            await asyncio.sleep(delay)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Channels subscribed:   {total_channels}")
    print(f"  Discussion groups:     {total_discussions}")
    print(f"  Failed:                {total_failed}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
