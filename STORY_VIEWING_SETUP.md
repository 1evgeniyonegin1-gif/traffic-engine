# Настройка и запуск Reverse Viewing (просмотр Stories ЦА)

**Дата реализации:** 27 января 2026
**Статус:** Готов к тестированию

---

## ✅ Что было реализовано

### Новые файлы:
1. `traffic_engine/channels/story_viewer/__init__.py` - Инициализация модуля
2. `traffic_engine/channels/story_viewer/story_viewer.py` - Класс для просмотра stories через Telethon API
3. `traffic_engine/channels/story_viewer/story_monitor.py` - Основной цикл мониторинга

### Изменённые файлы:
1. `traffic_engine/main.py` - Интеграция StoryMonitor (запуск/остановка)
2. `traffic_engine/config.py` - Добавлен параметр `story_view_min_quality_score`
3. `.env` - Обновлены лимиты для day 2 прогрева

---

## 🎯 Функционал

**Что делает Story Viewer:**
1. Выбирает пользователей из таблицы `traffic_target_audience` с `quality_score >= 70`
2. Проверяет наличие активных stories у выбранного пользователя
3. Смотрит 1 рандомную story (если их несколько)
4. Логирует просмотр в `traffic_actions` (action_type='story_view')
5. Обновляет счётчик `daily_story_views` в `userbot_accounts`

**Безопасность:**
- 3 просмотра/день на аккаунт (день 2 прогрева)
- Интервалы 5-15 минут между просмотрами
- Только рабочие часы (9:00-23:00)
- Обработка FloodWait с автоматическим cooldown
- Только высококачественная ЦА (quality_score >= 70)

---

## 📋 Предварительные требования

### 1. Проверить наличие ЦА в БД

```sql
-- Подключиться к БД
psql -U postgres -d info_business

-- Проверить количество пользователей ЦА с высоким quality_score
SELECT COUNT(*) as high_quality_users
FROM traffic_target_audience
WHERE quality_score >= 70
  AND status IN ('new', 'contacted');
```

**Ожидаемый результат:** Минимум 10-20 пользователей

**Если 0:** Сначала нужно собрать ЦА через комментирование (запустить `run_auto_comments.py` на несколько часов)

### 2. Проверить статус аккаунтов

```sql
-- Проверить активные аккаунты
SELECT id, phone, status, daily_comments, daily_story_views, last_action_at
FROM traffic_userbot_accounts
WHERE status IN ('active', 'warming');
```

**Ожидаемый результат:** Минимум 1 активный аккаунт

---

## 🚀 Запуск

### Локальное тестирование

```bash
# 1. Перейти в директорию проекта
cd "c:\Users\mafio\OneDrive\Документы\projects\info-business\traffic-engine-mvp"

# 2. Активировать venv (если используется)
# venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Запустить Traffic Engine
python run_auto_comments.py
```

### Что должно произойти при запуске

**В логах вы увидите:**
```
Starting Traffic Engine ===
Database initialized
Telegram notifier initialized
Found 1 active tenant(s)
Starting tenant: Info Business
Story monitor initialized
Story monitor started for tenant infobusiness
Tenant infobusiness started (with story viewing)
Traffic Engine is running. Press Ctrl+C to stop.
```

**Через 5-15 минут:**
```
📍 Selected target user 123456789 (quality=85, source=channel_subscribers)
👁️ Viewing story 12345 from user 123456789...
⏱️ Simulating view delay: 5.2s
✅ Successfully viewed story 12345 from user 123456789
📊 Account 1 story views: 1
⏳ Waiting 7.3 min before next story view...
```

---

## 🧪 Проверки после запуска

### 1. Проверить логи

```bash
# Смотреть логи в реальном времени
tail -f logs/traffic_engine_*.log | grep -E "(story_view|StoryMonitor)"

# Поиск ошибок
grep "ERROR" logs/traffic_engine_*.log | tail -20
grep "FloodWait" logs/traffic_engine_*.log
```

### 2. Проверить записи в БД

```sql
-- Последние 10 просмотров stories
SELECT
    id,
    account_id,
    action_type,
    target_user_id,
    target_story_id,
    status,
    error_message,
    created_at
FROM traffic_actions
WHERE action_type = 'story_view'
ORDER BY created_at DESC
LIMIT 10;
```

**Ожидаемый результат:**
- `status = 'success'` для успешных просмотров
- `status = 'skipped'` для пользователей без stories
- `status = 'failed'` только если есть критические ошибки

### 3. Проверить счётчики аккаунтов

```sql
-- Счётчики просмотров по аккаунтам
SELECT
    id,
    phone,
    daily_story_views,
    daily_comments,
    last_action_at
FROM traffic_userbot_accounts
ORDER BY id;
```

**Ожидаемый результат:**
- `daily_story_views` увеличивается после каждого просмотра
- Не превышает `MAX_STORY_VIEWS_PER_DAY=3`

### 4. Статистика за день

```sql
-- Статистика просмотров за сегодня
SELECT
    DATE(created_at) as date,
    account_id,
    COUNT(*) as total_views,
    COUNT(CASE WHEN status='success' THEN 1 END) as successful,
    COUNT(CASE WHEN status='skipped' THEN 1 END) as skipped,
    COUNT(CASE WHEN status='failed' THEN 1 END) as failed
FROM traffic_actions
WHERE action_type = 'story_view'
  AND created_at >= CURRENT_DATE
GROUP BY DATE(created_at), account_id;
```

---

## ⚠️ Возможные проблемы и решения

### Проблема 1: "No target users available for story viewing"

**Причина:** В БД нет пользователей ЦА с `quality_score >= 70`

