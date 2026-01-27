#!/usr/bin/env python
"""Загрузить session strings из .session файлов в БД."""

import asyncio
import sys
import os
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount
from traffic_engine.config import settings


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

        # Получаем все аккаунты
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant.id)
        )
        accounts = result.scalars().all()

        print(f"Found {len(accounts)} accounts\n")

        for account in accounts:
            session_file = f"sessions/{account.phone}.session"

            if not os.path.exists(session_file):
                print(f"  ERROR {account.phone} - session file not found!")
                continue

            print(f"  Loading session for {account.phone}...")

            # Создаём временный клиент для чтения session string
            try:
                client = TelegramClient(
                    session_file.replace(".session", ""),
                    settings.telegram_api_id,
                    settings.telegram_api_hash
                )

                await client.connect()

                # Получаем session string
                session_string = StringSession.save(client.session)

                await client.disconnect()

                # Обновляем в БД
                account.session_string = session_string
                print(f"    OK Loaded {len(session_string)} chars")

            except Exception as e:
                print(f"    ERROR: {e}")

        await session.commit()
        print("\nAll sessions loaded!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
