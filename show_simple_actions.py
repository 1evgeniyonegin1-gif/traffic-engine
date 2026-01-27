import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def show_actions():
    try:
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        conn = await asyncpg.connect(db_url)

        # Структура таблицы
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'traffic_actions'
            ORDER BY ordinal_position
        """)

        print("\nСтруктура таблицы traffic_actions:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']}")

        # Всего действий
        total = await conn.fetchval('SELECT COUNT(*) FROM traffic_actions')
        print(f'\n\nВсего действий: {total}')

        # За сегодня
        today = await conn.fetchval(
            'SELECT COUNT(*) FROM traffic_actions WHERE created_at::date = CURRENT_DATE'
        )
        print(f'Сегодня: {today}')

        # Последние 20 действий - простой запрос
        actions = await conn.fetch('''
            SELECT *
            FROM traffic_actions
            ORDER BY created_at DESC
            LIMIT 20
        ''')

        print('\n' + '='*80)
        print('ПОСЛЕДНИЕ 20 ДЕЙСТВИЙ')
        print('='*80)

        for r in actions:
            created = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else 'N/A'
            print(f"\n[{created}] {r['action_type']} - {r['status']}")
            print(f"Account ID: {r['account_id']}")

            if r.get('content'):
                content = r['content'].replace('\n', ' ')[:200]
                print(f"Контент: {content}")

            if r.get('metadata'):
                print(f"Metadata: {r['metadata']}")

            print('-'*80)

        await conn.close()

    except Exception as e:
        import traceback
        print(f"\nОшибка: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(show_actions())
