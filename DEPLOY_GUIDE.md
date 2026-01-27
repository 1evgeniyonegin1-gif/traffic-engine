# Деплой Story Viewing на сервер 🚀

## Быстрый деплой (5 минут)

### 1. Закоммитить изменения
```bash
cd "c:\Users\mafio\OneDrive\Документы\projects\info-business\traffic-engine-mvp"

git add .
git commit -m "fix: Story Viewing готов - исправлены все проблемы

- Исправлены ошибки кодировки Windows (emoji -> ASCII)
- Добавлена тестовая ЦА (100 пользователей)
- Понижен порог quality_score с 70 до 50
- Созданы скрипты для мониторинга и статистики
- Story Viewing полностью функционален"

git push
```

### 2. Подключиться к серверу
```bash
ssh root@ВАШ_IP
```

### 3. Обновить код на сервере
```bash
cd /root/traffic-engine-mvp
git pull
```

### 4. Обновить .env (если нужно)
```bash
nano .env
```

Проверить что стоит:
```env
STORY_VIEW_MIN_QUALITY_SCORE=50
MAX_STORY_VIEWS_PER_DAY=3
MIN_STORY_INTERVAL_SEC=300
MAX_STORY_INTERVAL_SEC=900
```

### 5. Добавить ЦА на сервере
```bash
# Опция 1: Тестовая ЦА (быстро)
python scripts/quick_add_audience.py

# Опция 2: Реальная ЦА (медленнее, но лучше)
python scripts/collect_target_audience.py
```

### 6. Проверить готовность
```bash
python scripts/check_story_viewing_ready.py
```

Должно быть: `[OK] Всё проверки пройдены!`

### 7. Перезапустить систему
```bash
# Если используете systemd
systemctl restart traffic-engine

# Или если через screen/tmux
pkill -f run_auto_comments.py
screen -dmS traffic python run_auto_comments.py
```

### 8. Мониторинг
```bash
# Смотреть логи
tail -f logs/traffic_engine_*.log | grep -E "(story|comment)"

# В другом окне - статистика
python scripts/show_comments_stats.py
python scripts/story_stats.py
```

---

## Полезные команды на сервере

### Статистика
```bash
# Все комментарии и story views
python scripts/show_comments_stats.py

# Статус системы
python scripts/quick_status.py

# Все аккаунты
python scripts/show_all_accounts.py

# Проверить ЦА
python scripts/check_audience.py
```

### Управление
```bash
# Перезапуск
systemctl restart traffic-engine

# Статус
systemctl status traffic-engine

# Логи в реальном времени
journalctl -u traffic-engine -f

# Или если через screen
screen -r traffic
```

### Проблемы?
```bash
# Проверить что работает
ps aux | grep python

# Проверить порты
netstat -tulpn | grep python

# Очистить логи (если большие)
rm logs/*.log
```

---

## Systemd сервис (если ещё нет)

Создать файл `/etc/systemd/system/traffic-engine.service`:

```ini
[Unit]
Description=Traffic Engine - Auto Comments & Story Viewing
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/traffic-engine-mvp
ExecStart=/usr/bin/python3 /root/traffic-engine-mvp/run_auto_comments.py
Restart=always
RestartSec=10
StandardOutput=append:/root/traffic-engine-mvp/logs/systemd.log
StandardError=append:/root/traffic-engine-mvp/logs/systemd.log

[Install]
WantedBy=multi-user.target
```

Активировать:
```bash
systemctl daemon-reload
systemctl enable traffic-engine
systemctl start traffic-engine
systemctl status traffic-engine
```

---

## Ожидаемое поведение

### Комментарии
- **Сейчас:** ~8-14% success rate (норма для прогрева)
- **Через неделю:** должно вырасти до 30-50%

### Story Views
- **День 2:** 3 просмотра/день, интервалы 5-15 мин
- **Ожидаемо:** 40-60% success (у многих нет сторис - это норма)

### Логи
```
[INFO] Viewing story from user @test_user (quality: 75)
[SUCCESS] Story viewed successfully
[INFO] User @another_user has no stories (норма)
[INFO] Posted comment to @portnyaginlive: "текст..." (success)
```

---

## Что делать после деплоя

### Первый час
```bash
# Смотреть логи
tail -f logs/traffic_engine_*.log
```

Ищем:
- ✅ `Story viewed successfully` - работает!
- ✅ `Posted comment` + `success` - работает!
- ⚠️ `No stories available` - норма
- ❌ `FloodWait` > 3 раз - проблема (увеличить интервалы)

### Каждый день
```bash
# Статистика
python scripts/show_comments_stats.py
```

Проверяем:
- Success rate растёт?
- Нет банов аккаунтов?
- FloodWait не часто?

### Через неделю
- Если всё ОК → увеличить лимиты (День 4-7)
- Если проблемы → остаться на текущих лимитах

---

## Контакты для проверки

После деплоя напишите мне статистику:
```bash
python scripts/show_comments_stats.py
python scripts/story_stats.py
```

Проверю что всё работает правильно!
