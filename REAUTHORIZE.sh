#!/bin/bash
# ПРОСТОЙ скрипт реавторизации
# Просто запустите на сервере: ./REAUTHORIZE.sh

cd /opt/traffic-engine || exit 1
source venv/bin/activate
python scripts/simple_reauth.py
