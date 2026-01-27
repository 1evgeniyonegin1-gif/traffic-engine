"""
Замена текущих каналов на каналы с ОТКРЫТЫМИ комментариями
"""
import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

# Каналы с ОТКРЫТЫМИ комментариями
NEW_CHANNELS = [
    # Онлайн-заработок (приоритет 10)
    {"username": "freelance_ru", "priority": 10, "category": "freelance"},
    {"username": "udalenka", "priority": 10, "category": "freelance"},
    {"username": "remote_work_russia", "priority": 9, "category": "freelance"},
    {"username": "zarabotok_v_internete", "priority": 10, "category": "online_money"},
    {"username": "biznes_online", "priority": 10, "category": "online_business"},

    # Предпринимательство (приоритет 8-9)
    {"username": "startupoftheday", "priority": 9, "category": "startups"},
    {"username": "secretmag", "priority": 8, "category": "business"},
    {"username": "vc_ru", "priority": 9, "category": "business_news"},
    {"username": "pro_smm", "priority": 8, "category": "marketing"},
    {"username": "digital_marketing_ru", "priority": 7, "category": "marketing"},

    # Мотивация (приоритет 7-8)
    {"username": "motivacia", "priority": 8, "category": "motivation"},
    {"username": "samorazvitie", "priority": 8, "category": "self_development"},
    {"username": "uspeshnieludi", "priority": 7, "category": "success"},
    {"username": "biznesmotivacia", "priority": 7, "category": "motivation"},

    # Финансы (приоритет 8-9)
    {"username": "investicii_dengi", "priority": 8, "category": "finance"},
    {"username": "finansy_ru", "priority": 7, "category": "finance"},
    {"username": "passivincome", "priority": 9, "category": "passive_income"},

    # Нетворкинг (приоритет 6-7)
    {"username": "networking_ru", "priority": 6, "category": "networking"},
    {"username": "lichnyibrand", "priority": 7, "category": "personal_brand"},
    {"username": "targetolog_ru", "priority": 6, "category": "marketing"},

    # E-commerce (приоритет 7-8)
    {"username": "ecommerce_ru", "priority": 7, "category": "ecommerce"},
    {"username": "prodazhi_ru", "priority": 6, "category": "sales"},
    {"username": "wildberries_sellers", "priority": 8, "category": "ecommerce"},

    # IT и AI (приоритет 7-8)
    {"username": "chatgpt_ru", "priority": 8, "category": "ai"},
    {"username": "ai_news", "priority": 7, "category": "ai"},
    {"username": "tproger", "priority": 7, "category": "it"},
    {"username": "python_ru", "priority": 6, "category": "it"},

    # Инфопродукты (приоритет 8-9) - НАША ПРЯМАЯ ЦА!
    {"username": "onlinekursy", "priority": 9, "category": "infoproducts"},
    {"username": "obuchenie_online", "priority": 9, "category": "infoproducts"},
    {"username": "infobiz_ru", "priority": 10, "category": "infobusiness"},  # Прямое попадание!
]


async def replace_channels():
    """Заменить каналы в БД на новые с открытыми комментариями"""
    load_dotenv()
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

    conn = await asyncpg.connect(db_url)

    try:
        # Получить tenant_id
        tenant = await conn.fetchrow("SELECT id FROM traffic_tenants WHERE name = 'infobusiness'")
        if not tenant:
            print("Тенант 'infobusiness' не найден!")
            return

        tenant_id = tenant['id']
        print(f"Tenant ID: {tenant_id}")

        # 1. УДАЛИТЬ ВСЕ старые каналы
        deleted = await conn.execute("DELETE FROM traffic_target_channels WHERE tenant_id = $1", tenant_id)
        print(f"\nУдалено старых каналов: {deleted}")

        # 2. ДОБАВИТЬ новые каналы
        print(f"\nДобавление {len(NEW_CHANNELS)} новых каналов с ОТКРЫТЫМИ комментариями...\n")

        for ch in NEW_CHANNELS:
            # Генерируем временный channel_id (будет обновлён при первом запуске системы)
            # Используем хеш от username
            temp_channel_id = abs(hash(ch['username'])) % (10**10)

            await conn.execute("""
                INSERT INTO traffic_target_channels (
                    tenant_id,
                    channel_id,
                    username,
                    title,
                    priority,
                    is_active,
                    comment_strategy,
                    max_delay_minutes,
                    skip_ads,
                    skip_reposts,
                    min_post_length,
                    posts_processed,
                    comments_posted
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                tenant_id,
                temp_channel_id,
                ch['username'],
                ch['category'],  # Используем категорию как title
                ch['priority'],
                True,
                'smart',  # Стратегия по умолчанию
                10,
                True,
                True,
                100,
                0,  # posts_processed
                0   # comments_posted
            )
            print(f"[OK] @{ch['username']} (приоритет {ch['priority']}, категория {ch['category']})")

        # 3. Показать итоговый список
        channels = await conn.fetch("""
            SELECT username, priority, is_active
            FROM traffic_target_channels
            WHERE tenant_id = $1
            ORDER BY priority DESC, username
        """, tenant_id)

        print(f"\n{'='*80}")
        print(f"ИТОГО: {len(channels)} каналов с ОТКРЫТЫМИ комментариями")
        print(f"{'='*80}\n")

        for ch in channels:
            status = "[+]" if ch['is_active'] else "[-]"
            print(f"{status} @{ch['username']} (приоритет {ch['priority']})")

        print(f"\n{'='*80}")
        print("Замена завершена успешно!")
        print("Теперь можно запускать систему: python run_auto_comments.py")
        print(f"{'='*80}")

    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == '__main__':
    print("="*80)
    print("ЗАМЕНА КАНАЛОВ НА ПРОВЕРЕННЫЕ С ОТКРЫТЫМИ КОММЕНТАРИЯМИ")
    print("="*80)
    print("\nВНИМАНИЕ: Это удалит ВСЕ текущие каналы и добавит новые!")
    print("Всего будет добавлено: {} каналов\n".format(len(NEW_CHANNELS)))

    response = input("Продолжить? (yes/no): ")

    if response.lower() in ['yes', 'y', 'да']:
        asyncio.run(replace_channels())
    else:
        print("\nОтменено")
