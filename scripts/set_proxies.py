#!/usr/bin/env python
"""
Скрипт для добавления прокси к аккаунтам.

Использование:
    python scripts/set_proxies.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select

from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount


# Заполни прокси для каждого аккаунта
# Формат: telegram_id -> (type, host, port, username, password)
PROXY_CONFIG = {
    8460974753: ("socks5", "proxy1.example.com", 1080, "user1", "pass1"),
    8433781930: ("socks5", "proxy2.example.com", 1080, "user2", "pass2"),
    8499546801: ("socks5", "proxy3.example.com", 1080, "user3", "pass3"),
}


async def main():
    """Добавить прокси к аккаунтам."""
    logger.info("=== Добавление прокси к аккаунтам ===")

    async with get_session() as session:
        result = await session.execute(select(UserBotAccount))
        accounts = result.scalars().all()

        for account in accounts:
            proxy = PROXY_CONFIG.get(account.telegram_id)
            if proxy:
                account.proxy_type = proxy[0]
                account.proxy_host = proxy[1]
                account.proxy_port = proxy[2]
                account.proxy_username = proxy[3]
                account.proxy_password = proxy[4]
                logger.info(f"✅ {account.first_name} (ID:{account.telegram_id}) -> {proxy[1]}:{proxy[2]}")
            else:
                logger.warning(f"⚠️ {account.first_name} (ID:{account.telegram_id}) - прокси не задан")

        await session.commit()

    logger.info("=== Готово! ===")


if __name__ == "__main__":
    asyncio.run(main())
