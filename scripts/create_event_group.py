"""
Create Event Group - Создание группы-мероприятия для инвайтов.

Использование:
    python scripts/create_event_group.py --account karina --template profession_2026

Или интерактивно:
    python scripts/create_event_group.py --account karina

Создаёт:
1. Супергруппу с нужным названием и описанием
2. Добавляет в БД для автоинвайтов
3. Настраивает оффер который опубликуется при N участниках
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from telethon import TelegramClient
from sqlalchemy import select

from traffic_engine.config import settings
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, InviteChat, Tenant
from traffic_engine.channels.chat_inviter.group_creator import GroupCreator, GROUP_TEMPLATES


async def get_client_for_account(account_name: str) -> tuple:
    """Получить Telethon клиент для аккаунта."""
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


async def get_tenant_id() -> int:
    """Получить ID тенанта."""
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error("Tenant 'infobusiness' not found!")
            sys.exit(1)
        return tenant.id


async def list_templates():
    """Показать доступные шаблоны."""
    print()
    print("=" * 60)
    print("ДОСТУПНЫЕ ШАБЛОНЫ ГРУПП")
    print("=" * 60)
    print()

    for key, template in GROUP_TEMPLATES.items():
        print(f"📌 {key}")
        print(f"   Название: {template['title']}")
        print(f"   Описание: {template['description'][:100]}...")
        print()

    print("=" * 60)


async def create_group_interactive(client: TelegramClient, tenant_id: int):
    """Интерактивное создание группы."""
    print()
    print("=" * 60)
    print("СОЗДАНИЕ ГРУППЫ-МЕРОПРИЯТИЯ")
    print("=" * 60)
    print()

    # Выбор шаблона или ручной ввод
    print("Выберите шаблон:")
    templates = list(GROUP_TEMPLATES.keys())
    for i, key in enumerate(templates, 1):
        print(f"  {i}. {GROUP_TEMPLATES[key]['title']}")
    print(f"  {len(templates) + 1}. Создать свой")
    print()

    choice = input("Выбор (номер): ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(templates):
            template = GROUP_TEMPLATES[templates[idx]]
            title = template["title"]
            description = template["description"]
            offer = template["offer"]
        else:
            # Ручной ввод
            title = input("Название группы: ").strip()
            print("Описание (Enter для завершения):")
            description = input().strip()
            print("Оффер (сообщение для публикации, Enter для пропуска):")
            offer = input().strip() or None
    except (ValueError, IndexError):
        logger.error("Неверный выбор")
        return

    # Подставляем ссылку на воронку
    if offer:
        offer = offer.replace("{funnel_link}", settings.infobusiness_funnel_link or "")

    # Порог публикации оффера
    threshold_input = input("При скольки участниках опубликовать оффер? [50]: ").strip()
    try:
        publish_at = int(threshold_input) if threshold_input else 50
    except ValueError:
        publish_at = 50

    print()
    print("Создаю группу...")
    print(f"  Название: {title}")
    print(f"  Публикация оффера при: {publish_at} участниках")
    print()

    # Создаём
    creator = GroupCreator()
    result = await creator.create_megagroup(
        client=client,
        title=title,
        description=description,
        tenant_id=tenant_id,
        offer_message=offer,
        publish_offer_at=publish_at,
    )

    if result:
        print()
        print("=" * 60)
        print("✅ ГРУППА СОЗДАНА!")
        print("=" * 60)
        print(f"ID:      {result.chat_id}")
        print(f"Название: {result.title}")
        if result.invite_link:
            print(f"Ссылка:  {result.invite_link}")
        print()
        print("Группа добавлена в БД для автоинвайтов.")
        print("Запустите систему и она начнёт приглашать людей из ЦА.")
        print("=" * 60)
    else:
        print()
        print("❌ Не удалось создать группу")


async def create_group_from_template(
    client: TelegramClient,
    tenant_id: int,
    template_name: str,
    publish_at: int = 50,
):
    """Создать группу из шаблона."""
    if template_name not in GROUP_TEMPLATES:
        logger.error(f"Template '{template_name}' not found!")
        await list_templates()
        return

    template = GROUP_TEMPLATES[template_name]
    title = template["title"]
    description = template["description"]
    offer = template["offer"].replace("{funnel_link}", settings.infobusiness_funnel_link or "")

    logger.info(f"Creating group from template: {template_name}")
    logger.info(f"Title: {title}")

    creator = GroupCreator()
    result = await creator.create_megagroup(
        client=client,
        title=title,
        description=description,
        tenant_id=tenant_id,
        offer_message=offer,
        publish_offer_at=publish_at,
    )

    if result:
        logger.info(f"✅ Group created: {result.title} (ID: {result.chat_id})")
        return result
    else:
        logger.error("Failed to create group")
        return None


async def list_existing_groups():
    """Показать существующие группы."""
    async with get_session() as session:
        result = await session.execute(select(InviteChat))
        chats = result.scalars().all()

    if not chats:
        print()
        print("Нет созданных групп для инвайтов.")
        return

    print()
    print("=" * 60)
    print("СУЩЕСТВУЮЩИЕ ГРУППЫ ДЛЯ ИНВАЙТОВ")
    print("=" * 60)
    print()

    for chat in chats:
        status = "✅ Активна" if chat.is_active else "❌ Неактивна"
        offer_status = "📨 Оффер опубликован" if chat.offer_published else f"⏳ Ждём {chat.publish_offer_at_members} участников"

        print(f"📌 {chat.title}")
        print(f"   ID: {chat.chat_id}")
        print(f"   Статус: {status}")
        print(f"   Инвайтов: {chat.total_invited}")
        print(f"   Вступило: {chat.total_joined}")
        print(f"   {offer_status}")
        print()

    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="Создание группы-мероприятия для инвайтов",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:

  # Интерактивный режим
  python scripts/create_event_group.py --account karina

  # Из шаблона
  python scripts/create_event_group.py --account karina --template profession_2026

  # Показать шаблоны
  python scripts/create_event_group.py --list-templates

  # Показать существующие группы
  python scripts/create_event_group.py --list-groups
        """
    )

    parser.add_argument("--account", help="Имя аккаунта для создания группы")
    parser.add_argument("--template", help="Шаблон группы (profession_2026, remote_income, online_business)")
    parser.add_argument("--publish-at", type=int, default=50, help="При скольки участниках публиковать оффер")
    parser.add_argument("--list-templates", action="store_true", help="Показать доступные шаблоны")
    parser.add_argument("--list-groups", action="store_true", help="Показать существующие группы")

    args = parser.parse_args()

    if args.list_templates:
        await list_templates()
        return

    if args.list_groups:
        await list_existing_groups()
        return

    if not args.account:
        parser.error("--account is required for creating groups")
        return

    # Получаем клиент
    client, account = await get_client_for_account(args.account)

    if not client:
        return

    try:
        tenant_id = await get_tenant_id()

        if args.template:
            await create_group_from_template(
                client,
                tenant_id,
                args.template,
                args.publish_at,
            )
        else:
            await create_group_interactive(client, tenant_id)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
