# ✅ Story Viewing - Чеклист перед запуском

**Используйте этот чеклист перед запуском Story Viewing в продакшене.**

---

## 📋 Pre-flight проверки

### ✅ 1. База данных

```bash
# Проверить ЦА
psql -d info_business -c "SELECT COUNT(*) FROM traffic_target_audience WHERE quality_score >= 70;"
```

**Ожидаемо:** Минимум 10-20 пользователей
**Если 0:** Запустить систему на 2-3 часа для сбора ЦА

---

### ✅ 2. Аккаунты

```bash
# Проверить активные аккаунты
psql -d info_business -c "SELECT phone, status, daily_story_views FROM traffic_userbot_accounts WHERE status IN ('active', 'warming');"
```

**Ожидаемо:** Минимум 1 активный аккаунт
**Проверить:** Нет аккаунтов в cooldown

---

### ✅ 3. Настройки .env

```bash
grep -E "STORY_VIEW|MAX_STORY" .env
```

**Проверить:**
- [ ] `MAX_STORY_VIEWS_PER_DAY=3` (день 2)
- [ ] `MIN_STORY_INTERVAL_SEC=300` (5 мин)
- [ ] `MAX_STORY_INTERVAL_SEC=900` (15 мин)
- [ ] `STORY_VIEW_MIN_QUALITY_SCORE=70`

---

### ✅ 4. Код интегрирован

```bash
# Проверить импорты
grep -n "StoryMonitor" traffic_engine/main.py
```

**Ожидаемо:** 3 упоминания (import, запуск, остановка)

---

### ✅ 5. Автоматическая проверка

```bash
python scripts/check_story_viewing_ready.py
```

**Ожидаемо:** "✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!"

---

## 🚀 Запуск

### ✅ 6. Первый запуск

```bash
# Запустить
python run_auto_comments.py

# В отдельном терминале: мониторинг логов
tail -f logs/traffic_engine_*.log | grep -E "(story|Story)"
```

**Ожидать в логах (через 5-15 мин):**
```
Story monitor initialized
Story monitor started for tenant infobusiness
📍 Selected target user 123456789 (quality=85, source=channel_subscribers)
👁️ Viewing story 12345 from user 123456789...
✅ Successfully viewed story 12345 from user 123456789
```

---

## 🧪 Валидация (через 30 мин)

### ✅ 7. Проверить логи

```bash
# Успешные просмотры
grep "Successfully viewed story" logs/traffic_engine_*.log | wc -l

# Ошибки
grep "ERROR.*story" logs/traffic_engine_*.log

# FloodWait
grep "FloodWait.*story" logs/traffic_engine_*.log
```

**Ожидаемо:**
- Минимум 1-2 успешных просмотра
- 0 ERROR
- 0 FloodWait

---

### ✅ 8. Проверить БД

```sql
-- Записи о просмотрах
SELECT COUNT(*), status FROM traffic_actions
WHERE action_type='story_view'
GROUP BY status;

-- Счётчики аккаунтов
SELECT phone, daily_story_views FROM traffic_userbot_accounts;
```

**Ожидаемо:**
- Записи в `traffic_actions`
- `daily_story_views` > 0 хотя бы у одного аккаунта

---

### ✅ 9. Быстрая статистика

```bash
python scripts/story_stats.py
```

**Ожидаемо:**
```
📊 Story Views Today: 2
   ✅ Success: 1 (50%)
   ⏭️  Skipped: 1
   ❌ Failed: 0
```

---

## 📊 Мониторинг первые 24 часа

### ✅ 10. Проверки каждые 2-3 часа

```bash
# 1. Статистика
python scripts/story_stats.py

# 2. FloodWait
grep "FloodWait" logs/traffic_engine_*.log | tail -5

# 3. Ошибки
grep "ERROR.*story" logs/traffic_engine_*.log | tail -10
```

**Красные флаги:**
- ❌ FloodWait > 3 раз/час → увеличить интервалы
- ❌ Success rate < 30% → проверить ЦА
- ❌ Баны аккаунтов → СТОП

---

## 🎯 Критерии успеха (день 1)

- ✅ **Просмотров:** 8-12 за день (4 аккаунта × 2-3)
- ✅ **Success rate:** 40-60%
- ✅ **FloodWait:** 0-1 за день
- ✅ **Ошибок:** < 5%
- ✅ **Интервалы:** 5-15 минут соблюдаются

---

## 🔧 Если что-то не так

### Проблема: "No target users available"

```bash
# Проверить ЦА
psql -d info_business -c "SELECT quality_score, COUNT(*) FROM traffic_target_audience GROUP BY quality_score ORDER BY quality_score DESC;"

# Решение 1: Временно понизить порог
# В .env: STORY_VIEW_MIN_QUALITY_SCORE=50

# Решение 2: Собрать больше ЦА (запустить систему на 3+ часа)
```

---

### Проблема: FloodWait частые

```bash
# Увеличить интервалы в .env:
MIN_STORY_INTERVAL_SEC=600  # 10 минут
MAX_STORY_INTERVAL_SEC=1200 # 20 минут

# Перезапустить
```

---

### Проблема: Success rate < 30%

```sql
-- Проверить статусы
SELECT status, error_message, COUNT(*)
FROM traffic_actions
WHERE action_type='story_view'
GROUP BY status, error_message;

-- Причины:
-- "Private stories" - нормально, просто закрыты
-- "Invalid peer" - удалённые аккаунты
-- "No stories" - пользователь не публикует
```

---

## 📈 День 3: Увеличение лимитов

**Условия:**
- ✅ День 2 прошёл без FloodWait
- ✅ Success rate > 40%
- ✅ Нет банов аккаунтов

**Изменения в .env:**
```env
MAX_STORY_VIEWS_PER_DAY=5   # было 3
MIN_STORY_INTERVAL_SEC=180  # было 300 (3 мин вместо 5)
```

**Перезапустить и мониторить снова.**

---

## 🎉 Критерии готовности к продакшену

- ✅ 3 дня стабильной работы
- ✅ FloodWait < 2/день
- ✅ Success rate стабильно > 40%
- ✅ Нет банов аккаунтов
- ✅ Логи чистые (без ERROR)

---

**После прохождения всех проверок - система готова к продакшену! 🚀**
