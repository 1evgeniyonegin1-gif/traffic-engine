#!/usr/bin/env python
"""
Автоматическая реавторизация БЕЗ интерактивного ввода.
Использует коды из переменных окружения.

Использование:
  export CODE1=12345 CODE2=23456 CODE3=34567 CODE4=45678
  python scripts/auto_reauth.py
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


async def authorize_with_code(acc_id: int, phone: str, name: str, code: str):
    """Авторизовать аккаунт с готовым кодом."""
    logger.info(f"Авторизация: {name} ({phone})")

    client = Client(
        name=f"auto_{phone}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=phone,
        in_memory=True,
    )

    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        logger.info(f"  Код отправлен на {phone}")

        # Использовать код из параметра
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
    logger.info("АВТОМАТИЧЕСКАЯ РЕАВТОРИЗАЦИЯ")
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

    # Проверить коды в переменных окружения
    codes = []
    for i in range(1, len(accounts) + 1):
        code = os.getenv(f"CODE{i}")
        if not code:
            logger.error(f"\nОшибка: Не найдена переменная CODE{i}!")
            logger.info("\nИспользование:")
            logger.info("  export CODE1=xxxxx CODE2=xxxxx CODE3=xxxxx CODE4=xxxxx")
            logger.info("  python scripts/auto_reauth.py")
            return
        codes.append(code)

    logger.info(f"\nНайдено {len(accounts)} аккаунтов и {len(codes)} кодов\n")

    # Авторизовать все
    success = 0
    for (acc_id, phone, name), code in zip(accounts, codes):
        if await authorize_with_code(acc_id, phone, name, code):
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
