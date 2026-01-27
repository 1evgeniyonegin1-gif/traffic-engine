"""
Импорт аккаунта из TData (Telegram Desktop).

Использование:
  python scripts/import_tdata.py --tdata путь/к/tdata --name имя_аккаунта

Пример:
  python scripts/import_tdata.py --tdata "C:/Downloads/tdata" --name account1

Что делает:
1. Конвертирует TData в Telethon session
2. Проверяет авторизацию
3. Сохраняет сессию в sessions/
4. Добавляет аккаунт в базу данных

TData обычно содержит папки:
  - D877F783D5D3EF8C/ (или похожее) - данные сессии
  - key_datas - ключи шифрования
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from sqlalchemy import select

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


async def import_tdata(tdata_path: str, account_name: str) -> bool:
    """
    Импортировать аккаунт из TData.

    Args:
        tdata_path: Путь к папке tdata
        account_name: Имя для сохранения сессии

    Returns:
        True если успешно
    """
    from TGConvertor import SessionManager
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    tdata_folder = Path(tdata_path)

    if not tdata_folder.exists():
        logger.error(f"Папка не найдена: {tdata_folder}")
        return False

    # Проверяем структуру TData
    logger.info(f"Содержимое папки {tdata_folder}:")
    for item in tdata_folder.iterdir():
        logger.info(f"  - {item.name}")

    try:
        # Конвертируем TData в SessionManager
        logger.info("Конвертирую TData...")
        session_manager = SessionManager.from_tdata_folder(tdata_folder)

        logger.info(f"DC ID: {session_manager.dc_id}")
        logger.info(f"Auth key: {session_manager.auth_key_hex[:32]}...")

        # Получаем Telethon session string
        telethon_session = session_manager.to_telethon_string()
        logger.info(f"Telethon session создан")

        # Проверяем авторизацию
        logger.info("Проверяю авторизацию...")
        client = TelegramClient(
            StringSession(telethon_session),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        await client.connect()

        if not await client.is_user_authorized():
            logger.error("Сессия не авторизована! Возможно TData устарел.")
            await client.disconnect()
            return False

        me = await client.get_me()
        phone = me.phone or f"unknown_{me.id}"
        if not phone.startswith("+"):
            phone = f"+{phone}"

        logger.info(f"Авторизован: {me.first_name} (@{me.username or 'нет'}) ID:{me.id}")

        # Сохраняем сессию в файл
        os.makedirs("sessions", exist_ok=True)
        session_file = f"sessions/{account_name}.session"

        # Создаём клиент с файловой сессией для сохранения
        file_client = TelegramClient(
            f"sessions/{account_name}",
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        # Копируем сессию
        file_client.session.set_dc(session_manager.dc_id, "149.154.167.51", 443)
        file_client.session.auth_key = type('AuthKey', (), {'key': session_manager.auth_key})()
        file_client.session.save()

        logger.info(f"Сессия сохранена: {session_file}")

        # Добавляем в базу данных
        tenant_id = await get_tenant_id()

        async with get_session() as db_session:
            # Проверяем, нет ли уже такого аккаунта
            result = await db_session.execute(
                select(UserBotAccount).where(UserBotAccount.telegram_id == me.id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(f"Аккаунт {me.id} уже есть в базе, обновляю сессию...")
                existing.session_string = telethon_session
                await db_session.commit()
            else:
                account = UserBotAccount(
                    tenant_id=tenant_id,
                    phone=phone,
                    session_string=telethon_session,
                    telegram_id=me.id,
                    first_name=me.first_name or "User",
                    last_name=me.last_name or "",
                    username=me.username or "",
                    bio="",
                    status="warming",
                )
                db_session.add(account)
                await db_session.commit()
                logger.info(f"Аккаунт добавлен в базу данных!")

        await client.disconnect()

        logger.info("=" * 50)
        logger.info("УСПЕХ!")
        logger.info(f"Аккаунт: {me.first_name} (@{me.username or 'нет'})")
        logger.info(f"Телефон: {phone}")
        logger.info(f"Сессия: sessions/{account_name}.session")
        logger.info("=" * 50)

        return True

    except ImportError as e:
        if "opentele" in str(e):
            logger.error("Требуется установить opentele:")
            logger.error("  pip install opentele")
        else:
            logger.error(f"Ошибка импорта: {e}")
        return False

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    parser = argparse.ArgumentParser(
        description="Импорт Telegram аккаунта из TData",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/import_tdata.py --tdata "C:/Downloads/tdata" --name karina
  python scripts/import_tdata.py --tdata "./tdata_folder" --name account1
        """
    )
    parser.add_argument(
        "--tdata",
        required=True,
        help="Путь к папке tdata"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Имя для сохранения сессии (karina, account1, etc.)"
    )

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("ИМПОРТ TDATA")
    logger.info(f"Папка: {args.tdata}")
    logger.info(f"Имя: {args.name}")
    logger.info("=" * 50)

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены в .env!")
        sys.exit(1)

    success = await import_tdata(args.tdata, args.name)

    if success:
        logger.info("\nТеперь можно тестировать комментарии:")
        logger.info(f"  python scripts/test_send_comment.py")
    else:
        logger.error("\nИмпорт не удался. Проверь:")
        logger.error("  1. Путь к tdata правильный")
        logger.error("  2. TData не повреждён")
        logger.error("  3. Аккаунт не забанен")


if __name__ == "__main__":
    asyncio.run(main())
