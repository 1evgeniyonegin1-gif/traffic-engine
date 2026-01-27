#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для добавления YouTube URLs вручную

Запусти и вставляй URLs по одному (Enter после каждого).
Пустая строка = завершить ввод.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def main():
    print("=" * 60)
    print("ДОБАВЛЕНИЕ YOUTUBE ВИДЕО ДЛЯ VIZARD")
    print("=" * 60)
    print()
    print("Вставляй URLs по одному (Enter после каждого)")
    print("Пустая строка = завершить ввод")
    print()
    print("Где искать видео (открой в браузере):")
    print("  https://www.youtube.com/results?search_query=инфобизнес+с+нуля")
    print("  https://www.youtube.com/results?search_query=заработок+на+reels")
    print("  https://www.youtube.com/results?search_query=онлайн+бизнес+2025")
    print()
    print("Критерии: 10-60 минут, >10K просмотров")
    print("=" * 60)
    print()

    urls = []

    while True:
        try:
            url = input(f"[{len(urls)+1}] URL: ").strip()
        except EOFError:
            break

        if not url:
            break

        # Валидация URL
        if 'youtube.com/watch' in url or 'youtu.be/' in url:
            urls.append(url)
            print(f"    OK - добавлено")
        else:
            print(f"    Пропущено - не YouTube URL")

    if not urls:
        print("\nНет URLs для сохранения")
        return

    # Сохранение
    output_dir = Path(__file__).parent.parent / "vizard_content"
    output_dir.mkdir(exist_ok=True)

    urls_file = output_dir / "youtube_urls.txt"
    with open(urls_file, 'w', encoding='utf-8') as f:
        for url in urls:
            f.write(url + '\n')

    json_file = output_dir / "youtube_videos.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'count': len(urls),
            'videos': [{'url': url} for url in urls]
        }, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"СОХРАНЕНО: {len(urls)} URLs")
    print(f"Файл: {urls_file}")
    print("=" * 60)
    print()
    print("СЛЕДУЮЩИЙ ШАГ:")
    print("  python scripts/vizard_generate.py")


if __name__ == '__main__':
    main()
