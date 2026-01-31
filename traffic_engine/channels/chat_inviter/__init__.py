"""
Chat Inviter - Модуль инвайтов в группы-мероприятия.

Функции:
- Инвайт пользователей из ЦА в группы-мероприятия
- Создание групп по шаблонам
- Публикация оффера при достижении порога участников
"""

from .chat_inviter import ChatInviter
from .group_creator import GroupCreator
from .invite_monitor import InviteMonitor

__all__ = ["ChatInviter", "GroupCreator", "InviteMonitor"]
