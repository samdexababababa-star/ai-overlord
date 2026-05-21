"""WebAIProvider — exposes each learned web AI as a regular Provider.

This is the integration point with the existing :class:`ModelRouter`. By
implementing the :class:`backend.app.providers.base.Provider` interface, a
learned web AI (e.g. ``web-ai-gemini-web``) becomes a routable model. That
means Tree-of-Thoughts, Reflexion, Debate, Constitutional and the Council's
agent pinning all work transparently against it.

The provider is *passive*: it doesn't open Chrome on its own — it requires
that the user has the controlled Chrome instance running (the same one the
``browser`` tool already uses). When no browser is reachable, it raises
``TransientError`` so the router fails over to the next candidate.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import ProviderModel
from ..log import get_logger
from ..providers.base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    TransientError,
)
from .client import WebAIClient
from .profiles import ProfileHealth, ProfileStore, SiteProfile, get_profile_store

log = get_logger(__name__)


WEB_AI_MODEL_PREFIX = "web-ai:"


def model_id_for_profile(profile_id: str) -> str:
    return f"{WEB_AI_MODEL_PREFIX}{profile_id}"


def profile_id_for_model(model_id: str) -> str | None:
    if model_id.startswith(WEB_AI_MODEL_PREFIX):
        return model_id[len(WEB_AI_MODEL_PREFIX):]
    return None


class WebAIProvider(Provider):
    """One ``Provider`` that fronts *all* learned web AI sites.

    Each site shows up as a model whose id is ``web-ai:<profile_id>``. The
    router treats this provider like any other; the difference is just that
    "calling the model" means driving Chrome rather than HTTP.
    """

    name = "web_ai"
    base_url = ""  # not HTTP-based
    supports_streaming = False

    def __init__(
        self,
        store: ProfileStore | None = None,
        client_factory: type[WebAIClient] | None = None,
    ):
        # We don't carry API keys; pass a sentinel so the base class is happy.
        super().__init__(["web-ai-local"])
        self.store = store or get_profile_store()
        self._client_factory = client_factory or WebAIClient

    # ------------------------------------------------------------------
    # Model catalog (recomputed from the live profile store)
    # ------------------------------------------------------------------

    @property
    def models(self) -> list[ProviderModel]:
        out: list[ProviderModel] = []
        for profile in self.store.list_all():
            if profile.category.value != "ai":
                continue
            if not profile.is_ready():
                continue
            out.append(
                ProviderModel(
                    id=model_id_for_profile(profile.id),
                    provider=self.name,
                    label=f"WebAI: {profile.label}",
                    capabilities=["chat", "reason"],
                    context_window=32_000,
                    cost_tier=0,
                )
            )
        return out

    async def validate_key(self, key: str) -> bool:
        return True  # always usable as long as Chrome is reachable

    # ------------------------------------------------------------------
    # The actual chat call — route through the web client
    # ------------------------------------------------------------------

    def _resolve_profile(self, model_id: str) -> SiteProfile:
        pid = profile_id_for_model(model_id)
        if pid is None:
            raise ProviderError(f"web_ai: not a web-ai model id: {model_id}")
        profile = self.store.get(pid)
        if profile is None:
            raise ProviderError(f"web_ai: unknown profile {pid}")
        if profile.health.status == ProfileHealth.NEEDS_LOGIN:
            raise TransientError(f"web_ai: profile {pid} needs login")
        if not profile.is_ready():
            raise TransientError(f"web_ai: profile {pid} is not ready")
        return profile

    @staticmethod
    def _flatten_messages(messages: list) -> str:
        """Collapse the role/content history into a single prompt string."""
        parts: list[str] = []
        for m in messages:
            role = getattr(m, "role", "user")
            content = (getattr(m, "content", "") or "").strip()
            if not content:
                continue
            if role == "system":
                parts.append(f"[Context]\n{content}")
            elif role == "user":
                parts.append(f"[User]\n{content}")
            elif role == "assistant":
                parts.append(f"[Previously you said]\n{content}")
            elif role == "tool":
                parts.append(f"[Tool output]\n{content[:1000]}")
        return "\n\n".join(parts).strip()

    async def chat(self, req: ChatRequest) -> ChatResponse:
        profile = self._resolve_profile(req.model)
        prompt = self._flatten_messages(list(req.messages))
        client = self._client_factory(profile=profile, store=self.store)
        result = await client.ask(prompt, timeout_ms=profile.stream_settle.max_ms)
        if not result.ok:
            raise TransientError(
                f"web_ai: site {profile.id} returned no answer: {result.error}"
            )
        return ChatResponse(
            text=result.text,
            model=req.model,
            provider=self.name,
            finish_reason="stop",
            usage={
                "web_ai_elapsed_ms": result.elapsed_ms,
                "web_ai_retries": result.retries,
                "web_ai_selector_repaired": result.selector_repaired,
            },
        )

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        resp = await self.chat(req)
        yield resp.text


_singleton: WebAIProvider | None = None


def get_web_ai_provider() -> WebAIProvider:
    global _singleton
    if _singleton is None:
        _singleton = WebAIProvider()
    return _singleton


def reset_web_ai_provider_for_tests() -> WebAIProvider:
    global _singleton
    _singleton = WebAIProvider()
    return _singleton
