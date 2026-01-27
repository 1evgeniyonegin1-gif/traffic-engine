#!/usr/bin/env python
"""
Get Telegram IDs and profile links for all accounts.
Simple script to check accounts without making any changes.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


async def main():
    """Get info for all accounts."""
    print("\n=== ACCOUNT INFO ===\n")

    # Check API credentials
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены в .env!")
        sys.exit(1)

    # Initialize database
    await init_db()

    # Get accounts
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.status.in_(["active", "warming"])
            )
        )
        accounts = result.scalars().all()

    if not accounts:
        logger.error("Нет аккаунтов в базе!")
        sys.exit(1)

    print(f"Найдено {len(accounts)} аккаунтов\n")
    print("-" * 70)

    for account in accounts:
        client = TelegramClient(
            StringSession(account.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print(f"[ERROR] {account.phone}: NOT authorized")
                continue

            me = await client.get_me()
            username = f"@{me.username}" if me.username else "no username"

            print(f"""
[OK] {account.phone}
   Name: {me.first_name} {me.last_name or ''}
   ID: {me.id}
   Username: {username}
   Link: https://t.me/user?id={me.id}
   DB Status: {account.status}
""")

        except Exception as e:
            print(f"[ERROR] {account.phone}: {e}")
        finally:
            try:
                await client.disconnect()
            except:
                pass

    print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())
