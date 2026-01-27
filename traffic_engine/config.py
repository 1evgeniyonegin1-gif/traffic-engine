"""
Configuration for Traffic Engine.

Загружает настройки из .env файла.
"""

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ===========================================
    # DATABASE
    # ===========================================
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/info_business",
        description="PostgreSQL connection URL"
    )

    # ===========================================
    # TELEGRAM API
    # ===========================================
    telegram_api_id: int = Field(
        default=0,
        description="Telegram API ID from my.telegram.org"
    )
    telegram_api_hash: str = Field(
        default="",
        description="Telegram API Hash from my.telegram.org"
    )

    # ===========================================
    # ADMIN BOT
    # ===========================================
    admin_bot_token: str = Field(
        default="",
        description="Admin bot token from @BotFather"
    )
    admin_telegram_ids: str = Field(
        default="756877849",
        description="Comma-separated list of admin Telegram IDs"
    )

    @property
    def admin_ids(self) -> List[int]:
        """Parse admin IDs from comma-separated string."""
        if not self.admin_telegram_ids:
            return []
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",")]

    # ===========================================
    # AI PROVIDERS
    # ===========================================
    # Claude (Anthropic)
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude"
    )

    # YandexGPT (резерв)
    yandex_service_account_id: Optional[str] = Field(default=None)
    yandex_key_id: Optional[str] = Field(default=None)
    yandex_private_key_raw: Optional[str] = Field(default=None, alias="yandex_private_key")
    yandex_folder_id: Optional[str] = Field(default=None)

    @property
    def yandex_private_key(self) -> Optional[str]:
        """Parse private key, converting \\n to real newlines."""
        if not self.yandex_private_key_raw:
            return None
        # Convert literal \n to actual newlines
        return self.yandex_private_key_raw.replace("\\n", "\n")

    # ===========================================
    # RATE LIMITS
    # ===========================================
    max_comments_per_day: int = Field(default=80, ge=1, le=200)
    max_invites_per_day: int = Field(default=40, ge=0, le=100)  # 0 = отключено
    max_story_views_per_day: int = Field(default=250, ge=0, le=500)  # 0 = отключено
    max_story_reactions_per_day: int = Field(default=100, ge=0, le=200)  # 0 = отключено

    min_comment_interval_sec: int = Field(default=30, ge=10)
    max_comment_interval_sec: int = Field(default=180, ge=30)
    min_invite_interval_sec: int = Field(default=60, ge=30)
    max_invite_interval_sec: int = Field(default=300, ge=60)
    min_story_interval_sec: int = Field(default=2, ge=1)
    max_story_interval_sec: int = Field(default=10, ge=2)

    # Story viewing settings
    story_view_min_quality_score: int = Field(
        default=70,
        ge=0,
        le=100,
        description="Minimum quality_score for selecting users from target audience for story viewing"
    )

    # ===========================================
    # WORKING HOURS (Human Simulation)
    # ===========================================
    work_start_hour: int = Field(default=9, ge=0, le=23)
    work_end_hour: int = Field(default=23, ge=1, le=24)

    # ===========================================
    # WARMUP (Прогрев аккаунтов)
    # ===========================================
    warmup_days: int = Field(
        default=7,
        description="Days to warmup new accounts before full activity"
    )
    # Постепенное увеличение лимитов по дням прогрева
    # День 1-2: 3-5 комментов, День 3-4: 8-12, День 5-6: 15-20, День 7+: полные лимиты
    warmup_day1_comments: int = Field(default=3, description="Max comments on day 1-2")
    warmup_day3_comments: int = Field(default=8, description="Max comments on day 3-4")
    warmup_day5_comments: int = Field(default=15, description="Max comments on day 5-6")
    warmup_day1_invites: int = Field(default=0, description="Max invites on day 1-2 (disabled)")
    warmup_day3_invites: int = Field(default=3, description="Max invites on day 3-4")
    warmup_day5_invites: int = Field(default=8, description="Max invites on day 5-6")
    warmup_day1_stories: int = Field(default=10, description="Max story views on day 1-2")
    warmup_day3_stories: int = Field(default=30, description="Max story views on day 3-4")
    warmup_day5_stories: int = Field(default=60, description="Max story views on day 5-6")
    # Интервалы между действиями при прогреве (увеличенные)
    warmup_min_interval_sec: int = Field(default=120, description="Min interval during warmup")
    warmup_max_interval_sec: int = Field(default=600, description="Max interval during warmup")

    # ===========================================
    # NOTIFICATIONS (Telegram alerts)
    # ===========================================
    alert_bot_token: str = Field(
        default="",
        description="Telegram bot token for sending alerts"
    )
    alert_admin_id: int = Field(
        default=756877849,
        description="Telegram ID to receive alerts"
    )
    alerts_enabled: bool = Field(
        default=True,
        description="Enable/disable Telegram alerts"
    )

    # ===========================================
    # LOGGING
    # ===========================================
    log_level: str = Field(default="INFO")

    # ===========================================
    # ENCRYPTION (for session strings)
    # ===========================================
    encryption_key: str = Field(
        default="",
        description="Fernet encryption key for session strings"
    )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance (for dependency injection)."""
    return settings
