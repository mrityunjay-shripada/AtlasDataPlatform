"""
StorageManager — Supabase Storage (primary) + local fallback.

Architecture:
  Supabase Storage is the primary persistence layer when credentials exist.
  Local disk is used automatically as a development / offline fallback.
  DuckDB never owns data — it only queries persisted files.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from atlas.core.contracts import Storage
from atlas.core.models import MarketIntelligenceDataset
from atlas.core.settings import get_settings
from atlas.utils.logging import get_logger

logger = get_logger("atlas.storage")


def _slug(topic: str) -> str:
    import re
    s = topic.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:80] or "topic"


class StorageManager(Storage):
    """
    Primary: Supabase Storage (when configured)
    Fallback: local datasets_dir
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_root = self.settings.datasets_dir
        self.local_root.mkdir(parents=True, exist_ok=True)
        self._supabase = None
        self._supabase_init_attempted = False

    # ------------------------------------------------------------------
    # Supabase client
    # ------------------------------------------------------------------

    @property
    def supabase_enabled(self) -> bool:
        return self.settings.has_supabase_credentials

    def _get_supabase(self):
        if self._supabase_init_attempted:
            return self._supabase
        self._supabase_init_attempted = True

        if not self.settings.has_supabase_credentials:
            logger.info("Supabase credentials not configured — using local storage")
            return None

        try:
            from supabase import create_client
            self._supabase = create_client(
                self.settings.supabase_url,
                self.settings.supabase_key,
            )
            logger.info("Supabase client initialized (bucket=%s)", self.settings.supabase_bucket)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase client init failed — falling back to local: %s", exc)
            self._supabase = None
        return self._supabase

    def _bucket(self) -> str:
        return self.settings.supabase_bucket or "atlasdataplatform"

    def _remote_paths(self, slug: str, ts: str) -> dict[str, str]:
        base = f"datasets/{slug}"
        return {
            "latest_json": f"{base}/latest.json",
            "versioned_json": f"{base}/{ts}.json",
            "latest_parquet": f"{base}/latest.parquet",
            "versioned_parquet": f"{base}/{ts}.parquet",
        }

    # ------------------------------------------------------------------
    # Serialize helpers
    # ------------------------------------------------------------------

    def _serialize(self, dataset: MarketIntelligenceDataset) -> tuple[bytes, Optional[bytes], str]:
        payload = dataset.model_dump(mode="json")
        json_bytes = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        checksum = hashlib.sha256(json_bytes).hexdigest()[:16]
        dataset.metadata.checksum = checksum

        parquet_bytes: Optional[bytes] = None
        try:
            import pandas as pd
            if dataset.content_supply:
                df = pd.DataFrame([v.model_dump(mode="json") for v in dataset.content_supply])
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    df.to_parquet(tmp_path, index=False)
                    parquet_bytes = tmp_path.read_bytes()
                finally:
                    tmp_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Parquet serialization failed: %s", exc)

        return json_bytes, parquet_bytes, checksum

    # ------------------------------------------------------------------
    # Local helpers (fallback)
    # ------------------------------------------------------------------

    def _upload_local(
        self,
        topic: str,
        slug: str,
        ts: str,
        json_bytes: bytes,
        parquet_bytes: Optional[bytes],
    ) -> str:
        topic_dir = self.local_root / slug
        topic_dir.mkdir(parents=True, exist_ok=True)

        (topic_dir / "latest.json").write_bytes(json_bytes)
        (topic_dir / f"{ts}.json").write_bytes(json_bytes)

        if parquet_bytes:
            (topic_dir / "latest.parquet").write_bytes(parquet_bytes)
            (topic_dir / f"{ts}.parquet").write_bytes(parquet_bytes)

        location = str(topic_dir / "latest.json")
        logger.info("Persisted locally: %s", location)
        return location

    def _download_local(self, topic: str, version: Optional[str] = None) -> Optional[MarketIntelligenceDataset]:
        slug = _slug(topic)
        topic_dir = self.local_root / slug
        path = topic_dir / (f"{version}.json" if version else "latest.json")
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MarketIntelligenceDataset.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.error("Local load failed %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Supabase helpers (primary)
    # ------------------------------------------------------------------

    def _upload_supabase(
        self,
        client,
        slug: str,
        ts: str,
        json_bytes: bytes,
        parquet_bytes: Optional[bytes],
    ) -> str:
        bucket = self._bucket()
        paths = self._remote_paths(slug, ts)

        # Upload JSON (latest + versioned)
        for key in ("latest_json", "versioned_json"):
            remote = paths[key]
            try:
                # Remove existing latest so upsert works cleanly across SDK versions
                if key == "latest_json":
                    try:
                        client.storage.from_(bucket).remove([remote])
                    except Exception:
                        pass
                client.storage.from_(bucket).upload(
                    remote,
                    json_bytes,
                    file_options={"content-type": "application/json", "upsert": "true"},
                )
            except Exception as exc:  # noqa: BLE001
                # Some SDK versions use update for existing files
                try:
                    client.storage.from_(bucket).update(
                        remote,
                        json_bytes,
                        file_options={"content-type": "application/json"},
                    )
                except Exception:
                    raise RuntimeError(f"Supabase JSON upload failed ({remote}): {exc}") from exc

        # Upload Parquet if available
        if parquet_bytes:
            for key in ("latest_parquet", "versioned_parquet"):
                remote = paths[key]
                try:
                    if key == "latest_parquet":
                        try:
                            client.storage.from_(bucket).remove([remote])
                        except Exception:
                            pass
                    client.storage.from_(bucket).upload(
                        remote,
                        parquet_bytes,
                        file_options={"content-type": "application/octet-stream", "upsert": "true"},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Supabase Parquet upload skipped (%s): %s", remote, exc)

        location = f"supabase://{bucket}/{paths['latest_json']}"
        logger.info("Persisted to Supabase: %s", location)
        return location

    def _download_supabase(
        self, client, topic: str, version: Optional[str] = None
    ) -> Optional[MarketIntelligenceDataset]:
        bucket = self._bucket()
        slug = _slug(topic)
        if version:
            remote = f"datasets/{slug}/{version}.json"
        else:
            remote = f"datasets/{slug}/latest.json"

        try:
            data_bytes = client.storage.from_(bucket).download(remote)
            data = json.loads(data_bytes.decode("utf-8"))
            dataset = MarketIntelligenceDataset.model_validate(data)
            logger.info("Loaded from Supabase: %s", remote)
            return dataset
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase download failed (%s): %s", remote, exc)
            return None

    def _exists_supabase(self, client, topic: str) -> bool:
        bucket = self._bucket()
        slug = _slug(topic)
        prefix = f"datasets/{slug}"
        try:
            items = client.storage.from_(bucket).list(prefix)
            return any(
                (item.get("name") if isinstance(item, dict) else getattr(item, "name", "")) == "latest.json"
                for item in (items or [])
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase exists check failed: %s", exc)
            return False

    def _list_versions_supabase(self, client, topic: str) -> list[str]:
        bucket = self._bucket()
        slug = _slug(topic)
        prefix = f"datasets/{slug}"
        try:
            items = client.storage.from_(bucket).list(prefix)
            names = []
            for item in (items or []):
                name = item.get("name") if isinstance(item, dict) else getattr(item, "name", "")
                if name.endswith(".json") and name != "latest.json":
                    names.append(name.replace(".json", ""))
            return sorted(names)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase list_versions failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Public Storage interface
    # ------------------------------------------------------------------

    def upload(self, dataset: MarketIntelligenceDataset, topic: str) -> str:
        slug = _slug(topic)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
        json_bytes, parquet_bytes, checksum = self._serialize(dataset)

        client = self._get_supabase()
        location: Optional[str] = None

        # Primary: Supabase
        if client is not None:
            try:
                location = self._upload_supabase(client, slug, ts, json_bytes, parquet_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.error("Supabase primary upload failed — falling back to local: %s", exc)
                client = None  # force local fallback

        # Fallback / always keep a local copy for DuckDB & dev
        local_location = self._upload_local(topic, slug, ts, json_bytes, parquet_bytes)
        if location is None:
            location = local_location

        dataset.metadata.storage_location = location
        dataset.metadata.checksum = checksum
        logger.info(
            "Dataset persisted | topic=%s primary=%s checksum=%s",
            topic, location, checksum,
        )
        return location

    def download(self, topic: str, version: Optional[str] = None) -> Optional[MarketIntelligenceDataset]:
        client = self._get_supabase()

        # Primary: Supabase
        if client is not None:
            ds = self._download_supabase(client, topic, version)
            if ds is not None:
                return ds
            logger.info("Supabase miss for '%s' — trying local fallback", topic)

        # Fallback: local
        return self._download_local(topic, version)

    def exists(self, topic: str) -> bool:
        client = self._get_supabase()
        if client is not None:
            if self._exists_supabase(client, topic):
                return True
        return (self.local_root / _slug(topic) / "latest.json").exists()

    def latest_version(self, topic: str) -> Optional[str]:
        versions = self.list_versions(topic)
        return versions[-1] if versions else None

    def list_versions(self, topic: str) -> list[str]:
        client = self._get_supabase()
        if client is not None:
            remote = self._list_versions_supabase(client, topic)
            if remote:
                return remote

        topic_dir = self.local_root / _slug(topic)
        if not topic_dir.exists():
            return []
        return sorted(p.stem for p in topic_dir.glob("*.json") if p.stem != "latest")
