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
from traffic_engine.notifications import TelegramNotifier


class TrafficEngine:
    """
    Main Traffic Engine class.

    Управляет всеми компонентами системы:
    - Account Manager
    - Channel Monitor (автокомментирование)
    - Stories Reactor (в будущем)
    - Chat Inviter (в будущем)
    """

    def __init__(self):
        """Initialize Traffic Engine."""
        self.monitors: Dict[int, ChannelMonitor] = {}  # tenant_id -> monitor
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

        logger.info(f"Tenant {tenant.name} started")

        # Send start notification
        if self.notifier:
            accounts_count = len(account_manager._clients) if hasattr(account_manager, '_clients') else 0
            channels_count = len(monitor._channels) if hasattr(monitor, '_channels') else 0
            await self.notifier.notify_system_start(accounts_count, channels_count)

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
