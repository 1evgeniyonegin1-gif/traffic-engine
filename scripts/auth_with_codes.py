#!/usr/bin/env python
"""
Авторизация с готовыми кодами из переменных окружения.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from pyrogram import Client
from sqlalchemy import text

from traffic_engine.database import get_session
from traffic_engine.config import settings


# Коды для каждого аккаунта (замените на актуальные)
CODES = {
    "+998993466132": "12098",
    "+380954967658": "",  # Нужно получить
    "+380955161146": "",  # Нужно получить
    "+380955300455": "",  # Нужно получить
}


async def authorize_account(acc_id: int, phone: str, name: str, code: str):
    """Авторизовать аккаунт с кодом."""
    logger.info(f"Авторизация: {name} ({phone})")

    client = Client(
        name=f"auth_{phone}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=phone,
        in_memory=True,
    )

    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        logger.info(f"  Код отправлен")

        # Использовать код
        await client.sign_in(phone, sent_code.phone_code_hash, code)
        session_string = await client.export_session_string()

        # Сохранить в БД
        async with get_session() as db:
            await db.execute(
                text("UPDATE traffic_userbot_accounts SET session_string = :session WHERE id = :id"),
                {"session": session_string, "id": acc_id}
            )
            await db.commit()

        logger.success(f"  ✓ {name} авторизован!")
        await client.disconnect()
        return True

    except Exception as e:
        logger.error(f"  ✗ Ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False


async def main():
    logger.info("=" * 60)
    logger.info("АВТОРИЗАЦИЯ С КОДАМИ")
    logger.info("=" * 60)

    # Получить аккаунты
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, phone, first_name FROM traffic_userbot_accounts "
            "WHERE session_string = '' OR session_string IS NULL "
            "ORDER BY phone"
        ))
        accounts = list(result.fetchall())

    if not accounts:
        logger.info("Нет аккаунтов для авторизации")
        return

    logger.info(f"\nНайдено {len(accounts)} аккаунтов\n")

    # Авторизовать
    success = 0
    for acc_id, phone, name in accounts:
        code = CODES.get(phone, "")
        if not code:
            logger.warning(f"⚠ Нет кода для {name} ({phone}), пропускаем")
            continue

        if await authorize_account(acc_id, phone, name, code):
            success += 1
        await asyncio.sleep(2)

    logger.info("\n" + "=" * 60)
    logger.info(f"ГОТОВО: {success}/{len(accounts)}")
    logger.info("=" * 60)

    if success == len(accounts):
        logger.success("\n✓ Все аккаунты авторизованы!")
        logger.info("Запустите: systemctl start traffic-engine\n")


if __name__ == "__main__":
    asyncio.run(main())
