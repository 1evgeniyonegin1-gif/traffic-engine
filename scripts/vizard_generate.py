#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт 2: Генерация клипов через Vizard API

Читает youtube_urls.txt и отправляет каждое видео в Vizard API.
Сохраняет project_id для дальнейшего скачивания.

API Key: задаётся в .env как VIZARD_API_KEY
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from dotenv import load_dotenv

# Загрузка .env
load_dotenv()

# Конфигурация
API_KEY = os.getenv('VIZARD_API_KEY', '3ca8ee192df443a499a61f5a8c1d48b6')
BASE_URL = "https://elb-api.vizard.ai/hvizard-server-front/open-api/v1"

# Настройки генерации
DEFAULT_SETTINGS = {
    'lang': 'ru',  # Язык субтитров
    'videoType': 2,  # 2 = YouTube
    'ratioOfClip': 1,  # 1 = 9:16 вертикальный (Reels/Shorts/TikTok)
    'maxClipNumber': 30,  # Максимум клипов с видео
    'removeSilenceSwitch': 1,  # Удалять тишину
    'subtitleSwitch': 1,  # Субтитры включены
    'headlineSwitch': 1,  # AI-заголовок
    'highlightSwitch': 1,  # Выделение ключевых слов
    'emojiSwitch': 0,  # Без эмодзи
    'autoBrollSwitch': 0,  # Без авто B-roll
}


def create_project(video_url: str, project_name: str = None) -> dict:
    """Создаёт проект в Vizard для генерации клипов"""

    endpoint = f"{BASE_URL}/project/create"

    headers = {
        'VIZARDAI_API_KEY': API_KEY,
        'Content-Type': 'application/json'
    }

    payload = {
        **DEFAULT_SETTINGS,
        'videoUrl': video_url,
    }

    if project_name:
        payload['projectName'] = project_name

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'error': str(e), 'status_code': getattr(e.response, 'status_code', None)}


def check_project_status(project_id: str) -> dict:
    """Проверяет статус генерации проекта"""

    endpoint = f"{BASE_URL}/project/query"

    headers = {
        'VIZARDAI_API_KEY': API_KEY,
        'Content-Type': 'application/json'
    }

    payload = {'projectId': project_id}

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


def main():
    print("=" * 60)
    print("ГЕНЕРАЦИЯ КЛИПОВ ЧЕРЕЗ VIZARD API")
    print("=" * 60)
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
    print(f"Формат: 9:16 (вертикальный)")
    print(f"Максимум клипов: {DEFAULT_SETTINGS['maxClipNumber']} на видео")
    print()

    # Путь к файлам
    content_dir = Path(__file__).parent.parent / "vizard_content"
    urls_file = content_dir / "youtube_urls.txt"

    if not urls_file.exists():
        print(f"[X] Файл не найден: {urls_file}")
        print("   Сначала запусти: python scripts/find_youtube_videos.py")
        return

    # Чтение URLs
    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("[X] Файл youtube_urls.txt пуст")
        return

    print(f"Найдено {len(urls)} видео для обработки")
    print()

    # Результаты
    projects = []
    failed = []

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Отправляю: {url[:60]}...")

        result = create_project(url)

        if 'error' in result:
            print(f"   [X] Ошибка: {result['error']}")
            failed.append({'url': url, 'error': result['error']})
        elif result.get('code') == 2000:  # Vizard использует 2000 для успеха
            # projectId может быть в корне ИЛИ в data
            project_id = result.get('projectId') or result.get('data', {}).get('projectId')
            print(f"   [OK] Project ID: {project_id}")
            projects.append({
                'url': url,
                'project_id': project_id,
                'response': result,
                'created_at': datetime.now().isoformat()
            })
        elif result.get('code') == 4003:  # Rate limit
            print(f"   [!] Rate limit! Жду 60 сек...")
            time.sleep(60)
            # Повторная попытка
            result = create_project(url)
            if result.get('code') == 2000:
                project_id = result.get('data', {}).get('projectId')
                print(f"   [OK] Project ID: {project_id}")
                projects.append({
                    'url': url,
                    'project_id': project_id,
                    'response': result,
                    'created_at': datetime.now().isoformat()
                })
            else:
                error_msg = result.get('message', 'Unknown error')
                print(f"   [X] Повтор не удался: {error_msg}")
                failed.append({'url': url, 'error': error_msg, 'response': result})
        else:
            error_msg = result.get('message', 'Unknown error')
            print(f"   [!] API ответ: {result.get('code')} - {error_msg}")
            failed.append({'url': url, 'error': error_msg, 'response': result})

        # Пауза между запросами (rate limiting) - 5 сек вместо 2
        if i < len(urls):
            time.sleep(5)

    print()
    print("=" * 60)
    print(f"РЕЗУЛЬТАТ: {len(projects)} успешно / {len(failed)} ошибок")
    print("=" * 60)

    # Сохранение результатов
    projects_file = content_dir / "vizard_projects.json"
    with open(projects_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'settings': DEFAULT_SETTINGS,
            'total_urls': len(urls),
            'successful': len(projects),
            'failed': len(failed),
            'projects': projects,
            'errors': failed
        }, f, ensure_ascii=False, indent=2)

    print(f"[OK] Проекты сохранены: {projects_file}")

    if projects:
        print()
        print("СЛЕДУЮЩИЕ ШАГИ:")
        print("  1. Подожди 5-15 минут пока Vizard обработает видео")
        print("  2. Запусти: python scripts/vizard_download.py")

        # Расчёт кредитов
        expected_clips = len(projects) * DEFAULT_SETTINGS['maxClipNumber']
        print()
        print(f"Ожидаемый результат:")
        print(f"   Видео обработано: {len(projects)}")
        print(f"   Клипов максимум: ~{expected_clips}")
        print(f"   Кредитов использовано: ~{len(projects)} (1 кредит = 1 видео)")


if __name__ == '__main__':
    main()
