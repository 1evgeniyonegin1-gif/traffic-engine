import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def show_bios():
    load_dotenv()
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

    conn = await asyncpg.connect(db_url)

    accs = await conn.fetch('SELECT username, bio, first_name FROM traffic_userbot_accounts')

    print("\nБИОГРАФИИ АККАУНТОВ:")
    print('='*80)

    for a in accs:
        print(f"\n@{a['username']}")
        print(f"Имя: {a['first_name']}")
        print(f"Био: {a['bio']}")
        print('-'*80)

    await conn.close()

if __name__ == '__main__':
    asyncio.run(show_bios())
