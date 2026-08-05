"""
DuckDB analytical engine — queries persisted datasets only.
"""

from __future__ import annotations

from typing import Any, Optional

from atlas.core.contracts import AnalyticsEngine
from atlas.core.models import MarketIntelligenceDataset
from atlas.utils.logging import get_logger

logger = get_logger("atlas.analytics")


class DuckDBAnalyticsEngine(AnalyticsEngine):
    def __init__(self) -> None:
        self._conn = None

    def _connection(self):
        if self._conn is None:
            import duckdb
            self._conn = duckdb.connect(database=":memory:")
        return self._conn

    def load_dataset(self, path: str) -> Any:
        conn = self._connection()
        if path.endswith(".parquet"):
            return conn.execute(f"SELECT * FROM read_parquet('{path}')").fetchdf()
        if path.endswith(".json"):
            return conn.execute(f"SELECT * FROM read_json_auto('{path}')").fetchdf()
        raise ValueError(f"Unsupported path: {path}")

    def query(self, sql: str) -> Any:
        return self._connection().execute(sql).fetchdf()

    def summary_stats(self, dataset: MarketIntelligenceDataset) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "topic": dataset.topic,
            "content_supply_count": len(dataset.content_supply),
            "search_demand_count": len(dataset.search_demand),
            "community_voice_count": len(dataset.community_voice),
            "derived_metrics": dataset.derived_metrics,
            "provider_health": [h.model_dump(mode="json") for h in dataset.provider_health],
        }
        if dataset.content_supply:
            views = [v.view_count for v in dataset.content_supply]
            stats["top_videos"] = sorted(
                [
                    {"title": v.title, "views": v.view_count, "channel": v.channel_title, "engagement_rate": v.engagement_rate}
                    for v in dataset.content_supply
                ],
                key=lambda x: x["views"],
                reverse=True,
            )[:10]
            stats["total_views"] = sum(views)
            stats["avg_views"] = sum(views) / len(views)
        if dataset.community_voice:
            stats["top_communities"] = sorted(
                [
                    {"subreddit": d.subreddit, "title": d.title, "score": d.score, "comments": d.num_comments}
                    for d in dataset.community_voice
                ],
                key=lambda x: x["score"],
                reverse=True,
            )[:10]
        if dataset.search_demand:
            rising = [t for t in dataset.search_demand if t.related_query_type == "rising"]
            stats["rising_queries"] = [
                {"query": t.related_query, "interest": t.interest}
                for t in rising[:10]
            ]
            regions = [t for t in dataset.search_demand if t.region]
            stats["top_regions"] = sorted(
                [{"region": t.region, "interest": t.region_interest or 0} for t in regions],
                key=lambda x: x["interest"],
                reverse=True,
            )[:10]
        return stats
