"""
Тестовая отправка комментария через Telethon.

Этот скрипт:
1. Авторизует аккаунт (попросит номер телефона и код)
2. Найдёт последний пост в целевом канале
3. Отправит комментарий
4. Выведет ссылку на комментарий
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from traffic_engine.config import settings

# Целевой канал для теста (с открытыми комментами)
# Можно заменить на любой канал с комментариями
TARGET_CHANNEL = "lentachold"  # канал с комментариями

# Данные аккаунта
SESSION_NAME = "sessions/account1"
ACCOUNT_NAME = "LIME"


async def main():
    print(f"=== Тест отправки комментария ===\n")
    print(f"Аккаунт: {ACCOUNT_NAME}")
    print(f"Канал: @{TARGET_CHANNEL}\n")

    # Создаём папку для сессий
    os.makedirs("sessions", exist_ok=True)

    # Создаём клиент
    client = TelegramClient(
        SESSION_NAME,
        settings.telegram_api_id,
        settings.telegram_api_hash
    )

    await client.start()
    me = await client.get_me()
    print(f"Авторизован как: {me.first_name} (@{me.username})\n")

    # Получаем канал
    try:
        channel = await client.get_entity(TARGET_CHANNEL)
        print(f"Канал найден: {channel.title}")
    except Exception as e:
        print(f"Ошибка: не могу найти канал @{TARGET_CHANNEL}")
        print(f"Детали: {e}")
        await client.disconnect()
        return

    # Получаем последние посты
    messages = await client.get_messages(channel, limit=5)

    # Ищем пост с комментариями
    target_post = None
    for msg in messages:
        if msg.replies and msg.replies.replies > 0:
            target_post = msg
            break

    if not target_post:
        # Берём просто последний пост
        target_post = messages[0] if messages else None

    if not target_post:
        print("Нет постов в канале")
        await client.disconnect()
        return

    print(f"\nПост #{target_post.id}:")
    print(f"  Текст: {target_post.text[:100]}..." if target_post.text else "  [медиа]")
    print(f"  Комментариев: {target_post.replies.replies if target_post.replies else 0}")

    # Генерируем комментарий
    # Простой тестовый коммент
    comment_text = "интересно, а как долго ты к этому шёл?"

    print(f"\nОтправляю комментарий: {comment_text}")

    try:
        # Получаем discussion (чат для комментариев)
        discussion = await client(GetDiscussionMessageRequest(
            peer=channel,
            msg_id=target_post.id
        ))

        # Отправляем комментарий
        result = await client.send_message(
            discussion.chats[0],
            comment_text,
            reply_to=discussion.messages[0].id
        )

        # Формируем ссылку
        # Для публичных каналов: t.me/channel/post_id?comment=comment_id
        comment_link = f"https://t.me/{TARGET_CHANNEL}/{target_post.id}?comment={result.id}"

        print(f"\n{'='*50}")
        print(f"КОММЕНТАРИЙ ОТПРАВЛЕН!")
        print(f"{'='*50}")
        print(f"Ссылка: {comment_link}")
        print(f"{'='*50}")

    except Exception as e:
        print(f"\nОшибка при отправке: {e}")
        print("\nВозможные причины:")
        print("- У канала отключены комментарии")
        print("- Нужно сначала подписаться на канал")
        print("- Канал ограничил кто может комментировать")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
