#!/usr/bin/env python
"""
Test Telethon sessions - проверка работоспособности сессий.

Этот скрипт проверяет:
1. Подключение к БД
2. Загрузку аккаунтов
3. Инициализацию Telethon клиентов
4. Авторизацию в Telegram
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
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import UserBotAccount, Tenant


async def test_accounts():
    """Тестируем все аккаунты."""
    logger.info("=== Testing Telethon Sessions ===")

    # Инициализируем БД
    await init_db()
    logger.info("Database initialized")

    # Получаем все аккаунты
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.status.in_(["active", "warming"])
            )
        )
        accounts = result.scalars().all()

        if not accounts:
            logger.error("No accounts found in database!")
            return

        logger.info(f"Found {len(accounts)} account(s)")

        # Тестируем каждый аккаунт
        for account in accounts:
            await test_single_account(account)
            await asyncio.sleep(2)  # Пауза между аккаунтами


async def test_single_account(account: UserBotAccount):
    """Тестируем один аккаунт."""
    logger.info(f"\n--- Testing account: {account.phone} ---")
    logger.info(f"Telegram ID: {account.telegram_id}")
    logger.info(f"Status: {account.status}")
    logger.info(f"Session string length: {len(account.session_string)} chars")

    try:
        # Создаём Telethon клиент
        client = TelegramClient(
            StringSession(account.session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        # Подключаемся
        await client.connect()
        logger.info("Connected to Telegram")

        # Проверяем авторизацию
        if not await client.is_user_authorized():
            logger.error("NOT AUTHORIZED! Session is invalid.")
            await client.disconnect()
            return

        # Получаем информацию о пользователе
        me = await client.get_me()
        logger.info(f"✓ Authorized as: {me.first_name} (@{me.username}) ID:{me.id}")

        # Проверяем соответствие ID
        if me.id != account.telegram_id:
            logger.warning(f"ID mismatch! DB: {account.telegram_id}, Actual: {me.id}")

        # Отключаемся
        await client.disconnect()
        logger.info(f"✓ Account {account.phone} - OK")

    except Exception as e:
        logger.error(f"✗ Account {account.phone} - ERROR: {e}")


async def main():
    """Main entry point."""
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="INFO",
    )

    await test_accounts()
    logger.info("\n=== Test completed ===")


if __name__ == "__main__":
    asyncio.run(main())
