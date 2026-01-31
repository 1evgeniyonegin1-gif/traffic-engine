"""
Group Creator - Создание групп-мероприятий.

Автоматическое создание групп:
1. Создаём группу с названием "Новая профессия 2026" и т.п.
2. Настраиваем описание
3. Добавляем в БД для инвайтов
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditPhotoRequest,
    EditTitleRequest,
    ToggleJoinToSendRequest,
)
from telethon.tl.functions.messages import (
    CreateChatRequest,
    EditChatAboutRequest,
    EditChatTitleRequest,
)
from telethon.tl.types import (
    InputChatUploadedPhoto,
    InputPeerChannel,
)
from telethon.errors import FloodWaitError

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import InviteChat


class GroupCreator:
    """
    Создание групп-мероприятий для инвайтов.

    Варианты:
    1. Megagroup (супергруппа) - до 200k участников
    2. Обычная группа - до 200 участников

    Для инвайтов лучше супергруппа.
    """

    async def create_megagroup(
        self,
        client: TelegramClient,
        title: str,
        description: str,
        tenant_id: int,
        offer_message: Optional[str] = None,
        publish_offer_at: int = 50,
    ) -> Optional[InviteChat]:
        """
        Создать супергруппу для инвайтов.

        Args:
            client: Telethon клиент
            title: Название группы
            description: Описание группы
            tenant_id: ID тенанта
            offer_message: Сообщение-оффер для публикации
            publish_offer_at: При скольки участниках публиковать оффер

        Returns:
            InviteChat или None при ошибке
        """
        try:
            logger.info(f"🔨 Creating megagroup: {title}")

            # 1. Создаём супергруппу (megagroup=True)
            result = await client(CreateChannelRequest(
                title=title,
                about=description,
                megagroup=True,  # Это делает её супергруппой
                for_import=False,
            ))

            # Получаем созданную группу
            chat = result.chats[0]
            chat_id = chat.id

            logger.info(f"✅ Megagroup created: {title} (ID: {chat_id})")

            # 2. Опционально: разрешить отправку без одобрения
            try:
                await client(ToggleJoinToSendRequest(
                    channel=chat,
                    enabled=False,  # Не требовать одобрения
                ))
            except Exception as e:
                logger.debug(f"Could not toggle join settings: {e}")

            # 3. Получить invite link
            invite_link = None
            try:
                full_chat = await client.get_entity(chat_id)
                if hasattr(full_chat, "username") and full_chat.username:
                    invite_link = f"https://t.me/{full_chat.username}"
            except Exception as e:
                logger.debug(f"Could not get invite link: {e}")

            # 4. Сохранить в БД
            async with get_session() as session:
                invite_chat = InviteChat(
                    tenant_id=tenant_id,
                    chat_id=chat_id,
                    title=title,
                    invite_link=invite_link,
                    is_active=True,
                    offer_message=offer_message,
                    publish_offer_at_members=publish_offer_at,
                )
                session.add(invite_chat)
                await session.commit()
                await session.refresh(invite_chat)

            logger.info(f"✅ Megagroup saved to DB: {title}")
            return invite_chat

        except FloodWaitError as e:
            logger.warning(f"FloodWait creating group: {e.seconds}s")
            raise

        except Exception as e:
            logger.error(f"❌ Error creating megagroup: {e}")
            return None

    async def set_group_photo(
        self,
        client: TelegramClient,
        chat_id: int,
        photo_path: str,
    ) -> bool:
        """
        Установить фото группы.

        Args:
            client: Telethon клиент
            chat_id: ID группы
            photo_path: Путь к файлу фото

        Returns:
            True если успешно
        """
        try:
            chat_entity = await client.get_entity(chat_id)

            # Загружаем фото
            file = await client.upload_file(photo_path)

            await client(EditPhotoRequest(
                channel=chat_entity,
                photo=InputChatUploadedPhoto(file=file),
            ))

            logger.info(f"✅ Photo set for chat {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to set photo: {e}")
            return False

    async def update_group_info(
        self,
        client: TelegramClient,
        chat_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Обновить информацию о группе.

        Args:
            client: Telethon клиент
            chat_id: ID группы
            title: Новое название
            description: Новое описание

        Returns:
            True если успешно
        """
        try:
            chat_entity = await client.get_entity(chat_id)

            if title:
                await client(EditTitleRequest(
                    channel=chat_entity,
                    title=title,
                ))
                logger.info(f"✅ Title updated: {title}")

            if description:
                # Для супергрупп используем EditChatAboutRequest
                await client(EditChatAboutRequest(
                    peer=chat_entity,
                    about=description,
                ))
                logger.info(f"✅ Description updated")

            # Обновляем в БД
            if title:
                async with get_session() as session:
                    from sqlalchemy import select
                    result = await session.execute(
                        select(InviteChat).where(InviteChat.chat_id == chat_id)
                    )
                    chat = result.scalar_one_or_none()
                    if chat:
                        chat.title = title
                        await session.commit()

            return True

        except Exception as e:
            logger.error(f"Failed to update group info: {e}")
            return False


# Шаблоны групп для инфобизнеса
GROUP_TEMPLATES = {
    "profession_2026": {
        "title": "🚀 Новая профессия 2026",
        "description": """Канал для тех, кто хочет освоить востребованную профессию и выйти на доход от 100К.

📌 Что внутри:
• Разборы реальных кейсов
• Пошаговые инструкции
• Ответы на вопросы

Присоединяйся, скоро начнём!""",
        "offer": """🔥 СТАРТ через 24 часа!

Бесплатный мастер-класс "Как начать зарабатывать от 100К на удалёнке"

👉 Регистрация: {funnel_link}

Места ограничены! ⏰""",
    },

    "remote_income": {
        "title": "💰 Удалённый заработок 2026",
        "description": """Сообщество для тех, кто хочет зарабатывать из дома.

Без опыта | Без вложений | С нуля до результата

Присоединяйся!""",
        "offer": """⚡️ ВНИМАНИЕ!

Запускаем бесплатный интенсив "Первые 50К за месяц"

✅ Практика с первого дня
✅ Без сложных навыков
✅ Поддержка куратора

👉 Записаться: {funnel_link}""",
    },

    "online_business": {
        "title": "🎯 Онлайн-бизнес с нуля",
        "description": """Строим бизнес в интернете вместе.

От идеи до первых продаж за 30 дней.

Присоединяйся к сообществу!""",
        "offer": """🎁 ПОДАРОК для участников группы!

Бесплатный гайд "5 способов заработать первые 30К онлайн"

+ Приглашение на закрытый вебинар

👉 Забрать: {funnel_link}""",
    },
}
