"""
YouTube Content Supply Provider.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from atlas.core.contracts import Provider, ProviderResult
from atlas.core.models import (
    CollectionJob,
    ProviderHealth,
    ProviderStatus,
    SignalType,
    VideoRecord,
)
from atlas.core.settings import get_settings
from atlas.utils.logging import get_logger

logger = get_logger("atlas.providers.youtube")


class YouTubeProvider(Provider):
    name = "youtube"
    signal_type = SignalType.CONTENT_SUPPLY.value
    version = "1.0.0"
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self) -> None:
        self.settings = get_settings()

    def collect(self, topic: str, job: Optional[CollectionJob] = None) -> ProviderResult:
        started = datetime.now(timezone.utc)
        health = ProviderHealth(
            provider=self.name,
            status=ProviderStatus.FAILED,
            started_at=started,
        )
        errors: list[str] = []
        records: list[VideoRecord] = []
        retries = 0

        if not self.settings.has_youtube_credentials:
            msg = "YouTube API key not configured"
            logger.warning(msg)
            health.status = ProviderStatus.SKIPPED
            health.error = msg
            health.finished_at = datetime.now(timezone.utc)
            return ProviderResult(
                provider=self.name,
                signal=self.signal_type,
                status=ProviderStatus.SKIPPED,
                records=[],
                errors=[msg],
                health=health,
            )

        logger.info("YouTube collection started | topic='%s'", topic)
        try:
            channel_ids = self._search_channels(topic, self.settings.max_youtube_channels)
            for cid in channel_ids:
                try:
                    videos = self._fetch_channel_videos(cid, self.settings.max_videos_per_channel)
                    records.extend(videos)
                except Exception as exc:  # noqa: BLE001
                    retries += 1
                    errors.append(f"channel {cid}: {exc}")
                    logger.warning("Channel %s failed: %s", cid, exc)

            status = ProviderStatus.SUCCESS if records else ProviderStatus.PARTIAL
            if errors and records:
                status = ProviderStatus.PARTIAL
            if not records and errors:
                status = ProviderStatus.FAILED

            health.status = status
            health.records_collected = len(records)
            health.retries = retries
            health.finished_at = datetime.now(timezone.utc)
            health.duration_seconds = (health.finished_at - started).total_seconds()
            if errors:
                health.error = "; ".join(errors[:3])

            logger.info(
                "YouTube finished | records=%d status=%s duration=%.1fs",
                len(records), status.value, health.duration_seconds,
            )
            return ProviderResult(
                provider=self.name,
                signal=self.signal_type,
                status=status,
                records=records,
                metadata={"channels_searched": len(channel_ids)},
                errors=errors,
                health=health,
            )
        except Exception as exc:  # noqa: BLE001
            health.status = ProviderStatus.FAILED
            health.error = str(exc)
            health.finished_at = datetime.now(timezone.utc)
            health.duration_seconds = (health.finished_at - started).total_seconds()
            logger.error("YouTube provider failed: %s", exc)
            return ProviderResult(
                provider=self.name,
                signal=self.signal_type,
                status=ProviderStatus.FAILED,
                records=[],
                errors=[str(exc)],
                health=health,
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
           retry=retry_if_exception_type((requests.RequestException,)))
    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "key": self.settings.youtube_api_key}
        resp = requests.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=30)
        if resp.status_code == 403:
            raise RuntimeError(f"YouTube quota/auth error: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    def _search_channels(self, query: str, limit: int) -> list[str]:
        data = self._get("search", {
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": min(limit, 50),
        })
        ids = []
        for item in data.get("items", []):
            cid = item.get("snippet", {}).get("channelId") or item.get("id", {}).get("channelId")
            if cid:
                ids.append(cid)
        return ids[:limit]

    def _fetch_channel_videos(self, channel_id: str, limit: int) -> list[VideoRecord]:
        # Get uploads playlist
        ch = self._get("channels", {"part": "contentDetails,snippet", "id": channel_id})
        items = ch.get("items", [])
        if not items:
            return []
        uploads = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        channel_title = items[0].get("snippet", {}).get("title", "")
        if not uploads:
            return []

        # Playlist items
        pl = self._get("playlistItems", {
            "part": "contentDetails",
            "playlistId": uploads,
            "maxResults": min(limit, 50),
        })
        video_ids = [i["contentDetails"]["videoId"] for i in pl.get("items", []) if "contentDetails" in i]
        if not video_ids:
            return []

        # Video details
        vids = self._get("videos", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids[:50]),
        })
        records: list[VideoRecord] = []
        for item in vids.get("items", []):
            records.append(self._to_record(item, channel_title))
        return records

    def _to_record(self, item: dict[str, Any], channel_title: str) -> VideoRecord:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})
        published = snippet.get("publishedAt")
        published_dt = None
        if published:
            try:
                published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except Exception:
                pass
        duration_iso = content.get("duration", "PT0S")
        duration_sec = _parse_duration(duration_iso)
        return VideoRecord(
            video_id=item["id"],
            channel_id=snippet.get("channelId", ""),
            channel_title=channel_title or snippet.get("channelTitle", ""),
            title=snippet.get("title", ""),
            description=(snippet.get("description") or "")[:3000],
            published_at=published_dt,
            view_count=int(stats.get("viewCount", 0) or 0),
            like_count=int(stats.get("likeCount", 0) or 0),
            comment_count=int(stats.get("commentCount", 0) or 0),
            duration_seconds=duration_sec,
            tags=snippet.get("tags") or [],
            thumbnail_url=(snippet.get("thumbnails", {}).get("high") or {}).get("url"),
            category_id=snippet.get("categoryId"),
        )


def _parse_duration(iso: str) -> int:
    import re
    if not iso or not iso.startswith("PT"):
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s
