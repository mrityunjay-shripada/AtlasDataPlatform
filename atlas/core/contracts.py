"""
Abstract contracts for AtlasDataPlatform.

All concrete implementations must satisfy these interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from atlas.core.models import (
    CollectionJob,
    MarketIntelligenceDataset,
    ProgressEvent,
    ProviderHealth,
    ProviderStatus,
    ValidationReport,
)


class Provider(ABC):
    """Base contract for every data provider."""

    name: str
    signal_type: str
    version: str = "1.0.0"

    @abstractmethod
    def collect(self, topic: str, job: Optional[CollectionJob] = None) -> "ProviderResult":
        """
        Collect data for the given topic.

        Must never raise third-party exceptions across the boundary.
        Must return a ProviderResult even on total failure.
        """
        ...

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status=ProviderStatus.SKIPPED)


class ProviderResult:
    """Typed result returned by every provider."""

    def __init__(
        self,
        provider: str,
        signal: str,
        status: ProviderStatus,
        records: list[Any],
        derived_metrics: Optional[dict[str, float]] = None,
        metadata: Optional[dict[str, Any]] = None,
        errors: Optional[list[str]] = None,
        health: Optional[ProviderHealth] = None,
    ) -> None:
        self.provider = provider
        self.signal = signal
        self.status = status
        self.records = records or []
        self.derived_metrics = derived_metrics or {}
        self.metadata = metadata or {}
        self.errors = errors or []
        self.health = health


class Storage(ABC):
    """Persistence contract."""

    @abstractmethod
    def upload(self, dataset: MarketIntelligenceDataset, topic: str) -> str:
        """Persist dataset and return storage location / path."""
        ...

    @abstractmethod
    def download(self, topic: str, version: Optional[str] = None) -> Optional[MarketIntelligenceDataset]:
        """Load a dataset by topic (latest if version is None)."""
        ...

    @abstractmethod
    def exists(self, topic: str) -> bool:
        ...

    @abstractmethod
    def latest_version(self, topic: str) -> Optional[str]:
        ...

    @abstractmethod
    def list_versions(self, topic: str) -> list[str]:
        ...


class AnalyticsEngine(ABC):
    """Analytical query contract. Must never own the data."""

    @abstractmethod
    def load_dataset(self, path: str) -> Any:
        ...

    @abstractmethod
    def query(self, sql: str) -> Any:
        ...

    @abstractmethod
    def summary_stats(self, dataset: MarketIntelligenceDataset) -> dict[str, Any]:
        ...


class FeatureEngineer(ABC):
    """Deterministic feature engineering contract."""

    @abstractmethod
    def engineer(self, dataset: MarketIntelligenceDataset) -> MarketIntelligenceDataset:
        ...


class ValidationEngine(ABC):
    """Data quality contract."""

    @abstractmethod
    def validate(self, dataset: MarketIntelligenceDataset) -> ValidationReport:
        ...
