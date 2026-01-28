#!/bin/bash
# Скрипт для реавторизации аккаунтов на сервере

echo "===================================="
echo "РЕАВТОРИЗАЦИЯ АККАУНТОВ"
echo "===================================="
echo ""
echo "Этот скрипт запустится ИНТЕРАКТИВНО."
echo "Вам нужно будет вводить коды из Telegram."
echo ""
echo "Коды придут на номера:"
echo "  - Карина (+380954967658)"
echo "  - Люба (+380955161146)"
echo "  - Кира (+380955300455)"
echo "  - Лёша (+998993466132)"
echo ""
read -p "Нажмите Enter чтобы начать..."

cd /opt/traffic-engine || exit 1
source venv/bin/activate

python scripts/reauthorize_accounts.py

echo ""
echo "===================================="
echo "ГОТОВО!"
echo "===================================="
echo ""
echo "Теперь запустите систему:"
echo "  systemctl start traffic-engine"
echo ""
