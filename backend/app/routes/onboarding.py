"""Onboarding & key-management API.

GET  /onboarding/providers       — info about each supported provider, how to obtain keys
GET  /onboarding/keys            — list configured keys (masked)
POST /onboarding/keys            — add a key
POST /onboarding/keys/validate   — validate a candidate key against the provider
DELETE /onboarding/keys          — remove a key
POST /onboarding/reload          — rebuild the provider registry from the keystore
GET  /onboarding/env-detect      — detect API keys already in system env / .env files
POST /onboarding/env-import      — import detected env keys into the keystore
"""

from __future__ import annotations

import os
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Environment-variable auto-detection
# ---------------------------------------------------------------------------

# Maps each environment variable name to the provider it belongs to.
ENV_VAR_MAP: dict[str, str] = {
    "MISTRAL_API_KEY": "mistral",
    "NVIDIA_API_KEY": "nvidia",
    "NVIDIA_NIM_API_KEY": "nvidia",
    "GOOGLE_AI_API_KEY": "google",
    "GOOGLE_API_KEY": "google",
    "GEMINI_API_KEY": "google",
    "GROQ_API_KEY": "groq",
    "OPENROUTER_API_KEY": "openrouter",
    "CEREBRAS_API_KEY": "cerebras",
    "TOGETHER_API_KEY": "together",
    "TOGETHER_AI_API_KEY": "together",
}


def _load_dotenv(p: Path) -> dict[str, str]:
    """Tiny .env parser (stdlib only, no python-dotenv dependency)."""
    out: dict[str, str] = {}
    if not p.exists():
        return out
    try:
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v:
                out[k] = v
    except Exception:
        return out
    return out


def _detect_env_keys() -> dict[str, dict[str, str]]:
    """Return ``{env_var: {"provider": "...", "value": "...", "source": "..."}}``."""
    found: dict[str, dict[str, str]] = {}

    # 1. System environment.
    for env_var, provider in ENV_VAR_MAP.items():
        v = os.environ.get(env_var)
        if v:
            found[env_var] = {"provider": provider, "value": v, "source": "env"}

    # 2. .env files at repo root and home directory.
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path.home() / ".overlord.env",
    ]
    for cand in candidates:
        for k, v in _load_dotenv(cand).items():
            if k in ENV_VAR_MAP and k not in found:
                found[k] = {
                    "provider": ENV_VAR_MAP[k],
                    "value": v,
                    "source": str(cand),
                }
    return found


@router.get("/env-detect")
def env_detect() -> dict:
    """List API keys we can auto-import from environment variables / .env files.

    Values are returned **masked** — the actual key is held server-side until
    the user confirms the import via POST ``/onboarding/env-import``.
    """
    found = _detect_env_keys()
    out: list[dict] = []
    for env_var, info in found.items():
        v = info["value"]
        masked = v[:4] + "…" + v[-4:] if len(v) > 12 else "…"
        out.append({
            "env_var": env_var,
            "provider": info["provider"],
            "masked": masked,
            "source": info["source"],
        })
    return {"keys": out}


class EnvImportRequest(BaseModel):
    env_vars: list[str] | None = None  # if None, import everything detected


@router.post("/env-import")
async def env_import(req: EnvImportRequest) -> dict:
    """Persist the detected env keys into the encrypted keystore."""
    found = _detect_env_keys()
    selected = req.env_vars if req.env_vars else list(found.keys())
    imported = 0
    for env_var in selected:
        info = found.get(env_var)
        if not info:
            continue
        label = env_var.lower()
        add_key(info["provider"], label, info["value"])
        imported += 1
    if imported:
        await get_registry().load(all_keys())
    return {"ok": True, "imported": imported}
