#!/usr/bin/env python
"""
Subscribe All Channels - Подписка всех аккаунтов на все каналы.

Этот скрипт подписывает все активные аккаунты на все целевые каналы.
Использует безопасные паузы чтобы избежать FloodWait.

Запуск:
    cd traffic-engine-mvp
    python scripts/subscribe_all_channels.py
"""

import asyncio
import random
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount, TargetChannel
from traffic_engine.core import AccountManager


async def subscribe_account_to_channels(
    account_manager: AccountManager,
    account: UserBotAccount,
    channels: list,
) -> dict:
    """
    Подписать один аккаунт на список каналов.

    Returns:
        dict с результатами: {success: [], failed: [], already: []}
    """
    results = {"success": [], "failed": [], "already": []}

    client = await account_manager.get_client(account.id)
    if not client:
        logger.error(f"Failed to get client for {account.phone}")
        return results

    if not client.is_connected():
        await client.connect()

    logger.info(f"📱 Processing account: {account.first_name} ({account.phone})")

    for channel in channels:
        if not channel.username:
            logger.warning(f"  ⚠️ Channel {channel.id} has no username, skipping")
            continue

        username = f"@{channel.username}" if not channel.username.startswith("@") else channel.username

        try:
            # Проверяем, подписаны ли уже
            try:
                entity = await client.get_entity(username)
                # Если get_entity работает без ошибки - можем читать канал
                results["already"].append(channel.username)
                logger.info(f"  ✓ Already can access {username}")
                continue
            except UserNotParticipantError:
                pass  # Нужно подписаться
            except ValueError:
                pass  # Нужно подписаться

            # Подписываемся
            await client(JoinChannelRequest(username))
            results["success"].append(channel.username)
            logger.info(f"  ✅ Joined {username}")

            # Пауза между подписками (30-60 сек)
            delay = random.randint(30, 60)
            logger.info(f"  ⏳ Waiting {delay}s...")
            await asyncio.sleep(delay)

        except FloodWaitError as e:
            logger.warning(f"  ⚠️ FloodWait {e.seconds}s for {username}")
            results["failed"].append((channel.username, f"FloodWait {e.seconds}s"))
            # Ждём FloodWait + буфер
            await asyncio.sleep(e.seconds + 10)

        except ChannelPrivateError:
            logger.warning(f"  ❌ Channel {username} is private")
            results["failed"].append((channel.username, "Private"))

        except UserBannedInChannelError:
            logger.error(f"  🚫 Account banned in {username}")
            results["failed"].append((channel.username, "Banned"))

        except Exception as e:
            logger.error(f"  ❌ Error joining {username}: {e}")
            results["failed"].append((channel.username, str(e)))

    return results


async def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("SUBSCRIBE ALL CHANNELS")
    logger.info("=" * 60)
    logger.info("")

    # Initialize database
    await init_db()

    async with get_session() as session:
        # Load active accounts
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.status == "active")
        )
        accounts = result.scalars().all()

        if not accounts:
            logger.error("No active accounts found!")
            return

        logger.info(f"Found {len(accounts)} active account(s)")

        # Load active channels
        result = await session.execute(
            select(TargetChannel).where(TargetChannel.is_active == True)
        )
        channels = result.scalars().all()

        if not channels:
            logger.error("No active channels found!")
            return

        logger.info(f"Found {len(channels)} active channel(s)")
        logger.info("")

        # Get tenant_id from first account
        tenant_id = accounts[0].tenant_id

        # Create account manager
        account_manager = AccountManager(tenant_id)
        await account_manager.initialize()

        # Process each account
        total_results = {"success": 0, "failed": 0, "already": 0}

        for account in accounts:
            results = await subscribe_account_to_channels(
                account_manager, account, channels
            )

            total_results["success"] += len(results["success"])
            total_results["failed"] += len(results["failed"])
            total_results["already"] += len(results["already"])

            # Большая пауза между аккаунтами (2-5 минут)
            if account != accounts[-1]:
                delay = random.randint(120, 300)
                logger.info(f"\n⏳ Waiting {delay // 60} min before next account...\n")
                await asyncio.sleep(delay)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✅ Successfully joined: {total_results['success']}")
        logger.info(f"✓ Already subscribed: {total_results['already']}")
        logger.info(f"❌ Failed: {total_results['failed']}")
        logger.info("")

        # Close account manager
        await account_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
