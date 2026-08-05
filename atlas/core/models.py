"""
Canonical domain models for AtlasDataPlatform.

These are the ONLY shapes that cross module boundaries.
Provider-specific objects must never leave the provider layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SignalType(str, Enum):
    CONTENT_SUPPLY = "content_supply"
    SEARCH_DEMAND = "search_demand"
    COMMUNITY_VOICE = "community_voice"


class ProgressStage(str, Enum):
    STARTED = "started"
    PROVIDER_STARTED = "provider_started"
    PROVIDER_COMPLETED = "provider_completed"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    NORMALIZATION_STARTED = "normalization_started"
    NORMALIZATION_COMPLETED = "normalization_completed"
    FEATURES_STARTED = "features_started"
    FEATURES_COMPLETED = "features_completed"
    STORAGE_STARTED = "storage_started"
    STORAGE_COMPLETED = "storage_completed"
    DASHBOARD_READY = "dashboard_ready"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Progress & Health
# ---------------------------------------------------------------------------

class ProgressEvent(BaseModel):
    stage: ProgressStage
    message: str
    provider: Optional[str] = None
    progress: float = Field(ge=0.0, le=1.0, default=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider: str
    status: ProviderStatus
    records_collected: int = 0
    duration_seconds: float = 0.0
    retries: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ValidationIssue(BaseModel):
    severity: str  # "error" | "warning"
    field: Optional[str] = None
    message: str
    record_id: Optional[str] = None


class ValidationReport(BaseModel):
    is_valid: bool = True
    total_records: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    duplicates_removed: int = 0
    nulls_filled: int = 0

    def add_error(self, message: str, field: Optional[str] = None, record_id: Optional[str] = None) -> None:
        self.issues.append(ValidationIssue(severity="error", field=field, message=message, record_id=record_id))
        self.is_valid = False

    def add_warning(self, message: str, field: Optional[str] = None, record_id: Optional[str] = None) -> None:
        self.issues.append(ValidationIssue(severity="warning", field=field, message=message, record_id=record_id))


# ---------------------------------------------------------------------------
# Domain Records (provider outputs mapped into these)
# ---------------------------------------------------------------------------

class VideoRecord(BaseModel):
    """Normalized content-supply record (primarily from YouTube)."""
    video_id: str
    channel_id: str
    channel_title: str = ""
    title: str
    description: str = ""
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_seconds: int = 0
    tags: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    category_id: Optional[str] = None
    # Derived (filled by feature engineering)
    views_per_day: float = 0.0
    engagement_rate: float = 0.0
    like_rate: float = 0.0
    comment_rate: float = 0.0


class TrendRecord(BaseModel):
    """Normalized search-demand record (primarily from Google Trends)."""
    keyword: str
    date: Optional[str] = None
    interest: int = 0
    timeframe: str = ""
    related_query: Optional[str] = None
    related_query_type: Optional[str] = None  # top | rising
    related_topic: Optional[str] = None
    related_topic_type: Optional[str] = None
    region: Optional[str] = None
    region_interest: Optional[int] = None
    # Derived
    trend_velocity: float = 0.0
    growth_rate: float = 0.0
    momentum: float = 0.0
    seasonality_score: float = 0.0


class DiscussionRecord(BaseModel):
    """Normalized community-voice record (primarily from Reddit)."""
    post_id: str
    subreddit: str
    title: str
    body: str = ""
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: Optional[datetime] = None
    author: Optional[str] = None
    flair: Optional[str] = None
    permalink: str = ""
    # Derived
    post_age_hours: float = 0.0
    comments_per_hour: float = 0.0
    score_per_hour: float = 0.0
    engagement_score: float = 0.0
    popularity_score: float = 0.0
    discussion_density: float = 0.0
    average_comment_length: float = 0.0


class MarketSignal(BaseModel):
    """Generic signal wrapper used for cross-provider aggregation."""
    signal_type: SignalType
    source_provider: str
    record_id: str
    title: str = ""
    score: float = 0.0
    timestamp: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dataset & Job
# ---------------------------------------------------------------------------

class DatasetMetadata(BaseModel):
    dataset_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    schema_version: str = "1.0.0"
    platform_version: str = "0.1.0"
    provider_versions: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: float = 0.0
    storage_location: Optional[str] = None
    record_counts: dict[str, int] = Field(default_factory=dict)
    checksum: Optional[str] = None
    status: JobStatus = JobStatus.SUCCEEDED


class MarketIntelligenceDataset(BaseModel):
    """
    The single canonical artifact consumed by every downstream module.
    """
    topic: str
    metadata: DatasetMetadata
    content_supply: list[VideoRecord] = Field(default_factory=list)
    search_demand: list[TrendRecord] = Field(default_factory=list)
    community_voice: list[DiscussionRecord] = Field(default_factory=list)
    derived_metrics: dict[str, float] = Field(default_factory=dict)
    collection_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_health: list[ProviderHealth] = Field(default_factory=list)
    validation_report: Optional[ValidationReport] = None

    def record_counts(self) -> dict[str, int]:
        return {
            "content_supply": len(self.content_supply),
            "search_demand": len(self.search_demand),
            "community_voice": len(self.community_voice),
        }


class CollectionJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    topic: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    provider_health: list[ProviderHealth] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retries: int = 0
    dataset_id: Optional[str] = None
    progress_events: list[ProgressEvent] = Field(default_factory=list)
    cache_hit: bool = False

    def add_event(self, stage: ProgressStage, message: str, **kwargs: Any) -> ProgressEvent:
        event = ProgressEvent(stage=stage, message=message, **kwargs)
        self.progress_events.append(event)
        return event
