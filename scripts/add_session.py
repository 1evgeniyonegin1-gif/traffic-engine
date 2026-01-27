#!/usr/bin/env python
"""
Add userbot accounts from session strings.

Usage:
    python scripts/add_session.py
"""

import asyncio
import sys
from pathlib import Path

# Fix for Python 3.14 + Pyrogram
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from pyrogram import Client
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, Tenant


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


async def add_session_account(session_string: str, tenant_id: int, account_num: int) -> bool:
    """Add account from session string."""
    print(f"\n--- Добавление аккаунта #{account_num} ---")

    # Create client from session string
    client = Client(
        name=f"session_import_{account_num}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=session_string,
        in_memory=True,
    )

    try:
        await client.start()

        # Get user info
        me = await client.get_me()
        phone = me.phone_number or f"unknown_{me.id}"

        logger.info(f"Подключено: {me.first_name} (@{me.username}) ID:{me.id}")

        # Check if already exists
        async with get_session() as db_session:
            result = await db_session.execute(
                select(UserBotAccount).where(UserBotAccount.telegram_id == me.id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(f"Аккаунт {me.id} уже существует, пропускаем")
                return False

            # Save to database
            account = UserBotAccount(
                tenant_id=tenant_id,
                phone=phone if phone.startswith("+") else f"+{phone}",
                session_string=session_string,
                telegram_id=me.id,
                first_name=me.first_name or "User",
                last_name=me.last_name,
                username=me.username,
                bio="",
                status="warming",
            )
            db_session.add(account)
            await db_session.commit()

            logger.info(f"Аккаунт {me.first_name} (ID:{me.id}) добавлен!")
            return True

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return False
    finally:
        try:
            await client.stop()
        except:
            pass


async def main():
    """Main function."""
    print("=== Добавление аккаунтов из Session Strings ===\n")

    # Check API credentials
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены!")
        sys.exit(1)

    # Session strings to add
    sessions = [
        "40e4f8593f7adc802d06928b05b56ec9af93571d318d71192cec7d6acde3d4c6d0e12b296d3fbf3af154fda85bc60eef56809a2afafe82940d35dc558d30b6ac115ec364e46430006a2171858ff653ce91a9a04b114cb7df76951c0caa9150ca8df11bf7229a945ad424e5f5ce09c030a27e663fa44d07589d022d0b3b1b3f27b3210b08f80f303208a845a68324635f8071893ec9569c2f9e2dc5a583acfea3fbeb33cfaa71d8a50bbad47dfb7024fbbb78c5056f6f047ed687fb38166fe905bb9255eded797736c58a2072f8b20f551bd1114bf423d759380dd148172d8b71d56236be258cc394eb53d164d0a93c72a2e8ef71977aac780f4ac73869a38c77:2",
        "5737c9bd3c286c3c3c60b6566060fcb802af3d0e27d0842d63d06ed9b896dee640d3fa2e680f727af01f257c3d0c4af33f4d8191bec747c9c563500360b2f83b41265545efd78f76b39592f5540e0026ed4cf811f3fe29e26193aaaf67b60313a6b555971e0fbbd3c9b7cfecf4c14eae8395495865278aa29dcb064320fdb048edd495dcb70fb1293a225d79f73cc6afa180f9e15dd51ffe59314f836875c7e09838b3002185ea357e2b3349603cd465899ec27b1a0064a13e5897bc0f94d924a8cc9d02282d37af3950b5400edab776bcd1ea90f2f6f07a2aa245ba83be56affb94267375e6a021c7ff4cf5e29cc9d4650296d7a04ecc99fbde103785c6db7a:2",
        "68c522a3f43caf2b3b3c57d22193002211a22effe19cda2fa9efba24db3b1e0786460c471d77cccfd28f9ba18513fba86ab9b9916d431889f81dab7deb5ba41dd3da9bcb68161839cdfc99e9c01a8e3ffb1d06ac428770005b3754070bb9b1cd4145c113f7b261de4b8f5ac171daf991da847318cdb7d8585ed3656f5aa9424bd4af4584f4caaa9d921a16e9717e7730262446d075c69b2cd6f4652056bbbb4bb5cbb204812792a7b24a3d04eee48cc1d831e1bb2eba140c39b00c0840c4fc639eed8e0960fa956075111e8087e4e093c0f33d099dabe877994852106640134fc59ec2058430f55c13d2e2892be841f07881069f0fff7c45e3941598e797f363:2",
    ]

    print(f"Найдено {len(sessions)} session strings\n")

    # Select tenant
    tenant_id = await select_tenant()

    # Add each account
    success = 0
    for i, session_str in enumerate(sessions, 1):
        if await add_session_account(session_str, tenant_id, i):
            success += 1
        await asyncio.sleep(2)  # Small delay between accounts

    print(f"\n=== Готово! Добавлено {success}/{len(sessions)} аккаунтов ===")
    print("\nАккаунты в режиме прогрева (warming).")
    print("Система будет использовать их осторожно первые 7 дней.")


if __name__ == "__main__":
    asyncio.run(main())
