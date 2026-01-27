#!/usr/bin/env python
"""
Автоматически присоединиться к discussion groups всех активных каналов.

Discussion groups нужны для комментирования в некоторых каналах.
"""

import asyncio
import sys
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from pyrogram import Client
from pyrogram.errors import FloodWait, UserAlreadyParticipant, ChannelPrivate

from traffic_engine.database import get_session
from traffic_engine.database.models import TargetChannel, UserBotAccount
from traffic_engine.config import settings


async def join_discussion_group(client: Client, channel_id: int, channel_title: str):
    """Присоединиться к discussion group канала."""
    try:
        # Получить канал
        channel = await client.get_chat(channel_id)

        # Проверить есть ли linked discussion group
        if not channel.linked_chat:
            logger.info(f"  {channel_title}: нет discussion group")
            return False

        discussion_id = channel.linked_chat.id
        logger.info(f"  {channel_title}: найдена discussion group {discussion_id}")

        # Присоединиться
        try:
            await client.join_chat(discussion_id)
            logger.success(f"  {channel_title}: успешно присоединились!")
            return True
        except UserAlreadyParticipant:
            logger.info(f"  {channel_title}: уже участник")
            return True

    except ChannelPrivate:
        logger.warning(f"  {channel_title}: канал приватный, не можем присоединиться")
        return False
    except FloodWait as e:
        logger.warning(f"  {channel_title}: FloodWait {e.value}s")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        error_str = str(e).encode('ascii', 'ignore').decode('ascii')
        logger.error(f"  {channel_title}: ошибка - {error_str[:100]}")
        return False


async def main():
    """Главная функция."""
    logger.info("=== Автоматическое присоединение к Discussion Groups ===")

    # Получить активные каналы
    async with get_session() as db:
        result = await db.execute(
            select(TargetChannel).where(TargetChannel.is_active == True)
        )
        channels = result.scalars().all()

    if not channels:
        logger.error("Нет активных каналов!")
        return

    logger.info(f"Найдено {len(channels)} активных каналов")

    # Получить первый активный аккаунт
    async with get_session() as db:
        result = await db.execute(
            select(UserBotAccount).where(UserBotAccount.status == "active").limit(1)
        )
        account = result.scalar_one_or_none()

    if not account:
        logger.error("Нет активных аккаунтов!")
        return

    logger.info(f"Используем аккаунт: {account.first_name} ({account.phone})")

    # Создать клиент
    client = Client(
        name=f"discussion_joiner_{account.phone}",
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        session_string=account.session_string,
    )

    async with client:
        joined = 0
        for channel in channels:
            result = await join_discussion_group(client, channel.channel_id, channel.title)
            if result:
                joined += 1

            # Задержка между каналами для безопасности
            await asyncio.sleep(random.uniform(3, 7))

    logger.success(f"=== Готово! Присоединились к {joined} discussion groups ===")


if __name__ == "__main__":
    asyncio.run(main())
