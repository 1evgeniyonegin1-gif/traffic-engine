#!/usr/bin/env python
"""
Добавить 4 аккаунта в базу данных для инфобизнеса.

Аккаунты:
1. Лёша Лаймов (@lemonlime192) - account1.session
2. Карина (@karinko_o) - karina.session
3. Люба (@lyuba_ok) - ua_account1.session
4. Кира (@kirushka_94) - ua_account2.session
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from loguru import logger

from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant, UserBotAccount


# Данные аккаунтов
ACCOUNTS = [
    {
        "phone": "+380950182582",  # Лёша
        "username": "lemonlime192",
        "first_name": "Лёша",
        "last_name": "Лаймов",
        "session_name": "account1",
        "bio": "кислый, но полезный 🍋",
        "status": "active",
    },
    {
        "phone": "+380950182983",  # Карина
        "username": "karinko_o",
        "first_name": "Карина",
        "last_name": None,
        "session_name": "karina",
        "bio": "планирую всё, делаю половину",
        "status": "active",
    },
    {
        "phone": "+380950182098",  # Люба
        "username": "lyuba_ok",
        "first_name": "Люба",
        "last_name": None,
        "session_name": "ua_account1",
        "bio": "обещала себе вставать в 7... не получается",
        "status": "active",
    },
    {
        "phone": "+380950182910",  # Кира
        "username": "kirushka_94",
        "first_name": "Кира",
        "last_name": None,
        "session_name": "ua_account2",
        "bio": "мечты большие, будильник громкий",
        "status": "active",
    },
]


async def main():
    """Добавить аккаунты в БД."""

    logger.info("=== Настройка аккаунтов для Traffic Engine ===\n")

    # Инициализация БД
    await init_db()
    logger.info("БД инициализирована")

    async with get_session() as session:
        # Находим тенанта infobusiness
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            logger.error("Тенант 'infobusiness' не найден!")
            logger.info("Сначала запустите: python scripts/init_db.py")
            return

        logger.info(f"Тенант найден: {tenant.display_name}\n")

        # Добавляем аккаунты
        added = 0
        for acc_data in ACCOUNTS:
            # Проверяем, есть ли уже
            result = await session.execute(
                select(UserBotAccount).where(
                    UserBotAccount.phone == acc_data["phone"]
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.warning(
                    f"Аккаунт {acc_data['first_name']} (@{acc_data['username']}) "
                    f"уже существует - пропускаю"
                )
                continue

            # Создаём новый аккаунт
            account = UserBotAccount(
                tenant_id=tenant.id,
                phone=acc_data["phone"],
                username=acc_data["username"],
                first_name=acc_data["first_name"],
                last_name=acc_data["last_name"],
                session_name=acc_data["session_name"],
                bio=acc_data["bio"],
                status=acc_data["status"],
                is_active=True,
            )

            session.add(account)
            logger.success(
                f"Добавлен: {acc_data['first_name']} (@{acc_data['username']}) "
                f"- {acc_data['session_name']}.session"
            )
            added += 1

        if added > 0:
            await session.commit()
            logger.success(f"\n✅ Добавлено аккаунтов: {added}")
        else:
            logger.info("\n✅ Все аккаунты уже были добавлены")

        # Показываем статистику
        result = await session.execute(
            select(UserBotAccount).where(
                UserBotAccount.tenant_id == tenant.id,
                UserBotAccount.is_active == True,
            )
        )
        all_accounts = result.scalars().all()

        logger.info(f"\nВсего активных аккаунтов для {tenant.name}: {len(all_accounts)}")
        for acc in all_accounts:
            logger.info(
                f"  - {acc.first_name} (@{acc.username}) - "
                f"сессия: {acc.session_name}.session"
            )

        logger.info("\n✅ Готово! Теперь можно запускать: python run_auto_comments.py")


if __name__ == "__main__":
    asyncio.run(main())
