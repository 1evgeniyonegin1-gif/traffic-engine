import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def show_accounts():
    try:
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        conn = await asyncpg.connect(db_url)

        # Структура таблицы аккаунтов
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'traffic_userbot_accounts'
            ORDER BY ordinal_position
        """)

        print("\nСтруктура таблицы traffic_userbot_accounts:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']}")

        # Все аккаунты
        accounts = await conn.fetch('SELECT * FROM traffic_userbot_accounts')

        print('\n' + '='*80)
        print('ВСЕ АККАУНТЫ')
        print('='*80)

        for acc in accounts:
            print(f"\nID: {acc['id']}")
            print(f"Имя: {acc.get('name', 'N/A')}")
            print(f"Username: @{acc.get('username', 'N/A')}")
            print(f"Телефон: {acc.get('phone_number', 'N/A')}")
            print(f"Session: {acc.get('session_file', 'N/A')}")
            print(f"Статус: {acc.get('status', 'N/A')}")
            print(f"Активен: {acc.get('is_active', False)}")
            print('-'*80)

        # Статистика по статусам действий
        stats = await conn.fetch('''
            SELECT status, COUNT(*) as cnt
            FROM traffic_actions
            GROUP BY status
        ''')

        print('\nСтатистика действий:')
        for s in stats:
            print(f"  {s['status']}: {s['cnt']}")

        # Последние ошибки (без JOIN)
        errors = await conn.fetch('''
            SELECT
                created_at,
                content,
                error_message,
                account_id,
                target_channel_id
            FROM traffic_actions
            WHERE status = 'failed'
            ORDER BY created_at DESC
            LIMIT 5
        ''')

        print('\n' + '='*80)
        print('ПОСЛЕДНИЕ 5 ОШИБОК')
        print('='*80)

        for r in errors:
            created = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{created}] Account ID: {r['account_id']}")
            print(f"Channel ID: {r['target_channel_id']}")

            if r['content']:
                content = r['content'].replace('\n', ' ')[:80]
                print(f"Текст: {content}...")

            print(f"ОШИБКА: {r['error_message']}")
            print('-'*80)

        await conn.close()

    except Exception as e:
        import traceback
        print(f"\nОшибка: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(show_accounts())
