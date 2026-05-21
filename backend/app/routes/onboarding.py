"""Onboarding & key-management API.

GET  /onboarding/providers       — info about each supported provider, how to obtain keys
GET  /onboarding/keys            — list configured keys (masked)
POST /onboarding/keys            — add a key
POST /onboarding/keys/validate   — validate a candidate key against the provider
DELETE /onboarding/keys          — remove a key
POST /onboarding/reload          — rebuild the provider registry from the keystore
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..keystore import add_key, all_keys, list_keys, remove_key
from ..providers import get_registry
from ..providers.registry import PROVIDER_CLASSES

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


PROVIDER_INFO = {
    "mistral": {
        "label": "Mistral AI",
        "console": "https://console.mistral.ai/api-keys/",
        "signup": "https://console.mistral.ai/",
        "steps": [
            "Go to https://console.mistral.ai/ and sign up (no card needed for the free workspace).",
            "Open the API Keys page: https://console.mistral.ai/api-keys/",
            "Click 'Create new key', give it a name (e.g. 'overlord-1'), copy the value.",
            "Paste it below. The first key unlocks the full provider catalog.",
        ],
        "tier_note": "Free workspace gets generous monthly tokens; add several keys to spread quota.",
    },
    "nvidia": {
        "label": "NVIDIA NIM (build.nvidia.com)",
        "console": "https://build.nvidia.com/",
        "signup": "https://build.nvidia.com/",
        "steps": [
            "Open https://build.nvidia.com/ and sign in with an NVIDIA Developer account.",
            "Pick any model card (e.g. Llama 3.3 70B), then click 'Get API Key'.",
            "Copy the 'nvapi-…' key and paste it below.",
            "Each free account gets a monthly credit pool shared across the catalog.",
        ],
        "tier_note": "Hosts 80+ free models including DeepSeek-R1, Llama 3.3 70B, Qwen Coder, vision.",
    },
    "google": {
        "label": "Google AI Studio (Gemini / Gemma)",
        "console": "https://aistudio.google.com/apikey",
        "signup": "https://aistudio.google.com/",
        "steps": [
            "Sign in at https://aistudio.google.com/ with a Google account.",
            "Open https://aistudio.google.com/apikey and click 'Create API key'.",
            "Pick or create a Google Cloud project (free tier).",
            "Copy the 'AIza…' key and paste it below.",
        ],
        "tier_note": "Free tier: Gemini 2.5 Flash & Flash-Lite, Gemma 3, embedding-004. Daily limits per key.",
    },
    "groq": {
        "label": "Groq Cloud",
        "console": "https://console.groq.com/keys",
        "signup": "https://console.groq.com/",
        "steps": [
            "Go to https://console.groq.com/ and sign in (free).",
            "Open https://console.groq.com/keys and click 'Create API Key'.",
            "Copy the 'gsk_…' key and paste it below.",
        ],
        "tier_note": "Ultra-fast Llama 3.3 70B inference (~800 tok/s). Free tier with daily TPM caps.",
    },
    "openrouter": {
        "label": "OpenRouter",
        "console": "https://openrouter.ai/keys",
        "signup": "https://openrouter.ai/",
        "steps": [
            "Go to https://openrouter.ai/ and create a free account.",
            "Open https://openrouter.ai/keys and create an API key.",
            "Copy the 'sk-or-…' key and paste it below.",
        ],
        "tier_note": "Unified gateway to 200+ models. Several free models available (Llama, DeepSeek, Qwen).",
    },
    "cerebras": {
        "label": "Cerebras Cloud",
        "console": "https://cloud.cerebras.ai/",
        "signup": "https://cloud.cerebras.ai/",
        "steps": [
            "Go to https://cloud.cerebras.ai/ and sign up.",
            "Navigate to API Keys in your dashboard.",
            "Create a new key and paste it below.",
        ],
        "tier_note": "Ultra-fast inference on Wafer-Scale hardware. Free tier with daily limits.",
    },
    "together": {
        "label": "Together AI",
        "console": "https://api.together.xyz/settings/api-keys",
        "signup": "https://api.together.xyz/",
        "steps": [
            "Go to https://api.together.xyz/ and sign up.",
            "Navigate to https://api.together.xyz/settings/api-keys.",
            "Create an API key and paste it below.",
        ],
        "tier_note": "Fast open-source model inference. Free credits on signup.",
    },
}


class AddKeyRequest(BaseModel):
    provider: str
    label: str
    value: str


class RemoveKeyRequest(BaseModel):
    provider: str
    label: str


class ValidateRequest(BaseModel):
    provider: str
    value: str


@router.get("/providers")
def providers_info() -> dict:
    info = {}
    for name, meta in PROVIDER_INFO.items():
        cls = PROVIDER_CLASSES.get(name)
        if not cls:
            continue
        # Build dummy to get model list (no keys required for metadata)
        try:
            tmp = cls([])
            models = [m.model_dump() for m in tmp.models]
        except Exception:
            models = []
        info[name] = {**meta, "models": models}
    return info


@router.get("/keys")
def list_configured_keys() -> dict:
    return list_keys()


@router.post("/keys")
async def add_key_endpoint(req: AddKeyRequest) -> dict:
    if req.provider not in PROVIDER_CLASSES:
        raise HTTPException(status_code=400, detail="unknown provider")
    if not req.value.strip():
        raise HTTPException(status_code=400, detail="empty key")
    add_key(req.provider, req.label.strip() or "key", req.value)
    # Reload the registry so the new key is live immediately
    await get_registry().load(all_keys())
    return {"ok": True}


@router.delete("/keys")
async def remove_key_endpoint(req: RemoveKeyRequest) -> dict:
    remove_key(req.provider, req.label)
    await get_registry().load(all_keys())
    return {"ok": True}


@router.post("/keys/validate")
async def validate_key(req: ValidateRequest) -> dict:
    cls = PROVIDER_CLASSES.get(req.provider)
    if not cls:
        raise HTTPException(status_code=400, detail="unknown provider")
    tmp = cls([req.value])
    ok = await tmp.validate_key(req.value)
    return {"ok": ok}


@router.post("/reload")
async def reload_keys() -> dict:
    await get_registry().load(all_keys())
    return {"ok": True, "providers": [p.name for p in get_registry().providers()]}
