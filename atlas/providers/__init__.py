"""Data providers for AtlasDataPlatform."""

from atlas.providers.registry import ProviderRegistry, get_registry
from atlas.providers.youtube import YouTubeProvider
from atlas.providers.trends import GoogleTrendsProvider
from atlas.providers.reddit import RedditProvider

__all__ = [
    "ProviderRegistry",
    "get_registry",
    "YouTubeProvider",
    "GoogleTrendsProvider",
    "RedditProvider",
]


def register_default_providers(registry: ProviderRegistry | None = None) -> ProviderRegistry:
    """Register the three built-in providers."""
    reg = registry or get_registry()
    reg.register(YouTubeProvider())
    reg.register(GoogleTrendsProvider())
    reg.register(RedditProvider())
    return reg
