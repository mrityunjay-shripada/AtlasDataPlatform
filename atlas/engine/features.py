"""
Deterministic feature engineering for AtlasDataPlatform.
No AI. Pure quantitative metrics only.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from atlas.core.contracts import FeatureEngineer
from atlas.core.models import DiscussionRecord, MarketIntelligenceDataset, TrendRecord, VideoRecord
from atlas.utils.logging import get_logger

logger = get_logger("atlas.engine.features")


class DeterministicFeatureEngineer(FeatureEngineer):
    def engineer(self, dataset: MarketIntelligenceDataset) -> MarketIntelligenceDataset:
        logger.info("Feature engineering started")
        now = datetime.now(timezone.utc)

        for v in dataset.content_supply:
            self._video_features(v, now)
        for t in dataset.search_demand:
            pass  # trend features computed at aggregate level
        for d in dataset.community_voice:
            self._discussion_features(d, now)

        dataset.derived_metrics = self._aggregate_metrics(dataset)
        logger.info("Feature engineering completed | metrics=%d", len(dataset.derived_metrics))
        return dataset

    def _video_features(self, v: VideoRecord, now: datetime) -> None:
        age_days = 1.0
        if v.published_at:
            pub = v.published_at if v.published_at.tzinfo else v.published_at.replace(tzinfo=timezone.utc)
            age_days = max((now - pub).total_seconds() / 86400.0, 0.01)
        v.views_per_day = round(v.view_count / age_days, 2)
        v.engagement_rate = round(
            (v.like_count + v.comment_count) / max(v.view_count, 1), 6
        )
        v.like_rate = round(v.like_count / max(v.view_count, 1), 6)
        v.comment_rate = round(v.comment_count / max(v.view_count, 1), 6)

    def _discussion_features(self, d: DiscussionRecord, now: datetime) -> None:
        age_hours = 24.0
        if d.created_utc:
            created = d.created_utc if d.created_utc.tzinfo else d.created_utc.replace(tzinfo=timezone.utc)
            age_hours = max((now - created).total_seconds() / 3600.0, 0.01)
        d.post_age_hours = round(age_hours, 2)
        d.comments_per_hour = round(d.num_comments / age_hours, 3)
        d.score_per_hour = round(d.score / age_hours, 3)
        d.engagement_score = round((d.score * d.upvote_ratio) + (d.num_comments * 2.0), 2)
        d.popularity_score = round(math.log1p(d.score) * 2 + math.log1p(d.num_comments) * 3, 2)
        post_len = max(len(d.body) + len(d.title), 1)
        d.discussion_density = round((d.num_comments / post_len) * 100, 3)
        d.average_comment_length = 0.0  # would need comment bodies

    def _aggregate_metrics(self, ds: MarketIntelligenceDataset) -> dict[str, float]:
        metrics: dict[str, float] = {}
        videos = ds.content_supply
        trends = ds.search_demand
        discussions = ds.community_voice

        if videos:
            metrics["avg_views_per_day"] = round(float(np.mean([v.views_per_day for v in videos])), 2)
            metrics["avg_engagement_rate"] = round(float(np.mean([v.engagement_rate for v in videos])), 6)
            metrics["total_views"] = float(sum(v.view_count for v in videos))
            metrics["creator_activity"] = float(len({v.channel_id for v in videos}))
            metrics["upload_frequency_proxy"] = float(len(videos))

        interest_series = [t.interest for t in trends if t.date and t.interest > 0]
        if len(interest_series) >= 2:
            arr = np.array(interest_series, dtype=float)
            metrics["avg_interest"] = round(float(np.mean(arr)), 2)
            metrics["peak_interest"] = float(np.max(arr))
            metrics["trend_velocity"] = round(float(np.polyfit(np.arange(len(arr)), arr, 1)[0]), 4)
            metrics["search_momentum"] = round(float(arr[-1] - arr[0]), 2)
            metrics["growth_rate"] = round(float((arr[-1] - arr[0]) / max(arr[0], 1)), 4)

        if discussions:
            metrics["avg_discussion_velocity"] = round(
                float(np.mean([d.comments_per_hour for d in discussions])), 3
            )
            metrics["avg_popularity_score"] = round(
                float(np.mean([d.popularity_score for d in discussions])), 2
            )
            metrics["community_activity"] = float(len({d.subreddit for d in discussions}))
            metrics["total_discussion_score"] = float(sum(d.score for d in discussions))

        metrics["content_supply_count"] = float(len(videos))
        metrics["search_demand_count"] = float(len(trends))
        metrics["community_voice_count"] = float(len(discussions))
        return metrics
