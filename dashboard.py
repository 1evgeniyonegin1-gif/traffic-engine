#!/usr/bin/env python
"""
Real-time web dashboard for monitoring auto-comments system.
Run: python dashboard.py
Open: http://localhost:8050

Features:
- Real-time updates via Server-Sent Events (SSE)
- Live feed of recent actions
- Account and channel status monitoring
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template_string, Response, stream_with_context
from sqlalchemy import select, func

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Traffic Engine Dashboard</title>
    <meta charset="utf-8">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }
        h1 {
            color: #00d9ff;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        h1 .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #4CAF50;
            animation: pulse 2s infinite;
        }
        h1 .status-dot.disconnected {
            background: #f44336;
            animation: none;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #16213e;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            text-align: center;
            border: 1px solid #0f3460;
            transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); }
        .stat-number {
            font-size: 48px;
            font-weight: bold;
            color: #00d9ff;
        }
        .stat-number.success { color: #4CAF50; }
        .stat-number.error { color: #f44336; }
        .stat-number.pending { color: #FF9800; }
        .stat-label {
            color: #888;
            margin-top: 5px;
            font-size: 14px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #16213e;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            margin-bottom: 30px;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        th {
            background: #0f3460;
            color: #00d9ff;
            font-weight: 600;
        }
        tr:hover { background: #1a2a4a; }
        .status-success { color: #4CAF50; font-weight: bold; }
        .status-failed { color: #f44336; font-weight: bold; }
        .status-flood_wait { color: #FF9800; font-weight: bold; }
        .status-banned { color: #9c27b0; font-weight: bold; }
        .channel-active { color: #4CAF50; }
        .channel-inactive { color: #666; }
        .error-msg {
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 12px;
            color: #888;
        }
        .header-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .updated {
            color: #666;
            font-size: 12px;
        }
        .updated span { color: #00d9ff; }
        h2 {
            color: #00d9ff;
            margin-top: 30px;
            font-size: 18px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        h2::before {
            content: '';
            width: 4px;
            height: 20px;
            background: #00d9ff;
            border-radius: 2px;
        }
        .live-badge {
            background: #4CAF50;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
            animation: pulse 2s infinite;
        }
        .new-row {
            animation: highlight 2s ease-out;
        }
        @keyframes highlight {
            0% { background: rgba(0, 217, 255, 0.3); }
            100% { background: transparent; }
        }
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="header-bar">
        <h1>
            <span class="status-dot" id="statusDot"></span>
            Traffic Engine Dashboard
        </h1>
        <div class="updated">
            Last update: <span id="lastUpdate">{{ updated }}</span>
            <span class="live-badge">LIVE</span>
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-number success" id="statSuccess">{{ stats.success }}</div>
            <div class="stat-label">Successful comments</div>
        </div>
        <div class="stat-card">
            <div class="stat-number error" id="statFailed">{{ stats.failed }}</div>
            <div class="stat-label">Errors</div>
        </div>
        <div class="stat-card">
            <div class="stat-number pending" id="statFloodWait">{{ stats.flood_wait }}</div>
            <div class="stat-label">Flood Wait</div>
        </div>
        <div class="stat-card">
            <div class="stat-number" id="statChannels">{{ stats.channels_active }}</div>
            <div class="stat-label">Active channels</div>
        </div>
    </div>

    <h2>Recent Actions</h2>
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Comment</th>
                <th>Error</th>
            </tr>
        </thead>
        <tbody id="actionsTable">
            {% for action in actions %}
            <tr>
                <td>{{ action.time }}</td>
                <td>@{{ action.channel }}</td>
                <td class="status-{{ action.status }}">{{ action.status }}</td>
                <td>{{ action.content[:50] }}{% if action.content|length > 50 %}...{% endif %}</td>
                <td class="error-msg" title="{{ action.error }}">{{ action.error[:60] if action.error else '-' }}</td>
            </tr>
            {% endfor %}
            {% if not actions %}
            <tr id="noActionsRow"><td colspan="5" style="text-align:center;color:#666;">No actions yet</td></tr>
            {% endif %}
        </tbody>
    </table>

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
        {% for ch in channels %}
        <tr>
            <td>@{{ ch.username }}</td>
            <td>{{ ch.title[:30] }}</td>
            <td>{{ ch.strategy }}</td>
            <td>{{ ch.posts }}</td>
            <td>{{ ch.comments }}</td>
            <td class="{% if ch.active %}channel-active{% else %}channel-inactive{% endif %}">
                {{ 'Active' if ch.active else 'Disabled' }}
            </td>
        </tr>
        {% endfor %}
    </table>

    <h2>Accounts</h2>
    <table>
        <tr>
            <th>Name</th>
            <th>Phone</th>
            <th>Status</th>
            <th>Today</th>
            <th>Total</th>
        </tr>
        {% for acc in accounts %}
        <tr>
            <td>{{ acc.name }}</td>
            <td>{{ acc.phone }}</td>
            <td class="status-{{ acc.status }}">{{ acc.status }}</td>
            <td>{{ acc.today }}</td>
            <td>{{ acc.total }}</td>
        </tr>
        {% endfor %}
    </table>

    <script>
        // SSE connection for real-time updates
        let eventSource = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 10;

        function connect() {
            eventSource = new EventSource('/stream');

            eventSource.onopen = function() {
                console.log('SSE connected');
                document.getElementById('statusDot').classList.remove('disconnected');
                reconnectAttempts = 0;
            };

            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };

            eventSource.onerror = function() {
                console.log('SSE error, reconnecting...');
                document.getElementById('statusDot').classList.add('disconnected');
                eventSource.close();

                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    setTimeout(connect, 5000);
                }
            };
        }

        function updateDashboard(data) {
            // Update stats
            document.getElementById('statSuccess').textContent = data.stats.success || 0;
            document.getElementById('statFailed').textContent = data.stats.failed || 0;
            document.getElementById('statFloodWait').textContent = data.stats.flood_wait || 0;
            document.getElementById('statChannels').textContent = data.stats.channels_active || 0;

            // Update timestamp
            document.getElementById('lastUpdate').textContent = data.updated;

            // Update actions table if there's new data
            if (data.actions && data.actions.length > 0) {
                updateActionsTable(data.actions);
            }
        }

        function updateActionsTable(actions) {
            const tbody = document.getElementById('actionsTable');
            const noActionsRow = document.getElementById('noActionsRow');
            if (noActionsRow) noActionsRow.remove();

            // Build new HTML
            let html = '';
            actions.forEach((action, idx) => {
                const isNew = idx === 0;
                html += `<tr class="${isNew ? 'new-row' : ''}">
                    <td>${action.time}</td>
                    <td>@${action.channel}</td>
                    <td class="status-${action.status}">${action.status}</td>
                    <td>${(action.content || '').substring(0, 50)}${(action.content || '').length > 50 ? '...' : ''}</td>
                    <td class="error-msg" title="${action.error || ''}">${(action.error || '-').substring(0, 60)}</td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

        // Start connection
        connect();
    </script>
</body>
</html>
"""


