"""
Comment Generator - AI генерация умных комментариев.

Использует YandexGPT для генерации релевантных комментариев
под постами в целевых каналах.
"""

import random
import time
from typing import Dict, List, Optional

import httpx
import jwt
from loguru import logger

from traffic_engine.config import settings


class YandexGPTClient:
    """Клиент для YandexGPT API"""

    def __init__(self):
        self.service_account_id = settings.yandex_service_account_id
        self.key_id = settings.yandex_key_id
        self.private_key = settings.yandex_private_key
        self.folder_id = settings.yandex_folder_id
        self.model = "yandexgpt-32k"
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1"
        self.iam_token = None
        self.token_expires_at = 0

    def _create_jwt_token(self) -> str:
        """Создание JWT токена для получения IAM токена"""
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

    async def _get_iam_token(self, force_refresh: bool = False) -> str:
        """Получение IAM токена через JWT"""
        if self.iam_token and not force_refresh and time.time() < self.token_expires_at:
            return self.iam_token

        try:
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
                logger.info("YandexGPT IAM token obtained")
                return self.iam_token
        except Exception as e:
            logger.error(f"Error obtaining IAM token: {e}")
            raise

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.8,
        max_tokens: int = 200
    ) -> Optional[str]:
        """Генерирует текст через YandexGPT"""
        for attempt in range(2):
            try:
                iam_token = await self._get_iam_token(force_refresh=(attempt > 0))

                messages = [
                    {"role": "system", "text": system_prompt},
                    {"role": "user", "text": user_message}
                ]

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self.base_url}/completion",
                        headers={
                            "Authorization": f"Bearer {iam_token}",
                            "Content-Type": "application/json",
                            "x-folder-id": self.folder_id
                        },
                        json={
                            "modelUri": f"gpt://{self.folder_id}/{self.model}/latest",
                            "completionOptions": {
                                "stream": False,
                                "temperature": temperature,
                                "maxTokens": str(max_tokens)
                            },
                            "messages": messages
                        }
                    )

                    if response.status_code in [401, 403] and attempt == 0:
                        logger.warning("YandexGPT token expired, refreshing...")
                        self.iam_token = None
                        self.token_expires_at = 0
                        continue

                    response.raise_for_status()
                    result = response.json()
                    return result["result"]["alternatives"][0]["message"]["text"]

            except httpx.HTTPStatusError as e:
                if e.response.status_code in [401, 403] and attempt == 0:
                    self.iam_token = None
                    self.token_expires_at = 0
                    continue
                logger.error(f"YandexGPT API error: {e}")
                return None
            except Exception as e:
                logger.error(f"YandexGPT error: {e}")
                return None

        return None


