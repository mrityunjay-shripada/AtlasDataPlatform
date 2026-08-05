"""
Data Collection Engine — orchestrates providers, validation, features, storage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from atlas.core.contracts import ProviderResult
from atlas.core.models import (
    CollectionJob,
    DatasetMetadata,
    DiscussionRecord,
    JobStatus,
    MarketIntelligenceDataset,
    ProgressStage,
    ProviderStatus,
    TrendRecord,
    VideoRecord,
)
from atlas.core.settings import get_settings
from atlas.engine.features import DeterministicFeatureEngineer
from atlas.engine.validation import SchemaValidationEngine
from atlas.providers.registry import ProviderRegistry, get_registry
from atlas.providers import register_default_providers
from atlas.utils.logging import get_logger

logger = get_logger("atlas.engine.collector")

ProgressCallback = Callable[[ProgressStage, str, float], None]


class DataCollectionEngine:
    """
    Orchestrates the full collection → validation → features pipeline.
    Providers remain independent; this class owns the workflow.
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.settings = get_settings()
        self.registry = registry or get_registry()
        if not self.registry.list_providers():
            register_default_providers(self.registry)
        self.validator = SchemaValidationEngine()
        self.feature_engineer = DeterministicFeatureEngineer()
        self.progress_callback = progress_callback

    def _emit(self, job: CollectionJob, stage: ProgressStage, message: str, progress: float = 0.0, **kwargs) -> None:
        job.add_event(stage, message, progress=progress, **kwargs)
        if self.progress_callback:
            try:
                self.progress_callback(stage, message, progress)
            except Exception:
                pass

    def collect(self, topic: str, enabled_providers: list[str] | None = None) -> MarketIntelligenceDataset:
        job = CollectionJob(topic=topic, status=JobStatus.RUNNING, started_at=datetime.now(timezone.utc))
        self._emit(job, ProgressStage.STARTED, f"Collection started for '{topic}'", 0.0)
        logger.info("CollectionJob %s started | topic='%s'", job.job_id, topic)

        if enabled_providers is not None:
            wanted = {n.strip().lower() for n in enabled_providers}
            for name in list(self.registry._providers.keys()):
                if name.lower() in wanted:
                    self.registry.enable(name)
                else:
                    self.registry.disable(name)

        providers = self.registry.list_providers(enabled_only=True)
        if not providers:
            logger.warning("No providers enabled for topic='%s'", topic)
        total = max(len(providers), 1)
        all_results: list[ProviderResult] = []

        for idx, provider in enumerate(providers):
            pct = (idx / total) * 0.6
            self._emit(
                job,
                ProgressStage.PROVIDER_STARTED,
                f"Collecting {provider.name}…",
                progress=pct,
                provider=provider.name,
            )
            try:
                result = provider.collect(topic, job=job)
            except Exception as exc:  # noqa: BLE001
                logger.error("Provider %s raised: %s", provider.name, exc)
                from atlas.core.models import ProviderHealth
                result = ProviderResult(
                    provider=provider.name,
                    signal=getattr(provider, "signal_type", "unknown"),
                    status=ProviderStatus.FAILED,
                    records=[],
                    errors=[str(exc)],
                    health=ProviderHealth(provider=provider.name, status=ProviderStatus.FAILED, error=str(exc)),
                )
            all_results.append(result)
            if result.health:
                job.provider_health.append(result.health)
            self._emit(
                job,
                ProgressStage.PROVIDER_COMPLETED,
                f"{provider.name} → {result.status.value} ({len(result.records)} records)",
                progress=((idx + 1) / total) * 0.6,
                provider=provider.name,
            )

        # Assemble dataset
        self._emit(job, ProgressStage.NORMALIZATION_STARTED, "Normalizing dataset…", 0.65)
        content_supply: list[VideoRecord] = []
        search_demand: list[TrendRecord] = []
        community_voice: list[DiscussionRecord] = []

        for result in all_results:
            for rec in result.records:
                if isinstance(rec, VideoRecord):
                    content_supply.append(rec)
                elif isinstance(rec, TrendRecord):
                    search_demand.append(rec)
                elif isinstance(rec, DiscussionRecord):
                    community_voice.append(rec)

        meta = DatasetMetadata(
            topic=topic,
            schema_version=self.settings.atlas_schema_version,
            platform_version=self.settings.atlas_platform_version,
            provider_versions={p.name: p.version for p in providers},
            record_counts={
                "content_supply": len(content_supply),
                "search_demand": len(search_demand),
                "community_voice": len(community_voice),
            },
        )

        dataset = MarketIntelligenceDataset(
            topic=topic,
            metadata=meta,
            content_supply=content_supply,
            search_demand=search_demand,
            community_voice=community_voice,
            collection_metadata={
                "job_id": job.job_id,
                "errors": [e for r in all_results for e in r.errors],
            },
            provider_health=job.provider_health,
        )
        self._emit(job, ProgressStage.NORMALIZATION_COMPLETED, "Normalization complete", 0.75)

        # Validation
        self._emit(job, ProgressStage.VALIDATION_STARTED, "Validating…", 0.8)
        report = self.validator.validate(dataset)
        dataset.validation_report = report
        self._emit(job, ProgressStage.VALIDATION_COMPLETED, f"Validation → valid={report.is_valid}", 0.85)

        # Features
        self._emit(job, ProgressStage.FEATURES_STARTED, "Engineering features…", 0.9)
        dataset = self.feature_engineer.engineer(dataset)
        self._emit(job, ProgressStage.FEATURES_COMPLETED, "Features complete", 0.95)

        # Finalize job
        job.finished_at = datetime.now(timezone.utc)
        job.duration_seconds = (job.finished_at - job.started_at).total_seconds() if job.started_at else 0
        any_success = any(h.status in (ProviderStatus.SUCCESS, ProviderStatus.PARTIAL) for h in job.provider_health)
        any_fail = any(h.status == ProviderStatus.FAILED for h in job.provider_health)
        if any_success and any_fail:
            job.status = JobStatus.PARTIAL_SUCCESS
        elif any_success:
            job.status = JobStatus.SUCCEEDED
        else:
            job.status = JobStatus.FAILED

        dataset.metadata.status = job.status
        dataset.metadata.duration_seconds = job.duration_seconds
        dataset.collection_metadata["job_status"] = job.status.value
        dataset.collection_metadata["duration_seconds"] = job.duration_seconds

        self._emit(job, ProgressStage.COMPLETED, f"Collection finished → {job.status.value}", 1.0)
        logger.info(
            "CollectionJob %s finished | status=%s duration=%.1fs records=%s",
            job.job_id, job.status.value, job.duration_seconds, dataset.record_counts(),
        )
        return dataset
