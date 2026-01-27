"""
Импорт аккаунта из готового .session файла (Telethon).

Использование:
  python scripts/import_session.py --session путь/к/файлу.session --name имя

Пример:
  python scripts/import_session.py --session "205040644_telethon.session" --name account1
"""
import argparse
import asyncio
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, Tenant

TENANT_NAME = "infobusiness"


async def get_tenant_id() -> int:
    """Получить ID тенанта."""
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error(f"Тенант '{TENANT_NAME}' не найден!")
            sys.exit(1)
        return tenant.id


async def import_session(session_path: str, account_name: str) -> bool:
    """
    Импортировать аккаунт из .session файла.
    """
    if not os.path.exists(session_path):
        logger.error(f"Файл не найден: {session_path}")
        return False

    # Копируем сессию в папку sessions/
    os.makedirs("sessions", exist_ok=True)
    dest_path = f"sessions/{account_name}.session"

    if session_path != dest_path:
        shutil.copy2(session_path, dest_path)
        logger.info(f"Сессия скопирована: {dest_path}")

    # Подключаемся для проверки
    logger.info("Проверяю авторизацию...")

    client = TelegramClient(
        f"sessions/{account_name}",
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            logger.error("Сессия не авторизована! Файл повреждён или устарел.")
            await client.disconnect()
            return False

        me = await client.get_me()
        phone = me.phone or f"unknown_{me.id}"
        if phone and not phone.startswith("+"):
            phone = f"+{phone}"

        logger.info(f"Авторизован: {me.first_name} (@{me.username or 'нет'})")
        logger.info(f"ID: {me.id}")
        logger.info(f"Телефон: {phone}")

        # Получаем string session для хранения в БД
        string_session = StringSession.save(client.session)

        # Добавляем в базу данных
        tenant_id = await get_tenant_id()

        async with get_session() as db_session:
            # Проверяем, нет ли уже такого аккаунта
            result = await db_session.execute(
                select(UserBotAccount).where(UserBotAccount.telegram_id == me.id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(f"Аккаунт {me.id} уже есть в базе, обновляю...")
                existing.session_string = string_session
                existing.phone = phone
                existing.first_name = me.first_name or "User"
                existing.last_name = me.last_name or ""
                existing.username = me.username or ""
                await db_session.commit()
                logger.info("Аккаунт обновлён!")
            else:
                account = UserBotAccount(
                    tenant_id=tenant_id,
                    phone=phone,
                    session_string=string_session,
                    telegram_id=me.id,
                    first_name=me.first_name or "User",
                    last_name=me.last_name or "",
                    username=me.username or "",
                    bio="",
                    status="warming",
                )
                db_session.add(account)
                await db_session.commit()
                logger.info("Аккаунт добавлен в базу данных!")

        await client.disconnect()

        logger.info("=" * 50)
        logger.info("УСПЕХ!")
        logger.info(f"Имя: {me.first_name} {me.last_name or ''}")
        logger.info(f"Username: @{me.username or 'нет'}")
        logger.info(f"ID: {me.id}")
        logger.info(f"Телефон: {phone}")
        logger.info(f"Сессия: sessions/{account_name}.session")
        logger.info("=" * 50)

        return True

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()
        return False


async def main():
    parser = argparse.ArgumentParser(description="Импорт Telegram аккаунта из .session файла")
    parser.add_argument("--session", required=True, help="Путь к .session файлу")
    parser.add_argument("--name", required=True, help="Имя для аккаунта (account1, karina, etc.)")

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("ИМПОРТ SESSION")
    logger.info(f"Файл: {args.session}")
    logger.info(f"Имя: {args.name}")
    logger.info("=" * 50)

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены в .env!")
        sys.exit(1)

    success = await import_session(args.session, args.name)

    if success:
        logger.info("\nТеперь можно тестировать!")
        logger.info("  python scripts/test_send_comment.py")


if __name__ == "__main__":
    asyncio.run(main())
