"""
AtlasDataPlatform
================

Marketing Intelligence Operating System — Data Platform layer.

Public entry point:
    from atlas.engine import DataCollectionEngine
    dataset = DataCollectionEngine().collect("Artificial Intelligence")
"""

__version__ = "1.0.0"
__schema_version__ = "1.0.0"

from atlas.core.settings import get_settings

__all__ = [
    "__version__",
    "__schema_version__",
    "get_settings",
]
