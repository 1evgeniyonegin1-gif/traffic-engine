"""
Database models for Traffic Engine.

Модели для хранения:
- Tenant (проекты/ниши)
- UserBotAccount (userbot аккаунты)
- TargetChannel (каналы для мониторинга)
- TrafficAction (лог действий)
- TargetAudience (целевая аудитория)
- InviteChat (чаты для инвайтов)
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class TimestampMixin:
    """Mixin для автоматических timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class Tenant(Base, TimestampMixin):
    """
    Тенант (проект/ниша).

    Позволяет использовать одну систему для разных проектов:
    - infobusiness (курсы по заработку)
    - nl_international (здоровье, NL)
    - и др.
    """
    __tablename__ = "traffic_tenants"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Идентификация
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Конфигурация
    config_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    funnel_link: Mapped[str] = mapped_column(String(500))  # Ссылка на воронку

    # Статус
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Лимиты (можно переопределить для каждого тенанта)
    max_accounts: Mapped[int] = mapped_column(Integer, default=5)
    max_daily_comments: Mapped[int] = mapped_column(Integer, default=200)
    max_daily_invites: Mapped[int] = mapped_column(Integer, default=150)
    max_daily_story_views: Mapped[int] = mapped_column(Integer, default=500)

    # Relationships
    accounts: Mapped[List["UserBotAccount"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    target_channels: Mapped[List["TargetChannel"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    actions: Mapped[List["TrafficAction"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.name}>"


class UserBotAccount(Base, TimestampMixin):
    """
    Userbot аккаунт для выполнения действий.

    Хранит session string для Pyrogram и отслеживает лимиты.
    """
    __tablename__ = "traffic_userbot_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("traffic_tenants.id"), index=True)

    # Telegram данные
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    session_string: Mapped[str] = mapped_column(Text)  # Зашифрованный session
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Профиль
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Статус аккаунта
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True
    )  # active, warming, banned, cooldown, disabled

    # Время последнего использования и cooldown
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Дневные лимиты (сбрасываются в полночь)
    daily_comments: Mapped[int] = mapped_column(Integer, default=0)
    daily_invites: Mapped[int] = mapped_column(Integer, default=0)
    daily_story_views: Mapped[int] = mapped_column(Integer, default=0)
    daily_story_reactions: Mapped[int] = mapped_column(Integer, default=0)
    limits_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Флаги возможностей
    can_comment: Mapped[bool] = mapped_column(Boolean, default=True)
    can_invite: Mapped[bool] = mapped_column(Boolean, default=True)
    can_view_stories: Mapped[bool] = mapped_column(Boolean, default=True)

    # Прогрев аккаунта
    warmup_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    warmup_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Прокси (опционально)
    proxy_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # socks5, http
    proxy_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    proxy_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    proxy_password: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="accounts")
    actions: Mapped[List["TrafficAction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_account_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<UserBotAccount {self.phone} ({self.status})>"

    @property
    def is_available(self) -> bool:
        """Проверяет, доступен ли аккаунт для действий."""
        if self.status != "active":
            return False
        if self.cooldown_until and self.cooldown_until > datetime.now():
            return False
        return True


class TargetChannel(Base, TimestampMixin):
    """
    Канал для мониторинга и автокомментирования.
    """
    __tablename__ = "traffic_target_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("traffic_tenants.id"), index=True)

    # Telegram данные
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255))

    # Настройки
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1-10, выше = важнее

    # Стратегия комментирования
    comment_strategy: Mapped[str] = mapped_column(
        String(50),
        default="smart"
    )  # smart, supportive, funny, expert
    max_delay_minutes: Mapped[int] = mapped_column(Integer, default=5)

    # Фильтры
    skip_ads: Mapped[bool] = mapped_column(Boolean, default=True)
    skip_reposts: Mapped[bool] = mapped_column(Boolean, default=True)
    min_post_length: Mapped[int] = mapped_column(Integer, default=50)

    # Последний обработанный пост
    last_post_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Статистика
    posts_processed: Mapped[int] = mapped_column(Integer, default=0)
    comments_posted: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="target_channels")

    # Indexes
    __table_args__ = (
        Index("idx_channel_tenant_active", "tenant_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<TargetChannel @{self.username or self.channel_id}>"


class TrafficAction(Base, TimestampMixin):
    """
    Лог всех действий системы.

    Используется для:
    - Отслеживания истории
    - Аналитики эффективности
    - Отладки проблем
    """
    __tablename__ = "traffic_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("traffic_tenants.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("traffic_userbot_accounts.id"), index=True)

    # Тип действия
    action_type: Mapped[str] = mapped_column(
        String(50),
        index=True
    )  # comment, story_view, story_react, invite, join_channel

    # Контекст действия
    target_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_story_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Содержимое
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Текст комментария
    reaction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Эмодзи реакции

    # Результат
    status: Mapped[str] = mapped_column(
        String(20),
        index=True
    )  # success, failed, flood_wait, banned
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flood_wait_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # AI метаданные
    ai_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # claude, yandexgpt
    ai_prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Конверсия (заполняется позже)
    conversion_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    conversion_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    conversion_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="actions")
    account: Mapped["UserBotAccount"] = relationship(back_populates="actions")

    # Indexes
    __table_args__ = (
        Index("idx_action_tenant_type_date", "tenant_id", "action_type", "created_at"),
        Index("idx_action_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<TrafficAction {self.action_type} ({self.status})>"


class TargetAudience(Base, TimestampMixin):
    """
    Целевая аудитория для stories и инвайтов.

    Собирается из:
    - Подписчиков каналов
    - Участников групп
    - Тех, кто смотрел наши сторис
    """
    __tablename__ = "traffic_target_audience"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("traffic_tenants.id"), index=True)

    # Telegram данные
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Источник
    source_type: Mapped[str] = mapped_column(
        String(50)
    )  # channel_subscribers, group_members, story_viewers, commenters
    source_id: Mapped[int] = mapped_column(BigInteger)  # ID канала/группы
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Статус обработки
    status: Mapped[str] = mapped_column(
        String(20),
        default="new",
        index=True
    )  # new, processed, invited, converted, blocked, error

    # Действия
    story_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    story_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    story_reacted: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_to_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Качество (для приоритизации)
    quality_score: Mapped[int] = mapped_column(Integer, default=50)  # 0-100

    # Indexes
    __table_args__ = (
        Index("idx_audience_tenant_status", "tenant_id", "status"),
        Index("idx_audience_user_tenant", "user_id", "tenant_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<TargetAudience {self.user_id} ({self.status})>"


class InviteChat(Base, TimestampMixin):
    """
    Чат для инвайтов.

    Создаём тематические чаты, приглашаем ЦА,
    публикуем оффер с ссылкой на воронку.
    """
    __tablename__ = "traffic_invite_chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("traffic_tenants.id"), index=True)

    # Telegram данные
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    invite_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Настройки
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_members: Mapped[int] = mapped_column(Integer, default=1000)

    # Сообщение-оффер
    offer_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    offer_published: Mapped[bool] = mapped_column(Boolean, default=False)
    offer_published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Порог для публикации оффера
    publish_offer_at_members: Mapped[int] = mapped_column(Integer, default=50)

    # Статистика
    total_invited: Mapped[int] = mapped_column(Integer, default=0)
    total_joined: Mapped[int] = mapped_column(Integer, default=0)
    total_left: Mapped[int] = mapped_column(Integer, default=0)
    total_converted: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<InviteChat {self.title}>"
