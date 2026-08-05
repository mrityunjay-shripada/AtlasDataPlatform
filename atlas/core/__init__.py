"""Core domain primitives, settings, contracts, and shared models."""

from atlas.core.settings import Settings, get_settings
from atlas.core.models import (
    CollectionJob,
    DatasetMetadata,
    DiscussionRecord,
    JobStatus,
    MarketIntelligenceDataset,
    MarketSignal,
    ProgressEvent,
    ProgressStage,
    ProviderHealth,
    ProviderStatus,
    SignalType,
    TrendRecord,
    ValidationIssue,
    ValidationReport,
    VideoRecord,
)
from atlas.core.contracts import (
    AnalyticsEngine,
    FeatureEngineer,
    Provider,
    ProviderResult,
    Storage,
    ValidationEngine,
)
from atlas.core.secrets import apply_streamlit_secrets

__all__ = [
    "Settings",
    "get_settings",
    "apply_streamlit_secrets",
    # Models
    "CollectionJob",
    "DatasetMetadata",
    "DiscussionRecord",
    "JobStatus",
    "MarketIntelligenceDataset",
    "MarketSignal",
    "ProgressEvent",
    "ProgressStage",
    "ProviderHealth",
    "ProviderStatus",
    "SignalType",
    "TrendRecord",
    "ValidationIssue",
    "ValidationReport",
    "VideoRecord",
    # Contracts
    "AnalyticsEngine",
    "FeatureEngineer",
    "Provider",
    "ProviderResult",
    "Storage",
    "ValidationEngine",
]
