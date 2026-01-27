#!/usr/bin/env python
"""
Copy posts from TransformRepublic to our channels.
Copies EXACT content, only replacing bot links.
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


SOURCE_CHANNEL = "TransformRepublic"

# Bot links for each account (replace source link with these)
BOT_LINKS = {
    "+380954967658": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg",
    "+380955300455": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg1",
    "+380955161146": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg2",
}

# Source bot link to replace
SOURCE_BOT_LINK = "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_AriaDigaTT"

CHANNEL_KEYWORDS = {
    "+380954967658": "карин",
    "+380955300455": "кир",
    "+380955161146": "люб",
}


async def main():
    logger.info("=== COPY POSTS FROM TRANSFORM REPUBLIC ===")

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
        accounts = list(result.scalars().all())

    if not accounts:
        logger.error("No accounts in database!")
        sys.exit(1)

    logger.info(f"Found {len(accounts)} accounts")

    # Use first account to fetch source posts
    first_account = accounts[0]

    client = TelegramClient(
        StringSession(first_account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    await client.connect()

    if not await client.is_user_authorized():
        logger.error("First account not authorized!")
        sys.exit(1)

    # Fetch source posts
    logger.info(f"Fetching posts from @{SOURCE_CHANNEL}...")
    try:
        source_entity = await client.get_entity(SOURCE_CHANNEL)
        logger.info(f"Found source channel: {source_entity.title}")
    except Exception as e:
        logger.error(f"Cannot access source channel: {e}")
        await client.disconnect()
        sys.exit(1)

    source_posts = []
    async for message in client.iter_messages(source_entity, limit=20):
        if message.text or message.media:
            source_posts.append(message)

    # Reverse to get chronological order
    source_posts.reverse()
    logger.info(f"Found {len(source_posts)} posts to copy")

    await client.disconnect()

    # Create temp dir for media
    temp_dir = Path("temp_media")
    temp_dir.mkdir(exist_ok=True)

    # Copy to each account's channel
    for account in accounts:
        bot_link = BOT_LINKS.get(account.phone)
        keyword = CHANNEL_KEYWORDS.get(account.phone)

        if not bot_link or not keyword:
            logger.warning(f"No config for {account.phone}, skipping")
            continue

        logger.info(f"\n{'='*50}")
        logger.info(f"Processing {account.phone}")
        logger.info(f"{'='*50}")

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

            # Find target channel
            target_channel = None
            async for dialog in client.iter_dialogs():
                if isinstance(dialog.entity, Channel):
                    if keyword in dialog.entity.title.lower():
                        target_channel = dialog.entity
                        logger.info(f"Found target channel: {dialog.entity.title}")
                        break

            if not target_channel:
                logger.error(f"Target channel not found for {account.phone}")
                continue

            # Delete ALL old posts
            logger.info("Deleting old posts...")
            old_messages = []
            async for msg in client.iter_messages(target_channel, limit=100):
                old_messages.append(msg.id)

            if old_messages:
                await client.delete_messages(target_channel, old_messages)
                logger.info(f"Deleted {len(old_messages)} old posts")

            # Re-fetch source posts for each account (to download media fresh)
            source_client = TelegramClient(
                StringSession(account.session_string),
                settings.telegram_api_id,
                settings.telegram_api_hash
            )
            await source_client.connect()
            source_entity = await source_client.get_entity(SOURCE_CHANNEL)

            source_posts = []
            async for message in source_client.iter_messages(source_entity, limit=20):
                if message.text or message.media:
                    source_posts.append(message)
            source_posts.reverse()

            # Copy posts
            pinned_id = None
            for i, source_post in enumerate(source_posts):
                # Replace bot link in text
                text = source_post.text or ""
                if SOURCE_BOT_LINK in text:
                    text = text.replace(SOURCE_BOT_LINK, bot_link)

                # Send message with media if present
                if source_post.media:
                    try:
                        # Download media with timeout
                        media_path = await asyncio.wait_for(
                            source_client.download_media(
                                source_post,
                                file=str(temp_dir / f"media_{i}")
                            ),
                            timeout=30
                        )

                        if media_path:
                            # If text is too long for caption (>1024), send separately
                            if text and len(text) > 1024:
                                # Send text first
                                msg = await client.send_message(target_channel, text)
                                # Then send media without caption
                                await client.send_file(target_channel, media_path)
                            else:
                                msg = await client.send_file(
                                    target_channel,
                                    media_path,
                                    caption=text if text else None
                                )
                            # Clean up
                            try:
                                os.remove(media_path)
                            except:
                                pass
                        else:
                            if text:
                                msg = await client.send_message(target_channel, text)
                            else:
                                continue
                    except asyncio.TimeoutError:
                        logger.warning(f"Media download timeout for post {i+1}, sending text only")
                        if text:
                            msg = await client.send_message(target_channel, text)
                        else:
                            continue
                else:
                    if text:
                        msg = await client.send_message(target_channel, text)
                    else:
                        continue

                logger.info(f"Posted {i+1}/{len(source_posts)}")

                # First post will be pinned
                if i == 0:
                    pinned_id = msg.id

                await asyncio.sleep(0.5)

            await source_client.disconnect()

            # Pin first post
            if pinned_id:
                try:
                    await client.pin_message(target_channel, pinned_id)
                    logger.info("First post pinned")
                except Exception as e:
                    logger.warning(f"Could not pin: {e}")

            logger.info(f"Done with {account.phone}")

        except Exception as e:
            logger.error(f"Error for {account.phone}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                await client.disconnect()
            except:
                pass

        await asyncio.sleep(2)

    # Cleanup temp dir
    try:
        for f in temp_dir.iterdir():
            f.unlink()
        temp_dir.rmdir()
    except:
        pass

    logger.info("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
