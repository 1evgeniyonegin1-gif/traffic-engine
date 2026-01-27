#!/usr/bin/env python
"""
Подписка на группы обсуждения каналов.

Проблема: Для комментирования нужно быть участником не канала,
а ГРУППЫ ОБСУЖДЕНИЯ (linked chat), которая привязана к каналу.
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
from telethon.tl.functions.messages import GetPeerDialogsRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    ChatWriteForbiddenError,
    InviteRequestSentError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount

# Каналы для проверки
CHANNELS = [
    "mspiridonov",
    "Oskar_Hartmann",
    "portnyaginlive",
    "Theedinorogblog",
    "sberstartup",
]


async def main():
    await init_db()

    print("=" * 70)
    print("PROVERKA I PODPISKA NA GRUPPY OBSUZHDENI")
    print("=" * 70)

    # Get Karina's account
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.phone == "+380954967658")
        )
        account = result.scalar_one_or_none()

        if not account:
            print("ERROR: Account Karina not found!")
            return

    print(f"Account: {account.first_name} ({account.phone})")
    print()

    # Connect
    client = TelegramClient(
        StringSession(account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )
    await client.connect()

    if not await client.is_user_authorized():
        print("ERROR: Account not authorized!")
        await client.disconnect()
        return

    for username in CHANNELS:
        print(f"\n--- @{username} ---")

        try:
            # Get channel entity
            channel = await client.get_entity(username)
            print(f"  Kanal: {channel.title}")

            # Get full channel info
            full = await client(GetFullChannelRequest(channel))
            linked_chat_id = full.full_chat.linked_chat_id

            if not linked_chat_id:
                print("  [!] Net gruppy obsuzhdenia (kommentarii zakryty)")
                continue

            print(f"  Linked chat ID: {linked_chat_id}")

            # Get discussion group entity
            try:
                discussion = await client.get_entity(linked_chat_id)
                print(f"  Gruppa: {discussion.title}")

                # Try to join discussion group
                try:
                    await client(JoinChannelRequest(discussion))
                    print("  [+] PRISOEDINILIS k gruppe!")
                    await asyncio.sleep(random.randint(30, 60))
                except InviteRequestSentError:
                    print("  [?] Zayavka na vstuplenie otpravlena (gruppa zakryta)")
                except Exception as e:
                    if "already" in str(e).lower() or "PARTICIPANT" in str(e).upper():
                        print("  [OK] Uzhe v gruppe")
                    else:
                        print(f"  [!] Ne udalos prisoedinitsya: {str(e)[:50]}")

                # Try sending test (will fail but shows error)
                # We don't actually send, just check

            except Exception as e:
                print(f"  [X] Ne mogu poluchit gruppu: {str(e)[:50]}")

        except FloodWaitError as e:
            print(f"  [X] FloodWait {e.seconds}s")
            await asyncio.sleep(e.seconds + 10)
        except Exception as e:
            print(f"  [X] Oshibka: {str(e)[:60]}")

        await asyncio.sleep(2)

    await client.disconnect()
    print("\n" + "=" * 70)
    print("GOTOVO")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
