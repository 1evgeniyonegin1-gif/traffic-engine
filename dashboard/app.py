"""
Traffic Engine Dashboard - Веб-интерфейс с аналитикой.

Запуск: python dashboard/app.py
Открыть: http://localhost:8050

Показывает в реальном времени:
- Все аккаунты и их статусы
- Комментарии (какой аккаунт, в какой канал, текст)
- Просмотры сторис (кого посмотрели, реакции)
- Инвайты (кого пригласили, в какую группу)
- Статистика за день/неделю/месяц
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template_string, jsonify
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from traffic_engine.config import settings
from traffic_engine.database.models import (
    Tenant,
    UserBotAccount,
    TargetChannel,
    TrafficAction,
    TargetAudience,
    InviteChat,
)

app = Flask(__name__)

# HTML шаблон дашборда
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Traffic Engine Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            min-height: 100vh;
        }

        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px 30px;
            border-bottom: 1px solid #2a2a4a;
        }

        .header h1 {
            font-size: 24px;
            font-weight: 600;
            color: #fff;
        }

        .header .subtitle {
            color: #888;
            font-size: 14px;
            margin-top: 5px;
        }

        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 20px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: #1a1a2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a2a4a;
        }

        .stat-card .label {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .stat-card .value {
            font-size: 32px;
            font-weight: 700;
            margin: 10px 0;
        }

        .stat-card .change {
            font-size: 12px;
        }

        .stat-card .change.positive { color: #4ade80; }
        .stat-card .change.negative { color: #f87171; }

        .section {
            background: #1a1a2e;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #2a2a4a;
            overflow: hidden;
        }

        .section-header {
            padding: 15px 20px;
            border-bottom: 1px solid #2a2a4a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .section-header h2 {
            font-size: 16px;
            font-weight: 600;
        }

        .section-header .badge {
            background: #3b82f6;
            color: #fff;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
        }

        .table-wrapper {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }

        th {
            background: #16213e;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            font-weight: 600;
        }

        td {
            font-size: 13px;
        }

        tr:hover td {
            background: rgba(59, 130, 246, 0.1);
        }

        .status {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 500;
        }

        .status.success { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
        .status.failed { background: rgba(248, 113, 113, 0.2); color: #f87171; }
        .status.active { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
        .status.warming { background: rgba(251, 191, 36, 0.2); color: #fbbf24; }
        .status.banned { background: rgba(248, 113, 113, 0.2); color: #f87171; }

        .emoji { font-size: 16px; margin-right: 5px; }

        .text-truncate {
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .time-ago {
            color: #666;
            font-size: 12px;
        }

        .refresh-btn {
            background: #3b82f6;
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }

        .refresh-btn:hover {
            background: #2563eb;
        }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }

        @media (max-width: 1200px) {
            .grid-2 {
                grid-template-columns: 1fr;
            }
        }

        .account-row {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .account-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 12px;
        }

        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #888;
            font-size: 12px;
        }

        .live-dot {
            width: 8px;
            height: 8px;
            background: #4ade80;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1>Traffic Engine Dashboard</h1>
                <div class="subtitle">Monitoring all actions in real-time</div>
            </div>
            <div class="auto-refresh">
                <div class="live-dot"></div>
                <span>Auto-refresh every 30 sec</span>
                <button class="refresh-btn" onclick="refreshAll()">Refresh</button>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- Статистика -->
        <div class="stats-grid" id="stats">
            <!-- Заполняется JS -->
        </div>

        <!-- Аккаунты -->
        <div class="section">
            <div class="section-header">
                <h2>Accounts</h2>
                <span class="badge" id="accounts-count">0</span>
            </div>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Account</th>
                            <th>Phone / Country</th>
                            <th>Proxy</th>
                            <th>Status</th>
                            <th>Comments</th>
                            <th>Stories</th>
                            <th>Invites</th>
                            <th>Last activity</th>
                        </tr>
                    </thead>
                    <tbody id="accounts-table">
                        <!-- Заполняется JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <div class="grid-2">
            <!-- Последние комментарии -->
            <div class="section">
                <div class="section-header">
                    <h2>Recent Comments</h2>
                    <span class="badge" id="comments-count">0</span>
                </div>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Account</th>
                                <th>Channel</th>
                                <th>Comment</th>
                                <th>Status</th>
                                <th>When</th>
                            </tr>
                        </thead>
                        <tbody id="comments-table">
                            <!-- Заполняется JS -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Последние просмотры сторис -->
            <div class="section">
                <div class="section-header">
                    <h2>Story Views</h2>
                    <span class="badge" id="stories-count">0</span>
                </div>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Account</th>
                                <th>User</th>
                                <th>Reaction</th>
                                <th>Status</th>
                                <th>When</th>
                            </tr>
                        </thead>
                        <tbody id="stories-table">
                            <!-- Заполняется JS -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Последние инвайты -->
        <div class="section">
            <div class="section-header">
                <h2>Recent Invites</h2>
                <span class="badge" id="invites-count">0</span>
            </div>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Account</th>
                            <th>User</th>
                            <th>Group</th>
                            <th>Status</th>
                            <th>When</th>
                        </tr>
                    </thead>
                    <tbody id="invites-table">
                        <!-- Заполняется JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // Форматирование времени
        function timeAgo(dateStr) {
            const date = new Date(dateStr);
            const now = new Date();
            const seconds = Math.floor((now - date) / 1000);

            if (seconds < 60) return 'just now';
            if (seconds < 3600) return Math.floor(seconds / 60) + ' min ago';
            if (seconds < 86400) return Math.floor(seconds / 3600) + ' h ago';
            return Math.floor(seconds / 86400) + ' d ago';
        }

        // Загрузка статистики
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                document.getElementById('stats').innerHTML = `
                    <div class="stat-card">
                        <div class="label">Comments Today</div>
                        <div class="value" style="color: #3b82f6;">${data.comments_today}</div>
                        <div class="change positive">Success: ${data.comments_success}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">Stories Today</div>
                        <div class="value" style="color: #8b5cf6;">${data.stories_today}</div>
                        <div class="change positive">+ reactions: ${data.reactions_today}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">Invites Today</div>
                        <div class="value" style="color: #f59e0b;">${data.invites_today}</div>
                        <div class="change">Success: ${data.invites_success}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">Active Accounts</div>
                        <div class="value" style="color: #4ade80;">${data.active_accounts}</div>
                        <div class="change">Total: ${data.total_accounts}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">Success Rate</div>
                        <div class="value" style="color: ${data.success_rate >= 70 ? '#4ade80' : '#f87171'};">${data.success_rate}%</div>
                        <div class="change">Today</div>
                    </div>
                `;
            } catch (e) {
                console.error('Error loading stats:', e);
            }
        }

        // Определение страны по коду телефона
        function getCountryByPhone(phone) {
            if (!phone) return { flag: '❓', name: 'Unknown' };
            const p = phone.replace(/[^0-9+]/g, '');

            // Индонезия
            if (p.startsWith('+62') || p.startsWith('62')) return { flag: '🇮🇩', name: 'Indonesia' };
            // Россия
            if (p.startsWith('+7') || p.startsWith('7')) return { flag: '🇷🇺', name: 'Russia' };
            // Украина
            if (p.startsWith('+380') || p.startsWith('380')) return { flag: '🇺🇦', name: 'Ukraine' };
            // Казахстан (тоже +7, но 7 7xx)
            if (p.startsWith('+77') || p.startsWith('77')) return { flag: '🇰🇿', name: 'Kazakhstan' };
            // США
            if (p.startsWith('+1') || p.length === 10) return { flag: '🇺🇸', name: 'USA' };
            // Индия
            if (p.startsWith('+91') || p.startsWith('91')) return { flag: '🇮🇳', name: 'India' };
            // Канада (тоже +1)
            // Великобритания
            if (p.startsWith('+44') || p.startsWith('44')) return { flag: '🇬🇧', name: 'UK' };
            // Германия
            if (p.startsWith('+49') || p.startsWith('49')) return { flag: '🇩🇪', name: 'Germany' };
            // Беларусь
            if (p.startsWith('+375') || p.startsWith('375')) return { flag: '🇧🇾', name: 'Belarus' };

            return { flag: '🌍', name: 'Other' };
        }

        // Загрузка аккаунтов
        async function loadAccounts() {
            try {
                const res = await fetch('/api/accounts');
                const data = await res.json();

                document.getElementById('accounts-count').textContent = data.length;

                document.getElementById('accounts-table').innerHTML = data.map(acc => {
                    const country = getCountryByPhone(acc.phone);
                    const proxyOk = acc.proxy_host ? true : false;
                    const proxyWarning = !proxyOk && country.name !== 'Russia';  // Нужен прокси для не-RU

                    return `
                    <tr style="${proxyWarning ? 'background: rgba(248, 113, 113, 0.1);' : ''}">
                        <td>
                            <div class="account-row">
                                <div class="account-avatar">${(acc.first_name || '?')[0]}</div>
                                <div>
                                    <div>${acc.first_name || 'Unknown'} ${acc.last_name || ''}</div>
                                    <div style="color: #666; font-size: 11px;">@${acc.username || 'none'}</div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <div>${acc.phone || '-'}</div>
                            <div style="font-size: 11px;">${country.flag} ${country.name}</div>
                        </td>
                        <td>
                            ${proxyOk
                                ? `<span class="status success">✅ ${acc.proxy_type || 'proxy'}</span>
                                   <div style="font-size: 10px; color: #666; margin-top: 2px;">${acc.proxy_host}:${acc.proxy_port}</div>`
                                : `<span class="status failed">❌ No proxy</span>
                                   ${proxyWarning ? '<div style="font-size: 10px; color: #f87171;">⚠️ Risk of ban!</div>' : ''}`
                            }
                        </td>
                        <td><span class="status ${acc.status}">${acc.status}</span></td>
                        <td>${acc.daily_comments || 0}</td>
                        <td>${acc.daily_story_views || 0} / ${acc.daily_story_reactions || 0}</td>
                        <td>${acc.daily_invites || 0}</td>
                        <td class="time-ago">${acc.last_used_at ? timeAgo(acc.last_used_at) : '-'}</td>
                    </tr>
                `}).join('') || '<tr><td colspan="8" style="text-align: center; color: #666;">No accounts</td></tr>';
            } catch (e) {
                console.error('Error loading accounts:', e);
            }
        }

        // Загрузка комментариев
        async function loadComments() {
            try {
                const res = await fetch('/api/comments');
                const data = await res.json();

                document.getElementById('comments-count').textContent = data.length;

                document.getElementById('comments-table').innerHTML = data.map(c => `
                    <tr>
                        <td>${c.account_name}</td>
                        <td>@${c.channel}</td>
                        <td class="text-truncate">${c.content || '-'}</td>
                        <td><span class="status ${c.status}">${c.status}</span></td>
                        <td class="time-ago">${timeAgo(c.created_at)}</td>
                    </tr>
                `).join('') || '<tr><td colspan="5" style="text-align: center; color: #666;">No data</td></tr>';
            } catch (e) {
                console.error('Error loading comments:', e);
            }
        }

        // Загрузка сторис
        async function loadStories() {
            try {
                const res = await fetch('/api/stories');
                const data = await res.json();

                document.getElementById('stories-count').textContent = data.length;

                document.getElementById('stories-table').innerHTML = data.map(s => `
                    <tr>
                        <td>${s.account_name}</td>
                        <td>ID: ${s.user_id}</td>
                        <td>${s.reaction || '-'}</td>
                        <td><span class="status ${s.status}">${s.status}</span></td>
                        <td class="time-ago">${timeAgo(s.created_at)}</td>
                    </tr>
                `).join('') || '<tr><td colspan="5" style="text-align: center; color: #666;">No data</td></tr>';
            } catch (e) {
                console.error('Error loading stories:', e);
            }
        }

        // Загрузка инвайтов
        async function loadInvites() {
            try {
                const res = await fetch('/api/invites');
                const data = await res.json();

                document.getElementById('invites-count').textContent = data.length;

                document.getElementById('invites-table').innerHTML = data.map(i => `
                    <tr>
                        <td>${i.account_name}</td>
                        <td>ID: ${i.user_id}</td>
                        <td>${i.chat_name || 'ID: ' + i.chat_id}</td>
                        <td><span class="status ${i.status}">${i.status}</span></td>
                        <td class="time-ago">${timeAgo(i.created_at)}</td>
                    </tr>
                `).join('') || '<tr><td colspan="5" style="text-align: center; color: #666;">No data</td></tr>';
            } catch (e) {
                console.error('Error loading invites:', e);
            }
        }

        // Обновить всё
        function refreshAll() {
            loadStats();
            loadAccounts();
            loadComments();
            loadStories();
            loadInvites();
        }

        // Первоначальная загрузка
        refreshAll();

        // Авто-обновление каждые 30 секунд
        setInterval(refreshAll, 30000);
    </script>
</body>
</html>
"""