**Решение:**
```sql
-- Проверить какие пользователи есть
SELECT quality_score, COUNT(*)
FROM traffic_target_audience
GROUP BY quality_score
ORDER BY quality_score DESC;

-- Временно понизить порог (только для теста!)
-- Отредактировать .env: STORY_VIEW_MIN_QUALITY_SCORE=50
```

### Проблема 2: "⏭️ User XXX has no active stories"

**Это нормально!** Многие пользователи не публикуют stories регулярно.

**Ожидаемый success rate:** 40-60% (из 10 попыток 4-6 успешных)

### Проблема 3: "⚠️ FloodWait 120s for account 1"

**Причина:** Telegram ограничил частоту запросов

**Решение:**
- Система автоматически установит cooldown
- Аккаунт возобновит работу через указанное время
- Если FloodWait частые (>3 раз/час) → увеличить интервалы в .env:
  ```env
  MIN_STORY_INTERVAL_SEC=600  # 10 минут
  MAX_STORY_INTERVAL_SEC=1200  # 20 минут
  ```

### Проблема 4: "Failed to get stories for user XXX: UserPrivacyRestrictedError"

**Это нормально!** Пользователь закрыл stories для неподписчиков.

**Действия:** Никаких, система автоматически пропустит и выберет следующего.

### Проблема 5: "Cannot get entity for user XXX: PeerIdInvalidError"

**Причина:** Пользователь удалил аккаунт или заблокировал бота

**Действия:** Система автоматически пропустит, можно очистить ЦА:
```sql
-- Опционально: удалить недоступных пользователей
DELETE FROM traffic_target_audience
WHERE user_id IN (
  SELECT DISTINCT target_user_id
  FROM traffic_actions
  WHERE action_type = 'story_view'
    AND status = 'failed'
    AND error_message LIKE '%Invalid peer%'
);
```

---

## 📈 Увеличение лимитов (после успешных тестов)

### День 3-4 (через 24-48 часов):
```env
MAX_STORY_VIEWS_PER_DAY=5
MIN_STORY_INTERVAL_SEC=180  # 3 минуты
MAX_STORY_INTERVAL_SEC=600  # 10 минут
```

### День 5-7:
```env
MAX_STORY_VIEWS_PER_DAY=10
MIN_STORY_INTERVAL_SEC=120  # 2 минуты
```

### День 8-14:
```env
MAX_STORY_VIEWS_PER_DAY=30
MIN_STORY_INTERVAL_SEC=60   # 1 минута
```

### День 15+:
```env
MAX_STORY_VIEWS_PER_DAY=50
```

**Правило:** Увеличивать лимиты только если:
- FloodWait ошибок < 2 раз/день
- Success rate > 40%
- Нет банов аккаунтов

---

## 📊 Мониторинг эффективности

### Полезные SQL запросы

```sql
-- 1. Success rate по дням
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_attempts,
    COUNT(CASE WHEN status='success' THEN 1 END) as successful,
    ROUND(100.0 * COUNT(CASE WHEN status='success' THEN 1 END) / COUNT(*), 1) as success_rate_pct
FROM traffic_actions
WHERE action_type = 'story_view'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- 2. Топ пользователей с stories
SELECT
    target_user_id,
    COUNT(*) as stories_viewed
FROM traffic_actions
WHERE action_type = 'story_view'
  AND status = 'success'
GROUP BY target_user_id
ORDER BY stories_viewed DESC
LIMIT 10;

-- 3. FloodWait частота
SELECT
    account_id,
    COUNT(*) as floodwait_count,
    AVG(CAST(SUBSTRING(error_message FROM '[0-9]+') AS INTEGER)) as avg_wait_seconds
FROM traffic_actions
WHERE action_type = 'story_view'
  AND status = 'failed'
  AND error_message LIKE '%FloodWait%'
GROUP BY account_id;
```

---

## 🛑 Остановка

```bash
# Нажать Ctrl+C в терминале
# Или
pkill -f "python run_auto_comments.py"
```

**Что произойдёт:**
- StoryMonitor gracefully остановится
- Все клиенты отключатся
- Уведомление в Telegram (если настроено)

---

## 🎯 Ожидаемые результаты (день 2-3)

| Метрика | Значение |
|---------|----------|
| **Просмотров/день** | 8-12 (4 аккаунта × 2-3) |
| **Success rate** | 40-60% |
| **FloodWait ошибок** | 0-1/день |
| **Охват ЦА** | ~10 уникальных пользователей/день |
| **Интервал между просмотрами** | 5-15 минут |

---

## 📝 Логирование

**Уровни логов:**
- `INFO` - успешные просмотры, запуск/остановка
- `DEBUG` - детали выбора пользователей, задержки
- `WARNING` - FloodWait, пользователи без stories
- `ERROR` - критические ошибки

**Изменить уровень в .env:**
```env
LOG_LEVEL=DEBUG  # для детальных логов
LOG_LEVEL=INFO   # для обычной работы
```

---

## 🔄 Следующие шаги (после успешного MVP)

1. **Реакции на stories** - отдельный action_type='story_reaction'
2. **Сбор viewers stories** - кто смотрит наши stories → добавить в ЦА
3. **Аналитика конверсий** - отслеживание story_view → funnel_visit
4. **Адаптивные лимиты** - автоматическое увеличение при 0 FloodWait

---

## 💡 Tips

1. **Запускайте в рабочие часы** (9-23) - вне этого времени система спит
2. **Не форсируйте увеличение лимитов** - безопасность > скорость
3. **Следите за FloodWait** - если частые → увеличить интервалы
4. **Регулярно проверяйте БД** - мониторинг счётчиков и ошибок
5. **Бэкапьте сессии аккаунтов** - они в папке `sessions/`

---

**Вопросы?** Проверьте логи в `logs/traffic_engine_*.log`
