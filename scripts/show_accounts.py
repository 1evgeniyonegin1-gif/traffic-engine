#!/usr/bin/env python
"""Показать все аккаунты в БД."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount


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

        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        accounts = result.scalars().all()

        print(f"Total accounts in DB: {len(accounts)}\n")

        for i, acc in enumerate(accounts, 1):
            print(f"{i}. {acc.first_name} {acc.last_name or ''} (@{acc.username})")
            print(f"   Phone: {acc.phone}")
            print(f"   Status: {acc.status}")
            print(f"   Warmup completed: {acc.warmup_completed}")
            print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
