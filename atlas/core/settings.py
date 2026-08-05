"""
Centralized configuration for AtlasDataPlatform.

All configuration MUST flow through this Settings class.
Never call os.getenv() or st.secrets directly elsewhere in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = atlas/ (parent of the atlas package)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Immutable application settings loaded from environment / .env / Streamlit secrets.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Platform
    # ------------------------------------------------------------------
    atlas_env: str = Field(default="development", description="development | staging | production")
    atlas_log_level: str = Field(default="INFO")
    atlas_cache_ttl_hours: int = Field(default=24, ge=1, le=168)
    atlas_schema_version: str = Field(default="1.0.0")
    atlas_platform_version: str = Field(default="0.1.0")

    # ------------------------------------------------------------------
    # Paths (local development)
    # ------------------------------------------------------------------
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    datasets_dir: Path = Field(default=PROJECT_ROOT / "data" / "datasets")
    raw_dir: Path = Field(default=PROJECT_ROOT / "data" / "raw")
    processed_dir: Path = Field(default=PROJECT_ROOT / "data" / "processed")

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------
    youtube_api_key: str = Field(default="")
    max_youtube_channels: int = Field(default=10, ge=1, le=50)
    max_videos_per_channel: int = Field(default=15, ge=1, le=50)
    max_comments_per_video: int = Field(default=30, ge=0, le=100)

    # ------------------------------------------------------------------
    # Reddit
    # ------------------------------------------------------------------
    reddit_client_id: str = Field(default="")
    reddit_client_secret: str = Field(default="")
    reddit_user_agent: str = Field(default="AtlasDataPlatform/1.0.0")
    max_reddit_subreddits: int = Field(default=8, ge=1, le=30)
    max_posts_per_subreddit: int = Field(default=50, ge=1, le=100)
    max_comments_per_post: int = Field(default=40, ge=0, le=100)

    # ------------------------------------------------------------------
    # Google Trends
    # ------------------------------------------------------------------
    google_trends_geo: str = Field(default="")
    google_trends_language: str = Field(default="en-US")
    google_trends_timezone: int = Field(default=330)

    # ------------------------------------------------------------------
    # Supabase
    # ------------------------------------------------------------------
    supabase_url: str = Field(default="")
    supabase_key: str = Field(default="")
    supabase_bucket: str = Field(default="atlasdataplatform")

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.atlas_env.lower() == "production"

    @property
    def has_youtube_credentials(self) -> bool:
        return bool(self.youtube_api_key.strip())

    @property
    def has_reddit_credentials(self) -> bool:
        return bool(self.reddit_client_id.strip() and self.reddit_client_secret.strip())

    @property
    def has_supabase_credentials(self) -> bool:
        return bool(self.supabase_url.strip() and self.supabase_key.strip())

    def ensure_directories(self) -> None:
        """Create local data directories if they do not exist."""
        for d in (self.data_dir, self.datasets_dir, self.raw_dir, self.processed_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    In Streamlit, secrets can be injected by overriding environment variables
    before the first call, or by a thin adapter that maps st.secrets → env.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings
