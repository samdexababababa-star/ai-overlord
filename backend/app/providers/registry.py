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
from .cerebras import CerebrasProvider
from .demo import DemoProvider
from .google import GoogleProvider
from .groq import GroqProvider
from .mistral import MistralProvider
from .nvidia import NvidiaProvider
from .openrouter import OpenRouterProvider
from .together import TogetherProvider

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "mistral": MistralProvider,
    "nvidia": NvidiaProvider,
    "google": GoogleProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
    "cerebras": CerebrasProvider,
    "together": TogetherProvider,
}


class ProviderRegistry:
    """Holds live :class:`Provider` instances keyed by name."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._lock = asyncio.Lock()

    async def load(self, keys_by_provider: dict[str, list[str]]) -> None:
        async with self._lock:
            for name, cls in PROVIDER_CLASSES.items():
                if name == "demo":
                    continue  # demo is always-on via ensure_demo
                keys = keys_by_provider.get(name, [])
                if keys:
                    self._providers[name] = cls(keys)
                    log.info("provider.loaded", provider=name, key_count=len(keys))
                else:
                    self._providers.pop(name, None)
            self._ensure_demo()
            self._ensure_web_ai()

    def _ensure_demo(self) -> None:
        """Always register the demo provider (zero-key fallback)."""
        if "demo" not in self._providers:
            self._providers["demo"] = DemoProvider()
            log.info("provider.loaded", provider="demo", key_count=0)

    def _ensure_web_ai(self) -> None:
        """Register the Web-AI Mesh provider whenever learned profiles exist.

        The provider lazily reads the on-disk profile store every time its
        ``models`` property is accessed, so it does not need any keys.
        """
        if "web_ai" in self._providers:
            return
        # Local import to keep playwright/web_ai out of registry's top-level
        # import path in case those modules fail at startup.
        try:
            from ..web_ai.provider import get_web_ai_provider

            self._providers["web_ai"] = get_web_ai_provider()
            log.info("provider.loaded", provider="web_ai", key_count=0)
        except Exception as e:  # noqa: BLE001
            log.warning("provider.web_ai_load_fail", error=str(e)[:200])

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
