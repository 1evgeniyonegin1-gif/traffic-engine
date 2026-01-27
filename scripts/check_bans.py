#!/usr/bin/env python
"""
Проверка статуса аккаунтов и каналов.

Показывает:
- Какие аккаунты забанены
- Какие аккаунты в cooldown
- Какие каналы недоступны
- Последние ошибки
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func, desc
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import (
    Tenant,
    UserBotAccount,
    TargetChannel,
    TrafficAction,
)


console = Console()


async def show_banned_accounts(tenant_id: int):
    """Показать забаненные и проблемные аккаунты."""
    async with get_session() as session:
        # Все аккаунты
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant_id)
        )
        accounts = result.scalars().all()

        if not accounts:
            console.print("[yellow]Нет аккаунтов[/yellow]")
            return

        # Группируем по статусу
        banned = [acc for acc in accounts if acc.status == "banned"]
        cooldown = [acc for acc in accounts if acc.status == "cooldown"]
        warming = [acc for acc in accounts if acc.status == "warming"]
        active = [acc for acc in accounts if acc.status == "active"]

        # Таблица проблемных аккаунтов
        if banned or cooldown:
            table = Table(
                title="⚠️ Проблемные аккаунты",
                show_header=True,
                header_style="bold red",
                box=box.ROUNDED
            )
            table.add_column("Аккаунт", style="cyan")
            table.add_column("Статус", justify="center")
            table.add_column("Причина", style="dim")
            table.add_column("Cooldown до", style="yellow")

            for acc in banned:
                table.add_row(
                    f"{acc.first_name} (@{acc.username})",
                    "[red]✗ ЗАБАНЕН[/red]",
                    acc.cooldown_reason or "неизвестно",
                    "-"
                )

            for acc in cooldown:
                cooldown_str = ""
                if acc.cooldown_until:
                    if acc.cooldown_until > datetime.now():
                        minutes = int((acc.cooldown_until - datetime.now()).total_seconds() / 60)
                        cooldown_str = f"{minutes} мин"
                    else:
                        cooldown_str = "истёк"

                table.add_row(
                    f"{acc.first_name} (@{acc.username})",
                    "[yellow]⏸ Cooldown[/yellow]",
                    acc.cooldown_reason or "FloodWait",
                    cooldown_str
                )

            console.print(table)
            console.print()
        else:
            console.print("[green]✅ Нет проблемных аккаунтов![/green]\n")

        # Таблица активных
        table2 = Table(
            title="✅ Активные аккаунты",
            show_header=True,
            header_style="bold green",
            box=box.ROUNDED
        )
        table2.add_column("Аккаунт", style="cyan")
        table2.add_column("Статус", justify="center")
        table2.add_column("Комментов сегодня", justify="right")

        today = datetime.now().date()

        for acc in active + warming:
            # Считаем комментарии сегодня
            result = await session.execute(
                select(func.count(TrafficAction.id)).where(
                    TrafficAction.account_id == acc.id,
                    TrafficAction.action_type == "comment",
                    TrafficAction.status == "success",
                    func.date(TrafficAction.created_at) == today,
                )
            )
            comments_today = result.scalar() or 0

            status_icon = "[green]✓ Активен[/green]" if acc.status == "active" else "[cyan]↻ Прогрев[/cyan]"

            table2.add_row(
                f"{acc.first_name} (@{acc.username})",
                status_icon,
                f"{comments_today}/80"
            )

        console.print(table2)
        console.print()


async def show_problem_channels(tenant_id: int):
    """Показать проблемные каналы."""
    async with get_session() as session:
        # Все каналы
        result = await session.execute(
            select(TargetChannel).where(
                TargetChannel.tenant_id == tenant_id
            )
        )
        channels = result.scalars().all()

        if not channels:
            console.print("[yellow]Нет каналов[/yellow]")
            return

        # Недавние ошибки по каналам
        week_ago = datetime.now() - timedelta(days=1)

        # Получаем ошибки
        result = await session.execute(
            select(
                TrafficAction.target_channel_id,
                func.count(TrafficAction.id).label("error_count"),
                func.max(TrafficAction.error_message).label("last_error")
            ).where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.status.in_(["failed", "banned"]),
                TrafficAction.created_at >= week_ago
            ).group_by(TrafficAction.target_channel_id)
        )

        errors_by_channel = {row.target_channel_id: {
            "count": row.error_count,
            "error": row.last_error
        } for row in result}

        # Каналы с ошибками
        problem_channels = [
            ch for ch in channels
            if ch.channel_id in errors_by_channel
        ]

        if problem_channels:
            table = Table(
                title="⚠️ Проблемные каналы (за последний день)",
                show_header=True,
                header_style="bold yellow",
                box=box.ROUNDED
            )
            table.add_column("Канал", style="cyan")
            table.add_column("Ошибок", justify="center", style="red")
            table.add_column("Последняя ошибка", style="dim", max_width=50)

            for ch in problem_channels:
                error_info = errors_by_channel[ch.channel_id]
                table.add_row(
                    f"@{ch.username}",
                    str(error_info["count"]),
                    error_info["error"] or "неизвестно"
                )

            console.print(table)
            console.print()
        else:
            console.print("[green]✅ Нет проблемных каналов![/green]\n")

        # Статистика успешных
        result = await session.execute(
            select(
                TrafficAction.target_channel_id,
                func.count(TrafficAction.id).label("success_count")
            ).where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.status == "success",
                TrafficAction.created_at >= week_ago
            ).group_by(TrafficAction.target_channel_id)
        )

        success_by_channel = {row.target_channel_id: row.success_count for row in result}

        # Топ-10 каналов по успешным комментам
        top_channels = sorted(
            [ch for ch in channels if ch.channel_id in success_by_channel],
            key=lambda x: success_by_channel[x.channel_id],
            reverse=True
        )[:10]

        if top_channels:
            table2 = Table(
                title="🔥 Топ-10 каналов (успешных комментов за день)",
                show_header=True,
                header_style="bold green",
                box=box.ROUNDED
            )
            table2.add_column("Место", justify="center")
            table2.add_column("Канал", style="cyan")
            table2.add_column("Комментов", justify="right", style="green")

            for i, ch in enumerate(top_channels, 1):
                table2.add_row(
                    str(i),
                    f"@{ch.username}",
                    str(success_by_channel[ch.channel_id])
                )

            console.print(table2)
            console.print()


async def show_recent_errors(tenant_id: int, limit: int = 10):
    """Показать последние ошибки."""
    async with get_session() as session:
        result = await session.execute(
            select(TrafficAction)
            .where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.status.in_(["failed", "banned", "flood_wait"])
            )
            .order_by(desc(TrafficAction.created_at))
            .limit(limit)
        )
        errors = result.scalars().all()

        if not errors:
            console.print("[green]✅ Нет недавних ошибок![/green]\n")
            return

        table = Table(
            title=f"🔴 Последние {limit} ошибок",
            show_header=True,
            header_style="bold red",
            box=box.ROUNDED
        )
        table.add_column("Время", style="dim")
        table.add_column("Аккаунт", style="cyan")
        table.add_column("Канал", style="blue")
        table.add_column("Ошибка", style="red", max_width=40)

        for err in errors:
            # Получаем аккаунт
            acc = await session.get(UserBotAccount, err.account_id)
            acc_name = f"@{acc.username}" if acc else f"ID:{err.account_id}"

            # Получаем канал
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.channel_id == err.target_channel_id
                )
            )
            channel = result.scalar_one_or_none()
            channel_name = f"@{channel.username}" if channel else f"ID:{err.target_channel_id}"

            # Время
            time_str = err.created_at.strftime("%H:%M:%S")

            # Ошибка
            error_str = err.error_message or "неизвестно"
            if len(error_str) > 40:
                error_str = error_str[:37] + "..."

            table.add_row(
                time_str,
                acc_name,
                channel_name,
                error_str
            )

        console.print(table)
        console.print()


async def main():
    """Показать статус аккаунтов и каналов."""
    console.print("\n" + "=" * 60)
    console.print("[bold red]⚠️ ПРОВЕРКА БАНОВ И ПРОБЛЕМ[/bold red]")
    console.print("=" * 60 + "\n")

    await init_db()

    async with get_session() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.name == "infobusiness")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            console.print("[red]Тенант 'infobusiness' не найден![/red]")
            return

        console.print(f"Тенант: [bold]{tenant.display_name}[/bold]\n")

        # Показываем статусы
        await show_banned_accounts(tenant.id)
        await show_problem_channels(tenant.id)
        await show_recent_errors(tenant.id, limit=10)

    console.print("[dim]Для обновления запустите: python scripts/check_bans.py[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
