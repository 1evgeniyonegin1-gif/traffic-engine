#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт 3: Скачивание и сортировка клипов из Vizard

Читает vizard_projects.json, проверяет статус генерации,
скачивает готовые клипы и сортирует по viral score.

Структура папок:
/clips/
  /group_a_transform/  <- Transform Republic (с плашками)
    /viral_10/
    /viral_9/
    ...
  /group_b_elo/        <- ELO (первые дни без плашек)
    /viral_10/
    /viral_9/
    ...
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('VIZARD_API_KEY', '3ca8ee192df443a499a61f5a8c1d48b6')
BASE_URL = "https://elb-api.vizard.ai/hvizard-server-front/open-api/v1"

# Время ожидания (секунды)
POLL_INTERVAL = 30
MAX_WAIT_TIME = 1800  # 30 минут максимум


def query_project(project_id: str) -> dict:
    """Запрашивает статус проекта и список клипов"""

    endpoint = f"{BASE_URL}/project/query/{project_id}"

    headers = {
        'VIZARDAI_API_KEY': API_KEY,
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


def download_clip(video_url: str, output_path: Path) -> bool:
    """Скачивает один клип"""
    try:
        response = requests.get(video_url, stream=True, timeout=120)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      [X] Ошибка скачивания: {e}")
        return False


def wait_for_projects(projects: list, max_wait: int = MAX_WAIT_TIME) -> dict:
    """Ждёт завершения генерации всех проектов"""

    results = {}
    start_time = time.time()

    pending = {p['project_id']: p for p in projects if p.get('project_id')}

    print(f"[...] Ожидание завершения {len(pending)} проектов...")
    print(f"   (максимум {max_wait // 60} минут)")
    print()

    while pending and (time.time() - start_time) < max_wait:
        for project_id in list(pending.keys()):
            result = query_project(project_id)

            if 'error' in result:
                print(f"   [!] {project_id}: {result['error']}")
                continue

            code = result.get('code')

            if code == 2000:  # Готово
                videos = result.get('videos', [])
                print(f"   [OK] {project_id}: {len(videos)} клипов готово")
                results[project_id] = result
                del pending[project_id]

            elif code == 1000:  # Ещё обрабатывается
                elapsed = int(time.time() - start_time)
                print(f"   [...] {project_id}: обработка... ({elapsed}s)")

            else:
                print(f"   [!] {project_id}: код {code}")

        if pending:
            time.sleep(POLL_INTERVAL)

    if pending:
        print(f"\n[!] Таймаут: {len(pending)} проектов не завершились")

    return results


def main():
    print("=" * 60)
    print("СКАЧИВАНИЕ КЛИПОВ ИЗ VIZARD")
    print("=" * 60)
    print()

    # Путь к файлам
    content_dir = Path(__file__).parent.parent / "vizard_content"
    projects_file = content_dir / "vizard_projects.json"

    if not projects_file.exists():
        print(f"[X] Файл не найден: {projects_file}")
        print("   Сначала запусти: python scripts/vizard_generate.py")
        return

    # Загрузка проектов
    with open(projects_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    projects = data.get('projects', [])
    if not projects:
        print("[X] Нет проектов для скачивания")
        return

    print(f"[i] Найдено {len(projects)} проектов")

    # Проверка статуса и ожидание
    ready_projects = wait_for_projects(projects)

    if not ready_projects:
        print("\n[X] Нет готовых проектов")
        return

    # Сбор всех клипов
    all_clips = []
    for project_id, result in ready_projects.items():
        videos = result.get('videos', [])
        for video in videos:
            video['source_project'] = project_id
            all_clips.append(video)

    print()
    print(f"[#] Всего клипов: {len(all_clips)}")

    # Сортировка по viral score
    all_clips.sort(key=lambda x: float(x.get('viralScore', 0)), reverse=True)

    # Разделение на 2 группы (Transform Republic и ELO)
    mid = len(all_clips) // 2
    group_a = all_clips[:mid]  # Лучшие по viral score -> Transform Republic
    group_b = all_clips[mid:]  # Остальные -> ELO

    print(f"   Группа A (Transform Republic): {len(group_a)} клипов")
    print(f"   Группа B (ELO): {len(group_b)} клипов")
    print()

    # Создание папок и скачивание
    clips_dir = content_dir / "clips"

    def download_group(clips: list, group_name: str, group_dir: Path):
        print(f"\n[>>] Скачивание группы: {group_name}")

        downloaded = 0
        for i, clip in enumerate(clips, 1):
            video_url = clip.get('videoUrl')
            if not video_url:
                continue

            viral_score = int(float(clip.get('viralScore', 0)))
            video_id = clip.get('videoId', f'clip_{i}')
            title = clip.get('title', 'untitled')[:50].replace('/', '-').replace('\\', '-')

            # Папка по viral score
            score_dir = group_dir / f"viral_{viral_score}"
            filename = f"{video_id}_{title}.mp4"
            output_path = score_dir / filename

            if output_path.exists():
                print(f"   [{i}/{len(clips)}] Уже скачан: {filename[:40]}...")
                downloaded += 1
                continue

            print(f"   [{i}/{len(clips)}] Скачиваю: {filename[:40]}... (score: {viral_score})")

            if download_clip(video_url, output_path):
                downloaded += 1

            # Небольшая пауза
            time.sleep(0.5)

        return downloaded

    # Скачивание обеих групп
    total_downloaded = 0
    total_downloaded += download_group(group_a, "Transform Republic", clips_dir / "group_a_transform")
    total_downloaded += download_group(group_b, "ELO", clips_dir / "group_b_elo")

    # Сохранение метаданных
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'total_clips': len(all_clips),
        'downloaded': total_downloaded,
        'group_a_count': len(group_a),
        'group_b_count': len(group_b),
        'clips': all_clips
    }

    metadata_file = clips_dir / "clips_metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"[OK] ГОТОВО: {total_downloaded} клипов скачано")
    print("=" * 60)
    print()
    print("СТРУКТУРА ПАПОК:")
    print(f"  {clips_dir}/")
    print(f"    group_a_transform/  <- Transform Republic (с плашками)")
    print(f"    group_b_elo/        <- ELO (прогрев без плашек)")
    print()
    print("СЛЕДУЮЩИЕ ШАГИ:")
    print("  1. Группа A: Добавь плашки CTA в CapCut")
    print("  2. Группа B: Первые 5 дней публикуй БЕЗ плашек")
    print("  3. Публикуй на все 6 аккаунтов")
    print()
    print("РЕКОМЕНДАЦИИ ПО ПУБЛИКАЦИИ:")
    print("  - Начинай с viral_10, viral_9 (лучшие)")
    print("  - 3-5 видео в день на аккаунт")
    print("  - Лучшее время: 12:00, 18:00, 21:00")


if __name__ == '__main__':
    main()
