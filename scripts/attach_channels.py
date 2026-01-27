#!/usr/bin/env python
"""
Attach personal channels to account profiles.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdatePersonalChannelRequest
from telethon.tl.types import Channel, InputChannel
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


# Channel title keywords to match
CHANNEL_KEYWORDS = {
    "+380954967658": "карин",  # Урок от Карины
    "+380955300455": "кир",    # Схема от Киры
    "+380955161146": "люб",    # Гайд от Любы
}


async def main():
    print("\n=== ATTACH PERSONAL CHANNELS ===\n")

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
        keyword = CHANNEL_KEYWORDS.get(account.phone)
        if not keyword:
            logger.warning(f"No channel keyword for {account.phone}, skipping")
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

            # Find the channel
            target_channel = None
            async for dialog in client.iter_dialogs():
                if isinstance(dialog.entity, Channel):
                    title_lower = dialog.entity.title.lower()
                    if keyword in title_lower:
                        target_channel = dialog.entity
                        logger.info(f"Found channel: {dialog.entity.title}")
                        break

            if not target_channel:
                logger.error(f"Channel not found for {account.phone}")
                continue

            # Attach channel to profile
            logger.info(f"Attaching channel to profile...")
            try:
                input_channel = InputChannel(
                    channel_id=target_channel.id,
                    access_hash=target_channel.access_hash
                )
                await client(UpdatePersonalChannelRequest(channel=input_channel))
                logger.info(f"OK - Personal channel attached for {account.phone}")
            except Exception as e:
                logger.error(f"Failed to attach channel: {e}")

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
