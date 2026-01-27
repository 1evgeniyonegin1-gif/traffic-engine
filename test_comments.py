"""Тест генерации комментариев с новыми промптами."""
import asyncio
import sys
import os
import time

# Добавляем путь к проекту
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

import httpx
import jwt
from typing import Dict
from traffic_engine.config import settings


class YandexGPTClient:
    """Минимальный клиент для теста"""

    def __init__(self):
        self.folder_id = settings.yandex_folder_id
        self.service_account_id = settings.yandex_service_account_id
        self.key_id = settings.yandex_key_id
        self.private_key = settings.yandex_private_key

    def _get_iam_token(self) -> str:
        now = int(time.time())
        payload = {
            "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            "iss": self.service_account_id,
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(payload, self.private_key, algorithm="PS256", headers={"kid": self.key_id})

        response = httpx.post(
            "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            json={"jwt": token},
            timeout=30.0
        )
        return response.json()["iamToken"]

    async def generate(self, system_prompt: str, user_message: str, temperature: float = 0.7, max_tokens: int = 200) -> str:
        iam_token = self._get_iam_token()

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                headers={"Authorization": f"Bearer {iam_token}"},
                json={
                    "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
                    "completionOptions": {
                        "stream": False,
                        "temperature": temperature,
                        "maxTokens": str(max_tokens)
                    },
                    "messages": [
                        {"role": "system", "text": system_prompt},
                        {"role": "user", "text": user_message}
                    ]
                }
            )
            data = response.json()
            return data["result"]["alternatives"][0]["message"]["text"]


# Промпты
STRATEGY_PROMPTS: Dict[str, str] = {
    "smart": """Ты обычный человек из телеги, листаешь каналы вечером.
Накидай коммент к посту — своё мнение или вопрос.

ВАЖНО - пиши как реальный человек:
- Можно начать с маленькой буквы
- Можно без точки в конце
- Иногда пропускай запятые где не критично
- Используй разговорные слова: ну, короче, кстати, типа, ваще, норм, оч
- Можно сокращения: спс, плз, имхо, кст
- Иногда опечатки ок (но не переборщи)
- НЕ пиши "отличный пост", "очень полезно", "спасибо автору" — это палево
- НЕ используй эмодзи вообще или максимум 1

Примеры живых комментов:
- "а если наоборот сделать? типа сначала х потом у"
- "ну хз, у меня не работало так"
- "кст хороший поинт про..."
- "о, я тоже об этом думал недавно"

Пост:
{post_text}

Коммент (только текст, без кавычек):""",

    "supportive": """Ты обычный чел из телеги, увидел пост который зацепил.
Напиши короткую реакцию — что откликнулось.

ВАЖНО - не будь роботом:
- Пиши как в переписке с другом
- Можно с маленькой буквы, без точки
- Разговорные слова: прям, реально, оч, кст, ваще
- НИКАКИХ "спасибо за пост", "очень полезно", "отличная статья"
- Без эмодзи или максимум 1
- 1-2 коротких предложения или даже одна фраза

Примеры:
- "прям в точку"
- "о да, знакомо"
- "вот это прям про меня"
- "жиза"
- "ну наконец кто-то это сказал"

Пост:
{post_text}

Коммент:""",

    "funny": """Ты чел с телеги который любит пошутить в комментах.
Напиши что-то ироничное или с подколом по теме.

ВАЖНО:
- Юмор должен быть в тему поста
- Пиши как живой человек, не как бот
- Можно сарказм, но без агрессии
- Разговорный стиль, можно без заглавных
- Без эмодзи (ну или 1 максимум)
- Короткая фраза, не расписывай

Примеры:
- "ну да, а потом удивляемся почему..."
- "классика жанра"
- "держите меня семеро"
- "мой кошелёк: нет, пожалуйста, не надо"

Пост:
{post_text}

Коммент:""",

    "expert": """Ты шаришь в теме поста и хочешь добавить от себя.
Напиши коммент с полезной инфой или своим опытом.

ВАЖНО - пиши как человек а не как учебник:
- Разговорный стиль, не официоз
- Можно: кст, имхо, по опыту, у меня было так
- Делись опытом как будто другу рассказываешь
- Не умничай слишком — это комменты, не лекция
- 2-3 предложения максимум
- Без эмодзи

Примеры:
- "кст по опыту — лучше сначала попробовать х, а потом уже у"
- "у меня похожая тема была, помогло когда..."
- "имхо тут ещё важно учитывать что..."
- "добавлю — ещё работает вариант с..."

Пост:
{post_text}

Коммент:""",
}

