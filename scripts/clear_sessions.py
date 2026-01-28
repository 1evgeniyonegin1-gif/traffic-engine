#!/usr/bin/env python
"""
Очистка сессий Telethon в базе данных.
После этого нужно будет реавторизовать все аккаунты.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text

from traffic_engine.database import get_session


async def main():
    logger.info("=== Очистка сессий Telethon ===")

    async with get_session() as db:
        # Получить список аккаунтов
        result = await db.execute(text(
            "SELECT id, phone, first_name FROM traffic_userbot_accounts"
        ))
        accounts = result.fetchall()

        logger.info(f"Найдено {len(accounts)} аккаунтов")

        for acc_id, phone, name in accounts:
            logger.info(f"  {name} ({phone})")

        # Подтверждение
        logger.warning("ВНИМАНИЕ: Это удалит все session_string из базы!")
        logger.warning("После этого нужно будет реавторизовать все аккаунты.")

        # Очистить session_string
        await db.execute(text(
            "UPDATE traffic_userbot_accounts SET session_string = ''"
        ))
        await db.commit()

        logger.success(f"Очищены сессии для {len(accounts)} аккаунтов")
        logger.info("Теперь запустите скрипт реавторизации:")
        logger.info("  python scripts/reauthorize_accounts.py")


if __name__ == "__main__":
    asyncio.run(main())
