#!/usr/bin/env python
"""
Generate avatars for accounts using YandexART.

Генерирует аватарки для аккаунтов через YandexART API.
"""

import asyncio
import base64
import time
from pathlib import Path

import httpx
import jwt
from loguru import logger

# Настройки YandexART (из NL проекта)
YANDEX_SERVICE_ACCOUNT_ID = "aje76dc7i20078podfrc"
YANDEX_KEY_ID = "ajensd96tl0d2q9fqmp9"
YANDEX_FOLDER_ID = "b1gibb3gjf11pjbu65r3"

# Приватный ключ (нужно взять из .env)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from traffic_engine.config import settings

# Конвертируем \n в реальные переносы строк
YANDEX_PRIVATE_KEY = settings.yandex_private_key.replace("\\n", "\n") if settings.yandex_private_key else None


# Промпты для генерации аватарок - гиперреалистичные фото
# Источники: https://automatorslab.ai/blog/imageprompt/ai-prompts-for-high-quality-realistic-photography-portraits/
AVATAR_PROMPTS = [
    {
        "name": "Карина",
        "prompt": "portrait photo of 25 year old woman, dark brown hair, natural smile, shot on Canon EOS R5 85mm f1.8, soft window light, detailed skin texture, no makeup, casual clothes, 8K UHD",
        "filename": "avatar_karina.jpg",
    },
    {
        "name": "Кира",
        "prompt": "closeup portrait young woman 23yo, light brown wavy hair, green eyes, golden hour sunlight, shot on Sony A7R IV 50mm f1.4, natural skin pores, freckles, white tshirt, photorealistic 8K",
        "filename": "avatar_kira.jpg",
    },
    {
        "name": "Люба",
        "prompt": "headshot portrait blonde woman 24yo, blue eyes, soft smile, indoor natural daylight, Hasselblad medium format, sharp focus on eyes, realistic skin texture, sweater, ultra detailed 8K HDR",
        "filename": "avatar_lyuba.jpg",
    },
]


class YandexART:
    """Клиент для YandexART API"""

    def __init__(self):
        self.service_account_id = YANDEX_SERVICE_ACCOUNT_ID
        self.key_id = YANDEX_KEY_ID
        self.private_key = YANDEX_PRIVATE_KEY
        self.folder_id = YANDEX_FOLDER_ID
        self.iam_token = None
        self.token_expires_at = 0

    def _create_jwt_token(self) -> str:
        """Создание JWT токена"""
        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': self.service_account_id,
            'iat': now,
            'exp': now + 3600
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm='PS256',
            headers={'kid': self.key_id}
        )

    async def _get_iam_token(self) -> str:
        """Получение IAM токена"""
        if self.iam_token and time.time() < self.token_expires_at:
            return self.iam_token

        jwt_token = self._create_jwt_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://iam.api.cloud.yandex.net/iam/v1/tokens',
                json={'jwt': jwt_token}
            )
            response.raise_for_status()
            result = response.json()
            self.iam_token = result['iamToken']
            self.token_expires_at = time.time() + (11 * 3600)
            return self.iam_token

    async def generate_image(self, prompt: str, width: int = 512, height: int = 512) -> bytes | None:
        """Генерация изображения"""
        try:
            iam_token = await self._get_iam_token()

            # Запрос на генерацию
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Отправляем запрос на генерацию
                response = await client.post(
                    "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync",
                    headers={
                        "Authorization": f"Bearer {iam_token}",
                        "Content-Type": "application/json",
                        "x-folder-id": self.folder_id,
                    },
                    json={
                        "modelUri": f"art://{self.folder_id}/yandex-art/latest",
                        "generationOptions": {
                            "seed": str(int(time.time())),
                        },
                        "messages": [
                            {
                                "weight": "1",
                                "text": prompt[:500],  # Лимит 500 символов
                            }
                        ],
                        "aspectRatio": {
                            "widthRatio": "1",
                            "heightRatio": "1",
                        },
                    },
                )
                response.raise_for_status()
                operation = response.json()
                operation_id = operation.get("id")

                logger.info(f"Запущена генерация, operation_id: {operation_id}")

                # Ждём результат
                for _ in range(60):  # Макс 60 секунд
                    await asyncio.sleep(2)

                    status_response = await client.get(
                        f"https://llm.api.cloud.yandex.net/operations/{operation_id}",
                        headers={"Authorization": f"Bearer {iam_token}"},
                    )
                    status_response.raise_for_status()
                    status = status_response.json()

                    if status.get("done"):
                        if "response" in status:
                            image_base64 = status["response"].get("image")
                            if image_base64:
                                return base64.b64decode(image_base64)
                        if "error" in status:
                            logger.error(f"Ошибка генерации: {status['error']}")
                            return None
                        break

                logger.warning("Таймаут генерации")
                return None

        except Exception as e:
            logger.error(f"Ошибка YandexART: {e}")
            import traceback
            traceback.print_exc()
            return None


async def main():
    """Генерация аватарок"""
    print("\n=== ГЕНЕРАЦИЯ АВАТАРОК ЧЕРЕЗ YANDEXART ===\n")

    # Создаём папку для аватарок
    avatars_dir = Path(__file__).parent.parent / "avatars"
    avatars_dir.mkdir(exist_ok=True)

    client = YandexART()

    for avatar in AVATAR_PROMPTS:
        print(f"\nGenerating avatar for {avatar['name']}...")
        print(f"   Prompt: {avatar['prompt'][:60]}...")

        image_data = await client.generate_image(avatar["prompt"])

        if image_data:
            filepath = avatars_dir / avatar["filename"]
            filepath.write_bytes(image_data)
            print(f"   OK! Saved: {filepath}")
        else:
            print(f"   ERROR generating")

        # Пауза между генерациями
        await asyncio.sleep(3)

    print(f"\n=== ГОТОВО! ===")
    print(f"Avatarki sokhraneny v papku: {avatars_dir}")
    print("Prover rezultat i skazhi, podkhodyat li.\n")


if __name__ == "__main__":
    asyncio.run(main())
