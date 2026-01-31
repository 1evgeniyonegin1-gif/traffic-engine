"""
Manage Proxy - Управление прокси для аккаунтов.

Использование:
    # Показать все аккаунты и их прокси
    python scripts/manage_proxy.py --list

    # Добавить прокси к аккаунту
    python scripts/manage_proxy.py --add --phone "+62xxx" --proxy "socks5://user:pass@ip:port"

    # Удалить прокси у аккаунта
    python scripts/manage_proxy.py --remove --phone "+62xxx"

    # Проверить работу прокси
    python scripts/manage_proxy.py --test --phone "+62xxx"
"""

import argparse
import asyncio
import io
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount


# Определение страны по коду телефона
COUNTRY_CODES = {
    "62": ("ID", "Indonesia"),
    "7": ("RU", "Russia"),
    "380": ("UA", "Ukraine"),
    "375": ("BY", "Belarus"),
    "77": ("KZ", "Kazakhstan"),
    "1": ("US", "USA"),
    "91": ("IN", "India"),
    "44": ("GB", "UK"),
    "49": ("DE", "Germany"),
}


def get_country_by_phone(phone: str) -> tuple[str, str]:
    """Определить страну по номеру телефона."""
    p = re.sub(r"[^0-9]", "", phone)

    # Проверяем от длинных кодов к коротким
    for code in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
        if p.startswith(code):
            return COUNTRY_CODES[code]

    return ("??", "Unknown")


def parse_proxy_url(proxy_url: str) -> dict:
    """
    Парсит URL прокси в компоненты.

    Форматы:
    - socks5://user:pass@ip:port
    - http://user:pass@ip:port
    - socks5://ip:port
    """
    try:
        # Добавляем схему если нет
        if not proxy_url.startswith(("http://", "https://", "socks5://", "socks4://")):
            proxy_url = f"socks5://{proxy_url}"

        parsed = urlparse(proxy_url)

        return {
            "type": parsed.scheme.replace("://", ""),
            "host": parsed.hostname,
            "port": parsed.port,
            "username": parsed.username,
            "password": parsed.password,
        }
    except Exception as e:
        logger.error(f"Failed to parse proxy URL: {e}")
        return None


async def list_accounts():
    """Показать все аккаунты с их прокси."""
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).order_by(UserBotAccount.phone)
        )
        accounts = result.scalars().all()

        if not accounts:
            print("\nNo accounts found.\n")
            return

        print("\n" + "=" * 100)
        print(f"{'Phone':<20} {'Country':<15} {'Name':<20} {'Status':<10} {'Proxy':<35}")
        print("=" * 100)

        accounts_without_proxy = []

        for acc in accounts:
            country_code, country_name = get_country_by_phone(acc.phone)

            proxy_info = "-"
            if acc.proxy_host:
                proxy_info = f"{acc.proxy_type}://{acc.proxy_host}:{acc.proxy_port}"
            else:
                if country_code != "RU":  # Не Россия - нужен прокси
                    accounts_without_proxy.append((acc.phone, country_name))

            status_icon = {
                "active": "✅",
                "warming": "🔥",
                "banned": "❌",
                "cooldown": "⏳",
                "disabled": "⛔",
            }.get(acc.status, "❓")

            print(f"{acc.phone:<20} {country_name:<15} {acc.first_name or '-':<20} {status_icon} {acc.status:<8} {proxy_info:<35}")

        print("=" * 100)
        print(f"Total accounts: {len(accounts)}")

        if accounts_without_proxy:
            print("\n⚠️  WARNING: The following non-Russian accounts have NO PROXY (high ban risk!):")
            for phone, country in accounts_without_proxy:
                print(f"   - {phone} ({country})")
            print("\n   Add proxy with: python scripts/manage_proxy.py --add --phone \"+62xxx\" --proxy \"socks5://user:pass@ip:port\"")

        print()


