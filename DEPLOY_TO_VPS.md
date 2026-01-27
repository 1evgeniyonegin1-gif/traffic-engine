# Деплой Traffic Engine на VPS

## Предварительные требования

### На VPS должны быть установлены:
- Python 3.10+
- PostgreSQL 14+
- Git
- systemd

## Шаг 1: Подготовка VPS

```bash
# Подключение
ssh root@194.87.86.103

# Обновление системы
apt update && apt upgrade -y

# Установка зависимостей
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib git

# Создание базы данных
sudo -u postgres psql
```

В psql:
```sql
CREATE DATABASE info_business;
CREATE USER traffic_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE info_business TO traffic_user;
\q
```

## Шаг 2: Клонирование репозитория

```bash
# Создать директорию
mkdir -p /opt/traffic-engine
cd /opt/traffic-engine

# Клонировать (после создания remote репозитория)
git clone <YOUR_REPO_URL> .

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

## Шаг 3: Конфигурация

Создать `.env` файл:

```bash
nano .env
```

Содержимое (скопировать из локального .env):
```env
DATABASE_URL=postgresql+asyncpg://traffic_user:your_secure_password@localhost:5432/info_business
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
ANTHROPIC_API_KEY=...
# ... остальные переменные
```

Скопировать session файлы:
```bash
# На локальной машине
scp -r sessions/ root@194.87.86.103:/opt/traffic-engine/

# Проверить на VPS
ls -la sessions/
```

## Шаг 4: Инициализация базы данных

```bash
source venv/bin/activate
python scripts/init_db.py
```

Добавить аккаунты:
```bash
python scripts/add_account.py
```

Добавить каналы:
```bash
python scripts/add_target_channels.py
```

## Шаг 5: Тестовый запуск

```bash
python run_auto_comments.py
```

Проверить, что всё работает. Нажать Ctrl+C для остановки.

## Шаг 6: Создание systemd сервиса

Создать файл сервиса:
```bash
nano /etc/systemd/system/traffic-engine.service
```

Содержимое:
```ini
[Unit]
Description=Traffic Engine - Auto Comments Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/traffic-engine
Environment="PATH=/opt/traffic-engine/venv/bin"
ExecStart=/opt/traffic-engine/venv/bin/python /opt/traffic-engine/run_auto_comments.py
Restart=always
RestartSec=10

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=traffic-engine

[Install]
WantedBy=multi-user.target
```

Активировать и запустить:
```bash
# Перезагрузить systemd
systemctl daemon-reload

# Включить автозапуск
systemctl enable traffic-engine

# Запустить сервис
systemctl start traffic-engine

# Проверить статус
systemctl status traffic-engine

# Смотреть логи в реальном времени
journalctl -u traffic-engine -f
```

## Шаг 7: Управление сервисом

```bash
# Остановить
systemctl stop traffic-engine

# Перезапустить
systemctl restart traffic-engine

# Посмотреть статус
systemctl status traffic-engine

# Логи (последние 100 строк)
journalctl -u traffic-engine -n 100

# Логи за сегодня
journalctl -u traffic-engine --since today
```

## Шаг 8: Обновление кода

При внесении изменений:

```bash
# На VPS
cd /opt/traffic-engine
git pull
source venv/bin/activate
pip install -r requirements.txt  # если обновились зависимости
systemctl restart traffic-engine
journalctl -u traffic-engine -f  # проверить запуск
```

## Мониторинг

### Проверка статистики:
```bash
cd /opt/traffic-engine
source venv/bin/activate
python check_pg_stats.py
```

### Анализ ошибок:
```bash
python check_failed_reasons.py
```

### Отключение проблемных каналов:
```bash
python scripts/disable_restricted_channels.py
```

## Troubleshooting

### Ошибки базы данных
```bash
# Проверить подключение к PostgreSQL
psql -U traffic_user -d info_business -h localhost

# Проверить логи PostgreSQL
tail -f /var/log/postgresql/postgresql-14-main.log
```

### Ошибки Telegram
```bash
# Проверить session файлы
ls -la sessions/

# Повторно авторизовать аккаунт
python scripts/auth_one.py
```

### Высокая нагрузка
```bash
# Проверить использование ресурсов
htop

# Проверить подключения к БД
psql -U traffic_user -d info_business -c "SELECT * FROM pg_stat_activity;"
```

## Backup

### Создание бэкапа БД:
```bash
pg_dump -U traffic_user info_business > backup_$(date +%Y%m%d).sql
```

### Восстановление:
```bash
psql -U traffic_user info_business < backup_20260127.sql
```

## Security

### Firewall:
```bash
# Разрешить только SSH
ufw allow 22
ufw enable

# PostgreSQL должен слушать только localhost
# В /etc/postgresql/14/main/postgresql.conf:
listen_addresses = 'localhost'
```

### Permissions:
```bash
# Права на .env
chmod 600 .env

# Права на sessions
chmod 600 sessions/*
```

## Полезные команды

```bash
# Проверить активные каналы
psql -U traffic_user info_business -c "SELECT username, title FROM traffic_target_channels WHERE is_active=true;"

# Статистика за сегодня
psql -U traffic_user info_business -c "SELECT status, COUNT(*) FROM traffic_actions WHERE action_type='comment' AND DATE(created_at)=CURRENT_DATE GROUP BY status;"

# Последние 10 комментариев
psql -U traffic_user info_business -c "SELECT created_at, status, content FROM traffic_actions WHERE action_type='comment' ORDER BY created_at DESC LIMIT 10;"
```
