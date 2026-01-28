#!/usr/bin/env python
"""
Реавторизация аккаунтов Telethon после очистки сессий.

Для каждого аккаунта:
1. Создаёт новую сессию
2. Запрашивает код из Telegram
3. Сохраняет session_string в БД
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


async def authorize_account(phone: str, account_id: int):
    """Авторизовать один аккаунт."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Авторизация аккаунта: {phone}")
    logger.info(f"{'='*60}")

    # Создать клиент с пустой сессией
    client = TelegramClient(
        StringSession(),
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
    )

    await client.connect()

    if not await client.is_user_authorized():
        # Отправить код
        await client.send_code_request(phone)
        logger.info(f"Код отправлен на номер {phone}")

        # Запросить код у пользователя
        code = input(f"\nВведите код для {phone}: ")

        try:
            await client.sign_in(phone, code)
            logger.success(f"Успешная авторизация для {phone}")
        except Exception as e:
            logger.error(f"Ошибка авторизации {phone}: {e}")
            # Может понадобиться пароль 2FA
            if "password" in str(e).lower():
                password = input(f"Введите пароль 2FA для {phone}: ")
                await client.sign_in(password=password)
                logger.success(f"Успешная авторизация с 2FA для {phone}")

    # Получить session string
    session_string = client.session.save()

    # Сохранить в БД
    async with get_session() as db:
        await db.execute(
            text("UPDATE traffic_userbot_accounts SET session_string = :session WHERE id = :id"),
            {"session": session_string, "id": account_id}
        )
        await db.commit()

    logger.success(f"Session string сохранён в БД для {phone}")

    await client.disconnect()
    return True


async def main():
    logger.info("=== Реавторизация аккаунтов ===\n")

    # Получить аккаунты с пустыми сессиями
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, phone, first_name FROM traffic_userbot_accounts "
            "WHERE session_string = '' OR session_string IS NULL "
            "ORDER BY phone"
        ))
        accounts = result.fetchall()

    if not accounts:
        logger.info("Нет аккаунтов требующих авторизации")
        return

    logger.info(f"Найдено {len(accounts)} аккаунтов для авторизации:\n")
    for acc_id, phone, name in accounts:
        logger.info(f"  {name} ({phone})")

    logger.info(f"\nВам нужно будет ввести коды из Telegram для каждого аккаунта")
    logger.info("Коды придут в приложение Telegram на эти номера\n")
    logger.info("Начинаем авторизацию...\n")

    # Авторизовать каждый аккаунт
    success_count = 0
    for acc_id, phone, name in accounts:
        try:
            success = await authorize_account(phone, acc_id)
            if success:
                success_count += 1
            await asyncio.sleep(2)  # Задержка между аккаунтами
        except Exception as e:
            logger.error(f"Критическая ошибка для {phone}: {e}")
            continue

    logger.info(f"\n{'='*60}")
    logger.success(f"Авторизовано {success_count} из {len(accounts)} аккаунтов")
    logger.info(f"{'='*60}")

    if success_count == len(accounts):
        logger.success("\nВсе аккаунты успешно авторизованы!")
        logger.info("Теперь можно запустить систему: systemctl start traffic-engine")
    else:
        logger.warning("\nНекоторые аккаунты не авторизованы. Запустите скрипт ещё раз.")


if __name__ == "__main__":
    asyncio.run(main())
