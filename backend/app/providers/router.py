"""Model router.

Given a :class:`TaskProfile`, picks the best available (provider, model) pair
across the registry. Selection is a small scoring function combining:
  - capability match (must include the requested capability)
  - cost (free providers preferred)
  - context window suitability
  - per-provider preference / health
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..config import ProviderModel
from ..log import get_logger
from .base import ChatMessage, ChatRequest, ChatResponse, Provider, ProviderError
from .registry import ProviderRegistry

log = get_logger(__name__)


Capability = Literal[
    "chat", "reason", "code", "vision", "embed", "audio", "fast", "long_context"
]


class TaskProfile(BaseModel):
    capability: Capability = "chat"
    estimated_input_tokens: int = 2_000
    prefer_free: bool = True
    # Optional explicit override
    pinned_model_id: str | None = None
    # Soft preference: list of providers to prefer in order
    prefer_providers: list[str] = Field(default_factory=list)
    # If true, vision-capable models that also handle text count for chat
    allow_overcap: bool = True


def _score(model: ProviderModel, profile: TaskProfile) -> float | None:
    if profile.capability not in model.capabilities and not (
        profile.allow_overcap and "chat" in model.capabilities and profile.capability == "chat"
    ):
        return None
    if model.context_window < profile.estimated_input_tokens:
        return None
    score = 100.0
    # Cost penalty
    if profile.prefer_free:
        score -= model.cost_tier * 25.0
    else:
        score -= model.cost_tier * 5.0
    # Provider preference bonus
    if profile.prefer_providers:
        try:
            idx = profile.prefer_providers.index(model.provider)
            score += (len(profile.prefer_providers) - idx) * 3.0
        except ValueError:
            pass
    # Reasoning/code/vision bonus for explicit capability match (specialist > generalist)
    specialist_caps = {"reason", "code", "vision", "embed", "audio"}
    if profile.capability in specialist_caps and profile.capability in model.capabilities:
        score += 10.0
    if "fast" in model.capabilities and profile.capability == "fast":
        score += 8.0
    return score


class ModelRouter:
    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def pick(self, profile: TaskProfile) -> tuple[Provider, ProviderModel] | None:
        if profile.pinned_model_id:
            found = self.registry.find_model(profile.pinned_model_id)
            if found:
                return found
            log.warning("router.pinned_missing", model=profile.pinned_model_id)
        ranked: list[tuple[float, Provider, ProviderModel]] = []
        for prov in self.registry.providers():
            for model in prov.models:
                s = _score(model, profile)
                if s is None:
                    continue
                ranked.append((s, prov, model))
        if not ranked:
            return None
        ranked.sort(key=lambda x: x[0], reverse=True)
        _, prov, model = ranked[0]
        return prov, model

    async def chat(
        self,
        messages: list[ChatMessage],
        profile: TaskProfile | None = None,
        **kwargs,
    ) -> ChatResponse:
        prof = profile or TaskProfile()
        # Try up to N candidates if the top one errors out.
        candidates: list[tuple[Provider, ProviderModel]] = []
        if prof.pinned_model_id:
            found = self.registry.find_model(prof.pinned_model_id)
            if found:
                candidates.append(found)
        ranked: list[tuple[float, Provider, ProviderModel]] = []
        for prov in self.registry.providers():
            for model in prov.models:
                s = _score(model, prof)
                if s is None:
                    continue
                ranked.append((s, prov, model))
        ranked.sort(key=lambda x: x[0], reverse=True)
        for _, prov, model in ranked[:5]:
            if (prov, model) not in candidates:
                candidates.append((prov, model))
        if not candidates:
            raise ProviderError("no provider matches task profile")
        last_err: Exception | None = None
        for prov, model in candidates:
            try:
                req = ChatRequest(model=model.id, messages=messages, **kwargs)
                resp = await prov.chat(req)
                log.info(
                    "router.chat.ok",
                    provider=prov.name,
                    model=model.id,
                    capability=prof.capability,
                )
                return resp
            except ProviderError as e:
                log.warning(
                    "router.chat.fail", provider=prov.name, model=model.id, error=str(e)[:200]
                )
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                log.exception("router.chat.unexpected", provider=prov.name, model=model.id)
                last_err = e
                continue
        raise last_err or ProviderError("all candidates failed")
