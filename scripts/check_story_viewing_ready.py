#!/usr/bin/env python
"""
Проверка готовности системы к запуску Story Viewing.

Проверяет:
1. Наличие ЦА с высоким quality_score
2. Наличие активных аккаунтов
3. Настройки в .env
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from loguru import logger

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import TargetAudience, UserBotAccount


async def check_target_audience():
    """Проверить наличие ЦА."""
    print("\n" + "="*60)
    print("1. ПРОВЕРКА ЦЕЛЕВОЙ АУДИТОРИИ")
    print("="*60)

    async with get_session() as session:
        # Всего пользователей ЦА
        result = await session.execute(
            select(func.count(TargetAudience.id))
        )
        total = result.scalar()
        print(f"   Всего пользователей в ЦА: {total}")

        # С высоким quality_score
        min_score = settings.story_view_min_quality_score
        result = await session.execute(
            select(func.count(TargetAudience.id))
            .where(
                TargetAudience.quality_score >= min_score,
                TargetAudience.status.in_(["new", "contacted"])
            )
        )
        high_quality = result.scalar()
        print(f"   С quality_score >= {min_score}: {high_quality}")

        if high_quality == 0:
            print("\n   [X] ОШИБКА: Нет пользователей с высоким quality_score!")
            print(f"   Требуется минимум 10-20 пользователей с quality_score >= {min_score}")
            print("\n   Решение:")
            print("   1. Запустить систему на 2-3 часа для сбора ЦА через комментирование")
            print("   2. Или временно понизить STORY_VIEW_MIN_QUALITY_SCORE в .env")
            return False

        # По источникам
        result = await session.execute(
            select(
                TargetAudience.source_type,
                func.count(TargetAudience.id)
            )
            .where(TargetAudience.quality_score >= min_score)
            .group_by(TargetAudience.source_type)
        )

        print(f"\n   Распределение по источникам (quality >= {min_score}):")
        for source, count in result:
            print(f"     - {source}: {count}")

        print(f"\n   [OK] Готово к запуску! ({high_quality} пользователей)")
        return True


async def check_accounts():
    """Проверить аккаунты."""
    print("\n" + "="*60)
    print("2. ПРОВЕРКА USERBOT АККАУНТОВ")
    print("="*60)

    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount)
            .where(UserBotAccount.status.in_(["active", "warming"]))
        )
        accounts = result.scalars().all()

        if not accounts:
            print("   [X] ОШИБКА: Нет активных аккаунтов!")
            return False

        print(f"   Активных аккаунтов: {len(accounts)}\n")

        for acc in accounts:
            print(f"   [Phone] {acc.phone}")
            print(f"      Статус: {acc.status}")
            print(f"      Комментариев сегодня: {acc.daily_comments}")
            print(f"      Story views сегодня: {acc.daily_story_views}")

            # Проверка лимитов
            if acc.daily_story_views >= settings.max_story_views_per_day:
                print(f"      [!] Лимит просмотров достигнут ({settings.max_story_views_per_day})")

            if acc.cooldown_until:
                print(f"      ⏳ Cooldown до: {acc.cooldown_until}")

            print()

        print("   [OK] Аккаунты готовы")
        return True


def check_settings():
    """Проверить настройки."""
    print("\n" + "="*60)
    print("3. ПРОВЕРКА НАСТРОЕК")
    print("="*60)

    print(f"   MAX_STORY_VIEWS_PER_DAY: {settings.max_story_views_per_day}")
    print(f"   MIN_STORY_INTERVAL_SEC: {settings.min_story_interval_sec} сек ({settings.min_story_interval_sec/60:.1f} мин)")
    print(f"   MAX_STORY_INTERVAL_SEC: {settings.max_story_interval_sec} сек ({settings.max_story_interval_sec/60:.1f} мин)")
    print(f"   STORY_VIEW_MIN_QUALITY_SCORE: {settings.story_view_min_quality_score}")
    print(f"   WORK_START_HOUR: {settings.work_start_hour}:00")
    print(f"   WORK_END_HOUR: {settings.work_end_hour}:00")

    # Проверка безопасности
    warnings = []

    if settings.max_story_views_per_day > 10:
        warnings.append("[!] MAX_STORY_VIEWS_PER_DAY > 10 - рискованно для прогрева")

    if settings.min_story_interval_sec < 180:
        warnings.append("[!] MIN_STORY_INTERVAL_SEC < 180 - слишком часто для дня 2-3")

    if settings.story_view_min_quality_score < 50:
        warnings.append("[!] STORY_VIEW_MIN_QUALITY_SCORE < 50 - низкое качество ЦА")

    if warnings:
        print("\n   Предупреждения:")
        for warn in warnings:
            print(f"     {warn}")
        print()
    else:
        print("\n   [OK] Настройки безопасны для прогрева")

    return True


async def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("ПРОВЕРКА ГОТОВНОСТИ STORY VIEWING")
    print("="*60)

    # Initialize database
    await init_db()

    # Проверки
    checks = [
        await check_target_audience(),
        await check_accounts(),
        check_settings(),
    ]

    # Итоги
    print("\n" + "="*60)
    print("ИТОГИ")
    print("="*60)

    if all(checks):
        print("\n[OK] ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print("\nМожно запускать:")
        print("  python run_auto_comments.py")
        print("\nМониторинг:")
        print("  tail -f logs/traffic_engine_*.log | grep story_view")
        return 0
    else:
        print("\n[X] ЕСТЬ ПРОБЛЕМЫ!")
        print("\nИсправьте ошибки перед запуском.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
