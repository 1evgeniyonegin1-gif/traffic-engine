#!/usr/bin/env python
"""
Add a new userbot account to Traffic Engine.

This script:
1. Authenticates with Telegram using phone number
2. Saves session string to database
3. Links account to a tenant
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from pyrogram import Client
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, Tenant


async def get_or_create_client(phone: str) -> Client:
    """Create Pyrogram client for authentication."""
    client = Client(
        name=f"account_{phone.replace('+', '')}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=phone,
        in_memory=True,
    )
    return client


async def select_tenant() -> int:
    """Show available tenants and let user select one."""
    async with get_session() as session:
        result = await session.execute(select(Tenant).where(Tenant.is_active == True))
        tenants = result.scalars().all()

        if not tenants:
            logger.error("No tenants found! Run init_db.py first.")
            sys.exit(1)

        print("\nДоступные тенанты:")
        for i, tenant in enumerate(tenants, 1):
            print(f"  {i}. {tenant.display_name} ({tenant.name})")

        while True:
            try:
                choice = int(input("\nВыберите тенант (номер): "))
                if 1 <= choice <= len(tenants):
                    return tenants[choice - 1].id
            except ValueError:
                pass
            print("Неверный выбор, попробуйте снова")


async def add_account():
    """Main function to add a new account."""
    print("=== Добавление нового userbot аккаунта ===\n")

    # Check API credentials
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error(
            "TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены!\n"
            "Получите их на https://my.telegram.org/apps\n"
            "И добавьте в .env файл."
        )
        sys.exit(1)

    # Select tenant
    tenant_id = await select_tenant()

    # Get phone number
    phone = input("\nВведите номер телефона (с +7): ").strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    # Check if account already exists
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.phone == phone)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.error(f"Аккаунт {phone} уже существует!")
            sys.exit(1)

    # Create client and authenticate
    print(f"\nАвторизация аккаунта {phone}...")
    print("Telegram отправит код подтверждения.\n")

    client = await get_or_create_client(phone)

    try:
        await client.start()

        # Get user info
        me = await client.get_me()
        session_string = await client.export_session_string()

        logger.info(f"Авторизация успешна! Пользователь: {me.first_name} (@{me.username})")

        # Get profile info
        first_name = input(f"\nИмя для профиля [{me.first_name}]: ").strip() or me.first_name
        last_name = input(f"Фамилия [{me.last_name or ''}]: ").strip() or me.last_name
        bio = input("Био (описание профиля): ").strip()

        # Save to database
        async with get_session() as session:
            account = UserBotAccount(
                tenant_id=tenant_id,
                phone=phone,
                session_string=session_string,  # TODO: encrypt this
                telegram_id=me.id,
                first_name=first_name,
                last_name=last_name,
                username=me.username,
                bio=bio,
                status="warming",  # New accounts start in warming status
            )
            session.add(account)
            await session.commit()

            logger.info(f"Аккаунт {phone} успешно добавлен!")

        print(f"""
=== Аккаунт добавлен! ===

Телефон: {phone}
Telegram ID: {me.id}
Username: @{me.username or 'нет'}
Статус: warming (прогрев)

Аккаунт будет в режиме прогрева {settings.warmup_days} дней.
После этого он перейдёт в режим active.

Не забудьте:
1. Установить аватарку
2. Заполнить био в Telegram
3. Подписаться на несколько каналов вручную
""")

    except Exception as e:
        logger.error(f"Ошибка авторизации: {e}")
        sys.exit(1)
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(add_account())