async def add_proxy(phone: str, proxy_url: str):
    """Добавить прокси к аккаунту."""
    proxy = parse_proxy_url(proxy_url)
    if not proxy:
        print(f"Error: Invalid proxy URL format: {proxy_url}")
        print("Expected format: socks5://user:pass@ip:port")
        return

    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.phone == phone)
        )
        account = result.scalar_one_or_none()

        if not account:
            print(f"Error: Account with phone {phone} not found.")
            return

        account.proxy_type = proxy["type"]
        account.proxy_host = proxy["host"]
        account.proxy_port = proxy["port"]
        account.proxy_username = proxy["username"]
        account.proxy_password = proxy["password"]

        await session.commit()

        country_code, country_name = get_country_by_phone(phone)
        print(f"\n✅ Proxy added to account {phone} ({country_name}):")
        print(f"   Type: {proxy['type']}")
        print(f"   Host: {proxy['host']}:{proxy['port']}")
        if proxy["username"]:
            print(f"   Auth: {proxy['username']}:***")
        print()


async def remove_proxy(phone: str):
    """Удалить прокси у аккаунта."""
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.phone == phone)
        )
        account = result.scalar_one_or_none()

        if not account:
            print(f"Error: Account with phone {phone} not found.")
            return

        account.proxy_type = None
        account.proxy_host = None
        account.proxy_port = None
        account.proxy_username = None
        account.proxy_password = None

        await session.commit()

        print(f"\n✅ Proxy removed from account {phone}.\n")


async def test_proxy(phone: str):
    """Проверить работу прокси."""
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.phone == phone)
        )
        account = result.scalar_one_or_none()

        if not account:
            print(f"Error: Account with phone {phone} not found.")
            return

        if not account.proxy_host:
            print(f"Error: Account {phone} has no proxy configured.")
            return

        print(f"\nTesting proxy for account {phone}...")
        print(f"Proxy: {account.proxy_type}://{account.proxy_host}:{account.proxy_port}")

        # Пробуем подключиться через прокси
        try:
            import aiohttp
            import aiohttp_socks

            proxy_url = f"{account.proxy_type}://"
            if account.proxy_username:
                proxy_url += f"{account.proxy_username}:{account.proxy_password}@"
            proxy_url += f"{account.proxy_host}:{account.proxy_port}"

            connector = aiohttp_socks.ProxyConnector.from_url(proxy_url)

            async with aiohttp.ClientSession(connector=connector) as http_session:
                async with http_session.get("https://api.ipify.org?format=json", timeout=10) as resp:
                    data = await resp.json()
                    ip = data.get("ip", "unknown")
                    print(f"\n✅ Proxy works! Your IP through proxy: {ip}")

                    # Проверим геолокацию IP
                    async with http_session.get(f"http://ip-api.com/json/{ip}", timeout=10) as geo_resp:
                        geo_data = await geo_resp.json()
                        country = geo_data.get("country", "Unknown")
                        city = geo_data.get("city", "Unknown")
                        print(f"   Location: {city}, {country}")

        except ImportError:
            print("\n⚠️  aiohttp-socks not installed. Run: pip install aiohttp-socks")
        except Exception as e:
            print(f"\n❌ Proxy test failed: {e}")

        print()


def main():
    parser = argparse.ArgumentParser(description="Manage proxy for Traffic Engine accounts")
    parser.add_argument("--list", action="store_true", help="List all accounts with their proxy status")
    parser.add_argument("--add", action="store_true", help="Add proxy to account")
    parser.add_argument("--remove", action="store_true", help="Remove proxy from account")
    parser.add_argument("--test", action="store_true", help="Test proxy connection")
    parser.add_argument("--phone", type=str, help="Phone number of the account")
    parser.add_argument("--proxy", type=str, help="Proxy URL (socks5://user:pass@ip:port)")

    args = parser.parse_args()

    if args.list:
        asyncio.run(list_accounts())
    elif args.add:
        if not args.phone or not args.proxy:
            print("Error: --add requires --phone and --proxy")
            return
        asyncio.run(add_proxy(args.phone, args.proxy))
    elif args.remove:
        if not args.phone:
            print("Error: --remove requires --phone")
            return
        asyncio.run(remove_proxy(args.phone))
    elif args.test:
        if not args.phone:
            print("Error: --test requires --phone")
            return
        asyncio.run(test_proxy(args.phone))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
