"""
Structured logging setup for AtlasDataPlatform.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from atlas.core.settings import get_settings


def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """
    Configure the root AtlasDataPlatform logger.

    Returns the 'atlas' logger. Safe to call multiple times.
    """
    settings = get_settings()
    log_level = (level or settings.atlas_log_level).upper()

    logger = logging.getLogger("atlas")
    if logger.handlers:
        # Already configured
        logger.setLevel(log_level)
        return logger

    logger.setLevel(log_level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def get_logger(name: str = "atlas") -> logging.Logger:
    """Return a child logger under the atlas namespace."""
    # Ensure root is configured
    setup_logging()
    return logging.getLogger(name)
