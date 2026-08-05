"""
Google Trends Search Demand Provider.

Includes urllib3 v2 compatibility patch for pytrends:
Retry.__init__() got an unexpected keyword argument 'method_whitelist'
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from atlas.core.contracts import Provider, ProviderResult
from atlas.core.models import (
    CollectionJob,
    ProviderHealth,
    ProviderStatus,
    SignalType,
    TrendRecord,
)
from atlas.core.settings import get_settings
from atlas.utils.logging import get_logger

logger = get_logger("atlas.providers.trends")


def _patch_urllib3_method_whitelist() -> None:
    """
    Solution 2: pytrends may pass method_whitelist to urllib3.util.retry.Retry.
    urllib3>=2 renamed that argument to allowed_methods.
    Patch once before importing TrendReq.
    """
    import urllib3.util.retry

    if getattr(urllib3.util.retry.Retry, "_atlas_method_whitelist_patched", False):
        return

    _original_retry_init = urllib3.util.retry.Retry.__init__

    def _patched_retry_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "method_whitelist" in kwargs:
            if "allowed_methods" not in kwargs:
                kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
            else:
                kwargs.pop("method_whitelist", None)
        return _original_retry_init(self, *args, **kwargs)

    urllib3.util.retry.Retry.__init__ = _patched_retry_init  # type: ignore[method-assign]
    urllib3.util.retry.Retry._atlas_method_whitelist_patched = True  # type: ignore[attr-defined]
    logger.info("Applied urllib3 Retry method_whitelist compatibility patch")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip().replace(",", "")
        if s.endswith("%"):
            s = s[:-1]
        return int(float(s))
    except Exception:
        return default


class GoogleTrendsProvider(Provider):
    name = "google_trends"
    signal_type = SignalType.SEARCH_DEMAND.value
    version = "1.2.0"

    def __init__(self) -> None:
        self.settings = get_settings()

    def collect(self, topic: str, job: Optional[CollectionJob] = None) -> ProviderResult:
        started = datetime.now(timezone.utc)
        health = ProviderHealth(provider=self.name, status=ProviderStatus.FAILED, started_at=started)
        errors: list[str] = []
        records: list[TrendRecord] = []

        logger.info("Google Trends collection started | topic='%s'", topic)

        try:
            pytrends = self._create_client()
        except Exception as exc:  # noqa: BLE001
            return self._fail(health, started, f"TrendReq init failed: {exc}")

        timeframe = "today 12-m"
        try:
            self._build_payload(pytrends, topic, timeframe)
        except Exception as exc:  # noqa: BLE001
            try:
                logger.warning("Primary payload failed (%s); retrying with 'today 3-m'", exc)
                timeframe = "today 3-m"
                self._build_payload(pytrends, topic, timeframe)
            except Exception as exc2:  # noqa: BLE001
                return self._fail(health, started, f"build_payload failed: {exc2}")

        # Interest over time
        try:
            iot = pytrends.interest_over_time()
            if iot is not None and not getattr(iot, "empty", True):
                if "isPartial" in iot.columns:
                    iot = iot.drop(columns=["isPartial"])
                cols = list(iot.columns)
                value_col = topic if topic in cols else (cols[0] if cols else None)
                if value_col:
                    for ts, row in iot.iterrows():
                        date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                        records.append(
                            TrendRecord(
                                keyword=topic,
                                date=date_str,
                                interest=_safe_int(row.get(value_col, 0)),
                                timeframe=timeframe,
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"interest_over_time: {type(exc).__name__}: {exc}")
            logger.warning("interest_over_time failed: %s", exc)

        time.sleep(1.0)

        # Related queries
        try:
            related = pytrends.related_queries() or {}
            block = related.get(topic) or {}
            for qtype in ("top", "rising"):
                df = block.get(qtype)
                if df is None or getattr(df, "empty", True):
                    continue
                for _, row in df.head(15).iterrows():
                    records.append(
                        TrendRecord(
                            keyword=topic,
                            related_query=str(row.get("query", "") or ""),
                            related_query_type=qtype,
                            interest=_safe_int(row.get("value", 0)),
                            timeframe=timeframe,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"related_queries: {type(exc).__name__}: {exc}")
            logger.warning("related_queries failed: %s", exc)

        time.sleep(1.0)

        # Related topics
        try:
            topics = pytrends.related_topics() or {}
            block = topics.get(topic) or {}
            for ttype in ("top", "rising"):
                df = block.get(ttype)
                if df is None or getattr(df, "empty", True):
                    continue
                for _, row in df.head(10).iterrows():
                    title = str(row.get("topic_title") or row.get("title") or "")
                    records.append(
                        TrendRecord(
                            keyword=topic,
                            related_topic=title,
                            related_topic_type=ttype,
                            interest=_safe_int(row.get("value", 0)),
                            timeframe=timeframe,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"related_topics: {type(exc).__name__}: {exc}")
            logger.warning("related_topics failed: %s", exc)

        time.sleep(1.0)

        # Regional interest
        try:
            region_df = pytrends.interest_by_region(
                resolution="COUNTRY",
                inc_low_vol=True,
                inc_geo_code=False,
            )
            if region_df is not None and not getattr(region_df, "empty", True):
                cols = list(region_df.columns)
                value_col = topic if topic in cols else (cols[0] if cols else None)
                if value_col:
                    for region_name, row in region_df.iterrows():
                        val = _safe_int(row.get(value_col, 0))
                        if val > 0:
                            records.append(
                                TrendRecord(
                                    keyword=topic,
                                    region=str(region_name),
                                    region_interest=val,
                                    timeframe=timeframe,
                                )
                            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"interest_by_region: {type(exc).__name__}: {exc}")
            logger.warning("interest_by_region failed: %s", exc)

        if records and not errors:
            status = ProviderStatus.SUCCESS
        elif records:
            status = ProviderStatus.PARTIAL
        else:
            status = ProviderStatus.FAILED
            if not errors:
                errors.append("No Google Trends records returned")

        health.status = status
        health.records_collected = len(records)
        health.finished_at = datetime.now(timezone.utc)
        health.duration_seconds = (health.finished_at - started).total_seconds()
        if errors:
            health.error = "; ".join(errors[:3])

        logger.info(
            "Google Trends finished | records=%d status=%s duration=%.1fs",
            len(records),
            status.value,
            health.duration_seconds,
        )
        return ProviderResult(
            provider=self.name,
            signal=self.signal_type,
            status=status,
            records=records,
            errors=errors,
            health=health,
        )

    def _create_client(self) -> Any:
        _patch_urllib3_method_whitelist()
        from pytrends.request import TrendReq

        return TrendReq(
            hl=self.settings.google_trends_language or "en-US",
            tz=int(self.settings.google_trends_timezone or 330),
            timeout=(10, 30),
            retries=0,
            backoff_factor=0.0,
        )

    def _build_payload(self, pytrends: Any, topic: str, timeframe: str) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                pytrends.build_payload(
                    kw_list=[topic],
                    timeframe=timeframe,
                    geo=self.settings.google_trends_geo or "",
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("build_payload attempt %s failed: %s", attempt, exc)
                time.sleep(1.5 * attempt)
        raise RuntimeError(f"Google Trends payload failed after retries: {last_exc}")

    def _fail(self, health: ProviderHealth, started: datetime, message: str) -> ProviderResult:
        health.status = ProviderStatus.FAILED
        health.error = message
        health.finished_at = datetime.now(timezone.utc)
        health.duration_seconds = (health.finished_at - started).total_seconds()
        logger.error("Google Trends provider failed: %s", message)
        return ProviderResult(
            provider=self.name,
            signal=self.signal_type,
            status=ProviderStatus.FAILED,
            records=[],
            errors=[message],
            health=health,
        )
