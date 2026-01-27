"""
Авторизация аккаунтов для комментирования.

Запуск:
  python scripts/authorize_accounts.py

Перед запуском заполни в .env:
  ACCOUNT_KARINA_PHONE=+79001234567
  ACCOUNT_KIRA_PHONE=+79001234568
  ACCOUNT_LYUBA_PHONE=+79001234569

При первом запуске для каждого аккаунта:
1. Telegram пришлёт код на телефон
2. Введи код в консоль
3. Сессия сохранится в sessions/имя.session

После авторизации можно запускать комментирование.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from dotenv import load_dotenv

load_dotenv()

# Telegram API
API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627")

# Аккаунты из .env
ACCOUNTS = [
    {
        "name": "karina",
        "display": "Карина",
        "phone": os.getenv("ACCOUNT_KARINA_PHONE", ""),
        "gender": os.getenv("ACCOUNT_KARINA_GENDER", "female"),
    },
    {
        "name": "kira",
        "display": "Кира",
        "phone": os.getenv("ACCOUNT_KIRA_PHONE", ""),
        "gender": os.getenv("ACCOUNT_KIRA_GENDER", "female"),
    },
    {
        "name": "lyuba",
        "display": "Люба",
        "phone": os.getenv("ACCOUNT_LYUBA_PHONE", ""),
        "gender": os.getenv("ACCOUNT_LYUBA_GENDER", "female"),
    },
]


async def authorize_account(account: dict) -> bool:
    """Авторизует один аккаунт."""
    name = account["name"]
    display = account["display"]
    phone = account["phone"]

    if not phone:
        print(f"  [{display}] Номер не указан в .env (ACCOUNT_{name.upper()}_PHONE)")
        return False

    session_path = f"sessions/{name}"
    os.makedirs("sessions", exist_ok=True)

    print(f"\n{'='*50}")
    print(f"Авторизация: {display}")
    print(f"Телефон: {phone}")
    print(f"{'='*50}")

    client = TelegramClient(session_path, API_ID, API_HASH)

    try:
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Уже авторизован как: {me.first_name} (@{me.username or 'нет username'})")
            await client.disconnect()
            return True

        # Отправляем код
        print("Отправляю код авторизации...")
        await client.send_code_request(phone)

        # Запрашиваем код у пользователя
        code = input(f"Введи код из Telegram для {display}: ").strip()

        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            # 2FA включена
            password = input("Введи пароль двухфакторной аутентификации: ").strip()
            await client.sign_in(password=password)

        me = await client.get_me()
        print(f"Успешно авторизован: {me.first_name} (@{me.username or 'нет username'})")

        await client.disconnect()
        return True

    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        await client.disconnect()
        return False


async def main():
    print("=" * 60)
    print("АВТОРИЗАЦИЯ АККАУНТОВ")
    print("=" * 60)

    # Проверяем какие аккаунты настроены
    configured = [a for a in ACCOUNTS if a["phone"]]

    if not configured:
        print("\nНет настроенных аккаунтов!")
        print("\nЗаполни номера в .env файле:")
        print("  ACCOUNT_KARINA_PHONE=+79001234567")
        print("  ACCOUNT_KIRA_PHONE=+79001234568")
        print("  ACCOUNT_LYUBA_PHONE=+79001234569")
        return

    print(f"\nНайдено аккаунтов с номерами: {len(configured)}")

    results = []
    for account in configured:
        success = await authorize_account(account)
        results.append((account["display"], success))

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ:")
    print("=" * 60)
    for name, success in results:
        status = "OK" if success else "ОШИБКА"
        print(f"  {name}: {status}")

    # Проверяем сессии
    print("\n" + "=" * 60)
    print("СОХРАНЁННЫЕ СЕССИИ:")
    print("=" * 60)
    if os.path.exists("sessions"):
        sessions = [f for f in os.listdir("sessions") if f.endswith(".session")]
        if sessions:
            for s in sessions:
                print(f"  sessions/{s}")
        else:
            print("  Нет сессий")
    else:
        print("  Папка sessions не создана")


if __name__ == "__main__":
    asyncio.run(main())
