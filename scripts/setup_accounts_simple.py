#!/usr/bin/env python
"""
Простое добавление 4 аккаунтов в БД.

Добавляет записи с минимальной информацией.
Session string оставляем пустым - AccountManager будет читать из .session файлов.
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
        "bio": "кислый, но полезный 🍋",
    },
    {
        "phone": "+380950182983",  # Карина
        "username": "karinko_o",
        "first_name": "Карина",
        "last_name": None,
        "bio": "планирую всё, делаю половину",
    },
    {
        "phone": "+380950182098",  # Люба
        "username": "lyuba_ok",
        "first_name": "Люба",
        "last_name": None,
        "bio": "обещала себе вставать в 7... не получается",
    },
    {
        "phone": "+380950182910",  # Кира
        "username": "kirushka_94",
        "first_name": "Кира",
        "last_name": None,
        "bio": "мечты большие, будильник громкий",
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
            # session_string оставляем пустым - будем читать из .session файлов
            account = UserBotAccount(
                tenant_id=tenant.id,
                phone=acc_data["phone"],
                session_string="",  # Пустая строка - AccountManager прочитает из .session файла
                username=acc_data["username"],
                first_name=acc_data["first_name"],
                last_name=acc_data["last_name"],
                bio=acc_data["bio"],
                status="warming",  # Начинаем с warming (прогрев)
                warmup_completed=False,
            )

            session.add(account)
            logger.success(
                f"Добавлен: {acc_data['first_name']} (@{acc_data['username']}) "
                f"- статус: warming (прогрев)"
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
                UserBotAccount.tenant_id == tenant.id
            )
        )
        all_accounts = result.scalars().all()

        logger.info(f"\nВсего активных аккаунтов для {tenant.name}: {len(all_accounts)}")
        for acc in all_accounts:
            logger.info(
                f"  - {acc.first_name} (@{acc.username}) - "
                f"статус: {acc.status}"
            )

        logger.info("\n✅ Готово! Теперь добавьте каналы: python scripts\\setup_channels.py")


if __name__ == "__main__":
    asyncio.run(main())
