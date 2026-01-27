#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для получения видео популярных спикеров через YouTube RSS

RSS не требует авторизации и не блокируется.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Спикеры и их каналы
SPEAKERS = {
    # Предприниматели
    "Игорь Рыбаков": "UCxrv6KBc6dONBV1xGxhLODw",
    "Оскар Хартманн": "UCRuGames0MR1r_Y8OLkfVIZw",
    "Дмитрий Портнягин": "UCnv62fgXB7JJGBvlzKW4ByA",  # Трансформатор
    "Евгений Черняк": "UCFVrR12bo5x02Vq3mKAhcEw",  # Big Money
    "Михаил Дашкиев": "UCB3VfKMR3bUjWxKHWs4FjQA",
    "Алекс Яновский": "UCiWQaUIhawlvNqtKqMw35_w",

    # Спикеры
    "Андрей Курпатов": "UCLlq3dKCwF4mQjMJVh7-Xjg",
    "Ицхак Пинтосевич": "UCaWyAC7b8-8SpPPdVF4hEbQ",
    "Максим Дорофеев": "UC1EwMsXtKPjCNLLtOlYx7mg",

    # Личный бренд
    "Мария Азаренок": "UCzWzAdIJSPXFwK9Xfwm1I7A",
}

# Известные длинные видео (подкасты, интервью) - backup список
KNOWN_VIDEOS = [
    # Трансформатор - длинные интервью
    "https://www.youtube.com/watch?v=TL1t3FPQEqc",  # Портнягин - Как заработать первый миллион
    "https://www.youtube.com/watch?v=wL8DVHuHvAk",  # Трансформатор подкаст
    "https://www.youtube.com/watch?v=8nVHRNgXg1k",  # Портнягин интервью

    # Big Money
    "https://www.youtube.com/watch?v=qp0HIF3SfI4",  # Черняк - бизнес интервью
    "https://www.youtube.com/watch?v=j7R-C4Dklf8",  # Big Money подкаст

    # Игорь Рыбаков
    "https://www.youtube.com/watch?v=RRJwdCDPxYU",  # Рыбаков - миллиардер о деньгах
    "https://www.youtube.com/watch?v=Rn6IHN7K85g",  # Рыбаков интервью

    # Бизнес Молодость
    "https://www.youtube.com/watch?v=1TskQpbjKxE",  # Дашкиев - как начать бизнес

    # Курпатов
    "https://www.youtube.com/watch?v=sHqYv-G6X9g",  # Курпатов - мышление
    "https://www.youtube.com/watch?v=dxQmOR_e1do",  # Курпатов лекция

    # Оскар Хартманн
    "https://www.youtube.com/watch?v=x0FSL-sFJDE",  # Хартманн - предпринимательство
]


def get_channel_id_from_handle(handle: str) -> str:
    """Получает channel_id по handle (@username)"""
    try:
        url = f"https://www.youtube.com/{handle}"
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urlopen(req, timeout=10)
        html = response.read().decode('utf-8', errors='replace')

        # Ищем channel_id в HTML
        match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"    Ошибка получения channel_id: {e}")
    return None


def get_videos_from_rss(channel_id: str, limit: int = 15) -> list:
    """Получает последние видео канала через RSS"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        req = Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urlopen(req, timeout=10)
        xml_data = response.read().decode('utf-8')

        # Парсим XML
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}

        videos = []
        for entry in root.findall('atom:entry', ns)[:limit]:
            video_id = entry.find('atom:id', ns).text.split(':')[-1]
            title = entry.find('atom:title', ns).text

            videos.append({
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'title': title[:80] if title else 'Unknown',
                'video_id': video_id
            })

        return videos
    except Exception as e:
        print(f"    RSS ошибка: {e}")
        return []


def main():
    print("=" * 60)
    print("ПОЛУЧЕНИЕ ВИДЕО СПИКЕРОВ")
    print("=" * 60)
    print()

    all_videos = []
    seen_ids = set()

    # Сначала добавляем известные видео
    print("Добавляю проверенные видео...")
    for url in KNOWN_VIDEOS:
        video_id = url.split('v=')[-1].split('&')[0]
        if video_id not in seen_ids:
            seen_ids.add(video_id)
            all_videos.append({
                'url': url,
                'video_id': video_id,
                'title': 'Проверенное видео',
                'source': 'known'
            })
    print(f"  Добавлено: {len(all_videos)}")
    print()

    # Получаем видео с каналов через RSS
    print("Получаю видео с каналов через RSS...")
    for speaker, channel_id in SPEAKERS.items():
        print(f"  {speaker}...", end=' ')

        videos = get_videos_from_rss(channel_id, limit=5)

        added = 0
        for v in videos:
            if v['video_id'] not in seen_ids:
                seen_ids.add(v['video_id'])
                v['speaker'] = speaker
                v['source'] = 'rss'
                all_videos.append(v)
                added += 1

        print(f"{added} видео")

    print()
    print(f"Всего собрано: {len(all_videos)} видео")

    # Сохранение
    output_dir = Path(__file__).parent.parent / "vizard_content"
    output_dir.mkdir(exist_ok=True)

    # Берём топ-15 для Vizard
    selected = all_videos[:15]

    urls_file = output_dir / "youtube_urls.txt"
    with open(urls_file, 'w', encoding='utf-8') as f:
        for v in selected:
            f.write(v['url'] + '\n')

    json_file = output_dir / "youtube_videos.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_collected': len(all_videos),
            'selected': len(selected),
            'videos': selected,
            'all_videos': all_videos
        }, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"СОХРАНЕНО: {len(selected)} видео для Vizard")
    print("=" * 60)
    print()
    print("Выбранные видео:")
    for i, v in enumerate(selected, 1):
        title = v.get('title', 'Unknown')[:50]
        speaker = v.get('speaker', 'N/A')
        print(f"  {i:2}. [{speaker}] {title}...")
        print(f"      {v['url']}")

    print()
    print(f"Файл URLs: {urls_file}")
    print()
    print("СЛЕДУЮЩИЙ ШАГ:")
    print("  python scripts/vizard_generate.py")


if __name__ == '__main__':
    main()
