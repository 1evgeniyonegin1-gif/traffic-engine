"""
Авторизация одного аккаунта с кодом через параметр.

Использование:
  # Шаг 1: Запросить код (отправит SMS)
  python scripts/auth_one.py --phone +573136968095 --name karina --request-code

  # Шаг 2: Ввести полученный код
  python scripts/auth_one.py --phone +573136968095 --name karina --code 12345
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627")


async def request_code(phone: str, name: str):
    """Отправляет запрос на код."""
    session_path = f"sessions/{name}"
    os.makedirs("sessions", exist_ok=True)

    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Уже авторизован: {me.first_name} (@{me.username or 'нет'})")
        await client.disconnect()
        return

    print(f"Отправляю код на {phone}...")
    result = await client.send_code_request(phone)
    print(f"Код отправлен! phone_code_hash: {result.phone_code_hash}")
    print(f"\nТеперь запусти:")
    print(f'  python scripts/auth_one.py --phone {phone} --name {name} --code ТВОЙ_КОД')

    await client.disconnect()


async def sign_in_with_code(phone: str, name: str, code: str):
    """Авторизуется с кодом."""
    session_path = f"sessions/{name}"

    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Уже авторизован: {me.first_name} (@{me.username or 'нет'})")
        await client.disconnect()
        return True

    try:
        # Сначала отправим код ещё раз чтобы получить hash
        result = await client.send_code_request(phone)

        # Теперь авторизуемся
        await client.sign_in(phone, code, phone_code_hash=result.phone_code_hash)

        me = await client.get_me()
        print(f"Успешно авторизован: {me.first_name} (@{me.username or 'нет'})")
        print(f"Сессия сохранена: sessions/{name}.session")
        await client.disconnect()
        return True

    except PhoneCodeInvalidError:
        print("ОШИБКА: Неверный код!")
        await client.disconnect()
        return False

    except SessionPasswordNeededError:
        print("Требуется 2FA пароль. Запусти с --password:")
        print(f'  python scripts/auth_one.py --phone {phone} --name {name} --code {code} --password ТВОЙ_ПАРОЛЬ')
        await client.disconnect()
        return False

    except Exception as e:
        print(f"Ошибка: {e}")
        await client.disconnect()
        return False


async def main():
    parser = argparse.ArgumentParser(description="Авторизация Telegram аккаунта")
    parser.add_argument("--phone", required=True, help="Номер телефона (+573136968095)")
    parser.add_argument("--name", required=True, help="Имя для сессии (karina, kira, lyuba)")
    parser.add_argument("--request-code", action="store_true", help="Запросить код")
    parser.add_argument("--code", help="Код из SMS")
    parser.add_argument("--password", help="2FA пароль (если включён)")

    args = parser.parse_args()

    if args.request_code:
        await request_code(args.phone, args.name)
    elif args.code:
        await sign_in_with_code(args.phone, args.name, args.code)
    else:
        print("Укажи --request-code или --code")
        print("\nПримеры:")
        print(f"  python scripts/auth_one.py --phone {args.phone} --name {args.name} --request-code")
        print(f"  python scripts/auth_one.py --phone {args.phone} --name {args.name} --code 12345")


if __name__ == "__main__":
    asyncio.run(main())
