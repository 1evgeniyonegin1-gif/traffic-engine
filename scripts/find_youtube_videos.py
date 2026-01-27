#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт 1: Поиск YouTube видео для нарезки через Vizard

Использует yt-dlp для поиска видео по ключевым словам.
Фильтрует по длине (10-60 минут) и просмотрам (>10K).

Вывод: youtube_urls.txt — список URL для Vizard API
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Ключевые слова для поиска
KEYWORDS = [
    "заработок на коротких видео",
    "как заработать на reels",
    "инфобизнес с нуля",
    "онлайн бизнес с нуля",
    "пассивный доход онлайн",
    "финансовая свобода инфобизнес",
    "заработок в интернете реально",
    "монетизация контента",
]

KEYWORDS_EN = [
    "how to make money with short videos",
    "reels monetization strategy",
    "online business from scratch",
    "passive income online business",
    "content creator income",
    "youtube shorts monetization",
]

# Фильтры
MIN_DURATION_SECONDS = 600   # 10 минут
MAX_DURATION_SECONDS = 3600  # 60 минут
MIN_VIEWS = 10000
RESULTS_PER_KEYWORD = 10


def search_youtube(keyword: str, limit: int = RESULTS_PER_KEYWORD) -> list:
    """Ищет видео через yt-dlp"""
    print(f"  Ищу: '{keyword}'...")

    try:
        # Используем ytsearch для поиска
        cmd = [
            sys.executable, '-m', 'yt_dlp',
            f'ytsearch{limit}:{keyword}',
            '--dump-json',
            '--flat-playlist',
            '--no-warnings',
            '--quiet'
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )

        videos = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                video_id = data.get('id') or data.get('url', '').split('=')[-1]
                if video_id and len(video_id) == 11:
                    videos.append({
                        'url': f'https://www.youtube.com/watch?v={video_id}',
                        'id': video_id,
                        'title': data.get('title', 'Unknown')[:80],
                    })
            except json.JSONDecodeError:
                continue

        print(f"    Найдено: {len(videos)}")
        return videos

    except subprocess.TimeoutExpired:
        print(f"    Таймаут")
        return []
    except Exception as e:
        print(f"    Ошибка: {e}")
        return []


def get_video_info(video_url: str) -> dict:
    """Получает детальную информацию о видео"""
    try:
        cmd = [
            sys.executable, '-m', 'yt_dlp',
            video_url,
            '--dump-json',
            '--no-download',
            '--no-warnings',
            '--quiet'
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except:
        pass
    return {}


def main():
    print("=" * 60)
    print("ПОИСК YOUTUBE ВИДЕО ДЛЯ VIZARD")
    print("=" * 60)
    print(f"Фильтры: {MIN_DURATION_SECONDS//60}-{MAX_DURATION_SECONDS//60} мин, >{MIN_VIEWS:,} просмотров")
    print()

    all_videos = []
    seen_ids = set()

    # Поиск по всем ключевым словам
    all_keywords = KEYWORDS + KEYWORDS_EN

    print(f"Поиск по {len(all_keywords)} ключевым словам...")
    print()

    for keyword in all_keywords:
        videos = search_youtube(keyword)
        for v in videos:
            if v['id'] not in seen_ids:
                seen_ids.add(v['id'])
                all_videos.append(v)

    print()
    print(f"Найдено уникальных видео: {len(all_videos)}")
    print()
    print("Получение детальной информации (это займёт время)...")
    print()

    # Получаем детальную информацию и фильтруем
    filtered_videos = []

    for i, video in enumerate(all_videos[:50], 1):  # Ограничим 50 для скорости
        print(f"  [{i}/{min(len(all_videos), 50)}] {video['title'][:40]}...", end=' ')

        info = get_video_info(video['url'])

        if not info:
            print("- нет данных")
            continue

        duration = info.get('duration', 0) or 0
        views = info.get('view_count', 0) or 0

        # Фильтрация
        if duration < MIN_DURATION_SECONDS:
            print(f"- слишком короткое ({duration//60} мин)")
            continue
        if duration > MAX_DURATION_SECONDS:
            print(f"- слишком длинное ({duration//60} мин)")
            continue
        if views < MIN_VIEWS:
            print(f"- мало просмотров ({views:,})")
            continue

        video['duration'] = duration
        video['duration_str'] = f"{duration//60}:{duration%60:02d}"
        video['views'] = views
        video['channel'] = info.get('channel', info.get('uploader', 'Unknown'))
        video['title'] = info.get('title', video['title'])[:80]

        filtered_videos.append(video)
        print(f"OK ({duration//60} мин, {views:,} просмотров)")

    # Сортировка по просмотрам
    filtered_videos.sort(key=lambda x: x['views'], reverse=True)

    print()
    print("=" * 60)
    print(f"ПОДХОДЯЩИХ ВИДЕО: {len(filtered_videos)}")
    print("=" * 60)

    if not filtered_videos:
        print("Видео не найдены. Попробуй изменить ключевые слова.")
        return

    # Топ-15 для Vizard
    top_videos = filtered_videos[:15]

    print()
    print("ТОП-15 ДЛЯ VIZARD:")
    print("-" * 60)
    for i, v in enumerate(top_videos, 1):
        print(f"{i:2}. {v['title'][:50]}...")
        print(f"    {v['channel']} | {v['duration_str']} | {v['views']:,} просмотров")
        print(f"    {v['url']}")
        print()

    # Сохранение в файлы
    output_dir = Path(__file__).parent.parent / "vizard_content"
    output_dir.mkdir(exist_ok=True)

    # URLs для Vizard
    urls_file = output_dir / "youtube_urls.txt"
    with open(urls_file, 'w', encoding='utf-8') as f:
        for v in top_videos:
            f.write(v['url'] + '\n')
    print(f"[OK] URLs сохранены: {urls_file}")

    # Полный JSON с метаданными
    json_file = output_dir / "youtube_videos.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'filters': {
                'min_duration_sec': MIN_DURATION_SECONDS,
                'max_duration_sec': MAX_DURATION_SECONDS,
                'min_views': MIN_VIEWS,
            },
            'total_found': len(all_videos),
            'after_filter': len(filtered_videos),
            'selected': len(top_videos),
            'videos': top_videos
        }, f, ensure_ascii=False, indent=2)
    print(f"[OK] JSON сохранён: {json_file}")

    print()
    print("СЛЕДУЮЩИЙ ШАГ:")
    print(f"  python scripts/vizard_generate.py")
    print()
    print(f"Ожидаемый расход кредитов Vizard: {len(top_videos)}")
    print(f"Ожидаемое количество клипов: ~{len(top_videos) * 30}")


if __name__ == '__main__':
    main()