def get_dashboard_data():
    """Get all data for dashboard using sync approach."""
    import asyncpg
    import os
    from dotenv import load_dotenv

    load_dotenv()

    data = {
        'stats': {'success': 0, 'failed': 0, 'flood_wait': 0, 'channels_active': 0},
        'actions': [],
        'channels': [],
        'accounts': [],
        'updated': datetime.now().strftime('%H:%M:%S'),
    }

    async def fetch_data():
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/info_business')
        # Convert SQLAlchemy URL to asyncpg format
        db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')

        conn = await asyncpg.connect(db_url)

        try:
            # Stats by status
            rows = await conn.fetch("""
                SELECT status, COUNT(*) as cnt
                FROM traffic_actions
                GROUP BY status
            """)
            for row in rows:
                status = row['status']
                cnt = row['cnt']
                if status == 'success':
                    data['stats']['success'] = cnt
                elif status == 'failed':
                    data['stats']['failed'] = cnt
                elif status == 'flood_wait':
                    data['stats']['flood_wait'] = cnt

            # Active channels count
            row = await conn.fetchrow("""
                SELECT COUNT(*) as cnt FROM traffic_target_channels WHERE is_active = true
            """)
            data['stats']['channels_active'] = row['cnt'] if row else 0

            # Last 20 actions with channel usernames
            rows = await conn.fetch("""
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
            for row in rows:
                data['actions'].append({
                    'time': row['created_at'].strftime('%H:%M:%S') if row['created_at'] else '-',
                    'channel': row['username'] or 'unknown',
                    'status': row['status'] or 'unknown',
                    'content': row['content'] or '',
                    'error': row['error_message'] or '',
                })

            # Channels
            rows = await conn.fetch("""
                SELECT username, title, comment_strategy, posts_processed, comments_posted, is_active
                FROM traffic_target_channels
                ORDER BY is_active DESC, priority DESC
            """)
            for row in rows:
                data['channels'].append({
                    'username': row['username'] or '',
                    'title': row['title'] or '',
                    'strategy': row['comment_strategy'] or 'smart',
                    'posts': row['posts_processed'] or 0,
                    'comments': row['comments_posted'] or 0,
                    'active': row['is_active'],
                })

            # Accounts
            rows = await conn.fetch("""
                SELECT first_name, phone, status, daily_comments_count, total_comments_count
                FROM traffic_user_bot_accounts
                ORDER BY status
            """)
            for row in rows:
                data['accounts'].append({
                    'name': row['first_name'] or 'Unknown',
                    'phone': row['phone'] or '-',
                    'status': row['status'] or 'unknown',
                    'today': row['daily_comments_count'] or 0,
                    'total': row['total_comments_count'] or 0,
                })

        finally:
            await conn.close()

    # Run async code
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(fetch_data())
    finally:
        loop.close()

    return data


@app.route('/')
def dashboard():
    try:
        data = get_dashboard_data()
    except Exception as e:
        return f"Error loading data: {e}", 500

    return render_template_string(
        HTML_TEMPLATE,
        updated=data.get('updated', datetime.now().strftime('%H:%M:%S')),
        **data
    )


@app.route('/stream')
def stream():
    """SSE endpoint for real-time updates."""
    def generate() -> Generator[str, None, None]:
        while True:
            try:
                data = get_dashboard_data()
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                error_data = {
                    'error': str(e),
                    'updated': datetime.now().strftime('%H:%M:%S'),
                    'stats': {'success': 0, 'failed': 0, 'flood_wait': 0, 'channels_active': 0},
                    'actions': [],
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            time.sleep(5)  # Update every 5 seconds

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/health')
def health():
    """Health check endpoint."""
    try:
        data = get_dashboard_data()
        return {
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'stats': data['stats'],
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}, 500


if __name__ == '__main__':
    print("=" * 60)
    print("Traffic Engine Dashboard (Real-time)")
    print("=" * 60)
    print("\nOpen in browser: http://localhost:8050")
    print("SSE endpoint: http://localhost:8050/stream")
    print("Health check: http://localhost:8050/health")
    print("\nPress Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=8050, debug=False, threaded=True)
