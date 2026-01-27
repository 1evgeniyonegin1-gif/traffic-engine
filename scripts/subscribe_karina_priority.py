#!/usr/bin/env python
"""
Подписка Карины на приоритетные каналы (5-7 шт).
Безопасно - небольшое количество подписок.
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
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount

# Приоритетные каналы (где чаще всего посты)
PRIORITY_CHANNELS = [
    "mspiridonov",      # Максим Спиридонов - частые посты
    "Oskar_Hartmann",   # Оскар Хартманн - частые посты
    "portnyaginlive",   # Портнягин
    "Theedinorogblog",  # Единорог
    "sberstartup",      # Сбер Стартап
]


async def is_subscribed(client: TelegramClient, channel_username: str) -> bool:
    """Check if subscribed."""
    try:
        entity = await client.get_entity(channel_username)
        me = await client.get_me()
        await client(GetParticipantRequest(channel=entity, participant=me))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        return False


async def main():
    await init_db()

    print("=" * 60)
    print("PODPISKA KARINY NA PRIORITETNYE KANALY")
    print("=" * 60)

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
    print(f"Kanalov: {len(PRIORITY_CHANNELS)}")
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

    joined = 0
    already = 0
    failed = 0

    for i, username in enumerate(PRIORITY_CHANNELS, 1):
        print(f"[{i}/{len(PRIORITY_CHANNELS)}] @{username}... ", end="", flush=True)

        try:
            # Check if already subscribed
            if await is_subscribed(client, username):
                print("[OK] uzhe podpisana")
                already += 1
                continue

            # Join
            await client(JoinChannelRequest(username))
            print("[+] PODPISANA!")
            joined += 1

            # Wait 45-90 sec between joins
            if i < len(PRIORITY_CHANNELS):
                delay = random.randint(45, 90)
                print(f"    Zhdu {delay}s...")
                await asyncio.sleep(delay)

        except FloodWaitError as e:
            print(f"[X] FloodWait {e.seconds}s")
            failed += 1
            await asyncio.sleep(e.seconds + 10)
        except ChannelPrivateError:
            print("[X] private")
            failed += 1
        except UserBannedInChannelError:
            print("[X] banned")
            failed += 1
        except Exception as e:
            print(f"[X] {str(e)[:40]}")
            failed += 1

    await client.disconnect()

    print()
    print("=" * 60)
    print("ITOGO:")
    print(f"  [+] Novo podpisano: {joined}")
    print(f"  [OK] Uzhe byli:     {already}")
    print(f"  [X] Oshibki:        {failed}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