NICHE_CONTEXT = """
Контекст: ты работаешь на удалёнке, шаришь в онлайн-заработке.
Пробовал разные схемы — что-то зашло, что-то нет. Знаешь тему изнутри."""

GENDER_PROMPTS = {
    "female": """
Ты ДЕВУШКА. Пиши от женского лица:
- Используй женский род: "попробовала", "узнала", "была", "сама"
- Можно: "ой", "блин", "вау", "круто же", "реально классно"
- Чуть мягче и эмоциональнее чем парни
- Иногда можно растянуть слова: "ну дааа", "точнооо"
- НО не переигрывай — ты обычная девушка, не стереотип""",

    "male": """
Ты ПАРЕНЬ. Пиши от мужского лица:
- Используй мужской род: "попробовал", "узнал", "был", "сам"
- Можно: "чел", "норм", "зачёт", "ну хз", "да ладно"
- Более прямолинейно, меньше эмоций
- НО не грубо — просто обычный парень из телеги""",
}


TEST_POST = """Как я заработал первые 50к на удалёнке

Короче, расскажу свою историю. Год назад сидел в офисе за 40к, ненавидел каждый понедельник.

Потом наткнулся на тему с копирайтингом. Первый месяц — 5к. Второй — 15к. Через полгода вышел на 50к чистыми.

Что помогло:
- Не распылялся на 10 ниш, выбрал одну
- Делал портфолио даже бесплатно
- Каждый день хоть час, но работал над навыком

Сейчас уже 80к+ и работаю 4-5 часов в день из дома.

Главное — просто начать, остальное приложится"""


async def generate_comment(client: YandexGPTClient, post_text: str, strategy: str, gender: str = None) -> str:
    gender_context = GENDER_PROMPTS.get(gender, "") if gender else ""

    system_prompt = f"""Ты помощник для генерации комментариев в Telegram.
{NICHE_CONTEXT}
{gender_context}

ВАЖНО:
- Пиши на русском языке
- Не упоминай что ты AI или бот
- Не рекламируй ничего
- Пиши естественно, как живой человек"""

    user_prompt = STRATEGY_PROMPTS[strategy].format(post_text=post_text[:1500])

    comment = await client.generate(
        system_prompt=system_prompt,
        user_message=user_prompt,
        temperature=0.85,
        max_tokens=150
    )

    # Постобработка
    if comment:
        comment = comment.strip().strip('"\'')
        if len(comment) > 300:
            comment = comment[:300]

    return comment or "[ошибка]"


async def main():
    client = YandexGPTClient()
    strategies = ["smart", "supportive"]  # Только 2 стратегии для краткости
    genders = ["female", "male"]

    results = []
    results.append("=" * 60)
    results.append("ТЕСТ ГЕНЕРАЦИИ КОММЕНТАРИЕВ С УЧЁТОМ ПОЛА")
    results.append("=" * 60)
    results.append(f"\nПост:\n{TEST_POST[:200]}...\n")
    results.append("=" * 60)

    for gender in genders:
        results.append(f"\n{'='*60}")
        results.append(f"ПОЛ: {gender.upper()}")
        results.append("=" * 60)

        for strategy in strategies:
            results.append(f"\n>> Стратегия: {strategy}")
            results.append("-" * 40)

            for i in range(2):
                try:
                    comment = await generate_comment(client, TEST_POST, strategy, gender)
                    # Убираем эмодзи из результата
                    comment = ''.join(c for c in comment if ord(c) < 0x10000)
                    results.append(f"  {i+1}. {comment}")
                except Exception as e:
                    results.append(f"  {i+1}. [ошибка: {e}]")

            results.append("")

    # Сохраняем в файл
    output = "\n".join(results)
    with open("test_comments_result.txt", "w", encoding="utf-8") as f:
        f.write(output)

    print("Результаты сохранены в test_comments_result.txt")


if __name__ == "__main__":
    asyncio.run(main())
