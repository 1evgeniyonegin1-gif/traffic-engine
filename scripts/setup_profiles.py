#!/usr/bin/env python
"""
Setup account profiles with personal channels.

Создаёт личные каналы для каждого аккаунта и публикует посты.
Использует Telethon (не Pyrogram).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.channels import CreateChannelRequest, ExportMessageLinkRequest
from telethon.tl.functions.messages import UpdatePinnedMessageRequest, ExportChatInviteRequest
from telethon.tl.types import Channel
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session, init_db
from traffic_engine.database.models import UserBotAccount, Tenant


# ============ НАСТРОЙКИ ПРОФИЛЕЙ ============

PROFILES = [
    {
        "phone": "+380954967658",  # Карина
        "first_name": "Карина",
        "last_name": "| Бесплатный урок 🎁",
        "channel_title": "Урок от Карины",
        "channel_description": "Здесь вы найдёте схему заработка на коротких видео!",
        "bot_link": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg",
        "avatar": "img.jpg",
    },
    {
        "phone": "+380955300455",  # Кіра
        "first_name": "Кира",
        "last_name": "| Дарю схему 🔥",
        "channel_title": "Схема от Киры",
        "channel_description": "Здесь вы найдёте схему заработка на коротких видео!",
        "bot_link": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg1",
        "avatar": "img (1).jpg",
    },
    {
        "phone": "+380955161146",  # Люба
        "first_name": "Люба",
        "last_name": "| Забирай гайд 💰",
        "channel_title": "Гайд от Любы",
        "channel_description": "Здесь вы найдёте схему заработка на коротких видео!",
        "bot_link": "https://t.me/Artemtime_bot?start=tdvideo_ref_661551295_tg2",
        "avatar": "img (2).jpg",
    },
]

# Посты для каналов (скопированы из Transform Republic)
POSTS = [
    # Пост 1 - Закреплённый (главный)
    """🎬 Смотришь короткие видео и завидуешь авторам?

Тайна их заработка — в одном переходе...

👇 Жми и забирай бесплатный урок:
{bot_link}""",

    # Пост 2 - Успехи
    """🔥 РУБРИКА: УСПЕХИ

Вот что пишут ребята, которые уже в теме:

💬 "За год заработал 1.000.000₽ на коротких видео. Последняя выплата — 138.000₽"

Хочешь также? 👇
{bot_link}""",

    # Пост 3 - Алгоритм
    """📱 Алгоритм — не хаос, а система.

3 шага к заработку на видео:
1️⃣ Понять как работают алгоритмы
2️⃣ Создать контент по готовым шаблонам
3️⃣ Получать деньги за просмотры

