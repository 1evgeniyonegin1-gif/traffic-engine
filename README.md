# Traffic Engine MVP

Система автоматизированной лидогенерации через Telegram.

**3 канала привлечения:**
1. **Комментарии** — AI-генерация комментариев в целевых каналах
2. **Сторис** — просмотр и реакции на сторис ЦА (обратный просмотр)
3. **Инвайты** — приглашение людей в группы-мероприятия

---

## Быстрый старт

### 1. Запуск системы

```bash
cd traffic-engine-mvp

# Активировать venv
..\venv\Scripts\activate  # Windows

# Запустить систему
python run_auto_comments.py
```

### 2. Запуск дашборда

```bash
# В отдельном терминале
python dashboard/app.py

# Открыть в браузере: http://localhost:8050
```

### 3. Проверка статистики

```bash
python scripts/check_stats.py      # Статистика
python scripts/show_accounts.py    # Аккаунты
python scripts/check_bans.py       # Баны
```

---

## Структура проекта

```
traffic-engine-mvp/
├── traffic_engine/              # Исходный код
│   ├── channels/
│   │   ├── auto_comments/      # Канал 1: Комментарии
│   │   ├── story_viewer/       # Канал 2: Сторис
│   │   └── chat_inviter/       # Канал 3: Инвайты
│   ├── core/                   # AccountManager, RateLimiter
│   ├── database/               # Модели БД
│   ├── notifications/          # Уведомления в Telegram
│   └── main.py                 # Точка входа
│
├── dashboard/                   # Веб-дашборд
│   └── app.py                  # Flask приложение
│
├── scripts/                    # Утилиты
│   ├── import_session.py       # Импорт аккаунта
│   ├── setup_account_profile.py # Настройка профиля
│   ├── create_event_group.py   # Создание группы
│   └── ...
│
├── sessions/                   # .session файлы
├── docs/                       # Документация
├── .env                        # Конфигурация
└── requirements.txt            # Зависимости
```

---

## Конфигурация (.env)

### Лимиты по умолчанию (прогрев)

```env
MAX_COMMENTS_PER_DAY=5        # Комментарии
MAX_STORY_VIEWS_PER_DAY=3     # Просмотры сторис
MAX_STORY_REACTIONS_PER_DAY=0 # Реакции (отключены)
MAX_INVITES_PER_DAY=0         # Инвайты (отключены)
```

### После прогрева (30 дней)

```env
MAX_COMMENTS_PER_DAY=50
MAX_STORY_VIEWS_PER_DAY=50
MAX_STORY_REACTIONS_PER_DAY=20
MAX_INVITES_PER_DAY=40
```

---

## График прогрева

| День | Комменты | Сторис | Реакции | Инвайты |
|------|----------|--------|---------|---------|
| 1-7  | 5/день   | 5/день | 0       | 0       |
| 8-14 | 25/день  | 10/день| 0       | 0       |
| 15-21| 35/день  | 20/день| 5/день  | 10/день |
| 22-30| 50/день  | 30/день| 10/день | 20/день |
| 30+  | 50/день  | 50/день| 20/день | 40/день |

Подробнее: [docs/WARMUP_SCHEDULE.md](docs/WARMUP_SCHEDULE.md)

---

## Уведомления

Система отправляет уведомления в Telegram при:
- Бане аккаунта
- FloodWait > 1 часа
- Ошибках AI
- Запуске/остановке системы

Настройки в `.env`:
```env
ALERT_BOT_TOKEN=your_bot_token
ALERT_ADMIN_ID=your_telegram_id
ALERTS_ENABLED=true
```

---

## Управление аккаунтами

### Импорт аккаунта

```bash
# Из .session файла
python scripts/import_session.py --session file.session --name account1

# Из tdata
python scripts/import_tdata.py --tdata path/to/tdata --name account1
```

### Настройка профиля

```bash
python scripts/setup_account_profile.py --account account1 \
    --name "Карина" \
    --bio "Из найма в онлайн | 150К на удалёнке" \
    --photo photos/avatar.jpg
```

### Создание группы-мероприятия

```bash
# Из шаблона
python scripts/create_event_group.py --account account1 --template profession_2026

# Интерактивно
python scripts/create_event_group.py --account account1

# Показать шаблоны
python scripts/create_event_group.py --list-templates
```

---

## Документация

| Файл | Описание |
|------|----------|
| [docs/WARMUP_SCHEDULE.md](docs/WARMUP_SCHEDULE.md) | График прогрева |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | Дашборд |
| [docs/CHAT_INVITER.md](docs/CHAT_INVITER.md) | Инвайты в группы |
| [docs/TARGET_CHANNELS.md](docs/TARGET_CHANNELS.md) | Целевые каналы |

---

## Ожидаемые результаты

**На 5 аккаунтов после прогрева:**

| Канал | Действий/день | Лидов/мес |
|-------|---------------|-----------|
| Комментарии | 250 | ~150 |
| Сторис | 1,250 | ~180 |
| Инвайты | 200 | ~300 |
| **Итого** | | **150-300** |

---

**Дата обновления:** 31 января 2026
