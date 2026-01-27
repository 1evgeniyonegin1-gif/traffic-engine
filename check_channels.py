import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def check_channels():
    try:
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        conn = await asyncpg.connect(db_url)

        # Сначала проверим структуру
        columns = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'traffic_target_channels'
            ORDER BY ordinal_position
        """)

        print("Структура таблицы traffic_target_channels:")
        col_names = [c['column_name'] for c in columns]
        for col in col_names:
            print(f"  - {col}")

        # Все целевые каналы
        channels = await conn.fetch('SELECT * FROM traffic_target_channels ORDER BY id')

        print(f"\n\nВсего целевых каналов: {len(channels)}\n")
        print('='*100)

        for ch in channels:
            print(f"\nID: {ch.get('id')}")
            print(f"Username: @{ch.get('username', 'N/A')}")
            print(f"Channel ID: {ch.get('telegram_channel_id', 'N/A')}")
            print(f"Priority: {ch.get('priority', 0)}")
            print(f"Active: {ch.get('is_active', True)}")

            # Показываем все поля
            for col in col_names:
                if col not in ['id', 'username', 'telegram_channel_id', 'priority', 'is_active']:
                    val = ch.get(col)
                    if val:
                        print(f"{col}: {val}")

            print('-'*100)

        await conn.close()

    except Exception as e:
        import traceback
        print(f"\nОшибка: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_channels())
