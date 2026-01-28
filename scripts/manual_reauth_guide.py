#!/usr/bin/env python
"""
Показывает пошаговую инструкцию для ручной реавторизации.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from traffic_engine.database import get_session


async def main():
    print("\n" + "=" * 80)
    print("ИНСТРУКЦИЯ ПО РЕАВТОРИЗАЦИИ")
    print("=" * 80)

    # Получить аккаунты
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, phone, first_name FROM traffic_userbot_accounts "
            "WHERE session_string = '' OR session_string IS NULL "
            "ORDER BY phone"
        ))
        accounts = result.fetchall()

    if not accounts:
        print("\n✓ Все аккаунты уже авторизованы!")
        return

    print(f"\nНужно авторизовать {len(accounts)} аккаунтов:")
    for i, (acc_id, phone, name) in enumerate(accounts, 1):
        print(f"  {i}. {name} - {phone}")

    print("\n" + "-" * 80)
    print("ШАГ 1: Подключитесь к серверу")
    print("-" * 80)
    print("\nСкопируйте и выполните:")
    print("\n  ssh root@194.87.86.103")

    print("\n" + "-" * 80)
    print("ШАГ 2: Запустите скрипт авторизации")
    print("-" * 80)
    print("\nСкопируйте и выполните:")
    print("\n  cd /opt/traffic-engine")
    print("  source venv/bin/activate")
    print("  python -c \"")
    print("import asyncio")
    print("from traffic_engine.channels.auth import authorize_single_account")

    for acc_id, phone, name in accounts:
        print(f"\nawait authorize_single_account({acc_id}, '{phone}', '{name}')")

    print("  \"")

    print("\n" + "-" * 80)
    print("ШАГ 3: Запустите систему")
    print("-" * 80)
    print("\n  systemctl start traffic-engine")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
