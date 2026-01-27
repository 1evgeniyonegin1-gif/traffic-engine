#!/usr/bin/env python
"""
Добавление целевых каналов для мониторинга.

Каналы по темам: бизнес, заработок, мотивация, саморазвитие.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import TargetChannel, Tenant, UserBotAccount


# Список каналов для мониторинга
# Формат: (username, title, comment_strategy)
# ПРОВЕРЕНО 23.01.2026 - только каналы с открытыми комментариями!
TARGET_CHANNELS = [
    # === Бизнес и предпринимательство (14) ===
    ("ikniga", "Книги на миллион", "supportive"),           # 923K подп.
    ("grebenukm", "Михаил Гребенюк", "smart"),              # 282K подп.
    ("portnyaginlive", "Дима Портнягин", "supportive"),     # 103K подп.
    ("oskar_hartmann", "Оскар Хартманн", "smart"),          # 88K подп.
    ("addmeto", "addmeto", "supportive"),                   # 74K подп.
    ("mspiridonov", "Максим Спиридонов", "supportive"),     # 63K подп.
    ("sberstartup", "СберСтартап", "smart"),                # 62K подп.
    ("startupoftheday", "Стартап дня", "smart"),            # 60K подп.
    ("Theedinorogblog", "The Edinorog", "smart"),           # 40K подп.
    ("kutergin_on_fire", "Кутергин в огне", "smart"),       # 40K подп.
    ("bezsmuzi", "Русский ИТ бизнес", "expert"),            # 26K подп.
    ("dindex", "Индекс дятла", "smart"),                    # 24K подп.
    ("ventureStuff", "Венчур по Понятиям", "expert"),       # 18K подп.
    ("pisarevich", "Ночной Писаревский", "smart"),          # 16K подп.

    # === Карьера и работа (4) ===
    ("careerspace", "careerspace", "supportive"),           # 139K подп.
    ("normrabota", "Норм работа", "supportive"),            # 111K подп.
    ("morejobs", "Больше джобсов", "supportive"),           # 65K подп.
    ("Salesnotes", "Заметки продавца B2B", "expert"),       # 16K подп.

    # === Мотивация и саморазвитие (6) ===
    ("silaslovv", "Сила Слов", "supportive"),               # 120K подп.
    ("anettaorlova", "Анетта Орлова", "supportive"),        # 42K подп.
    ("guzenuk", "Филипп Гузенюк", "smart"),                 # 22K подп.
    ("stoicstrategy", "StoicStrategy", "smart"),            # 19K подп.
    ("psychay", "Чай с психологом", "supportive"),          # 5K подп.
    ("productradar_official", "Product Radar", "smart"),    # 14K подп.

    # === Маркетинг и SMM (6) ===
    ("prostoecon", "Простая экономика", "expert"),          # 202K подп.
    ("marketpsy", "Психология Маркетинга", "smart"),        # 187K подп.
    ("dnative", "DNative — SMM", "expert"),                 # 64K подп.
    ("c_behavior", "Потребительское поведение", "expert"),  # 9K подп.
    ("sosindex", "Sosindex", "smart"),                      # 7K подп.
    ("blogmilova", "Ленивый маркетолог", "smart"),          # 2K подп.
]

TENANT_NAME = "infobusiness"


async def get_channel_info(client: TelegramClient, username: str) -> dict | None:
    """Получить информацию о канале через Telethon."""
    try:
        entity = await client.get_entity(username)
        return {
            "channel_id": entity.id,
            "title": entity.title if hasattr(entity, 'title') else username,
            "username": entity.username,
        }
    except Exception as e:
        logger.warning(f"Could not get info for @{username}: {e}")
        return None


async def main():
    """Добавить каналы в базу данных."""
    logger.info("=== Добавление целевых каналов ===")
    logger.info(f"Всего каналов: {len(TARGET_CHANNELS)}")

    # Получаем tenant
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error(f"Tenant '{TENANT_NAME}' не найден!")
            return

        tenant_id = tenant.id
        logger.info(f"Tenant ID: {tenant_id}")

        # Получаем первый аккаунт для проверки каналов
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant_id,
                UserBotAccount.status.in_(["active", "warming"])
            ).limit(1)
        )
        account = result.scalar_one_or_none()

        if not account:
            logger.error("Нет активных аккаунтов для проверки каналов!")
            return

    # Подключаемся через Telethon
    client = TelegramClient(
        StringSession(account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Аккаунт не авторизован!")
        await client.disconnect()
        return

    logger.info(f"Подключились как: {account.first_name}")

    added = 0
    skipped = 0
    failed = 0

    async with get_session() as session:
        for username, title, strategy in TARGET_CHANNELS:
            # Проверяем, не добавлен ли уже
            result = await session.execute(
                select(TargetChannel).where(TargetChannel.username == username)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(f"⏭️ @{username} уже добавлен")
                skipped += 1
                continue

            # Получаем информацию о канале
            info = await get_channel_info(client, username)

            if not info:
                logger.warning(f"❌ @{username} - не найден или недоступен")
                failed += 1
                await asyncio.sleep(2)
                continue

            # Добавляем канал
            channel = TargetChannel(
                tenant_id=tenant_id,
                channel_id=info["channel_id"],
                username=info["username"] or username,
                title=info["title"] or title,
                is_active=True,
                priority=5,
                comment_strategy=strategy,
                max_delay_minutes=10,
                skip_ads=True,
                skip_reposts=True,
                min_post_length=100,
            )
            session.add(channel)
            logger.info(f"✅ @{username} ({info['title']}) - добавлен")
            added += 1

            # Небольшая задержка между запросами
            await asyncio.sleep(3)

        await session.commit()

    await client.disconnect()

    logger.info("=" * 50)
    logger.info(f"Добавлено: {added}")
    logger.info(f"Пропущено (уже есть): {skipped}")
    logger.info(f"Не найдено: {failed}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
