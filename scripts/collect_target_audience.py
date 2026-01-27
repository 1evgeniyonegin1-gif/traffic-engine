#!/usr/bin/env python
"""
Быстрый сбор целевой аудитории из подписанных каналов.

Собирает подписчиков из target_channels и добавляет в target_audience.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select, text
from pyrogram import Client
from pyrogram.errors import FloodWait, ChannelPrivate, ChatAdminRequired
from traffic_engine.database import get_session
from traffic_engine.database.models import TargetChannel, TargetAudience, UserBotAccount
from traffic_engine.config import settings
import random


async def collect_from_channel(client: Client, channel: TargetChannel, tenant_id: int, limit: int = 200):
    """
    Собрать подписчиков из одного канала.

    Args:
        client: Pyrogram клиент
        channel: Канал для сбора
        tenant_id: ID тенанта
        limit: Макс кол-во подписчиков (для безопасности)
    """
    try:
        logger.info(f"Сбор ЦА из канала: {channel.title} (@{channel.username})")

        # Получить подписчиков
        collected = 0
        async for member in client.get_chat_members(channel.channel_id, limit=limit):
            if member.user.is_bot:
                continue

            # Добавить в БД
            async with get_session() as db:
                # Проверить что не существует
                result = await db.execute(
                    select(TargetAudience).where(
                        TargetAudience.user_id == member.user.id,
                        TargetAudience.tenant_id == tenant_id
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    continue

                # Создать запись
                audience = TargetAudience(
                    tenant_id=tenant_id,
                    user_id=member.user.id,
                    username=member.user.username,
                    first_name=member.user.first_name,
                    last_name=member.user.last_name,
                    source_type="channel_subscribers",
                    source_id=channel.channel_id,
                    source_name=channel.title,
                    quality_score=random.randint(60, 85),  # Базовый рандомный скор
                )
                db.add(audience)
                await db.commit()
                collected += 1

            # Небольшая задержка
            await asyncio.sleep(random.uniform(0.5, 1.5))

        logger.success(f"Собрано {collected} пользователей из {channel.title}")
        return collected

    except FloodWait as e:
        logger.warning(f"FloodWait {e.value}s на канале {channel.title}")
        return 0
    except (ChannelPrivate, ChatAdminRequired) as e:
        logger.error(f"Нет доступа к {channel.title}: {e}")
        return 0
    except Exception as e:
        logger.error(f"Ошибка сбора из {channel.title}: {e}")
        return 0


async def main():
    """Главная функция."""
    logger.info("=== Сбор целевой аудитории ===")

    # Получить активные каналы
    async with get_session() as db:
        result = await db.execute(
            select(TargetChannel).where(TargetChannel.is_active == True).limit(5)
        )
        channels = result.scalars().all()

    if not channels:
        logger.error("Нет активных каналов! Добавьте каналы через add_target_channels.py")
        return

    logger.info(f"Найдено {len(channels)} каналов для сбора ЦА")

    # Получить первый активный аккаунт
    async with get_session() as db:
        result = await db.execute(
            select(UserBotAccount).where(UserBotAccount.status == "active").limit(1)
        )
        account = result.scalar_one_or_none()

    if not account:
        logger.error("Нет активных аккаунтов! Добавьте аккаунты через add_account.py")
        return

    # Создать клиент
    client = Client(
        name=f"collector_{account.phone}",
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        session_string=account.session_string,
    )

    async with client:
        total = 0
        for channel in channels:
            count = await collect_from_channel(client, channel, account.tenant_id, limit=100)
            total += count

            # Задержка между каналами
            await asyncio.sleep(random.uniform(5, 10))

    logger.success(f"=== Сбор завершён! Всего собрано: {total} пользователей ===")

    # Показать статистику
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT COUNT(*) FROM traffic_target_audience WHERE quality_score >= 70"
        ))
        suitable = result.scalar()
        logger.info(f"Подходят для story viewing (score >= 70): {suitable}")


if __name__ == "__main__":
    asyncio.run(main())
