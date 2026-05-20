"""Tests for the model router scoring + selection."""

from __future__ import annotations

import pytest

from backend.app.providers.base import Provider
from backend.app.providers.google import GOOGLE_MODELS, GoogleProvider
from backend.app.providers.groq import GROQ_MODELS, GroqProvider
from backend.app.providers.mistral import MISTRAL_MODELS, MistralProvider
from backend.app.providers.nvidia import NVIDIA_MODELS, NvidiaProvider
from backend.app.providers.registry import ProviderRegistry
from backend.app.providers.router import ModelRouter, TaskProfile


def _registry_with_all() -> ProviderRegistry:
    reg = ProviderRegistry()
    # Manually wire fake keys so the registry exposes each provider's models.
    reg._providers["mistral"] = MistralProvider(["fake-mistral"])
    reg._providers["nvidia"] = NvidiaProvider(["nvapi-fake"])
    reg._providers["google"] = GoogleProvider(["AIza-fake"])
    reg._providers["groq"] = GroqProvider(["gsk_fake"])
    return reg


def test_catalog_present():
    reg = _registry_with_all()
    ids = {m.id for m in reg.all_models()}
    assert "mistral-large-latest" in ids
    assert "meta/llama-3.3-70b-instruct" in ids
    assert "gemini-2.5-flash" in ids
    assert "llama-3.3-70b-versatile" in ids


def test_router_picks_free_for_chat():
    reg = _registry_with_all()
    pick = ModelRouter(reg).pick(TaskProfile(capability="chat"))
    assert pick is not None
    _, model = pick
    assert model.cost_tier == 0


def test_router_picks_code_model():
    reg = _registry_with_all()
    pick = ModelRouter(reg).pick(TaskProfile(capability="code"))
    assert pick is not None
    _, model = pick
    assert "code" in model.capabilities


def test_router_picks_vision_model():
    reg = _registry_with_all()
    pick = ModelRouter(reg).pick(TaskProfile(capability="vision"))
    assert pick is not None
    _, model = pick
    assert "vision" in model.capabilities


def test_router_picks_embed_model():
    reg = _registry_with_all()
    pick = ModelRouter(reg).pick(TaskProfile(capability="embed"))
    assert pick is not None
    _, model = pick
    assert "embed" in model.capabilities


def test_router_returns_none_when_empty():
    pick = ModelRouter(ProviderRegistry()).pick(TaskProfile(capability="chat"))
    assert pick is None


def test_pinned_model_wins():
    reg = _registry_with_all()
    pick = ModelRouter(reg).pick(
        TaskProfile(capability="chat", pinned_model_id="mistral-small-latest")
    )
    assert pick is not None
    _, model = pick
    assert model.id == "mistral-small-latest"


def test_each_provider_catalog_non_empty():
    assert MISTRAL_MODELS and NVIDIA_MODELS and GOOGLE_MODELS and GROQ_MODELS


@pytest.mark.parametrize(
    "cls,prefix",
    [
        (MistralProvider, "mistral"),
        (NvidiaProvider, "nvidia"),
        (GoogleProvider, "google"),
        (GroqProvider, "groq"),
    ],
)
def test_provider_name(cls: type[Provider], prefix: str):
    p = cls(["fake"])
    assert p.name == prefix
    assert p.base_url.startswith("https://")
