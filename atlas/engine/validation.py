"""Validation engine for MarketIntelligenceDataset."""

from __future__ import annotations

from atlas.core.contracts import ValidationEngine
from atlas.core.models import MarketIntelligenceDataset, ValidationReport
from atlas.utils.logging import get_logger

logger = get_logger("atlas.engine.validation")


class SchemaValidationEngine(ValidationEngine):
    def validate(self, dataset: MarketIntelligenceDataset) -> ValidationReport:
        report = ValidationReport()
        report.total_records = (
            len(dataset.content_supply)
            + len(dataset.search_demand)
            + len(dataset.community_voice)
        )

        # Content supply
        seen_videos: set[str] = set()
        for v in dataset.content_supply:
            if not v.video_id:
                report.add_error("Missing video_id", field="video_id")
            elif v.video_id in seen_videos:
                report.duplicates_removed += 1
            else:
                seen_videos.add(v.video_id)
            if v.view_count < 0:
                report.add_warning("Negative view_count", field="view_count", record_id=v.video_id)

        # Search demand
        for t in dataset.search_demand:
            if not t.keyword:
                report.add_error("Missing keyword", field="keyword")

        # Community voice
        seen_posts: set[str] = set()
        for d in dataset.community_voice:
            if not d.post_id:
                report.add_error("Missing post_id", field="post_id")
            elif d.post_id in seen_posts:
                report.duplicates_removed += 1
            else:
                seen_posts.add(d.post_id)

        if report.total_records == 0:
            report.add_warning("Dataset contains zero records")

        logger.info(
            "Validation complete | valid=%s issues=%d duplicates=%d",
            report.is_valid, len(report.issues), report.duplicates_removed,
        )
        return report
