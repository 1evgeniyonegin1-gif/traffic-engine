#!/usr/bin/env python
"""
Проверка и исправление каналов в БД.

Этот скрипт:
1. Проверяет все каналы из БД на существование
2. Проверяет открыты ли комментарии
3. Деактивирует нерабочие каналы
4. Показывает какие каналы нужно заменить

Использование:
    python scripts/check_and_fix_channels.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select, update
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount, TargetChannel

TENANT_NAME = "infobusiness"


async def check_channel(client: TelegramClient, username: str) -> dict:
    """Проверить канал на существование и наличие комментариев."""
    result = {
        "username": username,
        "exists": False,
        "is_channel": False,
        "has_comments": False,
        "subscribers": 0,
        "title": "",
        "linked_chat_id": None,
        "error": None,
    }

    try:
        entity = await client.get_entity(username)
        result["exists"] = True

        if not isinstance(entity, Channel):
            result["error"] = "Не канал (пользователь или чат)"
            return result

        result["is_channel"] = True
        result["title"] = entity.title

        full_channel = await client(GetFullChannelRequest(entity))
        result["subscribers"] = full_channel.full_chat.participants_count or 0

        if full_channel.full_chat.linked_chat_id:
            result["has_comments"] = True
            result["linked_chat_id"] = full_channel.full_chat.linked_chat_id

    except Exception as e:
        error_msg = str(e)
        if "Nobody is using this username" in error_msg:
            result["error"] = "Канал не существует"
        elif "Could not find" in error_msg:
            result["error"] = "Не найден"
        elif "Cannot cast" in error_msg:
            result["error"] = "Это не канал"
        elif "FLOOD" in error_msg.upper():
            result["error"] = "FloodWait"
        elif "No user has" in error_msg:
            result["error"] = "Username не существует"
        else:
            result["error"] = error_msg[:80]

    return result


async def main():
    """Проверить все каналы из БД."""
    await init_db()

    logger.info("=" * 70)
    logger.info("ПРОВЕРКА КАНАЛОВ ИЗ БД")
    logger.info("=" * 70)

    # Получаем tenant и аккаунт
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error(f"Tenant '{TENANT_NAME}' не найден!")
            return

        # Получаем аккаунт для проверки
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant.id,
                UserBotAccount.status.in_(["active", "warming"])
            ).limit(1)
        )
        account = result.scalar_one_or_none()
        if not account:
            logger.error("Нет активных аккаунтов!")
            return

        # Получаем все каналы из БД
        result = await session.execute(
            select(TargetChannel).where(
                TargetChannel.tenant_id == tenant.id
            ).order_by(TargetChannel.priority.desc())
        )
        channels_in_db = result.scalars().all()

        logger.info(f"Каналов в БД: {len(channels_in_db)}")
        logger.info(f"Проверяю через аккаунт: {account.first_name} (@{account.username})")

    # Подключаемся к Telegram
    client = TelegramClient(
        StringSession(account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )
    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Аккаунт не авторизован!")
        await client.disconnect()
        return

    # Результаты проверки
    working = []      # Работают (есть комментарии)
    no_comments = []  # Существуют, но без комментариев
    broken = []       # Не существуют или ошибка

    for i, ch in enumerate(channels_in_db, 1):
        logger.info(f"[{i}/{len(channels_in_db)}] @{ch.username}...")

        check_result = await check_channel(client, ch.username)

        if check_result["error"]:
            logger.warning(f"  ❌ {check_result['error']}")
            broken.append({
                "db_id": ch.id,
                "username": ch.username,
                "error": check_result["error"],
                "priority": ch.priority,
            })
        elif not check_result["has_comments"]:
            logger.info(f"  ⚠️ Нет комментариев ({check_result['subscribers']:,} подп.)")
            no_comments.append({
                "db_id": ch.id,
                "username": ch.username,
                "title": check_result["title"],
                "subscribers": check_result["subscribers"],
                "priority": ch.priority,
            })
        else:
            logger.info(f"  ✅ OK! {check_result['title']} ({check_result['subscribers']:,} подп.)")
            working.append({
                "db_id": ch.id,
                "username": ch.username,
                "title": check_result["title"],
                "subscribers": check_result["subscribers"],
                "linked_chat_id": check_result["linked_chat_id"],
                "priority": ch.priority,
            })

        await asyncio.sleep(1.5)  # Задержка от флуда

    await client.disconnect()

    # Выводим результаты
    print("\n" + "=" * 70)
    print("REZULTATY PROVERKI")
    print("=" * 70)

    print(f"\n[OK] RABOTAYUSHCHIE KANALY ({len(working)}):")
    print("-" * 70)
    for ch in sorted(working, key=lambda x: x["subscribers"], reverse=True):
        print(f"  @{ch['username']:25} | {ch['subscribers']:>10,} podp. | prioritet {ch['priority']}")

    print(f"\n[!] BEZ KOMMENTARIEV ({len(no_comments)}):")
    print("-" * 70)
    for ch in sorted(no_comments, key=lambda x: x["subscribers"], reverse=True):
        print(f"  @{ch['username']:25} | {ch['subscribers']:>10,} podp. | prioritet {ch['priority']}")

    print(f"\n[X] NERABOCHIE ({len(broken)}):")
    print("-" * 70)
    for ch in broken:
        print(f"  @{ch['username']:25} | {ch['error']}")

    # Статистика
    print("\n" + "=" * 70)
    print("STATISTIKA")
    print("=" * 70)
    print(f"  Vsego v BD:           {len(channels_in_db)}")
    print(f"  [OK] Rabotayut:       {len(working)}")
    print(f"  [!] Bez kommentariev: {len(no_comments)}")
    print(f"  [X] Nerabochie:       {len(broken)}")

    # Деактивация нерабочих каналов
    if broken or no_comments:
        print("\n" + "=" * 70)
        print("ISPRAVLENIE")
        print("=" * 70)

        to_deactivate = [ch["db_id"] for ch in broken + no_comments]

        # Автоматически деактивируем если передан stdin
        import sys
        if not sys.stdin.isatty():
            response = sys.stdin.readline().strip()
        else:
            response = input(f"\nDeaktivirovat {len(to_deactivate)} nerabochih kanalov? (yes/no): ")

        if response.lower() in ['yes', 'y', 'da']:
            async with get_session() as session:
                await session.execute(
                    update(TargetChannel)
                    .where(TargetChannel.id.in_(to_deactivate))
                    .values(is_active=False)
                )
                await session.commit()
            print(f"[OK] Deaktivirovano {len(to_deactivate)} kanalov")
        else:
            print("Otmeneno")

    # Сохраняем отчёт
    report_path = Path(__file__).parent.parent / "docs" / "CHANNELS_CHECK_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Otchet proverki kanalov\n\n")
        f.write(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        f.write(f"## Rabotayushchie kanaly ({len(working)})\n\n")
        f.write("| Username | Nazvanie | Podpischikov | Prioritet |\n")
        f.write("|----------|----------|-------------|----------|\n")
        for ch in sorted(working, key=lambda x: x["subscribers"], reverse=True):
            title_safe = ch['title'].encode('ascii', 'replace').decode()
            f.write(f"| @{ch['username']} | {title_safe} | {ch['subscribers']:,} | {ch['priority']} |\n")

        f.write(f"\n## Bez kommentariev ({len(no_comments)})\n\n")
        f.write("| Username | Nazvanie | Podpischikov |\n")
        f.write("|----------|----------|-------------|\n")
        for ch in sorted(no_comments, key=lambda x: x["subscribers"], reverse=True):
            title_safe = ch['title'].encode('ascii', 'replace').decode()
            f.write(f"| @{ch['username']} | {title_safe} | {ch['subscribers']:,} |\n")

        f.write(f"\n## Nerabochie ({len(broken)})\n\n")
        f.write("| Username | Oshibka |\n")
        f.write("|----------|--------|\n")
        for ch in broken:
            f.write(f"| @{ch['username']} | {ch['error']} |\n")

    print(f"\nOtchet sohranen: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
