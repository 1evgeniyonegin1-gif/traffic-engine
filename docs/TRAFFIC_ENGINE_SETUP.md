# Traffic Engine — Техническая документация

## Обзор системы

Traffic Engine — система лидогенерации через Telegram с 3 каналами привлечения:
1. **Комментарии в каналах** — AI генерирует комменты под постами
2. **Просмотры сторис + реакции** — просмотр сторис ЦА + эмодзи реакции
3. **Инвайты в группы** — приглашение пользователей в группы-мероприятия

---

## Структура проекта

```
traffic-engine-mvp/
├── dashboard/                      # Веб-дашборд (Flask)
│   └── app.py                     # Главный файл дашборда
├── traffic_engine/
│   ├── channels/
│   │   ├── auto_comments/         # Канал 1: Комментарии
│   │   │   ├── channel_monitor.py # Мониторинг каналов
│   │   │   ├── comment_generator.py # AI генерация комментов
│   │   │   └── comment_poster.py  # Публикация комментариев
│   │   ├── story_viewer/          # Канал 2: Сторис
│   │   │   ├── story_monitor.py   # Мониторинг сторис
│   │   │   └── story_reactor.py   # Реакции на сторис
│   │   └── chat_inviter/          # Канал 3: Инвайты
│   │       ├── chat_inviter.py    # Инвайты пользователей
│   │       └── group_creator.py   # Создание групп
│   ├── database/
│   │   └── models.py              # SQLAlchemy модели
│   ├── notifications/
│   │   └── telegram_notifier.py   # Уведомления админу
│   └── main.py                    # Точка входа
├── scripts/
│   ├── manage_proxy.py            # Управление прокси
│   ├── setup_account_profile.py   # Настройка профилей
│   └── create_event_group.py      # Создание групп
└── docs/
    ├── TRAFFIC_ENGINE_SETUP.md    # Этот файл
    ├── DASHBOARD.md               # Документация дашборда
    └── CHAT_INVITER.md            # Документация инвайтов
```

---

## Требования

### Софт
- Python 3.10+
- PostgreSQL 13+ с pgvector
- Redis (опционально, для кэша)

### Python зависимости
```bash
pip install -r requirements.txt
```

Ключевые пакеты:
- `telethon` — Telegram API
- `sqlalchemy[asyncio]` — ORM
- `asyncpg` — PostgreSQL драйвер
- `flask` — веб-дашборд
- `aiohttp-socks` — прокси для аккаунтов

---

## Настройка

### 1. База данных

```sql
-- Создать базу
CREATE DATABASE traffic_engine;

-- Создать таблицы (автоматически через SQLAlchemy)
python -c "from traffic_engine.database import init_db; import asyncio; asyncio.run(init_db())"
```

### 2. Переменные окружения (.env)

```env
# База данных
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/traffic_engine

# Telegram API (получить на my.telegram.org)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash

# AI для генерации комментариев
YANDEX_FOLDER_ID=your_folder_id
YANDEX_API_KEY=your_api_key
YANDEX_MODEL=yandexgpt-32k

# Воронка
FUNNEL_LINK=https://t.me/your_bot

# Уведомления админу
ALERT_BOT_TOKEN=your_bot_token
ALERT_ADMIN_ID=your_telegram_id
ALERTS_ENABLED=true

# Лимиты (на аккаунт в день)
MAX_COMMENTS_PER_DAY=50
MAX_STORY_VIEWS_PER_DAY=250
MAX_STORY_REACTIONS_PER_DAY=50
MAX_INVITES_PER_DAY=40
```

### 3. Добавление аккаунтов

```bash
# Через QR код (рекомендуется)
python scripts/qr_auth.py

# Через session string
python scripts/simple_reauth.py
```

### 4. Настройка прокси для аккаунтов

**ВАЖНО:** Для иностранных аккаунтов (не RU) обязательно нужен прокси той же страны!

```bash
# Посмотреть все аккаунты
python scripts/manage_proxy.py --list

# Добавить прокси
python scripts/manage_proxy.py --add --phone "+62xxx" --proxy "socks5://user:pass@ip:port"

# Проверить прокси
python scripts/manage_proxy.py --test --phone "+62xxx"
```

---

## Запуск

### Основная система
```bash
cd traffic-engine-mvp
python -m traffic_engine.main
```

### Веб-дашборд (отдельно)
```bash
python dashboard/app.py
# Открыть http://localhost:8050
```

---

## Веб-дашборд

Дашборд показывает в реальном времени:

### Статистика (верхние карточки)
- Комментарии сегодня (всего / успешных)
- Сторис сегодня (просмотры + реакции)
- Инвайты сегодня
- Активные аккаунты
- Success Rate

### Таблица аккаунтов
| Колонка | Описание |
|---------|----------|
| Account | Имя + username |
| Phone/Country | Номер телефона + флаг страны |
| Proxy | Статус прокси (✅ настроен / ❌ нет + предупреждение) |
| Status | active/warming/banned/cooldown |
| Comments | Комментариев сегодня |
| Stories | Просмотров / реакций |
| Invites | Инвайтов сегодня |
| Last activity | Время последнего действия |

**Визуальные предупреждения:**
- Красный фон строки = аккаунт без прокси (не RU) — риск бана
- ⚠️ Risk of ban! — явное предупреждение

