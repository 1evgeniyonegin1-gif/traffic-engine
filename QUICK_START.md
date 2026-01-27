# Quick Start Guide

## Локальный запуск (Windows)

### 1. Активировать виртуальное окружение
```bash
cd c:\Users\mafio\OneDrive\Документы\projects\info-business\traffic-engine-mvp
venv\Scripts\activate
```

### 2. Запустить систему
```bash
python run_auto_comments.py
```

### 3. Проверить статистику
```bash
# В другом терминале
python check_pg_stats.py
python check_failed_reasons.py
```

## Управление каналами

### Отключить проблемные каналы
```bash
python scripts\disable_restricted_channels.py
```

### Подписаться на discussion groups
```bash
python scripts\auto_join_discussion_groups.py
```

### Показать активные каналы
```bash
python scripts\show_accounts.py
```

## Git операции

### Проверить изменения
```bash
git status
git diff
```

### Закоммитить изменения
```bash
git add .
git commit -m "описание изменений"
```

### Отправить на GitHub (после настройки remote)
```bash
git remote add origin <URL>
git push -u origin master
```

## Деплой на VPS

### Краткая версия:
```bash
# 1. Подключиться к VPS
ssh root@194.87.86.103

# 2. Клонировать репозиторий
git clone <URL> /opt/traffic-engine
cd /opt/traffic-engine

# 3. Настроить окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Настроить .env и sessions/

# 5. Инициализировать БД
python scripts/init_db.py

# 6. Настроить systemd
sudo cp traffic-engine.service /etc/systemd/system/
sudo systemctl enable traffic-engine
sudo systemctl start traffic-engine

# 7. Проверить логи
journalctl -u traffic-engine -f
```

**Полная инструкция:** См. [DEPLOY_TO_VPS.md](DEPLOY_TO_VPS.md)

## Troubleshooting

### Timezone ошибки
✅ Уже исправлены в коммите `0747922`

### Failed комментарии
```bash
# Проверить причины
python check_failed_reasons.py

# Отключить проблемные каналы
python scripts\disable_restricted_channels.py
```

### База данных не подключается
```bash
# Проверить PostgreSQL
# Windows: проверить в Services
# Linux: systemctl status postgresql

# Проверить DATABASE_URL в .env
```

### Аккаунты не авторизованы
```bash
python scripts\auth_one.py
```

## Полезные ссылки

- [Финальное резюме сессии](SESSION_FINAL_2026_01_27.md)
- [Инструкция по деплою](DEPLOY_TO_VPS.md)
- [Исправления timezone](docs/SESSION_2026_01_27_TIMEZONE_FIX.md)
- [Анализ ошибок](docs/FIXES_2026_01_27_EVENING.md)

## Статус проекта

✅ **Готов к продакшн деплою**

- 4 аккаунта активны
- 22 канала активны
- Success rate: 37.5% (ожидается 70-80%)
- Timezone ошибки исправлены
- Проблемные каналы отключены
