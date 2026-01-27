#!/usr/bin/env python
"""
Показать статистику работы Traffic Engine.

Показывает:
- Аккаунты и их статус
- Сколько комментариев отправлено сегодня/всего
- Последние действия
- Статус каналов
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import (
    Tenant,
    UserBotAccount,
    TargetChannel,
    TrafficAction,
)


console = Console()


async def show_accounts_stats(tenant_id: int):
    """Показать статистику аккаунтов."""
    async with get_session() as session:
        result = await session.execute(
            select(UserBotAccount).where(UserBotAccount.tenant_id == tenant_id)
        )
        accounts = result.scalars().all()

        if not accounts:
            console.print("[yellow]Нет аккаунтов в БД[/yellow]")
            return

        table = Table(title="🤖 Аккаунты", show_header=True, header_style="bold magenta")
        table.add_column("Имя", style="cyan")
        table.add_column("Username", style="blue")
        table.add_column("Статус", justify="center")
        table.add_column("Комменты сегодня", justify="right")
        table.add_column("Всего комментов", justify="right")
        table.add_column("Cooldown до", style="dim")

        today = datetime.now().date()

        for acc in accounts:
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

            # Всего комментариев
            result = await session.execute(
                select(func.count(TrafficAction.id)).where(
                    TrafficAction.account_id == acc.id,
                    TrafficAction.action_type == "comment",
                    TrafficAction.status == "success",
                )
            )
            comments_total = result.scalar() or 0

            # Статус
            if acc.status == "active":
                status_icon = "[green]✓ Активен[/green]"
            elif acc.status == "cooldown":
                status_icon = "[yellow]⏸ Cooldown[/yellow]"
            elif acc.status == "banned":
                status_icon = "[red]✗ Забанен[/red]"
            else:
                status_icon = f"[dim]{acc.status}[/dim]"

            # Cooldown
            cooldown_str = ""
            if acc.cooldown_until:
                if acc.cooldown_until > datetime.now():
                    minutes = int((acc.cooldown_until - datetime.now()).total_seconds() / 60)
                    cooldown_str = f"{minutes} мин"
                else:
                    cooldown_str = "[dim]истёк[/dim]"

            table.add_row(
                f"{acc.first_name} {acc.last_name or ''}".strip(),
                f"@{acc.username}",
                status_icon,
                f"{comments_today}/80",
                str(comments_total),
                cooldown_str,
            )

        console.print(table)
        console.print()


async def show_channels_stats(tenant_id: int):
    """Показать статистику каналов."""
    async with get_session() as session:
        result = await session.execute(
            select(TargetChannel).where(
                TargetChannel.tenant_id == tenant_id
            ).order_by(TargetChannel.priority.desc())
        )
        channels = result.scalars().all()

        if not channels:
            console.print("[yellow]Нет целевых каналов в БД[/yellow]")
            return

        table = Table(title="📢 Целевые каналы", show_header=True, header_style="bold cyan")
        table.add_column("Канал", style="cyan")
        table.add_column("Приоритет", justify="center")
        table.add_column("Постов обработано", justify="right")
        table.add_column("Комментов", justify="right")
        table.add_column("Последняя проверка", style="dim")
        table.add_column("Статус", justify="center")

        for ch in channels:
            status = "[green]✓[/green]" if ch.is_active else "[dim]✗[/dim]"

            last_check = ""
            if ch.last_processed_at:
                diff = datetime.now() - ch.last_processed_at
                if diff.total_seconds() < 3600:
                    last_check = f"{int(diff.total_seconds() / 60)} мин назад"
                elif diff.total_seconds() < 86400:
                    last_check = f"{int(diff.total_seconds() / 3600)} ч назад"
                else:
                    last_check = ch.last_processed_at.strftime("%d.%m %H:%M")

            table.add_row(
                f"@{ch.username}",
                str(ch.priority),
                str(ch.posts_processed),
                str(ch.comments_posted),
                last_check or "[dim]никогда[/dim]",
                status,
            )

        console.print(table)
        console.print()


async def show_recent_actions(tenant_id: int, limit: int = 10):
    """Показать последние действия."""
    async with get_session() as session:
        result = await session.execute(
            select(TrafficAction)
            .where(TrafficAction.tenant_id == tenant_id)
            .order_by(TrafficAction.created_at.desc())
            .limit(limit)
        )
        actions = result.scalars().all()

        if not actions:
            console.print("[yellow]Нет действий в БД[/yellow]")
            return

        table = Table(title=f"📝 Последние {limit} действий", show_header=True, header_style="bold green")
        table.add_column("Время", style="dim")
        table.add_column("Аккаунт", style="cyan")
        table.add_column("Тип", justify="center")
        table.add_column("Канал", style="blue")
        table.add_column("Статус", justify="center")
        table.add_column("Комментарий", style="dim", max_width=50)

        for action in actions:
            # Получаем аккаунт
            acc = await session.get(UserBotAccount, action.account_id)
            acc_name = f"@{acc.username}" if acc else f"ID:{action.account_id}"

            # Получаем канал
            result = await session.execute(
                select(TargetChannel).where(
                    TargetChannel.channel_id == action.target_channel_id
                )
            )
            channel = result.scalar_one_or_none()
            channel_name = f"@{channel.username}" if channel else f"ID:{action.target_channel_id}"

            # Статус
            if action.status == "success":
                status_icon = "[green]✓[/green]"
            elif action.status == "flood_wait":
                status_icon = f"[yellow]⏸ {action.flood_wait_seconds}s[/yellow]"
            elif action.status == "banned":
                status_icon = "[red]✗ Ban[/red]"
            else:
                status_icon = f"[dim]{action.status}[/dim]"

            # Время
            time_str = action.created_at.strftime("%H:%M:%S")

            # Комментарий (первые 50 символов)
            comment = (action.content or "")[:50]
            if len(action.content or "") > 50:
                comment += "..."

            table.add_row(
                time_str,
                acc_name,
                action.action_type,
                channel_name,
                status_icon,
                comment,
            )

        console.print(table)
        console.print()


async def show_daily_stats(tenant_id: int):
    """Показать статистику за сегодня."""
    async with get_session() as session:
        today = datetime.now().date()

        # Всего успешных комментариев
        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.action_type == "comment",
                TrafficAction.status == "success",
                func.date(TrafficAction.created_at) == today,
            )
        )
        comments_today = result.scalar() or 0

        # FloodWait случаев
        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.status == "flood_wait",
                func.date(TrafficAction.created_at) == today,
            )
        )
        flood_waits = result.scalar() or 0

        # Ошибок
        result = await session.execute(
            select(func.count(TrafficAction.id)).where(
                TrafficAction.tenant_id == tenant_id,
                TrafficAction.status == "failed",
                func.date(TrafficAction.created_at) == today,
            )
        )
        errors = result.scalar() or 0

        stats = f"""
[bold green]✓ Комментариев отправлено:[/bold green] {comments_today}
[bold yellow]⏸ FloodWait случаев:[/bold yellow] {flood_waits}
[bold red]✗ Ошибок:[/bold red] {errors}
        """

        console.print(Panel(stats.strip(), title="📊 Статистика за сегодня", border_style="blue"))
        console.print()


async def main():
    """Показать всю статистику."""
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]TRAFFIC ENGINE - СТАТИСТИКА[/bold cyan]")
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

        # Показываем статистику
        await show_daily_stats(tenant.id)
        await show_accounts_stats(tenant.id)
        await show_channels_stats(tenant.id)
        await show_recent_actions(tenant.id, limit=10)

    console.print("[dim]Для обновления запустите: python scripts/check_stats.py[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем[/yellow]")
