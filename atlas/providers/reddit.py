"""
Reddit Community Voice Provider.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from atlas.core.contracts import Provider, ProviderResult
from atlas.core.models import (
    CollectionJob,
    DiscussionRecord,
    ProviderHealth,
    ProviderStatus,
    SignalType,
)
from atlas.core.settings import get_settings
from atlas.utils.logging import get_logger

logger = get_logger("atlas.providers.reddit")


class RedditProvider(Provider):
    name = "reddit"
    signal_type = SignalType.COMMUNITY_VOICE.value
    version = "1.0.0"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._reddit = None

    def _client(self):
        if self._reddit is None:
            import praw
            self._reddit = praw.Reddit(
                client_id=self.settings.reddit_client_id,
                client_secret=self.settings.reddit_client_secret,
                user_agent=self.settings.reddit_user_agent,
                check_for_async=False,
            )
            self._reddit.read_only = True
        return self._reddit

    def collect(self, topic: str, job: Optional[CollectionJob] = None) -> ProviderResult:
        started = datetime.now(timezone.utc)
        health = ProviderHealth(provider=self.name, status=ProviderStatus.FAILED, started_at=started)
        errors: list[str] = []
        records: list[DiscussionRecord] = []

        if not self.settings.has_reddit_credentials:
            msg = "Reddit credentials not configured"
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

        logger.info("Reddit collection started | topic='%s'", topic)
        try:
            reddit = self._client()
            subreddits = []
            try:
                for sub in reddit.subreddits.search(topic, limit=self.settings.max_reddit_subreddits):
                    subreddits.append(sub)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"subreddit search: {exc}")
                logger.warning("Subreddit search failed: %s", exc)

            for sub in subreddits:
                try:
                    posts = list(sub.hot(limit=self.settings.max_posts_per_subreddit // max(len(subreddits), 1)))
                    for submission in posts:
                        try:
                            author = str(submission.author) if submission.author else "[deleted]"
                        except Exception:
                            author = "[deleted]"
                        created = None
                        if getattr(submission, "created_utc", None):
                            created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                        records.append(DiscussionRecord(
                            post_id=submission.id,
                            subreddit=str(submission.subreddit),
                            title=submission.title or "",
                            body=(getattr(submission, "selftext", "") or "")[:5000],
                            score=int(submission.score or 0),
                            upvote_ratio=float(getattr(submission, "upvote_ratio", 0.0) or 0.0),
                            num_comments=int(submission.num_comments or 0),
                            created_utc=created,
                            author=author,
                            flair=getattr(submission, "link_flair_text", None),
                            permalink=f"https://reddit.com{submission.permalink}" if submission.permalink else "",
                        ))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"r/{sub.display_name}: {exc}")
                    logger.warning("Failed collecting from r/%s: %s", sub.display_name, exc)

            status = ProviderStatus.SUCCESS if records and not errors else (
                ProviderStatus.PARTIAL if records else ProviderStatus.FAILED
            )
            health.status = status
            health.records_collected = len(records)
            health.finished_at = datetime.now(timezone.utc)
            health.duration_seconds = (health.finished_at - started).total_seconds()
            if errors:
                health.error = "; ".join(errors[:3])

            logger.info(
                "Reddit finished | records=%d status=%s duration=%.1fs",
                len(records), status.value, health.duration_seconds,
            )
            return ProviderResult(
                provider=self.name,
                signal=self.signal_type,
                status=status,
                records=records,
                metadata={"subreddits": len(subreddits)},
                errors=errors,
                health=health,
            )
        except Exception as exc:  # noqa: BLE001
            health.status = ProviderStatus.FAILED
            health.error = str(exc)
            health.finished_at = datetime.now(timezone.utc)
            health.duration_seconds = (health.finished_at - started).total_seconds()
            logger.error("Reddit provider failed: %s", exc)
            return ProviderResult(
                provider=self.name,
                signal=self.signal_type,
                status=ProviderStatus.FAILED,
                records=[],
                errors=[str(exc)],
                health=health,
            )
