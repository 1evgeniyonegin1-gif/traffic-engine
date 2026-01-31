"""
Setup Account Profile - Настройка профиля аккаунта.

Использование:
    python scripts/setup_account_profile.py --account account1 --name "Карина" --bio "Текст био"

Или интерактивно:
    python scripts/setup_account_profile.py

Что настраивает:
- Имя и фамилию
- Bio (описание)
- Фото профиля
- Username
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto
from telethon.errors import UsernameOccupiedError, UsernameInvalidError, FloodWaitError
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount


async def get_client_for_account(account_name: str) -> tuple:
    """
    Получить Telethon клиент для аккаунта.

    Returns:
        (client, account_record) или (None, None)
    """
    session_file = f"sessions/{account_name}.session"

    if not os.path.exists(session_file):
        logger.error(f"Session file not found: {session_file}")
        return None, None

    client = TelegramClient(
        f"sessions/{account_name}",
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    await client.connect()

    if not await client.is_user_authorized():
        logger.error(f"Account {account_name} is not authorized!")
        await client.disconnect()
        return None, None

    # Получаем запись из БД
    async with get_session() as session:
        me = await client.get_me()
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.telegram_id == me.id)
        )
        account = result.scalar_one_or_none()

    return client, account


async def update_profile(
    client: TelegramClient,
    first_name: str = None,
    last_name: str = None,
    bio: str = None,
) -> bool:
    """
    Обновить имя, фамилию и bio.

    Args:
        client: Telethon клиент
        first_name: Новое имя
        last_name: Новая фамилия (можно "" для удаления)
        bio: Новое описание профиля

    Returns:
        True если успешно
    """
    try:
        # Собираем параметры для обновления
        params = {}

        if first_name is not None:
            params["first_name"] = first_name
        if last_name is not None:
            params["last_name"] = last_name
        if bio is not None:
            params["about"] = bio

        if not params:
            logger.warning("No profile fields to update")
            return False

        await client(UpdateProfileRequest(**params))

        logger.info(f"✅ Profile updated!")
        if first_name:
            logger.info(f"   First name: {first_name}")
        if last_name is not None:
            logger.info(f"   Last name: {last_name or '(removed)'}")
        if bio:
            logger.info(f"   Bio: {bio[:50]}...")

        return True

    except FloodWaitError as e:
        logger.error(f"FloodWait: need to wait {e.seconds} seconds")
        return False
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return False


async def update_username(client: TelegramClient, username: str) -> bool:
    """
    Обновить username.

    Args:
        client: Telethon клиент
        username: Новый username (без @)

    Returns:
        True если успешно
    """
    try:
        # Убираем @ если есть
        username = username.lstrip("@")

        await client(UpdateUsernameRequest(username=username))

        logger.info(f"✅ Username updated: @{username}")
        return True

    except UsernameOccupiedError:
        logger.error(f"Username @{username} is already taken!")
        return False
    except UsernameInvalidError:
        logger.error(f"Username @{username} is invalid!")
        return False
    except FloodWaitError as e:
        logger.error(f"FloodWait: need to wait {e.seconds} seconds")
        return False
    except Exception as e:
        logger.error(f"Error updating username: {e}")
        return False


async def update_photo(client: TelegramClient, photo_path: str) -> bool:
    """
    Обновить фото профиля.

    Args:
        client: Telethon клиент
        photo_path: Путь к файлу фото

    Returns:
        True если успешно
    """
    if not os.path.exists(photo_path):
        logger.error(f"Photo file not found: {photo_path}")
        return False

    try:
        # Загружаем фото
        file = await client.upload_file(photo_path)

        # Устанавливаем как фото профиля
        await client(UploadProfilePhotoRequest(file=file))

        logger.info(f"✅ Profile photo updated from: {photo_path}")
        return True

    except FloodWaitError as e:
        logger.error(f"FloodWait: need to wait {e.seconds} seconds")
        return False
    except Exception as e:
        logger.error(f"Error updating photo: {e}")
        return False


async def show_current_profile(client: TelegramClient):
    """Показать текущий профиль."""
    me = await client.get_me()

    print()
    print("=" * 50)
    print("ТЕКУЩИЙ ПРОФИЛЬ")
    print("=" * 50)
    print(f"ID:        {me.id}")
    print(f"Имя:       {me.first_name}")
    print(f"Фамилия:   {me.last_name or '(нет)'}")
    print(f"Username:  @{me.username or '(нет)'}")
    print(f"Телефон:   {me.phone}")

    # Получаем bio
    try:
        from telethon.tl.functions.users import GetFullUserRequest
        full = await client(GetFullUserRequest(me))
        bio = full.full_user.about or "(нет)"
        print(f"Bio:       {bio}")
    except Exception:
        print("Bio:       (не удалось получить)")

    print("=" * 50)
    print()


async def interactive_setup(account_name: str):
    """Интерактивная настройка профиля."""
    client, account = await get_client_for_account(account_name)

    if not client:
        return

    try:
        await show_current_profile(client)

        print("Что хотите изменить?")
        print("1. Имя и фамилию")
        print("2. Bio (описание)")
        print("3. Username")
        print("4. Фото профиля")
        print("5. Всё сразу")
        print("0. Выход")
        print()

        choice = input("Выберите (0-5): ").strip()

        if choice == "0":
            return

        if choice in ("1", "5"):
            first_name = input("Новое имя: ").strip()
            last_name = input("Новая фамилия (Enter чтобы пропустить): ").strip()
            if first_name:
                await update_profile(client, first_name=first_name, last_name=last_name or None)

        if choice in ("2", "5"):
            print()
            print("Введите bio (Enter для завершения, пустая строка для отмены):")
            bio = input().strip()
            if bio:
                await update_profile(client, bio=bio)

        if choice in ("3", "5"):
            username = input("Новый username (без @): ").strip()
            if username:
                await update_username(client, username)

        if choice in ("4", "5"):
            photo_path = input("Путь к фото: ").strip()
            if photo_path:
                await update_photo(client, photo_path)

        print()
        await show_current_profile(client)

    finally:
        await client.disconnect()


async def main():
    parser = argparse.ArgumentParser(
        description="Настройка профиля аккаунта",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:

  # Интерактивный режим
  python scripts/setup_account_profile.py --account karina

  # Установить имя и bio
  python scripts/setup_account_profile.py --account karina --name "Карина" --bio "Из найма в онлайн"

  # Установить фото
  python scripts/setup_account_profile.py --account karina --photo photos/avatar.jpg

  # Установить всё сразу
  python scripts/setup_account_profile.py --account karina \\
      --name "Карина" \\
      --last-name "Морозова" \\
      --bio "Из найма в онлайн | 150К на удалёнке" \\
      --username karinko_online \\
      --photo photos/karina.jpg
        """
    )

    parser.add_argument("--account", required=True, help="Имя аккаунта (файл сессии)")
    parser.add_argument("--name", help="Новое имя")
    parser.add_argument("--last-name", help="Новая фамилия")
    parser.add_argument("--bio", help="Новое описание профиля")
    parser.add_argument("--username", help="Новый username")
    parser.add_argument("--photo", help="Путь к фото профиля")
    parser.add_argument("--show", action="store_true", help="Только показать текущий профиль")

    args = parser.parse_args()

    # Если не указаны параметры кроме account — интерактивный режим
    has_params = any([args.name, args.last_name, args.bio, args.username, args.photo, args.show])

    if not has_params:
        await interactive_setup(args.account)
        return

    # Получаем клиент
    client, account = await get_client_for_account(args.account)

    if not client:
        return

    try:
        if args.show:
            await show_current_profile(client)
            return

        # Обновляем профиль
        if args.name or args.last_name or args.bio:
            await update_profile(
                client,
                first_name=args.name,
                last_name=args.last_name,
                bio=args.bio,
            )

        if args.username:
            await update_username(client, args.username)

        if args.photo:
            await update_photo(client, args.photo)

        # Показываем результат
        await show_current_profile(client)

        # Обновляем в БД
        if account and (args.name or args.bio):
            async with get_session() as session:
                db_account = await session.get(UserBotAccount, account.id)
                if db_account:
                    if args.name:
                        db_account.first_name = args.name
                    if args.last_name is not None:
                        db_account.last_name = args.last_name
                    if args.bio:
                        db_account.bio = args.bio
                    await session.commit()
                    logger.info("✅ Database record updated")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
