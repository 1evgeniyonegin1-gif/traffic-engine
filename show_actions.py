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

        # Всего действий
        total = await conn.fetchval('SELECT COUNT(*) FROM traffic_actions')
        print(f'\nВсего действий: {total}')

        # За сегодня
        today = await conn.fetchval(
            'SELECT COUNT(*) FROM traffic_actions WHERE created_at::date = CURRENT_DATE'
        )
        print(f'Сегодня: {today}')

        # Последние 20 действий
        actions = await conn.fetch('''
            SELECT
                a.action_type,
                a.status,
                a.content,
                a.created_at,
                acc.display_name,
                acc.username as acc_username,
                ch.name as channel_name,
                ch.username as ch_username
            FROM traffic_actions a
            LEFT JOIN traffic_userbot_accounts acc ON a.account_id = acc.id
            LEFT JOIN traffic_target_channels ch ON a.channel_id = ch.id
            ORDER BY a.created_at DESC
            LIMIT 20
        ''')

        print('\n' + '='*80)
        print('ПОСЛЕДНИЕ 20 ДЕЙСТВИЙ')
        print('='*80)

        for r in actions:
            created = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else 'N/A'
            print(f"\n[{created}] {r['action_type']} - {r['status']}")

            if r['display_name']:
                print(f"Аккаунт: {r['display_name']} (@{r['acc_username']})")

            if r['channel_name']:
                print(f"Канал: {r['channel_name']} (@{r['ch_username']})")

            if r['content']:
                content = r['content'].replace('\n', ' ')[:150]
                print(f"Контент: {content}...")

            print('-'*80)

        await conn.close()

    except Exception as e:
        print(f"\nОшибка: {e}")

if __name__ == '__main__':
    asyncio.run(show_actions())
