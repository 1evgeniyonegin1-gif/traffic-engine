#!/usr/bin/env python
"""
Проверка каналов на существование и наличие открытых комментариев.
БЕЗ ПОДПИСКИ на каналы - только проверка через get_entity.

Использование:
    python scripts/verify_channels.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import select
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import Tenant, UserBotAccount


# Каналы для проверки (из нашего резерва)
CHANNELS_TO_VERIFY = [
    # Бизнес и предпринимательство
    "startupoftheday",
    "mspiridonov",
    "rybakovigor",
    "grebenukm",
    "temno",
    "bezsmuzi",
    "portnyaginlive",
    "Salesnotes",
    "ikniga",
    "business_theory",
    "ventureStuff",
    "Theedinorogblog",
    "addmeto",
    "rb_ru",
    "oskar_hartmann",

    # Фриланс и удалёнка
    "udalenka_vacansii",
    "designer_ru",
    "vacansii_na_udalenke",
    "expout",
    "normrabota",
    "morejobs",
    "careerspace",
    "worklis",
    "brain_drain_ru",
    "Work_Connect",

    # Мотивация и саморазвитие
    "silaslovv",
    "motivator_tv",
    "labkovskiy",
    "stoicstrategy",
    "guzenuk",
    "chillosophy",
    "psychay",
    "samorazvitiev",
    "ThinkCritical",
    "anettaorlova",

    # Маркетинг и SMM
    "TexterraBlog",
    "marketingold",
    "marketing_bez_vodi",
    "marketolog_digital",
    "sosindex",
    "c_behavior",
    "marketpsy",
    "blogmilova",
    "dnative",
    "Digitalmrktng",

    # Финансы и инвестиции
    "bitkogan",
    "tb_invest_official",
    "alfa_investments",
    "fatcat18",
    "banksta",
    "nebrexnya",
    "prostoecon",
    "multievan",
    "profitgate",
    "auantonov",

    # Инфобизнес
    "sberstartup",
    "dindex",
    "productradar_official",
    "kutergin_on_fire",
    "pisarevich",
]

TENANT_NAME = "infobusiness"


async def check_channel(client: TelegramClient, username: str) -> dict:
    """
    Проверить канал на существование и наличие комментариев.
    БЕЗ подписки на канал.
    """
    result = {
        "username": username,
        "exists": False,
        "is_channel": False,
        "has_comments": False,
        "subscribers": 0,
        "title": "",
        "error": None,
    }

    try:
        # Получаем entity канала (не подписываемся!)
        entity = await client.get_entity(username)
        result["exists"] = True

        # Проверяем что это канал, а не чат/пользователь
        from telethon.tl.types import Channel
        if not isinstance(entity, Channel):
            result["error"] = "Это не канал (возможно, пользователь или чат)"
            return result

        result["is_channel"] = True
        result["title"] = entity.title

        # Получаем полную информацию о канале
        full_channel = await client(GetFullChannelRequest(entity))

        # Количество подписчиков
        result["subscribers"] = full_channel.full_chat.participants_count or 0

        # Проверяем есть ли linked_chat (группа для комментариев)
        if full_channel.full_chat.linked_chat_id:
            result["has_comments"] = True

    except Exception as e:
        error_msg = str(e)
        if "Nobody is using this username" in error_msg:
            result["error"] = "Канал не существует"
        elif "Could not find" in error_msg:
            result["error"] = "Канал не найден"
        elif "FLOOD" in error_msg:
            result["error"] = "Слишком много запросов, подождите"
        else:
            result["error"] = error_msg[:100]

    return result


async def main():
    """Проверить все каналы из списка."""
    logger.info("=== Проверка каналов (БЕЗ ПОДПИСКИ) ===")
    logger.info(f"Всего каналов для проверки: {len(CHANNELS_TO_VERIFY)}")

    # Получаем аккаунт для проверки
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error(f"Tenant '{TENANT_NAME}' не найден!")
            return

        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant.id,
                UserBotAccount.status.in_(["active", "warming"])
            ).limit(1)
        )
        account = result.scalar_one_or_none()

        if not account:
            logger.error("Нет активных аккаунтов для проверки!")
            return

    # Подключаемся
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

    logger.info(f"Проверяем через аккаунт: {account.first_name}")

    # Результаты
    valid_channels = []  # Существуют + есть комментарии
    no_comments = []     # Существуют, но нет комментариев
    not_found = []       # Не найдены

    for i, username in enumerate(CHANNELS_TO_VERIFY, 1):
        logger.info(f"[{i}/{len(CHANNELS_TO_VERIFY)}] Проверяю @{username}...")

        result = await check_channel(client, username)

        if result["error"]:
            logger.warning(f"  ❌ {result['error']}")
            not_found.append(username)
        elif not result["has_comments"]:
            logger.info(f"  ⚠️ Нет комментариев ({result['subscribers']:,} подписчиков)")
            no_comments.append({
                "username": username,
                "title": result["title"],
                "subscribers": result["subscribers"]
            })
        else:
            logger.info(f"  ✅ Комментарии открыты! ({result['subscribers']:,} подписчиков)")
            valid_channels.append({
                "username": username,
                "title": result["title"],
                "subscribers": result["subscribers"]
            })

        # Задержка чтобы не получить флуд
        await asyncio.sleep(2)

    await client.disconnect()

    # Выводим результаты
    print("\n" + "=" * 70)
    print("REZULTATY PROVERKI")
    print("=" * 70)

    print(f"\n[OK] KANALY S OTKRYTYMI KOMMENTARIYAMI ({len(valid_channels)}):")
    print("-" * 70)
    for ch in sorted(valid_channels, key=lambda x: x["subscribers"], reverse=True):
        title_safe = ch['title'][:25].encode('ascii', 'replace').decode()
        print(f"  @{ch['username']:25} | {title_safe:25} | {ch['subscribers']:>10,} podp.")

    print(f"\n[!] KANALY BEZ KOMMENTARIEV ({len(no_comments)}):")
    print("-" * 70)
    for ch in sorted(no_comments, key=lambda x: x["subscribers"], reverse=True):
        title_safe = ch['title'][:25].encode('ascii', 'replace').decode()
        print(f"  @{ch['username']:25} | {title_safe:25} | {ch['subscribers']:>10,} podp.")

    print(f"\n[X] NE NAIDENY ({len(not_found)}):")
    print("-" * 70)
    for username in not_found:
        print(f"  @{username}")

    # Сохраняем результаты в файл
    output_file = Path(__file__).parent.parent / "docs" / "VERIFIED_CHANNELS_RESULT.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Результаты проверки каналов\n\n")
        f.write(f"**Дата проверки:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        f.write(f"## ✅ Каналы с открытыми комментариями ({len(valid_channels)})\n\n")
        f.write("| Username | Название | Подписчиков |\n")
        f.write("|----------|----------|-------------|\n")
        for ch in sorted(valid_channels, key=lambda x: x["subscribers"], reverse=True):
            f.write(f"| @{ch['username']} | {ch['title']} | {ch['subscribers']:,} |\n")

        f.write(f"\n## ⚠️ Каналы без комментариев ({len(no_comments)})\n\n")
        f.write("| Username | Название | Подписчиков |\n")
        f.write("|----------|----------|-------------|\n")
        for ch in sorted(no_comments, key=lambda x: x["subscribers"], reverse=True):
            f.write(f"| @{ch['username']} | {ch['title']} | {ch['subscribers']:,} |\n")

        f.write(f"\n## ❌ Не найдены ({len(not_found)})\n\n")
        for username in not_found:
            f.write(f"- @{username}\n")

        # Быстрый список для копирования
        f.write("\n## Быстрый список (только валидные)\n\n```\n")
        for ch in valid_channels:
            f.write(f"{ch['username']}\n")
        f.write("```\n")

    logger.info(f"\nРезультаты сохранены в: {output_file}")

    print("\n" + "=" * 70)
    print("STATISTIKA")
    print("=" * 70)
    print(f"  Vsego provereno:           {len(CHANNELS_TO_VERIFY)}")
    print(f"  [OK] S kommentariyami:     {len(valid_channels)}")
    print(f"  [!] Bez kommentariev:      {len(no_comments)}")
    print(f"  [X] Ne naideny:            {len(not_found)}")


if __name__ == "__main__":
    asyncio.run(main())
