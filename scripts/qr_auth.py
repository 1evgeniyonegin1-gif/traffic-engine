#!/usr/bin/env python
"""
Авторизация через QR-код (не требует SMS).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from sqlalchemy import text

from traffic_engine.database import get_session
from traffic_engine.config import settings


async def authorize_with_qr(acc_id: int, phone: str, name: str):
    """Авторизация через QR-код."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Авторизация: {name} ({phone})")
    logger.info(f"{'='*60}")

    client = Client(
        name=f"qr_{phone}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=phone,
        in_memory=True,
    )

    try:
        await client.connect()

        # Попробовать авторизоваться через QR
        logger.info("Генерация QR-кода...")

        # Получить QR код
        qr_code = await client.sign_in_qr()

        logger.info("\n" + "="*60)
        logger.info("СКАНИРУЙТЕ QR-КОД В TELEGRAM:")
        logger.info("="*60)
        logger.info(qr_code.url)
        logger.info("\nОткройте Telegram > Settings > Devices > Link Desktop Device")
        logger.info("Отсканируйте QR-код выше")
        logger.info("="*60)

        # Ждать сканирования
        await qr_code.wait()

        logger.success(f"✓ QR-код отсканирован!")

        # Получить session string
        session_string = await client.export_session_string()

        # Сохранить в БД
        async with get_session() as db:
            await db.execute(
                text("UPDATE traffic_userbot_accounts SET session_string = :session WHERE id = :id"),
                {"session": session_string, "id": acc_id}
            )
            await db.commit()

        logger.success(f"✓ {name} авторизован через QR!")
        await client.disconnect()
        return True

    except Exception as e:
        logger.error(f"✗ Ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False


async def main():
    logger.info("=" * 60)
    logger.info("АВТОРИЗАЦИЯ ЧЕРЕЗ QR-КОД")
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
    logger.info("Приготовьте Telegram на телефоне для сканирования QR-кодов\n")

    # Авторизовать каждый
    success = 0
    for acc_id, phone, name in accounts:
        if await authorize_with_qr(acc_id, phone, name):
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