class CommentGenerator:
    """
    AI-генерация умных комментариев через YandexGPT.

    Стратегии:
    - smart: Анализ поста и релевантный ответ
    - supportive: Поддерживающий комментарий
    - funny: Уместный юмор
    - expert: Экспертное мнение
    """

    STRATEGY_PROMPTS: Dict[str, str] = {
        "smart": """Ты обычный человек из телеги, листаешь каналы вечером.
Накидай коммент к посту — своё мнение, вопрос, или слегка спорное утверждение.

ВАЖНО - пиши как реальный человек, добавь ПРОВОКАЦИИ или ИРОНИИ:
- Можно начать с маленькой буквы
- Можно без точки в конце
- Используй разговорные слова: ну, короче, кстати, типа, ваще, норм, оч, чёт, чел
- Можно сокращения: спс, плз, имхо, кст, хз, имхо
- НЕ пиши "отличный пост", "очень полезно", "спасибо автору" — это палево
- МОЖНО не согласиться или усомниться — "ну не знаю", "а точно?", "сомневаюсь"
- МОЖНО задеть тему с юмором — "классика", "где-то это слышал", "опять эта песня"
- НЕ используй эмодзи вообще или максимум 1

Примеры ЖИВЫХ комментов С ХАРАКТЕРОМ:
- "а если наоборот сделать? типа сначала х потом у, а не как тут"
- "ну хз, у меня не работало так, может у автора специфика"
- "это же классика жанра, все так говорят, а потом удивляемся"
- "о, опять про это... хотя да, тема рабочая"
- "звучит красиво, но на практике обычно не так"
- "а есть кто реально так делал? интересно же"
- "чёт сомнительно, имхо проще через..."

Пост:
{post_text}

Коммент (только текст, без кавычек):""",

        "supportive": """Ты обычный чел из телеги, увидел пост который зацепил.
Напиши короткую эмоциональную реакцию — что откликнулось.

ВАЖНО - не будь роботом, покажи ЭМОЦИЮ:
- Пиши как в переписке с другом
- Можно с маленькой буквы, без точки
- Разговорные слова: прям, реально, оч, кст, ваще, бл*н, ё-моё
- НИКАКИХ "спасибо за пост", "очень полезно", "отличная статья"
- Без эмодзи или максимум 1
- 1-2 коротких предложения или даже одна фраза
- МОЖНО усилить: "прям ооочень", "ваааще", "точнооо"

Примеры С ЭМОЦИЕЙ:
- "прям в точку, бл*н"
- "о да, знакомо до боли"
- "вот это прям про меня, жиза"
- "ну наконец-то кто-то это сказал"
- "ооо да, сто процентов"
- "это просто ппц как в тему"

Пост:
{post_text}

Коммент:""",

        "funny": """Ты чел с телеги который любит пошутить или подколоть в комментах.
Напиши что-то ироничное, саркастичное или с лёгкой провокацией по теме.

ВАЖНО:
- Юмор должен быть в тему поста, но С ХАРАКТЕРОМ
- Можно сарказм, иронию, лёгкую провокацию
- Разговорный стиль, можно без заглавных
- Без эмодзи (ну или 1 максимум)
- Короткая фраза, не расписывай
- МОЖНО задеть больную тему с юмором

Примеры С ХАРАКТЕРОМ:
- "ну да, а потом удивляемся почему не работает"
- "классика жанра, слышал это раз 100 уже"
- "держите меня семеро, щас начну"
- "мой кошелёк: нет блин, только не это опять"
- "а че, так можно было? где были эти советы раньше"
- "окей, щас все побегут это делать, а через неделю..."
- "звучит как план без изъянов, что может пойти не так"

Пост:
{post_text}

Коммент:""",

        "expert": """Ты шаришь в теме поста и хочешь добавить от себя.
Напиши коммент с полезной инфой или своим опытом, но можно с лёгкой иронией.

ВАЖНО - пиши как человек а не как учебник:
- Разговорный стиль, не официоз
- Можно: кст, имхо, по опыту, у меня было так
- Делись опытом как будто другу рассказываешь
- НЕ умничай слишком — это комменты, не лекция
- 2-3 предложения максимум
- Без эмодзи
- МОЖНО добавить сомнение или альтернативу: "хотя у меня не взлетело", "правда у всех по-разному"

Примеры С ХАРАКТЕРОМ:
- "кст по опыту — лучше сначала х попробовать, а потом уже у, иначе потом переделывать"
- "у меня похожая тема была, помогло когда сделал наоборот, чёт"
- "имхо тут ещё важно учитывать что... а то потом сюрпризы"
- "добавлю — ещё работает вариант с..., хотя не у всех заходит"
- "по факту это работает, но есть нюанс который никто не говорит"
- "звучит норм, но на практике обычно вылезает что..."

Пост:
{post_text}

Коммент:""",
    }

    NICHE_PROMPTS: Dict[str, str] = {
        "infobusiness": """
Контекст: ты работаешь на удалёнке, шаришь в онлайн-заработке.
Пробовал разные схемы — что-то зашло, что-то нет. Знаешь тему изнутри.""",

        "nl_international": """
Контекст: следишь за питанием, пробуешь разные продукты для здоровья.
Не фанатик, но тема интересует. Есть свой опыт — и удачный и не очень.""",

        "traffic_engine_saas": """
Контекст: ты маркетолог/предприниматель, который тестирует разные способы привлечения клиентов.
Устал от дорогой рекламы. Нашёл способ получать лидов дешевле через умные комментарии.
Не продавец, а человек который делится опытом.""",
    }

    # Специальные промпты для B2B с CTA
    B2B_CTA_PROMPTS: Dict[str, str] = {
        "traffic_engine_soft": """
ВАЖНО: В конце комментария МЯГКО упомяни что автоматизировал лидогенерацию.
Примеры концовок (выбери подходящую или придумай свою):
- "кст у нас автоматизация комментов работает 24/7 — результаты тут: {cta_link}"
- "сам такое же юзаю через автокомменты — см. {cta_link}"
- "если тема интересует — у нас система автолидов работает, глянь {cta_link}"

НО! CTA должен быть естественным продолжением мысли, не рекламой.""",

        "traffic_engine_direct": """
ВАЖНО: После комментария добавь короткую ссылку на решение.
Примеры:
- "...кстати автоматизировал это — {cta_link}"
- "...есть рабочая тема по автолидам: {cta_link}"
""",
    }

    GENDER_PROMPTS: Dict[str, str] = {
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

    def __init__(self, tenant_name: str = "infobusiness"):
        """
        Initialize comment generator.

        Args:
            tenant_name: Название тенанта для выбора контекста
        """
        self.tenant_name = tenant_name
        self.client = YandexGPTClient()
        self.niche_context = self.NICHE_PROMPTS.get(tenant_name, "")

    async def generate(
        self,
        post_text: str,
        strategy: str = "smart",
        channel_title: Optional[str] = None,
        gender: Optional[str] = None,
        cta_link: Optional[str] = None,
        cta_style: str = "soft",
    ) -> Optional[str]:
        """
        Генерирует комментарий для поста.

        Args:
            post_text: Текст поста
            strategy: Стратегия комментирования
            channel_title: Название канала (для контекста)
            gender: Пол аккаунта ("female" или "male")
            cta_link: Ссылка для CTA (для B2B комментариев)
            cta_style: Стиль CTA - "soft" или "direct"

        Returns:
            Текст комментария или None при ошибке
        """
        if not post_text or len(post_text.strip()) < 20:
            logger.warning("Post text too short, skipping")
            return None

        base_prompt = self.STRATEGY_PROMPTS.get(strategy, self.STRATEGY_PROMPTS["smart"])

        # Контекст пола
        gender_context = self.GENDER_PROMPTS.get(gender, "") if gender else ""

        # CTA контекст для B2B
        cta_context = ""
        if cta_link and self.tenant_name == "traffic_engine_saas":
            cta_key = f"traffic_engine_{cta_style}"
            cta_template = self.B2B_CTA_PROMPTS.get(cta_key, "")
            cta_context = cta_template.format(cta_link=cta_link) if cta_template else ""

        system_prompt = f"""Ты помощник для генерации комментариев в Telegram.
{self.niche_context}
{gender_context}
{cta_context}

ВАЖНО:
- Пиши на русском языке
- Не упоминай что ты AI или бот
- Пиши естественно, как живой человек
- Комментарий должен быть уникальным и релевантным"""

        user_prompt = base_prompt.format(post_text=post_text[:1500])

        try:
            comment = await self.client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt,
                temperature=0.8,
                max_tokens=200
            )

            if comment:
                comment = self._postprocess_comment(comment)
                logger.debug(f"Generated comment ({strategy}): {comment[:50]}...")
                return comment

            return None

        except Exception as e:
            logger.error(f"Failed to generate comment: {e}")
            return None

    def _postprocess_comment(self, comment: str) -> str:
        """
        Постобработка комментария.
        """
        comment = comment.strip('"\'')

        unwanted_prefixes = [
            "Комментарий:",
            "Мой комментарий:",
            "Вот комментарий:",
        ]
        for prefix in unwanted_prefixes:
            if comment.startswith(prefix):
                comment = comment[len(prefix):].strip()

        if len(comment) > 500:
            comment = comment[:500]
            last_dot = comment.rfind('.')
            if last_dot > 200:
                comment = comment[:last_dot + 1]

        return comment

    async def should_comment(
        self,
        post_text: str,
        has_comments: bool = False,
        is_ad: bool = False,
        is_repost: bool = False,
    ) -> bool:
        """
        Решает, стоит ли комментировать пост.
        """
        if is_ad:
            logger.debug("Skipping ad post")
            return False

        if is_repost:
            logger.debug("Skipping repost")
            return False

        if len(post_text.strip()) < 50:
            logger.debug("Post too short")
            return False

        if not post_text.strip():
            return False

        bad_keywords = [
            "реклама", "промокод", "скидка 90%", "розыгрыш",
            "конкурс", "подписывайся", "переходи по ссылке",
        ]
        text_lower = post_text.lower()
        for keyword in bad_keywords:
            if keyword in text_lower:
                logger.debug(f"Post contains bad keyword: {keyword}")
                return False

        return random.random() < 0.8

    def get_random_strategy(self, weights: Optional[Dict[str, float]] = None) -> str:
        """
        Выбрать случайную стратегию комментирования.
        """
        if weights is None:
            weights = {
                "smart": 0.4,
                "supportive": 0.3,
                "funny": 0.15,
                "expert": 0.15,
            }

        strategies = list(weights.keys())
        probs = list(weights.values())

        return random.choices(strategies, weights=probs, k=1)[0]
