#!/usr/bin/env python
"""
Простая реавторизация через Pyrogram.
Просто запустите на сервере, коды придут в Telegram.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from pyrogram import Client
from sqlalchemy import text

from traffic_engine.database import get_session
from traffic_engine.config import settings


async def main():
    """Реавторизация всех аккаунтов."""
    logger.info("=" * 60)
    logger.info("РЕАВТОРИЗАЦИЯ АККАУНТОВ")
    logger.info("=" * 60)
    logger.info("")

    # Получить аккаунты
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, phone, first_name FROM traffic_userbot_accounts "
            "WHERE session_string = '' OR session_string IS NULL "
            "ORDER BY phone"
        ))
        accounts = result.fetchall()

    if not accounts:
        logger.info("Нет аккаунтов для авторизации")
        return

    logger.info(f"Найдено {len(accounts)} аккаунтов:\n")
    for acc_id, phone, name in accounts:
        logger.info(f"  {name} - {phone}")

    logger.info("\nКоды придут в Telegram на эти номера")
    logger.info("Приготовьтесь вводить коды!")
    logger.info("Начинаем...\n")

    # Авторизовать каждый
    success = 0
    for acc_id, phone, name in accounts:
        logger.info("\n" + "=" * 60)
        logger.info(f"Аккаунт: {name} ({phone})")
        logger.info("=" * 60)

        # Создать клиент Pyrogram
        client = Client(
            name=f"reauth_{phone}",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
            phone_number=phone,
            in_memory=True,
        )

        try:
            await client.connect()

            # Отправить код
            sent_code = await client.send_code(phone)
            logger.success(f"Код отправлен на {phone}!")

            # Попросить ввести код
            code = input(f"\nВведите код для {name} ({phone}): ")

            # Войти
            await client.sign_in(phone, sent_code.phone_code_hash, code)

            # Получить session string
            session_string = await client.export_session_string()

            # Сохранить в БД
            async with get_session() as db:
                await db.execute(
                    text("UPDATE traffic_userbot_accounts SET session_string = :session WHERE id = :id"),
                    {"session": session_string, "id": acc_id}
                )
                await db.commit()

            logger.success(f"✓ {name} авторизован!\n")
            success += 1

            await client.disconnect()
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"✗ Ошибка для {name}: {e}\n")
            try:
                await client.disconnect()
            except:
                pass

    logger.info("\n" + "=" * 60)
    logger.info(f"ГОТОВО: {success}/{len(accounts)} аккаунтов авторизовано")
    logger.info("=" * 60)

    if success == len(accounts):
        logger.success("\n✓ Все аккаунты готовы!")
        logger.info("Запустите систему: systemctl start traffic-engine\n")
    else:
        logger.warning(f"\n✗ Авторизовано только {success} из {len(accounts)}")
        logger.info("Запустите скрипт ещё раз для оставшихся\n")


if __name__ == "__main__":
    asyncio.run(main())
