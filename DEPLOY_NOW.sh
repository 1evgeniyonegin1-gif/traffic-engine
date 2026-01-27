#!/bin/bash
# Скрипт для деплоя всех исправлений на сервер

echo "===================================="
echo "DEPLOY: Story Viewing + Fixes"
echo "===================================="

# 1. Переход в директорию проекта
cd /root/traffic-engine-mvp || exit 1
echo "[1/8] В директории проекта"

# 2. Остановить систему (если запущена)
echo "[2/8] Остановка системы..."
systemctl stop traffic-engine 2>/dev/null || pkill -f run_auto_comments.py 2>/dev/null
sleep 3

# 3. Обновить код
echo "[3/8] Обновление кода с Git..."
git pull

# 4. Отключить проблемные каналы
echo "[4/8] Отключение проблемных каналов..."
python3 scripts/fix_bad_channels.py

# 5. Присоединиться к discussion groups
echo "[5/8] Присоединение к discussion groups..."
python3 scripts/auto_join_discussions.py

# 6. Добавить целевую аудиторию для Story Viewing
echo "[6/8] Добавление целевой аудитории..."
python3 scripts/quick_add_audience.py

# 7. Проверить готовность
echo "[7/8] Проверка готовности..."
python3 scripts/check_story_viewing_ready.py

# 8. Запустить систему
echo "[8/8] Запуск системы..."
systemctl start traffic-engine || (screen -dmS traffic python3 run_auto_comments.py && echo "Запущен через screen")

sleep 5

# Показать статус
echo ""
echo "===================================="
echo "СТАТУС ПОСЛЕ ДЕПЛОЯ:"
echo "===================================="
systemctl status traffic-engine --no-pager || screen -ls

echo ""
echo "===================================="
echo "Деплой завершён!"
echo "===================================="
echo ""
echo "Мониторинг:"
echo "  tail -f logs/traffic_engine_*.log | grep -E '(story|comment|success)'"
echo ""
echo "Статистика:"
echo "  python3 scripts/show_comments_stats.py"
echo ""