### API Endpoints
- `GET /api/stats` — общая статистика
- `GET /api/accounts` — список аккаунтов
- `GET /api/comments` — последние комментарии
- `GET /api/stories` — последние просмотры сторис
- `GET /api/invites` — последние инвайты

---

## Управление прокси

### Зачем нужен прокси

Telegram отслеживает:
- IP-адрес при входе
- Геолокацию
- Смену IP между сессиями

Если индонезийский аккаунт работает с российского IP — это красный флаг.

### Типы прокси

| Тип | Подходит для Telegram | Цена |
|-----|----------------------|------|
| **Residential** | ✅ Да | $3-7/мес |
| **Mobile** | ✅ Идеально | $15-30/мес |
| **Datacenter** | ❌ Детектятся | $0.5-2/мес |

### Где купить

| Провайдер | Цена Indonesia | URL |
|-----------|----------------|-----|
| Proxy-Seller | ~$3/мес | proxy-seller.com |
| Proxys.io | ~$4/мес | proxys.io |
| 922 S5 Proxy | ~$2.5/мес | 922proxy.com |

### Команды

```bash
# Список аккаунтов с прокси
python scripts/manage_proxy.py --list

# Добавить прокси
python scripts/manage_proxy.py --add --phone "+62xxx" --proxy "socks5://user:pass@ip:port"

# Удалить прокси
python scripts/manage_proxy.py --remove --phone "+62xxx"

# Тест прокси (показывает IP и геолокацию)
python scripts/manage_proxy.py --test --phone "+62xxx"
```

---

## Модели данных

### UserBotAccount
```python
class UserBotAccount:
    id: int
    phone: str                    # Номер телефона
    session_string: str           # Telethon session
    status: str                   # active, warming, banned, cooldown

    # Прокси
    proxy_type: str               # socks5, http
    proxy_host: str
    proxy_port: int
    proxy_username: str
    proxy_password: str

    # Лимиты
    daily_comments: int
    daily_story_views: int
    daily_story_reactions: int
    daily_invites: int
```

### TrafficAction
```python
class TrafficAction:
    id: int
    account_id: int
    action_type: str              # comment, story_view, story_reaction, invite
    status: str                   # success, failed, flood_wait
    content: str                  # Текст комментария
    created_at: datetime
```

---

## Расчёт бюджета

### Разовые расходы
| Статья | Кол-во | Цена | Итого |
|--------|--------|------|-------|
| Аккаунты Indonesia | 5-7 шт | 65₽ | ~450₽ |

### Ежемесячные расходы
| Статья | Кол-во | Цена | Итого |
|--------|--------|------|-------|
| Прокси Residential | 5 шт | ~300₽ | ~1,500₽ |
| YandexGPT | - | - | ~600₽ |
| Замена акков | 1-2 шт | 65₽ | ~130₽ |
| **ИТОГО** | | | **~2,230₽/мес** |

### Ожидаемый результат (5 аккаунтов)

| Канал | Действий/день | Лидов/мес |
|-------|---------------|-----------|
| Комментарии | 250 | ~150 |
| Story просмотры | 1,250 | ~187 |
| Story реакции | 250 | ~75 |
| Инвайты | 200 | ~300 |
| **ИТОГО** | | **150-300 лидов** |

---

## Безопасность

### Правила использования прокси
1. **1 прокси = 1 аккаунт** (не использовать один прокси для нескольких)
2. **Не менять прокси** после привязки
3. **Прогрев** — первые 7 дней минимальная активность
4. **Разные продавцы** — не все аккаунты из одного источника

### Лимиты (рекомендуемые)
| Действие | Новый аккаунт | После прогрева |
|----------|---------------|----------------|
| Комментарии | 10/день | 50/день |
| Просмотры сторис | 50/день | 250/день |
| Реакции | 10/день | 50/день |
| Инвайты | 5/день | 40/день |

---

## Troubleshooting

### AuthKeyDuplicatedError
**Причина:** Сессия используется с разных IP одновременно.
**Решение:** Проверить что аккаунт не залогинен в другом месте.

### FloodWaitError
**Причина:** Превышены лимиты Telegram.
**Решение:** Система автоматически ставит cooldown. Уменьшить лимиты.

### "Failed to get channel entity"
**Причина:** Аккаунт не подписан на канал.
**Решение:** Исправлено — система автоматически подписывается.

### "You must join discussion group"
**Причина:** Нужно вступить в группу обсуждений.
**Решение:** Исправлено — система автоматически вступает.

---

## Изменения 31.01.2026

### Дашборд
- Добавлена колонка **Phone/Country** с флагом страны
- Добавлена колонка **Proxy** с визуальным статусом
- Красный фон для аккаунтов без прокси (не RU)
- Предупреждение "⚠️ Risk of ban!"

### Скрипт manage_proxy.py
- `--list` — показать все аккаунты с прокси
- `--add` — добавить прокси
- `--remove` — удалить прокси
- `--test` — проверить работу прокси

### Исправления comment_poster.py
- Авто-подписка на каналы
- Авто-вступление в группы обсуждений
- Обработка AuthKeyDuplicatedError
- Улучшенное кэширование entities

---

## Контакты

- **Репозиторий:** traffic-engine-mvp
- **VPS:** 194.87.86.103
- **Admin Telegram ID:** 756877849