Всё это я даю БЕСПЛАТНО 👇
{bot_link}""",
]


async def setup_account(account: UserBotAccount, profile: dict) -> bool:
    """Setup single account profile and channel."""

    logger.info(f"\n{'='*50}")
    logger.info(f"Настройка аккаунта: {account.phone}")
    logger.info(f"{'='*50}")

    client = TelegramClient(
        StringSession(account.session_string),
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            logger.error(f"Account {account.phone} is not authorized!")
            return False

        me = await client.get_me()
        logger.info(f"Подключено: {me.first_name} (ID: {me.id})")

        # 1. Обновляем имя профиля
        logger.info(f"Обновляю имя на: {profile['first_name']} {profile['last_name']}")
        await client(UpdateProfileRequest(
            first_name=profile["first_name"],
            last_name=profile["last_name"],
        ))
        logger.info("OK - Имя обновлено")

        # 1.5 Устанавливаем аватарку
        if profile.get("avatar"):
            avatar_path = Path(__file__).parent.parent / "avatars" / profile["avatar"]
            if avatar_path.exists():
                logger.info(f"Устанавливаю аватарку: {profile['avatar']}")
                try:
                    file = await client.upload_file(str(avatar_path))
                    await client(UploadProfilePhotoRequest(file=file))
                    logger.info("OK - Аватарка установлена")
                except Exception as e:
                    logger.warning(f"Не удалось установить аватарку: {e}")
            else:
                logger.warning(f"Файл аватарки не найден: {avatar_path}")

        # 2. Создаём или находим канал
        logger.info(f"Ищу/создаю канал: {profile['channel_title']}")
        channel = None
        channel_id = None

        # Сначала ищем существующий канал
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, Channel):
                if profile["first_name"].lower() in dialog.entity.title.lower():
                    channel = dialog.entity
                    channel_id = dialog.entity.id
                    logger.info(f"Найден существующий канал: {dialog.entity.title}")
                    break

        # Если не нашли - создаём
        if not channel:
            try:
                result = await client(CreateChannelRequest(
                    title=profile["channel_title"],
                    about=profile["channel_description"],
                    megagroup=False  # channel, not supergroup
                ))
                channel = result.chats[0]
                channel_id = channel.id
                logger.info(f"OK - Channel created: {channel.title} (ID: {channel_id})")
            except Exception as e:
                if "CHANNELS_TOO_MUCH" in str(e):
                    logger.warning("Достигнут лимит каналов!")
                    return False
                else:
                    raise e

        # 3. Публикуем посты
        bot_link = profile["bot_link"]
        logger.info(f"Реферальная ссылка: {bot_link}")

        pinned_message_id = None
        for i, post_template in enumerate(POSTS):
            post_text = post_template.format(bot_link=bot_link)
            msg = await client.send_message(channel, post_text)
            logger.info(f"OK - Post {i+1} published")

            # Первый пост закрепляем
            if i == 0:
                pinned_message_id = msg.id

        # 4. Закрепляем первый пост
        if pinned_message_id:
            try:
                await client.pin_message(channel, pinned_message_id)
                logger.info("OK - Post pinned")
            except Exception as e:
                logger.warning(f"Не удалось закрепить пост: {e}")

        # 5. Получаем ссылку на канал
        try:
            invite = await client(ExportChatInviteRequest(peer=channel))
            invite_link = invite.link
            logger.info(f"Channel link: {invite_link}")
        except:
            invite_link = f"Канал: {profile['channel_title']}"

        logger.info(f"=== ACCOUNT {profile['first_name']} DONE ===")
        logger.info(f"Name: {profile['first_name']} {profile['last_name']}")
        logger.info(f"Channel: {profile['channel_title']}")
        logger.info(f"Link: {invite_link}")
        logger.info(f"Telegram ID: {me.id}")
        logger.info(f"Profile link: https://t.me/user?id={me.id}")
        logger.info("NOTE: Attach channel to profile manually in Telegram settings!")

        return True

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            await client.disconnect()
        except:
            pass


async def main():
    """Main function."""
    print("\n=== SETUP PROFILES ===\n")

    # Check API credentials
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        logger.error("TELEGRAM_API_ID и TELEGRAM_API_HASH не настроены в .env!")
        sys.exit(1)

    # Initialize database
    await init_db()

    # Get accounts
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.status.in_(["active", "warming"])
            )
        )
        accounts = result.scalars().all()

    if not accounts:
        logger.error("Нет аккаунтов в базе!")
        sys.exit(1)

    logger.info(f"Найдено {len(accounts)} аккаунтов")

    # Match accounts with profiles
    success = 0
    account_info = []

    for account in accounts:
        # Find matching profile
        profile = None
        for p in PROFILES:
            if p["phone"] == account.phone:
                profile = p
                break

        if not profile:
            logger.warning(f"Профиль для {account.phone} не найден, пропускаю")
            continue

        if await setup_account(account, profile):
            success += 1
            account_info.append(profile)

        # Delay between accounts
        await asyncio.sleep(3)

    print(f"""
╔══════════════════════════════════════════════════════════╗
║     ГОТОВО! Настроено {success}/{len(accounts)} аккаунтов
╠══════════════════════════════════════════════════════════╣
║
║     ⚠️  НЕ ЗАБУДЬ:
║     Для каждого аккаунта вручную прикрепи канал:
║
║     Telegram → Настройки → Редактировать профиль
║     → "Личный канал" → Выбрать созданный канал
║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    asyncio.run(main())
