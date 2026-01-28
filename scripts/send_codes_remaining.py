#!/usr/bin/env python
"""
Отправить коды только на оставшиеся 3 аккаунта.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession

from traffic_engine.config import settings


# Оставшиеся 3 аккаунта (у которых сессия недействительна)
PHONES = [
    "+380954967658",  # Карина
    "+380955161146",  # Люба
    "+380955300455",  # Кира
]


async def send_codes():
    """Отправить коды."""
    logger.info("Отправка кодов на 3 аккаунта...\n")

    for phone in PHONES:
        try:
            client = TelegramClient(
                StringSession(),
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
            )
            await client.connect()
            await client.send_code_request(phone)
            logger.success(f"✓ Код отправлен на {phone}")
            await client.disconnect()
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"✗ Ошибка для {phone}: {e}")

    logger.success("\n=== Коды отправлены! ===")
    logger.info("Проверьте на сервисе кнопку 'Получить код для входа'")


if __name__ == "__main__":
    asyncio.run(send_codes())
