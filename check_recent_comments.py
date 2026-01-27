import sqlite3
from datetime import datetime

conn = sqlite3.connect('traffic_engine.db')
cursor = conn.cursor()

# Статистика за сегодня
cursor.execute('SELECT COUNT(*) FROM comments WHERE created_at >= date("now")')
today_count = cursor.fetchone()[0]
print(f'Комментариев сегодня: {today_count}')

# Статистика за все время
cursor.execute('SELECT COUNT(*) FROM comments')
total_count = cursor.fetchone()[0]
print(f'Всего комментариев: {total_count}')

# Последние 20 комментариев
cursor.execute('''
    SELECT c.text, c.created_at, ch.name, ch.username, a.display_name, a.username
    FROM comments c
    JOIN channels ch ON c.channel_id = ch.id
    JOIN accounts a ON c.account_id = a.id
    ORDER BY c.created_at DESC
    LIMIT 20
''')

print('\n' + '='*80)
print('ПОСЛЕДНИЕ 20 КОММЕНТАРИЕВ')
print('='*80)

for row in cursor.fetchall():
    text, created_at, channel_name, channel_username, account_name, account_username = row
    print(f'\n[{created_at}]')
    print(f'Аккаунт: {account_name} (@{account_username})')
    print(f'Канал: {channel_name} (@{channel_username})')
    print(f'Текст: {text}')
    print('-'*80)

conn.close()
