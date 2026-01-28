#!/usr/bin/env python
"""
Отправить коды авторизации на все аккаунты.
Затем вручную запустите reauthorize_accounts.py на сервере.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text
from telethon import TelegramClient
from telethon.sessions import StringSession

from traffic_engine.database import get_session
from traffic_engine.config import settings


async def send_codes():
    """Отправить коды на все аккаунты."""
    logger.info("=== Отправка кодов авторизации ===\n")

    # Получить аккаунты
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT phone FROM traffic_userbot_accounts "
            "WHERE session_string = '' OR session_string IS NULL "
            "ORDER BY phone"
        ))
        phones = [row[0] for row in result.fetchall()]

    if not phones:
        logger.info("Нет аккаунтов для авторизации")
        return

    logger.info(f"Найдено {len(phones)} аккаунтов:\n")
    for phone in phones:
        logger.info(f"  {phone}")

    logger.info("\nОтправляю коды...\n")

    # Отправить коды
    for phone in phones:
        try:
            client = TelegramClient(
                StringSession(),
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
            )
            await client.connect()
            await client.send_code_request(phone)
            logger.success(f"Код отправлен на {phone}")
            await client.disconnect()
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка для {phone}: {e}")

    logger.success("\n=== Коды отправлены! ===")
    logger.info("Теперь подключитесь к серверу и запустите:")
    logger.info("  ssh root@194.87.86.103")
    logger.info("  cd /opt/traffic-engine && source venv/bin/activate")
    logger.info("  python scripts/reauthorize_accounts.py")


if __name__ == "__main__":
    asyncio.run(send_codes())
