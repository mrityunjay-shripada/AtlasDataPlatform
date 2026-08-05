"""
Provider Registry — central registration and lookup of data providers.
"""

from __future__ import annotations

from typing import Optional

from atlas.core.contracts import Provider
from atlas.core.models import ProviderHealth, ProviderStatus
from atlas.utils.logging import get_logger

logger = get_logger("atlas.providers.registry")


class ProviderRegistry:
    """Singleton-style registry for Provider implementations."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, provider: Provider, enabled: bool = True) -> None:
        name = provider.name
        if name in self._providers:
            logger.warning("Provider '%s' is being re-registered", name)
        self._providers[name] = provider
        self._enabled[name] = enabled
        logger.info("Registered provider '%s' (enabled=%s)", name, enabled)

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)
        self._enabled.pop(name, None)
        logger.info("Unregistered provider '%s'", name)

    def get(self, name: str) -> Optional[Provider]:
        if not self._enabled.get(name, False):
            return None
        return self._providers.get(name)

    def list_providers(self, enabled_only: bool = True) -> list[Provider]:
        result = []
        for name, provider in self._providers.items():
            if enabled_only and not self._enabled.get(name, False):
                continue
            result.append(provider)
        return result

    def enable(self, name: str) -> None:
        if name in self._providers:
            self._enabled[name] = True

    def disable(self, name: str) -> None:
        if name in self._providers:
            self._enabled[name] = False

    def health_snapshot(self) -> list[ProviderHealth]:
        return [
            ProviderHealth(
                provider=name,
                status=ProviderStatus.SKIPPED if not self._enabled.get(name) else ProviderStatus.SUCCESS,
            )
            for name in self._providers
        ]

    def clear(self) -> None:
        self._providers.clear()
        self._enabled.clear()


# Module-level default registry
_default_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    return _default_registry
