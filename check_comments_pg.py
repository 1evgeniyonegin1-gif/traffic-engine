import asyncio
import asyncpg
from datetime import datetime

async def check_comments():
    try:
        # Читаем DATABASE_URL из .env
        import os
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        # Убираем +asyncpg из DSN для asyncpg
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        print(f"Connecting to database...")

        conn = await asyncpg.connect(db_url)

        # Комментарии за сегодня
        result = await conn.fetchrow('SELECT COUNT(*) as cnt FROM comments WHERE created_at::date = CURRENT_DATE')
        print(f'\nКомментариев сегодня: {result["cnt"]}')

        # Всего комментариев
        result = await conn.fetchrow('SELECT COUNT(*) as cnt FROM comments')
        print(f'Всего комментариев: {result["cnt"]}')

        # Последние 20 комментариев
        results = await conn.fetch('''
            SELECT
                c.text,
                c.created_at,
                ch.name as channel_name,
                ch.username as channel_username,
                a.display_name as account_name,
                a.username as account_username
            FROM comments c
            JOIN channels ch ON c.channel_id = ch.id
            JOIN accounts a ON c.account_id = a.id
            ORDER BY c.created_at DESC
            LIMIT 20
        ''')

        if results:
            print('\n' + '='*80)
            print('ПОСЛЕДНИЕ 20 КОММЕНТАРИЕВ')
            print('='*80)

            for r in results:
                print(f"\n[{r['created_at'].strftime('%Y-%m-%d %H:%M:%S')}]")
                print(f"Аккаунт: {r['account_name']} (@{r['account_username']})")
                print(f"Канал: {r['channel_name']} (@{r['channel_username']})")
                print(f"Текст: {r['text']}")
                print('-'*80)
        else:
            print('\nКомментариев пока нет')

        await conn.close()

    except Exception as e:
        print(f'\nОшибка: {e}')
        print(f'Тип ошибки: {type(e).__name__}')

if __name__ == '__main__':
    asyncio.run(check_comments())
