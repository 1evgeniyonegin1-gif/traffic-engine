#!/usr/bin/env python
"""
Форсированная подписка аккаунтов на каналы.

Проблема: get_entity позволяет читать канал, но не гарантирует подписку.
Для комментирования в большинстве каналов нужно быть ПОДПИСАННЫМ.

Этот скрипт принудительно подписывает аккаунты через JoinChannelRequest.
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
from telethon.tl.types import ChannelParticipant
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    UserNotParticipantError,
    ChatAdminRequiredError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount, TargetChannel


async def is_subscribed(client: TelegramClient, channel_username: str) -> bool:
    """Check if the client is actually subscribed to the channel."""
    try:
        entity = await client.get_entity(channel_username)
        me = await client.get_me()

        # Try to get participant info
        participant = await client(GetParticipantRequest(
            channel=entity,
            participant=me
        ))
        return True
    except UserNotParticipantError:
        return False
    except Exception as e:
        logger.debug(f"Check subscription error: {e}")
        return False


async def force_join(client: TelegramClient, channel_username: str) -> tuple[bool, str]:
    """Force join a channel."""
    try:
        # First check if already subscribed
        if await is_subscribed(client, channel_username):
            return True, "already_subscribed"

        # Join the channel
        await client(JoinChannelRequest(channel_username))
        return True, "joined"

    except FloodWaitError as e:
        return False, f"flood_wait_{e.seconds}s"
    except ChannelPrivateError:
        return False, "private_channel"
    except UserBannedInChannelError:
        return False, "banned"
    except ChatAdminRequiredError:
        return False, "admin_required"
    except Exception as e:
        return False, str(e)[:50]


async def main():
    """Force join all accounts to all active channels."""
    await init_db()

    logger.info("=" * 70)
    logger.info("FORCE JOIN - PRINUDITELNAYA PODPISKA")
    logger.info("=" * 70)

    async with get_session() as session:
        # Get all active accounts
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.status == "active")
        )
        accounts = result.scalars().all()

        if not accounts:
            logger.error("Net aktivnyh akkauntov!")
            return

        # Get all active channels
        result = await session.execute(
            select(TargetChannel).where(TargetChannel.is_active == True)
        )
        channels = result.scalars().all()

        if not channels:
            logger.error("Net aktivnyh kanalov!")
            return

    logger.info(f"Akkauntov: {len(accounts)}")
    logger.info(f"Kanalov: {len(channels)}")
    logger.info("")

    # Stats
    total_joined = 0
    total_already = 0
    total_failed = 0

    for acc_idx, account in enumerate(accounts, 1):
        logger.info(f"\n[{acc_idx}/{len(accounts)}] Account: {account.first_name} ({account.phone})")

        # Connect
        client = TelegramClient(
            StringSession(account.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )
        await client.connect()

        if not await client.is_user_authorized():
            logger.error(f"  Account ne avtorizovan!")
            await client.disconnect()
            continue

        # Join each channel
        for ch_idx, channel in enumerate(channels, 1):
            logger.info(f"  [{ch_idx}/{len(channels)}] @{channel.username}...", end=" ")

            success, status = await force_join(client, channel.username)

            if success:
                if status == "already_subscribed":
                    print("[OK] uzhe podpisan")
                    total_already += 1
                else:
                    print("[+] PODPISAN!")
                    total_joined += 1
                    # Pause after joining (30-60 sec)
                    delay = random.randint(30, 60)
                    logger.info(f"      Zhdu {delay}s...")
                    await asyncio.sleep(delay)
            else:
                print(f"[X] {status}")
                total_failed += 1

                # If flood wait, pause
                if status.startswith("flood_wait"):
                    wait_time = int(status.split("_")[2].replace("s", ""))
                    logger.warning(f"      FloodWait! Zhdu {wait_time}s...")
                    await asyncio.sleep(wait_time + 10)

        await client.disconnect()

        # Pause between accounts (2-3 min)
        if acc_idx < len(accounts):
            delay = random.randint(120, 180)
            logger.info(f"\nPauza mezhdu akkauntami: {delay}s...\n")
            await asyncio.sleep(delay)

    # Summary
    print("\n" + "=" * 70)
    print("ITOGO")
    print("=" * 70)
    print(f"  [+] Novo podpisano:    {total_joined}")
    print(f"  [OK] Uzhe podpisany:   {total_already}")
    print(f"  [X] Oshibki:           {total_failed}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
