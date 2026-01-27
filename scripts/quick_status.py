"""Быстрая проверка статуса системы"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.database import get_session
from sqlalchemy import text


async def main():
    async with get_session() as db:
        # Аккаунты
        result = await db.execute(text("SELECT COUNT(*) FROM traffic_userbot_accounts WHERE status='active'"))
        print(f"Активных аккаунтов: {result.scalar()}")

        # Каналы
        result = await db.execute(text("SELECT COUNT(*) FROM traffic_target_channels WHERE is_active=true"))
        print(f"Активных каналов: {result.scalar()}")

        # ЦА
        result = await db.execute(text("SELECT COUNT(*) FROM traffic_target_audience"))
        print(f"Пользователей в ЦА: {result.scalar()}")

        # Действия
        result = await db.execute(text("SELECT COUNT(*) FROM traffic_actions WHERE action_type='story_view'"))
        print(f"Story views: {result.scalar()}")


if __name__ == "__main__":
    asyncio.run(main())
