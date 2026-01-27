import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def show_failures():
    try:
        load_dotenv()
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        conn = await asyncpg.connect(db_url)

        # Статистика по статусам
        stats = await conn.fetch('''
            SELECT status, COUNT(*) as cnt
            FROM traffic_actions
            GROUP BY status
        ''')

        print("\nСтатистика по статусам:")
        for s in stats:
            print(f"  {s['status']}: {s['cnt']}")

        # Последние ошибки
        errors = await conn.fetch('''
            SELECT
                a.created_at,
                a.content,
                a.error_message,
                a.flood_wait_seconds,
                a.target_channel_id,
                acc.display_name,
                acc.username
            FROM traffic_actions a
            LEFT JOIN traffic_userbot_accounts acc ON a.account_id = acc.id
            WHERE a.status = 'failed'
            ORDER BY a.created_at DESC
            LIMIT 10
        ''')

        print('\n' + '='*80)
        print('ПОСЛЕДНИЕ 10 ОШИБОК')
        print('='*80)

        for r in errors:
            created = r['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{created}]")
            if r['display_name']:
                print(f"Аккаунт: {r['display_name']} (@{r['username']})")
            print(f"Channel ID: {r['target_channel_id']}")

            if r['content']:
                content = r['content'].replace('\n', ' ')[:100]
                print(f"Текст: {content}...")

            print(f"ОШИБКА: {r['error_message']}")

            if r['flood_wait_seconds']:
                print(f"FloodWait: {r['flood_wait_seconds']} сек")

            print('-'*80)

        # Какие аккаунты используются
        accounts = await conn.fetch('''
            SELECT
                id,
                display_name,
                username,
                phone_number,
                status,
                is_active
            FROM traffic_userbot_accounts
        ''')

        print('\n' + '='*80)
        print('АККАУНТЫ В БД')
        print('='*80)
        for acc in accounts:
            status_emoji = "✓" if acc['is_active'] else "✗"
            print(f"{status_emoji} [{acc['id']}] {acc['display_name']} (@{acc['username']}) - {acc['phone_number']} - {acc['status']}")

        await conn.close()

    except Exception as e:
        import traceback
        print(f"\nОшибка: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(show_failures())
