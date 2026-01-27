import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def check_db():
    try:
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        print("Connecting to database...")
        conn = await asyncpg.connect(db_url)

        # Проверить существующие таблицы
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        if tables:
            print(f"\nНайдено таблиц: {len(tables)}")
            for t in tables:
                # Посчитать записи
                count = await conn.fetchval(f'SELECT COUNT(*) FROM {t["table_name"]}')
                print(f"  - {t['table_name']}: {count} записей")
        else:
            print("\nБД пустая - таблиц не найдено!")
            print("Нужно запустить: python scripts/init_db.py")

        await conn.close()

    except Exception as e:
        print(f"\nОшибка: {e}")
        print(f"Тип: {type(e).__name__}")

if __name__ == '__main__':
    asyncio.run(check_db())
