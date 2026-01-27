#!/usr/bin/env python
"""
Добавить целевые каналы для автокомментирования.

Каналы для инфобизнеса (заработок, удалёнка, AI).
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from loguru import logger

from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, TargetChannel


# Целевые каналы для инфобизнеса (30 каналов)
CHANNELS = [
    # Тестовый
    {
        "username": "lentachold",
        "title": "Лента Холд",
        "priority": 10,
        "is_active": True,
    },

    # === Бизнес и предпринимательство (15) ===
    {
        "username": "startupoftheday",
        "title": "Стартап дня",
        "priority": 9,
        "is_active": True,
    },
    {
        "username": "mspiridonov",
        "title": "Максим Спиридонов",
        "priority": 9,
        "is_active": True,
    },
    {
        "username": "rybakovigor",
        "title": "Игорь Рыбаков",
        "priority": 9,
        "is_active": True,
    },
    {
        "username": "grebenukm",
        "title": "Михаил Гребенюк",
        "priority": 8,
        "is_active": True,
    },
    {
        "username": "temno",
        "title": "Тёмная сторона",
        "priority": 8,
        "is_active": True,
    },
    {
        "username": "bezsmuzi",
        "title": "Русский ИТ Бизнес",
        "priority": 8,
        "is_active": True,
    },
    {
        "username": "Salesnotes",
        "title": "Заметки продавца B2B",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "ikniga",
        "title": "Книги на миллион",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "business_theory",
        "title": "Теория Бизнеса",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "dnevnikbogacha",
        "title": "Дневник Предпринимателя",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "ventureStuff",
        "title": "Венчур по Понятиям",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "Theedinorogblog",
        "title": "The Edinorog",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "addmeto",
        "title": "Addmeto",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "freakbook",
        "title": "Freakbook",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "moneyhack",
        "title": "Moneyhack",
        "priority": 6,
        "is_active": True,
    },

    # === Мотивация и саморазвитие (10) ===
    {
        "username": "silaslovv",
        "title": "Сила Слов",
        "priority": 8,
        "is_active": True,
    },
    {
        "username": "motivator_tv",
        "title": "МОТИВАТОР",
        "priority": 8,
        "is_active": True,
    },
    {
        "username": "zhit_interesno",
        "title": "Жить Интересно!",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "guzenuk",
        "title": "Филипп Гузенюк",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "Le_kinzhal",
        "title": "Кинжал",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "stoicstrategy",
        "title": "StoicStrategy",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "chillosophy",
        "title": "Ирина Хакамада",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "goodhabits",
        "title": "Хорошие привычки",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "psychay",
        "title": "Чай с психологом",
        "priority": 5,
        "is_active": True,
    },
    {
        "username": "samorazvitiev",
        "title": "Психология Развития",
        "priority": 5,
        "is_active": True,
    },

    # === Заработок и финансы (5) ===
    {
        "username": "smartfin",
        "title": "SmartFin",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "hranidengi",
        "title": "Храни деньги",
        "priority": 7,
        "is_active": True,
    },
    {
        "username": "finside",
        "title": "Финансовая сторона",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "dnative",
        "title": "DNative",
        "priority": 6,
        "is_active": True,
    },
    {
        "username": "blogmilova",
        "title": "Ленивый маркетолог",
        "priority": 6,
        "is_active": True,
    },
]


async def get_channel_info(username: str):
    """Получить информацию о канале через Telethon."""
    from telethon import TelegramClient
    from traffic_engine.config import settings

    client = TelegramClient(
        "temp_session",
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    try:
        await client.connect()

        # Если не авторизован - пропускаем
        if not await client.is_user_authorized():
            return None

        try:
            entity = await client.get_entity(username)
            return {
                "channel_id": entity.id,
                "title": getattr(entity, "title", username),
                "username": username.replace("@", ""),
            }
        except Exception as e:
            logger.warning(f"Не удалось получить данные канала @{username}: {e}")
            return None

    finally:
        await client.disconnect()


async def main():
    """Добавить каналы в БД."""

    logger.info("=== Настройка целевых каналов ===\n")

    # Инициализация БД
    await init_db()
    logger.info("БД инициализирована")

    async with get_session() as session:
        # Находим тенанта
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            logger.error("Тенант 'infobusiness' не найден!")
            return

        logger.info(f"Тенант: {tenant.display_name}\n")

        # Добавляем каналы
        added = 0
        for ch_data in CHANNELS:
            username = ch_data["username"].replace("@", "")

            # Проверяем, есть ли уже
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.username == username
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(f"Канал @{username} уже существует - пропускаю")
                continue

            # Пытаемся получить channel_id из Telegram
            logger.info(f"Получаю данные канала @{username}...")
            info = await get_channel_info(username)

            if info:
                channel_id = info["channel_id"]
                title = info["title"]
                logger.success(f"  ID: {channel_id}, Название: {title}")
            else:
                # Если не получилось - используем временный ID
                channel_id = -100000000 - added  # Временный ID
                title = ch_data["title"]
                logger.warning(f"  Не удалось получить ID, использую временный: {channel_id}")

            # Создаём канал
            channel = TargetChannel(
                tenant_id=tenant.id,
                channel_id=channel_id,
                username=username,
                title=title,
                priority=ch_data["priority"],
                is_active=ch_data["is_active"],
            )

            session.add(channel)
            logger.success(f"Добавлен: @{username} (приоритет: {ch_data['priority']})")
            added += 1

        if added > 0:
            await session.commit()
            logger.success(f"\n✅ Добавлено каналов: {added}")
        else:
            logger.info("\n✅ Все каналы уже были добавлены")

        # Статистика
        result = await session.execute(
            select(TargetChannel).where(
                TargetChannel.tenant_id == tenant.id,
                TargetChannel.is_active == True,
            )
        )
        all_channels = result.scalars().all()

        logger.info(f"\nВсего активных каналов: {len(all_channels)}")

        # Группируем по категориям
        by_priority = {}
        for ch in all_channels:
            by_priority.setdefault(ch.priority, []).append(ch)

        for priority in sorted(by_priority.keys(), reverse=True):
            channels = by_priority[priority]
            logger.info(f"\n  Приоритет {priority} ({len(channels)} каналов):")
            for ch in channels[:5]:  # Показываем первые 5
                logger.info(f"    - @{ch.username}")
            if len(channels) > 5:
                logger.info(f"    ... и ещё {len(channels) - 5}")

        logger.info("\n✅ Готово! Запускайте: python run_auto_comments.py")


if __name__ == "__main__":
    asyncio.run(main())
