#!/usr/bin/env python
"""
Traffic Engine - Main entry point.

Запускает систему автоматизированного трафика.
Использует Telethon для работы с Telegram API.
"""

import asyncio
import signal
import sys
from typing import Dict, Optional

from loguru import logger

from traffic_engine.config import settings
from traffic_engine.database import init_db, get_session
from traffic_engine.database.models import Tenant
from traffic_engine.core import AccountManager
from traffic_engine.channels.auto_comments import ChannelMonitor
from traffic_engine.channels.story_viewer import StoryMonitor
from traffic_engine.channels.chat_inviter import InviteMonitor
from traffic_engine.notifications import TelegramNotifier


class TrafficEngine:
    """
    Main Traffic Engine class.

    Управляет всеми компонентами системы:
    - Account Manager
    - Channel Monitor (автокомментирование)
    - Story Monitor (просмотр сторис ЦА)
    - Invite Monitor (инвайты в группы-мероприятия)
    """

    def __init__(self):
        """Initialize Traffic Engine."""
        self.monitors: Dict[int, ChannelMonitor] = {}  # tenant_id -> monitor
        self.story_monitors: Dict[int, StoryMonitor] = {}  # tenant_id -> story monitor
        self.invite_monitors: Dict[int, InviteMonitor] = {}  # tenant_id -> invite monitor
        self.account_managers: Dict[int, AccountManager] = {}
        self.notifier: Optional[TelegramNotifier] = None
        self._running = False

    async def start(self, tenant_names: Optional[list] = None) -> None:
        """
        Start Traffic Engine for specified tenants.

        Args:
            tenant_names: List of tenant names to start (None = all active)
        """
        logger.info("=== Starting Traffic Engine ===")

        # Initialize database
        await init_db()
        logger.info("Database initialized")

        # Initialize Telegram notifier for alerts
        if settings.alert_bot_token and settings.alerts_enabled:
            self.notifier = TelegramNotifier(
                bot_token=settings.alert_bot_token,
                admin_id=settings.alert_admin_id,
                enabled=True,
            )
            logger.info("Telegram notifier initialized")

        # Load tenants
        async with get_session() as session:
            from sqlalchemy import select
            query = select(Tenant).where(Tenant.is_active == True)

            if tenant_names:
                query = query.where(Tenant.name.in_(tenant_names))

            result = await session.execute(query)
            tenants = result.scalars().all()

            if not tenants:
                logger.error("No active tenants found!")
                return

            logger.info(f"Found {len(tenants)} active tenant(s)")

            # Start monitor for each tenant
            for tenant in tenants:
                await self._start_tenant(tenant)

        self._running = True

        # Keep running
        logger.info("Traffic Engine is running. Press Ctrl+C to stop.")

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

        await self.stop()

    async def _start_tenant(self, tenant: Tenant) -> None:
        """Start monitoring for a tenant."""
        logger.info(f"Starting tenant: {tenant.display_name}")

        # Create account manager
        account_manager = AccountManager(tenant.id)
        await account_manager.initialize()
        self.account_managers[tenant.id] = account_manager

        # Create channel monitor with notifier
        monitor = ChannelMonitor(
            tenant_id=tenant.id,
            account_manager=account_manager,
            notifier=self.notifier,
        )
        await monitor.initialize(tenant_name=tenant.name)
        self.monitors[tenant.id] = monitor

        # Start monitoring in background
        asyncio.create_task(monitor.start())

        # Create story monitor for viewing stories of target audience
        story_monitor = StoryMonitor(
            tenant_id=tenant.id,
            account_manager=account_manager,
            notifier=self.notifier,
        )
        await story_monitor.initialize()
        self.story_monitors[tenant.id] = story_monitor

        # Start story monitoring in background
        asyncio.create_task(story_monitor.start())

        # Create invite monitor for inviting target audience to event groups
        invite_monitor = InviteMonitor(
            tenant_id=tenant.id,
            account_manager=account_manager,
            notifier=self.notifier,
        )
        await invite_monitor.initialize()
        self.invite_monitors[tenant.id] = invite_monitor

        # Start invite monitoring in background
        asyncio.create_task(invite_monitor.start())

        logger.info(f"Tenant {tenant.name} started (comments + stories + invites)")

        # Send start notification
        if self.notifier:
            accounts_count = len(account_manager._clients) if hasattr(account_manager, '_clients') else 0
            channels_count = len(monitor._channels) if hasattr(monitor, '_channels') else 0
            await self.notifier.notify_system_start(accounts_count, channels_count)
            # Note: Story monitor also started but using same accounts

    async def stop(self) -> None:
        """Stop Traffic Engine."""
        logger.info("Stopping Traffic Engine...")
        self._running = False

        # Send stop notification
        if self.notifier:
            await self.notifier.notify_system_stop("Manual shutdown")
            await self.notifier.close()

        # Stop all monitors
        for tenant_id, monitor in self.monitors.items():
            await monitor.stop()

        # Stop all story monitors
        for tenant_id, story_monitor in self.story_monitors.items():
            await story_monitor.stop()

        # Stop all invite monitors
        for tenant_id, invite_monitor in self.invite_monitors.items():
            await invite_monitor.stop()

        # Close all account managers
        for tenant_id, manager in self.account_managers.items():
            await manager.close()

        logger.info("Traffic Engine stopped")


async def main():
    """Main entry point."""
    # Configure logging
    logger.add(
        "logs/traffic_engine_{time}.log",
        rotation="1 day",
        retention="7 days",
        level=settings.log_level,
    )

    engine = TrafficEngine()

    # Handle shutdown signals (use get_running_loop inside async context)
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(engine.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start engine
    await engine.start()


def run():
    """Entry point that creates event loop explicitly for Python 3.14+."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    run()
