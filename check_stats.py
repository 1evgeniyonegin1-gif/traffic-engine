import sqlite3
from datetime import datetime

conn = sqlite3.connect('traffic_engine.db')
cursor = conn.cursor()

# Комментарии сегодня
cursor.execute("""
    SELECT COUNT(*)
    FROM traffic_actions
    WHERE action_type='comment' AND date(created_at) = date('now')
""")
today_count = cursor.fetchone()[0]
print(f'Comments today: {today_count}')

# Успешные комментарии (все время)
cursor.execute("""
    SELECT COUNT(*)
    FROM traffic_actions
    WHERE action_type='comment' AND status='success'
""")
success_count = cursor.fetchone()[0]
print(f'Successful comments (all time): {success_count}')

# Последние 5 комментариев
cursor.execute("""
    SELECT content, status, created_at, target_channel_id
    FROM traffic_actions
    WHERE action_type='comment'
    ORDER BY created_at DESC
    LIMIT 5
""")

print('\nLast 5 comments:')
for row in cursor.fetchall():
    content = row[0][:50] + '...' if row[0] and len(row[0]) > 50 else row[0] or '(no content)'
    print(f'{row[2][:19]} | {row[1]:8} | Channel: {row[3]} | {content}')

conn.close()
