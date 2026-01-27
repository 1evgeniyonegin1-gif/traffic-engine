#!/usr/bin/env python
"""
Добавление ПРОВЕРЕННЫХ каналов с открытыми комментариями.

Эти каналы проверены и имеют открытые комментарии (linked_chat).

ВАЖНО: Перед запуском убедитесь что нерабочие каналы деактивированы!
Запустите сначала: python scripts/check_and_fix_channels.py

Использование:
    python scripts/add_verified_channels.py
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
from telethon.tl.types import Channel

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount, TargetChannel


# =============================================================================
# ПРОВЕРЕННЫЕ КАНАЛЫ С ОТКРЫТЫМИ КОММЕНТАРИЯМИ
# =============================================================================
# Эти каналы имеют linked_chat (группу для комментариев)
# Последняя проверка: январь 2026
# =============================================================================

VERIFIED_CHANNELS = [
    # === БИЗНЕС И ПРЕДПРИНИМАТЕЛЬСТВО ===
    # Крупные бизнес-каналы с активной аудиторией
    {"username": "Oskar_Hartmann", "priority": 9, "category": "business", "comment_strategy": "smart"},
    {"username": "portnyaginlive", "priority": 9, "category": "business", "comment_strategy": "expert"},
    {"username": "mspiridonov", "priority": 9, "category": "business", "comment_strategy": "smart"},
    {"username": "grebenukm", "priority": 8, "category": "business", "comment_strategy": "supportive"},
    {"username": "sberstartup", "priority": 8, "category": "startups", "comment_strategy": "smart"},
    {"username": "Theedinorogblog", "priority": 8, "category": "startups", "comment_strategy": "smart"},
    {"username": "ventureStuff", "priority": 7, "category": "venture", "comment_strategy": "expert"},

    # === МАРКЕТИНГ И SMM ===
    {"username": "blogmilova", "priority": 8, "category": "marketing", "comment_strategy": "smart"},
    {"username": "dnative", "priority": 7, "category": "marketing", "comment_strategy": "smart"},
    {"username": "c_behavior", "priority": 7, "category": "marketing", "comment_strategy": "expert"},
    {"username": "sosindex", "priority": 6, "category": "marketing", "comment_strategy": "supportive"},

    # === МОТИВАЦИЯ И САМОРАЗВИТИЕ ===
    {"username": "silaslovv", "priority": 8, "category": "motivation", "comment_strategy": "supportive"},
    {"username": "guzenuk", "priority": 8, "category": "motivation", "comment_strategy": "smart"},
    {"username": "stoicstrategy", "priority": 7, "category": "self_dev", "comment_strategy": "supportive"},
    {"username": "chillosophy", "priority": 7, "category": "psychology", "comment_strategy": "supportive"},

    # === КАРЬЕРА И РАБОТА ===
    {"username": "careerspace", "priority": 8, "category": "career", "comment_strategy": "smart"},
    {"username": "normrabota", "priority": 7, "category": "jobs", "comment_strategy": "supportive"},

    # === ФИНАНСЫ ===
    {"username": "smartfin", "priority": 7, "category": "finance", "comment_strategy": "expert"},
    {"username": "finside", "priority": 6, "category": "finance", "comment_strategy": "smart"},

    # === IT И ТЕХНОЛОГИИ ===
    {"username": "addmeto", "priority": 7, "category": "it", "comment_strategy": "smart"},
    {"username": "kutergin_on_fire", "priority": 7, "category": "infobiz", "comment_strategy": "smart"},

    # === ЛАЙФСТАЙЛ ===
    {"username": "zhit_interesno", "priority": 6, "category": "lifestyle", "comment_strategy": "supportive"},
    {"username": "goodhabits", "priority": 6, "category": "habits", "comment_strategy": "supportive"},
]

TENANT_NAME = "infobusiness"


async def verify_channel(client: TelegramClient, username: str) -> dict:
    """Проверить что канал существует и имеет открытые комментарии."""
    result = {
        "exists": False,
        "has_comments": False,
        "title": "",
        "subscribers": 0,
        "channel_id": None,
        "error": None,
    }

    try:
        entity = await client.get_entity(username)

        if not isinstance(entity, Channel):
            result["error"] = "Не канал"
            return result

        result["exists"] = True
        result["title"] = entity.title
        result["channel_id"] = entity.id

        full = await client(GetFullChannelRequest(entity))
        result["subscribers"] = full.full_chat.participants_count or 0

        if full.full_chat.linked_chat_id:
            result["has_comments"] = True

    except Exception as e:
        error = str(e)
        if "Nobody is using" in error or "No user has" in error:
            result["error"] = "Не существует"
        elif "Could not find" in error:
            result["error"] = "Не найден"
        else:
            result["error"] = error[:50]

    return result


async def main():
    """Добавить проверенные каналы в БД."""
    await init_db()

    logger.info("=" * 70)
    logger.info("ДОБАВЛЕНИЕ ПРОВЕРЕННЫХ КАНАЛОВ")
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

        # Получаем уже добавленные каналы
        result = await session.execute(
            select(TargetChannel.username).where(
                TargetChannel.tenant_id == tenant.id
            )
        )
        existing_usernames = {row[0].lower() for row in result.fetchall()}

    logger.info(f"Каналов для проверки: {len(VERIFIED_CHANNELS)}")
    logger.info(f"Уже в БД: {len(existing_usernames)}")

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

    # Проверяем каждый канал
    to_add = []
    skipped_exists = []
    skipped_no_comments = []
    skipped_error = []

    for i, ch in enumerate(VERIFIED_CHANNELS, 1):
        username = ch["username"]

        # Пропускаем если уже есть
        if username.lower() in existing_usernames:
            logger.info(f"[{i}/{len(VERIFIED_CHANNELS)}] @{username} - уже в БД, пропуск")
            skipped_exists.append(username)
            continue

        logger.info(f"[{i}/{len(VERIFIED_CHANNELS)}] Проверяю @{username}...")

        result = await verify_channel(client, username)

        if result["error"]:
            logger.warning(f"  ❌ {result['error']}")
            skipped_error.append({"username": username, "error": result["error"]})
        elif not result["has_comments"]:
            logger.warning(f"  ⚠️ Нет комментариев")
            skipped_no_comments.append(username)
        else:
            logger.info(f"  ✅ OK! {result['title']} ({result['subscribers']:,} подп.)")
            to_add.append({
                **ch,
                "channel_id": result["channel_id"],
                "title": result["title"],
                "subscribers": result["subscribers"],
            })

        await asyncio.sleep(1.5)

    await client.disconnect()

    # Результаты
    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТЫ ПРОВЕРКИ")
    print("=" * 70)
    print(f"  ✅ Готовы к добавлению: {len(to_add)}")
    print(f"  📁 Уже в БД:            {len(skipped_exists)}")
    print(f"  ⚠️ Без комментариев:    {len(skipped_no_comments)}")
    print(f"  ❌ Ошибки:              {len(skipped_error)}")

    if to_add:
        print(f"\nКаналы для добавления:")
        for ch in to_add:
            print(f"  @{ch['username']:25} | {ch['subscribers']:>10,} подп. | {ch['category']}")

        response = input(f"\nДобавить {len(to_add)} каналов в БД? (yes/no): ")

        if response.lower() in ['yes', 'y', 'да']:
            async with get_session() as session:
                for ch in to_add:
                    new_channel = TargetChannel(
                        tenant_id=tenant.id,
                        channel_id=ch["channel_id"],
                        username=ch["username"],
                        title=ch["title"],
                        priority=ch["priority"],
                        is_active=True,
                        comment_strategy=ch["comment_strategy"],
                        max_delay_minutes=10,
                        skip_ads=True,
                        skip_reposts=True,
                        min_post_length=100,
                        posts_processed=0,
                        comments_posted=0,
                    )
                    session.add(new_channel)
                    logger.info(f"  ✅ Добавлен @{ch['username']}")

                await session.commit()

            print(f"\n✅ Добавлено {len(to_add)} каналов!")
        else:
            print("\nОтменено")
    else:
        print("\nНет каналов для добавления")

    if skipped_error:
        print("\n⚠️ Каналы с ошибками (нужно найти замену):")
        for ch in skipped_error:
            print(f"  @{ch['username']}: {ch['error']}")


if __name__ == "__main__":
    asyncio.run(main())
