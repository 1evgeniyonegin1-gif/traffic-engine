#!/usr/bin/env python
"""
Импорт Auth Keys из сервиса покупки аккаунтов.
Создаёт session_string для Telethon из готовых Auth Keys.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.crypto import AuthKey

from traffic_engine.database import get_session
from traffic_engine.config import settings


# Данные от сервиса
AUTH_KEYS = {
    "+998993466132": {
        "auth_key_hex": "7b52a7975b260a067efd4b54c76905cc60330d20ff23ea52dd8bb610bd6b106ad93adbdad34c646c3b642ef901a27cf216e5b4935f32eaffe3635231425ef04f04bd747a7a9f3c7e6df20f78a92a1c18d3d6552cbac0a1cdc2bdb74d960fa0ece7b5bc0789536f362803a5210d3520d19c47cfbb36de09d0b19a7d017fe933e19f989b6a59ee232a0cac3f67e50f51e284f8a7544d763f90e78411f3288761d20e912f3603726c112513b94bf5f165057f224903390853bf67669f12428a736d35347a32c64ec4c6d55edb2dfe00103596a52604cc37254f975a5d5159dd953a0d32a40934ca3d5b1489ac88a2e8bbe1c0499da5f269ed7fc0f31cc1579f688b",
        "dc_id": 2,
        "user_id": 7673127503
    },
    "+380954967658": {
        "auth_key_hex": "40e4f8593f7adc802d06928b05b56ec9af93571d318d71192cec7d6acde3d4c6d0e12b296d3fbf3af154fda85bc60eef56809a2afafe82940d35dc558d30b6ac115ec364e46430006a2171858ff653ce91a9a04b114cb7df76951c0caa9150ca8df11bf7229a945ad424e5f5ce09c030a27e663fa44d07589d022d0b3b1b3f27b3210b08f80f303208a845a68324635f8071893ec9569c2f9e2dc5a583acfea3fbeb33cfaa71d8a50bbad47dfb7024fbbb78c5056f6f047ed687fb38166fe905bb9255eded797736c58a2072f8b20f551bd1114bf423d759380dd148172d8b71d56236be258cc394eb53d164d0a93c72a2e8ef71977aac780f4ac73869a38c77",
        "dc_id": 2,
        "user_id": 8460974753
    },
    "+380955161146": {
        "auth_key_hex": "68c522a3f43caf2b3b3c57d22193002211a22effe19cda2fa9efba24db3b1e0786460c471d77cccfd28f9ba18513fba86ab9b9916d431889f81dab7deb5ba41dd3da9bcb68161839cdfc99e9c01a8e3ffb1d06ac428770005b3754070bb9b1cd4145c113f7b261de4b8f5ac171daf991da847318cdb7d8585ed3656f5aa9424bd4af4584f4caaa9d921a16e9717e7730262446d075c69b2cd6f4652056bbbb4bb5cbb204812792a7b24a3d04eee48cc1d831e1bb2eba140c39b00c0840c4fc639eed8e0960fa956075111e8087e4e093c0f33d099dabe877994852106640134fc59ec2058430f55c13d2e2892be841f07881069f0fff7c45e3941598e797f363",
        "dc_id": 2,
        "user_id": 8460768950
    },
    "+380955300455": {
        "auth_key_hex": "5737c9bd3c286c3c3c60b6566060fcb802af3d0e27d0842d63d06ed9b896dee640d3fa2e680f727af01f257c3d0c4af33f4d8191bec747c9c563500360b2f83b41265545efd78f76b39592f5540e0026ed4cf811f3fe29e26193aaaf67b60313a6b555971e0fbbd3c9b7cfecf4c14eae8395495865278aa29dcb064320fdb048edd495dcb70fb1293a225d79f73cc6afa180f9e15dd51ffe59314f836875c7e09838b3002185ea357e2b3349603cd465899ec27b1a0064a13e5897bc0f94d924a8cc9d02282d37af3950b5400edab776bcd1ea90f2f6f07a2aa245ba83be56affb94267375e6a021c7ff4cf5e29cc9d4650296d7a04ecc99fbde103785c6db7a",
        "dc_id": 2,
        "user_id": 8471160613
    }
}


async def create_session_from_auth_key(phone: str, auth_key_hex: str, dc_id: int):
    """Создать session_string из Auth Key."""
    try:
        # Преобразовать HEX в bytes
        auth_key_bytes = bytes.fromhex(auth_key_hex)

        # Создать пустую StringSession
        session = StringSession()

        # Создать клиент
        client = TelegramClient(
            session,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
        )

        # Подключиться к Telegram
        await client.connect()

        # Установить auth_key и dc_id вручную через set_dc
        auth_key_obj = AuthKey(data=auth_key_bytes)
        client.session.set_dc(dc_id, '149.154.167.51', 443)  # DC2 IP
        client.session.auth_key = auth_key_obj

        # Сохранить session string
        session_string = client.session.save()

        await client.disconnect()

        logger.success(f"✓ Создана сессия для {phone}")
        return session_string

    except Exception as e:
        logger.error(f"✗ Ошибка для {phone}: {e}")
        return None


async def main():
    logger.info("=" * 60)
    logger.info("ИМПОРТ AUTH KEYS")
    logger.info("=" * 60)

    # Получить аккаунты из БД
    async with get_session() as db:
        result = await db.execute(text(
            "SELECT id, phone FROM traffic_userbot_accounts "
            "ORDER BY phone"
        ))
        accounts = {row[1]: row[0] for row in result.fetchall()}

    logger.info(f"\nНайдено {len(accounts)} аккаунтов в БД")
    logger.info(f"Есть {len(AUTH_KEYS)} Auth Keys для импорта\n")

    # Импортировать каждый
    success = 0
    for phone, data in AUTH_KEYS.items():
        if phone not in accounts:
            logger.warning(f"⚠ {phone} не найден в БД, пропускаем")
            continue

        logger.info(f"Обрабатываю {phone}...")

        session_string = await create_session_from_auth_key(
            phone,
            data["auth_key_hex"],
            data["dc_id"]
        )

        if session_string:
            # Сохранить в БД
            async with get_session() as db:
                await db.execute(
                    text("UPDATE traffic_userbot_accounts SET session_string = :session WHERE id = :id"),
                    {"session": session_string, "id": accounts[phone]}
                )
                await db.commit()

            logger.success(f"✓ {phone} сохранён в БД")
            success += 1

        await asyncio.sleep(1)

    logger.info("\n" + "=" * 60)
    logger.info(f"ГОТОВО: {success}/{len(AUTH_KEYS)} аккаунтов")
    logger.info("=" * 60)

    if success == len(AUTH_KEYS):
        logger.success("\n✓ Все аккаунты импортированы!")
        logger.info("Запустите: systemctl start traffic-engine\n")
    else:
        logger.warning(f"\n⚠ Импортировано только {success} из {len(AUTH_KEYS)}")


if __name__ == "__main__":
    asyncio.run(main())
