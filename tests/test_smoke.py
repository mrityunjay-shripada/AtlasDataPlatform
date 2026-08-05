"""Smoke tests for AtlasDataPlatform core components."""

from __future__ import annotations

from atlas.core.models import (
    CollectionJob,
    DiscussionRecord,
    JobStatus,
    MarketIntelligenceDataset,
    DatasetMetadata,
    ProviderStatus,
    TrendRecord,
    VideoRecord,
)
from atlas.engine.features import DeterministicFeatureEngineer
from atlas.engine.validation import SchemaValidationEngine
from atlas.providers.registry import ProviderRegistry
from atlas.providers.youtube import YouTubeProvider
from atlas.providers.trends import GoogleTrendsProvider
from atlas.providers.reddit import RedditProvider
from atlas.storage.manager import StorageManager


def test_models_instantiate():
    v = VideoRecord(video_id="x", channel_id="c", title="t")
    assert v.video_id == "x"
    t = TrendRecord(keyword="ai")
    assert t.keyword == "ai"
    d = DiscussionRecord(post_id="p", subreddit="s", title="t")
    assert d.post_id == "p"
    job = CollectionJob(topic="test")
    assert job.status == JobStatus.PENDING


def test_feature_engineering():
    ds = MarketIntelligenceDataset(
        topic="test",
        metadata=DatasetMetadata(topic="test"),
        content_supply=[
            VideoRecord(video_id="1", channel_id="c", title="t", view_count=1000, like_count=50, comment_count=10)
        ],
        community_voice=[
            DiscussionRecord(post_id="p1", subreddit="ml", title="hello", score=100, num_comments=20)
        ],
    )
    eng = DeterministicFeatureEngineer()
    result = eng.engineer(ds)
    assert "avg_views_per_day" in result.derived_metrics or "content_supply_count" in result.derived_metrics
    assert result.content_supply[0].engagement_rate >= 0


def test_validation():
    ds = MarketIntelligenceDataset(
        topic="test",
        metadata=DatasetMetadata(topic="test"),
        content_supply=[VideoRecord(video_id="1", channel_id="c", title="t")],
    )
    report = SchemaValidationEngine().validate(ds)
    assert report.total_records == 1


def test_registry():
    reg = ProviderRegistry()
    reg.register(YouTubeProvider())
    reg.register(GoogleTrendsProvider())
    reg.register(RedditProvider())
    names = [p.name for p in reg.list_providers()]
    assert "youtube" in names
    assert "google_trends" in names
    assert "reddit" in names


def test_storage_roundtrip(tmp_path, monkeypatch):
    from atlas.core import settings as settings_mod
    # Point datasets_dir to temp
    s = settings_mod.get_settings()
    monkeypatch.setattr(s, "datasets_dir", tmp_path)
    ds = MarketIntelligenceDataset(
        topic="Unit Test Topic",
        metadata=DatasetMetadata(topic="Unit Test Topic"),
        content_supply=[VideoRecord(video_id="vid1", channel_id="ch", title="Hello")],
    )
    mgr = StorageManager()
    loc = mgr.upload(ds, "Unit Test Topic")
    assert mgr.exists("Unit Test Topic")
    loaded = mgr.download("Unit Test Topic")
    assert loaded is not None
    assert loaded.topic == "Unit Test Topic"
    assert len(loaded.content_supply) == 1
