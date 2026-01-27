#!/usr/bin/env python
"""
Make channels public by setting usernames.
Then attach them to profiles.
"""

import asyncio
import sys
import random
import string
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import UpdateUsernameRequest
from telethon.tl.functions.account import UpdatePersonalChannelRequest
from telethon.tl.types import Channel, InputChannel
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


# Channel config: keyword to find, desired username prefix
CHANNEL_CONFIG = {
    "+380954967658": {"keyword": "карин", "username": "urok_karina"},
    "+380955300455": {"keyword": "кир", "username": "shema_kira"},
    "+380955161146": {"keyword": "люб", "username": "gaid_lyuba"},
}


def generate_username(base: str) -> str:
    """Generate unique username with random suffix."""
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"{base}_{suffix}"


async def main():
    print("\n=== MAKE CHANNELS PUBLIC & ATTACH ===\n")

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
                    if config["keyword"] in title_lower:
                        target_channel = dialog.entity
                        logger.info(f"Found channel: {dialog.entity.title}")
                        break

            if not target_channel:
                logger.error(f"Channel not found for {account.phone}")
                continue

            # Try to set username (make public)
            if not target_channel.username:
                logger.info("Channel is private, making it public...")

                for attempt in range(5):
                    username = generate_username(config["username"])
                    logger.info(f"Trying username: @{username}")
                    try:
                        await client(UpdateUsernameRequest(
                            channel=target_channel,
                            username=username
                        ))
                        logger.info(f"OK - Channel is now public: @{username}")
                        # Update channel info
                        target_channel = await client.get_entity(target_channel.id)
                        break
                    except Exception as e:
                        if "USERNAME_OCCUPIED" in str(e):
                            logger.warning(f"Username @{username} is taken, trying another...")
                            continue
                        else:
                            logger.error(f"Failed to set username: {e}")
                            break
                else:
                    logger.error("Could not find available username after 5 attempts")
                    continue
            else:
                logger.info(f"Channel already public: @{target_channel.username}")

            # Attach channel to profile
            logger.info(f"Attaching channel to profile...")
            try:
                input_channel = InputChannel(
                    channel_id=target_channel.id,
                    access_hash=target_channel.access_hash
                )
                await client(UpdatePersonalChannelRequest(channel=input_channel))
                logger.info(f"OK - Personal channel attached!")
                logger.info(f"Channel: https://t.me/{target_channel.username}")
            except Exception as e:
                logger.error(f"Failed to attach channel: {e}")

        except Exception as e:
            logger.error(f"Error for {account.phone}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                await client.disconnect()
            except:
                pass

        await asyncio.sleep(3)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
