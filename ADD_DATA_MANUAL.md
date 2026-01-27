# Ручное добавление аккаунтов на VPS

## Проблема
База на VPS пустая (0 аккаунтов, 0 каналов). Session файлы есть, но записей в БД нет.

## Решение: Экспорт/Импорт через psql

### На локальной машине:

1. Создать дамп аккаунтов и каналов:
```bash
# Windows (через psql или pgAdmin)
psql -U postgres -d info_business -c "\copy (SELECT * FROM traffic_userbot_accounts) TO 'C:\temp\accounts.csv' CSV HEADER"
psql -U postgres -d info_business -c "\copy (SELECT * FROM traffic_target_channels WHERE is_active=true) TO 'C:\temp\channels.csv' CSV HEADER"
```

### На VPS:

1. Скопировать CSV файлы:
```bash
scp C:\temp\accounts.csv root@194.87.86.103:/tmp/
scp C:\temp\channels.csv root@194.87.86.103:/tmp/
```

2. Импортировать:
```bash
ssh root@194.87.86.103

# Импорт аккаунтов
psql -U postgres -d info_business -c "\copy traffic_userbot_accounts FROM '/tmp/accounts.csv' CSV HEADER"

# Импорт каналов
psql -U postgres -d info_business -c "\copy traffic_target_channels FROM '/tmp/channels.csv' CSV HEADER"

# Проверка
psql -U postgres -d info_business -c "SELECT COUNT(*) FROM traffic_userbot_accounts;"
psql -U postgres -d info_business -c "SELECT COUNT(*) FROM traffic_target_channels WHERE is_active=true;"

# Перезапустить сервис
systemctl restart traffic-engine
journalctl -u traffic-engine -f
```

## Альтернатива: Python скрипт на VPS

Если session файлы уже на VPS, можно добавить аккаунты напрямую:

```python
# На VPS: /opt/traffic-engine/add_accounts_from_sessions.py

import asyncio
import glob
from telethon import TelegramClient
from telethon.sessions import StringSession
from traffic_engine.database import get_session
from traffic_engine.database.models import UserBotAccount, Tenant
from traffic_engine.config import settings
from sqlalchemy import select

async def add_accounts():
    # Get tenant
    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one()

    # Accounts info
    accounts_info = [
        {"+380954967658": ("Карина", None, "karina_free_lesson_636")},
        {"+380955300455": ("Кира", None, "kira_free_scheme_209")},
        {"+380955161146": ("Люба", None, "lyuba_free_guide_871")},
        {"+998993466132": ("Лёша", "Лаймов", "lemonlime192")},
    ]

    for acc in accounts_info:
        phone = list(acc.keys())[0]
        first_name, last_name, username = acc[phone]

        session_file = f"sessions/{phone}.session"

        # Connect and get session string
        client = TelegramClient(
            session_file.replace(".session", ""),
            settings.telegram_api_id,
            settings.telegram_api_hash
        )

        await client.connect()
        session_string = StringSession.save(client.session)
        await client.disconnect()

        # Add to DB
        async with get_session() as db_session:
            account = UserBotAccount(
                tenant_id=tenant.id,
                phone=phone,
                session_string=session_string,
                first_name=first_name,
                last_name=last_name,
                username=username,
                status="active"
            )
            db_session.add(account)
            await db_session.commit()

        print(f"✓ Added {first_name} ({phone})")

if __name__ == "__main__":
    asyncio.run(add_accounts())
```

Запустить:
```bash
python /opt/traffic-engine/add_accounts_from_sessions.py
```
