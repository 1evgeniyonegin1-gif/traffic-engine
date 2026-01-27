#!/usr/bin/env python
"""
Set usernames for accounts so they have clickable profile links.
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
from telethon.tl.functions.account import UpdateUsernameRequest
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


USERNAME_CONFIG = {
    "+380954967658": "karina_free_lesson",
    "+380955300455": "kira_free_scheme",
    "+380955161146": "lyuba_free_guide",
}


def generate_username(base: str) -> str:
    """Generate unique username with random suffix."""
    suffix = ''.join(random.choices(string.digits, k=3))
    return f"{base}_{suffix}"


async def main():
    print("\n=== SET ACCOUNT USERNAMES ===\n")

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
        base_username = USERNAME_CONFIG.get(account.phone)
        if not base_username:
            logger.warning(f"No username config for {account.phone}, skipping")
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

            if me.username:
                logger.info(f"Already has username: @{me.username}")
                logger.info(f"Profile link: https://t.me/{me.username}")
                continue

            # Try to set username
            for attempt in range(5):
                username = generate_username(base_username)
                logger.info(f"Trying username: @{username}")
                try:
                    await client(UpdateUsernameRequest(username=username))
                    logger.info(f"OK - Username set: @{username}")
                    logger.info(f"Profile link: https://t.me/{username}")
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
