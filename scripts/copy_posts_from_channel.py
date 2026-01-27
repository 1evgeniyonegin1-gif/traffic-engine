#!/usr/bin/env python
"""
Copy posts from source channel (TransformRepublic) to our channels.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, MessageMediaPhoto, MessageMediaDocument
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount


SOURCE_CHANNEL = "TransformRepublic"

# Bot links for each account
BOT_LINKS = {
    "+380954967658": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg",
    "+380955300455": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg1",
    "+380955161146": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg2",
}

CHANNEL_KEYWORDS = {
    "+380954967658": "карин",
    "+380955300455": "кир",
    "+380955161146": "люб",
}


async def get_source_posts(client):
    """Get all posts from source channel."""
    logger.info(f"Fetching posts from @{SOURCE_CHANNEL}...")

    try:
        entity = await client.get_entity(SOURCE_CHANNEL)
        logger.info(f"Found channel: {entity.title}")
    except Exception as e:
        logger.error(f"Cannot access source channel: {e}")
        return []

    posts = []
    async for message in client.iter_messages(entity, limit=50):
        if message.text or message.media:
            posts.append(message)
            logger.info(f"Post {message.id}: {message.text[:50] if message.text else '[media only]'}...")

    # Reverse to get chronological order (oldest first)
    posts.reverse()
    logger.info(f"Found {len(posts)} posts")
    return posts


async def main():
    print("\n=== COPY POSTS FROM TRANSFORM REPUBLIC ===\n")

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
    source_posts = await get_source_posts(client)

    if not source_posts:
        logger.error("No posts found in source channel!")
        await client.disconnect()
        sys.exit(1)

    # Print posts for review
    print("\n" + "="*60)
    print("POSTS FROM @TransformRepublic:")
    print("="*60)
    for i, post in enumerate(source_posts, 1):
        print(f"\n--- Post {i} ---")
        if post.text:
            print(post.text)
        if post.media:
            print(f"[Has media: {type(post.media).__name__}]")
        print()

    await client.disconnect()

    # Ask for confirmation
    print("="*60)
    proceed = input("\nCopy these posts to all 3 channels? (y/n): ")
    if proceed.lower() != 'y':
        print("Cancelled.")
        return

    # Now copy to each account's channel
    for account in accounts:
        bot_link = BOT_LINKS.get(account.phone)
        keyword = CHANNEL_KEYWORDS.get(account.phone)

        if not bot_link or not keyword:
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

            logger.info(f"Connected: {account.phone}")

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

            # Delete old posts first
            logger.info("Deleting old posts...")
            old_messages = []
            async for msg in client.iter_messages(target_channel, limit=100):
                old_messages.append(msg.id)

            if old_messages:
                await client.delete_messages(target_channel, old_messages)
                logger.info(f"Deleted {len(old_messages)} old posts")

            # Copy posts
            pinned_id = None
            for i, source_post in enumerate(source_posts):
                # Replace bot link in text
                text = source_post.text or ""

                # Replace any bot links with our link
                if "t.me/" in text and "bot" in text.lower():
                    # Find and replace bot link
                    import re
                    text = re.sub(
                        r'https?://t\.me/\S+bot\S*',
                        bot_link,
                        text,
                        flags=re.IGNORECASE
                    )

                # If no link was replaced but post looks like it should have one
                if bot_link not in text and ("забир" in text.lower() or "жми" in text.lower() or "переход" in text.lower()):
                    text = text + f"\n\n{bot_link}"

                # Send message
                if source_post.media:
                    # Download and re-upload media
                    media_path = await client.download_media(source_post, file="temp_media")
                    if media_path:
                        msg = await client.send_file(
                            target_channel,
                            media_path,
                            caption=text
                        )
                        # Clean up
                        Path(media_path).unlink(missing_ok=True)
                    else:
                        msg = await client.send_message(target_channel, text)
                else:
                    msg = await client.send_message(target_channel, text)

                logger.info(f"Posted {i+1}/{len(source_posts)}")

                # First post will be pinned
                if i == 0:
                    pinned_id = msg.id

                await asyncio.sleep(1)

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

        await asyncio.sleep(3)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
