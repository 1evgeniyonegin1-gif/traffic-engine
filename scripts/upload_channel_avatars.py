#!/usr/bin/env python
"""
Upload avatars to channels.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditPhotoRequest
from telethon.tl.types import Channel, InputChatUploadedPhoto
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


CHANNEL_CONFIG = {
    "+380954967658": {"keyword": "карин", "avatar": "img.jpg"},
    "+380955300455": {"keyword": "кир", "avatar": "img (1).jpg"},
    "+380955161146": {"keyword": "люб", "avatar": "img (2).jpg"},
}


async def main():
    print("\n=== UPLOAD CHANNEL AVATARS ===\n")

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
        config = CHANNEL_CONFIG.get(account.phone)
        if not config:
            logger.warning(f"No config for {account.phone}, skipping")
            continue

        avatar_path = Path(__file__).parent.parent / "avatars" / config["avatar"]
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
            logger.info(f"Connected: {account.phone}")

            # Find the channel
            target_channel = None
            async for dialog in client.iter_dialogs():
                if isinstance(dialog.entity, Channel):
                    title_lower = dialog.entity.title.lower()
                    if config["keyword"] in title_lower:
                        target_channel = dialog.entity
                        logger.info(f"Found channel: {dialog.entity.title}")
                        if dialog.entity.username:
                            logger.info(f"Channel link: https://t.me/{dialog.entity.username}")
                        break

            if not target_channel:
                logger.error(f"Channel not found for {account.phone}")
                continue

            # Upload avatar to channel
            logger.info(f"Uploading avatar to channel: {config['avatar']}")
            try:
                file = await client.upload_file(str(avatar_path))
                await client(EditPhotoRequest(
                    channel=target_channel,
                    photo=InputChatUploadedPhoto(file=file)
                ))
                logger.info(f"OK - Channel avatar uploaded!")
            except Exception as e:
                logger.error(f"Failed to upload channel avatar: {e}")

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
