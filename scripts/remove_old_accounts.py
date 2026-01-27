#!/usr/bin/env python
"""Удалить старые аккаунты из БД."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount


# Номера старых аккаунтов для удаления
OLD_PHONES = [
    "+380954967658",
    "+380955300455",
    "+380955161146",
    "+998993466132",
]


async def main():
    await init_db()

    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("Tenant not found!")
            return

        # Находим старые аккаунты
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant.id,
                UserBotAccount.phone.in_(OLD_PHONES)
            )
        )
        old_accounts = result.scalars().all()

        if not old_accounts:
            print("No old accounts found!")
            return

        print(f"Found {len(old_accounts)} old accounts to remove:\n")
        for acc in old_accounts:
            print(f"  - {acc.phone} (@{acc.username or 'no_username'})")

        print("\nRemoving...")

        # Удаляем
        await session.execute(
            delete(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant.id,
                UserBotAccount.phone.in_(OLD_PHONES)
            )
        )
        await session.commit()

        print(f"\nRemoved {len(old_accounts)} accounts successfully!")

        # Показываем оставшиеся
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        remaining = result.scalars().all()

        print(f"\nRemaining accounts: {len(remaining)}\n")
        for acc in remaining:
            print(f"  - {acc.first_name} (@{acc.username}) - {acc.phone}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