def get_db_session():
    """Create fresh database engine and session for each request."""
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=1,
        max_overflow=0,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


def run_async(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/stats')
def api_stats():
    """Today's statistics."""
    try:
        async def get_stats():
            engine, session_factory = get_db_session()
            try:
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

                async with session_factory() as session:
                    # Comments today
                    comments_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "comment",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    comments_today = comments_result.scalar() or 0

                    # Successful comments
                    comments_success_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "comment",
                            TrafficAction.status == "success",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    comments_success = comments_success_result.scalar() or 0

                    # Stories today
                    stories_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "story_view",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    stories_today = stories_result.scalar() or 0

                    # Reactions today
                    reactions_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "story_reaction",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    reactions_today = reactions_result.scalar() or 0

                    # Invites today
                    invites_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "invite",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    invites_today = invites_result.scalar() or 0

                    # Successful invites
                    invites_success_result = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.action_type == "invite",
                            TrafficAction.status == "success",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    invites_success = invites_success_result.scalar() or 0

                    # Accounts
                    accounts_result = await session.execute(select(UserBotAccount))
                    accounts = accounts_result.scalars().all()
                    total_accounts = len(accounts)
                    active_accounts = len([a for a in accounts if a.status == "active"])

                    # Success rate
                    total_actions = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(TrafficAction.created_at >= today)
                    )
                    total = total_actions.scalar() or 0

                    success_actions = await session.execute(
                        select(func.count(TrafficAction.id))
                        .where(and_(
                            TrafficAction.status == "success",
                            TrafficAction.created_at >= today,
                        ))
                    )
                    success = success_actions.scalar() or 0

                    success_rate = round((success / total * 100) if total > 0 else 0)

                    return {
                        "comments_today": comments_today,
                        "comments_success": comments_success,
                        "stories_today": stories_today,
                        "reactions_today": reactions_today,
                        "invites_today": invites_today,
                        "invites_success": invites_success,
                        "total_accounts": total_accounts,
                        "active_accounts": active_accounts,
                        "success_rate": success_rate,
                    }
            finally:
                await engine.dispose()

        return jsonify(run_async(get_stats()))
    except Exception as e:
        logger.error(f"API /api/stats error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/accounts')
def api_accounts():
    """List of accounts."""
    try:
        async def get_accounts():
            engine, session_factory = get_db_session()
            try:
                async with session_factory() as session:
                    result = await session.execute(
                        select(UserBotAccount).order_by(desc(UserBotAccount.last_used_at))
                    )
                    accounts = result.scalars().all()

                    return [{
                        "id": a.id,
                        "phone": a.phone,
                        "first_name": a.first_name,
                        "last_name": a.last_name,
                        "username": a.username,
                        "status": a.status,
                        "daily_comments": a.daily_comments,
                        "daily_story_views": a.daily_story_views,
                        "daily_story_reactions": a.daily_story_reactions,
                        "daily_invites": a.daily_invites,
                        "last_used_at": a.last_used_at.isoformat() if a.last_used_at else None,
                        "proxy_type": a.proxy_type,
                        "proxy_host": a.proxy_host,
                        "proxy_port": a.proxy_port,
                    } for a in accounts]
            finally:
                await engine.dispose()

        return jsonify(run_async(get_accounts()))
    except Exception as e:
        logger.error(f"API /api/accounts error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/comments')
def api_comments():
    """Recent comments."""
    try:
        async def get_comments():
            engine, session_factory = get_db_session()
            try:
                async with session_factory() as session:
                    result = await session.execute(
                        select(TrafficAction)
                        .where(TrafficAction.action_type == "comment")
                        .options(selectinload(TrafficAction.account))
                        .order_by(desc(TrafficAction.created_at))
                        .limit(50)
                    )
                    actions = result.scalars().all()

                    return [{
                        "account_name": a.account.first_name if a.account else "Unknown",
                        "channel": str(a.target_channel_id) if a.target_channel_id else "-",
                        "content": a.content[:100] if a.content else None,
                        "status": a.status,
                        "created_at": a.created_at.isoformat(),
                    } for a in actions]
            finally:
                await engine.dispose()

        return jsonify(run_async(get_comments()))
    except Exception as e:
        logger.error(f"API /api/comments error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/stories')
def api_stories():
    """Recent story views."""
    try:
        async def get_stories():
            engine, session_factory = get_db_session()
            try:
                async with session_factory() as session:
                    result = await session.execute(
                        select(TrafficAction)
                        .where(TrafficAction.action_type.in_(["story_view", "story_reaction"]))
                        .options(selectinload(TrafficAction.account))
                        .order_by(desc(TrafficAction.created_at))
                        .limit(50)
                    )
                    actions = result.scalars().all()

                    return [{
                        "account_name": a.account.first_name if a.account else "Unknown",
                        "user_id": a.target_user_id,
                        "reaction": a.reaction,
                        "status": a.status,
                        "created_at": a.created_at.isoformat(),
                    } for a in actions]
            finally:
                await engine.dispose()

        return jsonify(run_async(get_stories()))
    except Exception as e:
        logger.error(f"API /api/stories error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/invites')
def api_invites():
    """Recent invites."""
    try:
        async def get_invites():
            engine, session_factory = get_db_session()
            try:
                async with session_factory() as session:
                    result = await session.execute(
                        select(TrafficAction)
                        .where(TrafficAction.action_type == "invite")
                        .options(selectinload(TrafficAction.account))
                        .order_by(desc(TrafficAction.created_at))
                        .limit(50)
                    )
                    actions = result.scalars().all()

                    return [{
                        "account_name": a.account.first_name if a.account else "Unknown",
                        "user_id": a.target_user_id,
                        "chat_id": a.target_channel_id,
                        "chat_name": None,
                        "status": a.status,
                        "created_at": a.created_at.isoformat(),
                    } for a in actions]
            finally:
                await engine.dispose()

        return jsonify(run_async(get_invites()))
    except Exception as e:
        logger.error(f"API /api/invites error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("Traffic Engine Dashboard")
    print("=" * 50)
    print()
    print("Open in browser: http://localhost:8050")
    print()
    print("Ctrl+C to stop")
    print("=" * 50)

    app.run(host='0.0.0.0', port=8050, debug=True)
