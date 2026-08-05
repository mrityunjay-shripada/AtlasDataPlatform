#!/usr/bin/env python3
"""Phase 1 verification script."""

import sys
from pathlib import Path

# Ensure package is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main() -> int:
    print("=" * 60)
    print("AtlasDataPlatform — Phase 1 Verification")
    print("=" * 60)

    # 1. Import core
    from atlas import __version__, __schema_version__, get_settings
    print(f"✓ Package import OK  (version={__version__}, schema={__schema_version__})")

    # 2. Settings
    settings = get_settings()
    print(f"✓ Settings loaded    (env={settings.atlas_env}, log={settings.atlas_log_level})")
    print(f"  data_dir         = {settings.data_dir}")
    print(f"  datasets_dir     = {settings.datasets_dir}")
    print(f"  has_youtube      = {settings.has_youtube_credentials}")
    print(f"  has_reddit       = {settings.has_reddit_credentials}")
    print(f"  has_supabase     = {settings.has_supabase_credentials}")

    # 3. Logging
    from atlas.utils.logging import get_logger
    logger = get_logger("atlas.phase1")
    logger.info("Logging system operational")
    print("✓ Logging OK")

    # 4. Directories
    for d in (settings.data_dir, settings.datasets_dir, settings.raw_dir, settings.processed_dir):
        assert d.exists(), f"Missing directory: {d}"
    print("✓ Data directories exist")

    print("=" * 60)
    print("Phase 1 verification PASSED")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
