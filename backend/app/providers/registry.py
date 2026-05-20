"""Provider registry.

Holds the configured providers (built from keys persisted in the keystore) and
exposes lookups by name / model. The router queries this to pick a healthy
provider for any given task profile.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..config import ProviderModel
from ..log import get_logger
from .base import Provider
from .google import GoogleProvider
from .groq import GroqProvider
from .mistral import MistralProvider
from .nvidia import NvidiaProvider

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "mistral": MistralProvider,
    "nvidia": NvidiaProvider,
    "google": GoogleProvider,
    "groq": GroqProvider,
}


class ProviderRegistry:
    """Holds live :class:`Provider` instances keyed by name."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._lock = asyncio.Lock()

    async def load(self, keys_by_provider: dict[str, list[str]]) -> None:
        async with self._lock:
            for name, cls in PROVIDER_CLASSES.items():
                keys = keys_by_provider.get(name, [])
                if keys:
                    self._providers[name] = cls(keys)
                    log.info("provider.loaded", provider=name, key_count=len(keys))
                else:
                    self._providers.pop(name, None)

    def get(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def providers(self) -> list[Provider]:
        return list(self._providers.values())

    def all_models(self) -> list[ProviderModel]:
        out: list[ProviderModel] = []
        for p in self._providers.values():
            out.extend(p.models)
        return out

    def find_model(self, model_id: str) -> tuple[Provider, ProviderModel] | None:
        for p in self._providers.values():
            for m in p.models:
                if m.id == model_id:
                    return p, m
        return None

    def has_any(self) -> bool:
        return bool(self._providers)


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
