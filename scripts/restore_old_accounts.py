#!/usr/bin/env python
"""Восстановить старые 4 аккаунта (для которых есть sessions)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount


# СТАРЫЕ 4 аккаунта (для которых ЕСТЬ .session файлы)
OLD_ACCOUNTS = [
    {
        "phone": "+380954967658",
        "username": "karina_free_lesson_636",
        "first_name": "Карина",
        "last_name": None,
        "bio": "бесплатный урок",
    },
    {
        "phone": "+380955300455",
        "username": "kira_free_scheme_209",
        "first_name": "Кира",
        "last_name": None,
        "bio": "бесплатная схема",
    },
    {
        "phone": "+380955161146",
        "username": "lyuba_free_guide_871",
        "first_name": "Люба",
        "last_name": None,
        "bio": "бесплатный гайд",
    },
    {
        "phone": "+998993466132",
        "username": "lemonlime192",
        "first_name": "Лёша",
        "last_name": "Лаймов",
        "bio": "кислый, но полезный",
    },
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

        print(f"Tenant: {tenant.display_name}\n")

        # Удаляем все текущие аккаунты
        print("Removing current accounts...")
        await session.execute(
            delete(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        await session.commit()
        print("Removed!\n")

        # Добавляем старые 4 аккаунта
        print("Adding old 4 accounts...\n")
        for acc_data in OLD_ACCOUNTS:
            account = UserBotAccount(
                tenant_id=tenant.id,
                phone=acc_data["phone"],
                session_string="",  # Заполним позже из .session файлов
                username=acc_data["username"],
                first_name=acc_data["first_name"],
                last_name=acc_data.get("last_name"),
                bio=acc_data.get("bio"),
                status="warming",
                warmup_completed=False,
            )
            session.add(account)
            print(f"  + {acc_data['first_name']} (@{acc_data['username']}) - {acc_data['phone']}")

        await session.commit()
        print(f"\nAdded {len(OLD_ACCOUNTS)} accounts successfully!")

        # Показываем итог
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        accounts = result.scalars().all()

        print(f"\nTotal accounts: {len(accounts)}\n")
        for acc in accounts:
            print(f"  - {acc.first_name} (@{acc.username}) - {acc.phone}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
