#!/usr/bin/env python
"""
Upload avatars to accounts.
Only uploads avatars, doesn't touch channels or posts.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


PROFILES = {
    "+380954967658": "img.jpg",
    "+380955300455": "img (1).jpg",
    "+380955161146": "img (2).jpg",
}


async def main():
    print("\n=== UPLOAD AVATARS ===\n")

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID not configured!")
        sys.exit(1)

    await init_db()

    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.status.in_(["active", "warming"])
            )
        )
        accounts = result.scalars().all()

    if not accounts:
        logger.error("No accounts in database!")
        sys.exit(1)

    logger.info(f"Found {len(accounts)} accounts")

    for account in accounts:
        avatar_filename = PROFILES.get(account.phone)
        if not avatar_filename:
            logger.warning(f"No avatar for {account.phone}, skipping")
            continue

        avatar_path = Path(__file__).parent.parent / "avatars" / avatar_filename
        if not avatar_path.exists():
            logger.error(f"Avatar file not found: {avatar_path}")
            continue

        client = TelegramClient(
            StringSession(account.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                logger.error(f"{account.phone}: NOT authorized")
                continue

            me = await client.get_me()
            logger.info(f"Connected: {me.first_name} ({account.phone})")

            logger.info(f"Uploading avatar: {avatar_filename}")
            file = await client.upload_file(str(avatar_path))
            await client(UploadProfilePhotoRequest(file=file))
            logger.info(f"OK - Avatar uploaded for {account.phone}")

        except Exception as e:
            logger.error(f"Error for {account.phone}: {e}")
        finally:
            try:
                await client.disconnect()
            except:
                pass

        await asyncio.sleep(2)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
