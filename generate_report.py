#!/usr/bin/env python
"""
Generate HTML report for auto-comments system.
Run: python generate_report.py
Then open: reports/dashboard.html
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


async def generate_report():
    """Generate HTML dashboard report."""
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

    conn = await asyncpg.connect(db_url)

    try:
        # Stats by status
        stats = {'completed': 0, 'failed': 0, 'pending': 0}
        rows = await conn.fetch("""
            SELECT status, COUNT(*) as cnt
            FROM traffic_actions
            GROUP BY status
        """)
        for row in rows:
            if row['status'] in stats:
                stats[row['status']] = row['cnt']

        # Active channels count
        row = await conn.fetchrow("""
            SELECT COUNT(*) as cnt FROM traffic_target_channels WHERE is_active = true
        """)
        channels_active = row['cnt'] if row else 0

        # Last 20 actions
        actions = await conn.fetch("""
            SELECT
                ta.created_at,
                ta.status,
                ta.content,
                ta.error_message,
                tc.username
            FROM traffic_actions ta
            LEFT JOIN traffic_target_channels tc ON ta.target_channel_id = tc.channel_id
            ORDER BY ta.created_at DESC
            LIMIT 20
        """)

        # Channels
        channels = await conn.fetch("""
            SELECT username, title, comment_strategy, posts_processed, comments_posted, is_active
            FROM traffic_target_channels
            ORDER BY is_active DESC, priority DESC
        """)

        # Accounts
        accounts = await conn.fetch("""
            SELECT first_name, phone, status, daily_comments
            FROM traffic_userbot_accounts
            ORDER BY status
        """)

    finally:
        await conn.close()

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Traffic Engine Report</title>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{ color: #333; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-number {{
            font-size: 48px;
            font-weight: bold;
            color: #2196F3;
        }}
        .stat-number.success {{ color: #4CAF50; }}
        .stat-number.error {{ color: #f44336; }}
        .stat-number.pending {{ color: #FF9800; }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #2196F3;
            color: white;
        }}
        tr:hover {{ background: #f9f9f9; }}
        .status-completed {{ color: #4CAF50; font-weight: bold; }}
        .status-failed {{ color: #f44336; font-weight: bold; }}
        .status-pending {{ color: #FF9800; font-weight: bold; }}
        .channel-active {{ color: #4CAF50; }}
        .channel-inactive {{ color: #999; }}
        .error-msg {{
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 12px;
            color: #999;
        }}
        .updated {{
            text-align: right;
            color: #999;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
        }}
        .refresh-btn {{
            background: #2196F3;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}
        .refresh-btn:hover {{ background: #1976D2; }}
    </style>
</head>
<body>
    <h1>Traffic Engine Dashboard</h1>
    <div class="updated">
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        <br><small>Run <code>python generate_report.py</code> to refresh</small>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number success">{stats['completed']}</div>
            <div class="stat-label">Successful comments</div>
        </div>
        <div class="stat-card">
            <div class="stat-number error">{stats['failed']}</div>
            <div class="stat-label">Errors</div>
        </div>
        <div class="stat-card">
            <div class="stat-number pending">{stats['pending']}</div>
            <div class="stat-label">Pending</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{channels_active}</div>
            <div class="stat-label">Active channels</div>
        </div>
    </div>

    <h2>Recent Actions</h2>
    <table>
        <tr>
            <th>Time</th>
            <th>Channel</th>
            <th>Status</th>
            <th>Comment</th>
            <th>Error</th>
        </tr>
"""

    for action in actions:
        time_str = action['created_at'].strftime('%H:%M:%S') if action['created_at'] else '-'
        channel = action['username'] or 'unknown'
        status = action['status'] or 'unknown'
        content = (action['content'] or '')[:50]
        if len(action['content'] or '') > 50:
            content += '...'
        error = (action['error_message'] or '')[:60]

        html += f"""        <tr>
            <td>{time_str}</td>
            <td>@{channel}</td>
            <td class="status-{status}">{status}</td>
            <td>{content}</td>
            <td class="error-msg" title="{action['error_message'] or ''}">{error or '-'}</td>
        </tr>
"""

    if not actions:
        html += '        <tr><td colspan="5" style="text-align:center;color:#999;">No actions yet</td></tr>\n'

    html += """    </table>

    <h2>Active Channels</h2>
    <table>
        <tr>
            <th>Channel</th>
            <th>Title</th>
            <th>Strategy</th>
            <th>Posts</th>
            <th>Comments</th>
            <th>Status</th>
        </tr>
"""

    for ch in channels:
        active_class = 'channel-active' if ch['is_active'] else 'channel-inactive'
        active_text = 'Active' if ch['is_active'] else 'Disabled'
        title = (ch['title'] or '')[:30]

        html += f"""        <tr>
            <td>@{ch['username'] or ''}</td>
            <td>{title}</td>
            <td>{ch['comment_strategy'] or 'smart'}</td>
            <td>{ch['posts_processed'] or 0}</td>
            <td>{ch['comments_posted'] or 0}</td>
            <td class="{active_class}">{active_text}</td>
        </tr>
"""

    html += """    </table>

    <h2>Accounts</h2>
    <table>
        <tr>
            <th>Name</th>
            <th>Phone</th>
            <th>Status</th>
            <th>Today</th>
        </tr>
"""

    for acc in accounts:
        html += f"""        <tr>
            <td>{acc['first_name'] or 'Unknown'}</td>
            <td>{acc['phone'] or '-'}</td>
            <td>{acc['status'] or 'unknown'}</td>
            <td>{acc['daily_comments'] or 0}</td>
        </tr>
"""

    html += """    </table>
</body>
</html>
"""

    # Save report
    report_path = REPORTS_DIR / "dashboard.html"
    report_path.write_text(html, encoding='utf-8')
    print(f"Report saved to: {report_path}")
    print(f"\nOpen in browser: file:///{report_path.as_posix()}")

    # Print summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print('='*50)
    print(f"Successful comments: {stats['completed']}")
    print(f"Failed: {stats['failed']}")
    print(f"Pending: {stats['pending']}")
    print(f"Active channels: {channels_active}")
    print('='*50)


if __name__ == '__main__':
    asyncio.run(generate_report())
