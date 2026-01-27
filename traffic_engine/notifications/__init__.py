"""
Notifications module for Traffic Engine.

Provides alerting capabilities via Telegram.
"""

from .telegram_notifier import TelegramNotifier

__all__ = ["TelegramNotifier"]
