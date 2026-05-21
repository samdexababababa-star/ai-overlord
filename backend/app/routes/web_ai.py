"""Web-AI Mesh routes.

Lets the frontend register sites, kick off the learn cycle, query the
learned profile, and trigger ad-hoc asks / social posts. The actual
heavy lifting lives in :mod:`backend.app.web_ai`; this is just a thin
HTTP shell with pydantic models.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..hitl import get_hitl
from ..log import get_logger
from ..user_settings import get_settings_manager
from ..web_ai.auto_learner import LearnPhase, LearnState, SiteAutoLearner
from ..web_ai.client import WebAIClient
from ..web_ai.presets import PRESETS, PRESETS_BY_ID, apply_preset
from ..web_ai.profiles import (
    ProfileHealth,
    SiteCategory,
    SiteProfile,
    get_profile_store,
)
from ..web_ai.social import PostRequest, SocialAdapter

log = get_logger(__name__)

router = APIRouter(prefix="/web-ai", tags=["web-ai"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    url: str
    label: str = ""
    category: str = "ai"
    profile_id: str | None = None
    apply_preset_id: str | None = None


class PatchProfileRequest(BaseModel):
    label: str | None = None
    include_in_council: bool | None = None
    notes: str | None = None
    selectors: dict[str, Any] | None = None


class AskRequest(BaseModel):
    prompt: str
    timeout_ms: int = 90_000


class SocialPostRequest(BaseModel):
    text: str
    media_paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory learn-state cache (one per profile)
# ---------------------------------------------------------------------------


_learn_states: dict[str, LearnState] = {}


def _ensure_category(value: str) -> SiteCategory:
    try:
        return SiteCategory(value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid category {value}") from e


# ---------------------------------------------------------------------------
# CRUD on site profiles
# ---------------------------------------------------------------------------


@router.get("/sites")
def list_sites(category: str | None = None) -> dict:
    cat = _ensure_category(category) if category else None
    profiles = get_profile_store().list_all(category=cat)
    return {
        "sites": [_serialize_profile(p) for p in profiles],
        "presets": [
            {"id": p.id, "label": p.label, "url": p.url, "category": p.category.value}
            for p in PRESETS
        ],
    }


@router.post("/sites")
def register_site(req: RegisterRequest) -> dict:
    category = _ensure_category(req.category)
    store = get_profile_store()
    profile = store.upsert_from_url(
        url=req.url, label=req.label, category=category, profile_id=req.profile_id
    )
    if req.apply_preset_id and req.apply_preset_id in PRESETS_BY_ID:
        apply_preset(profile, PRESETS_BY_ID[req.apply_preset_id])
        store.save(profile)
    log.info("web_ai.routes.register", profile=profile.id, category=category.value)
    return _serialize_profile(profile)


@router.get("/sites/{profile_id}")
def get_site(profile_id: str) -> dict:
    profile = get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    return _serialize_profile(profile, include_full=True)


@router.patch("/sites/{profile_id}")
def patch_site(profile_id: str, req: PatchProfileRequest) -> dict:
    store = get_profile_store()
    patch: dict[str, Any] = {}
    if req.label is not None:
        patch["label"] = req.label
    if req.include_in_council is not None:
        patch["include_in_council"] = req.include_in_council
    if req.notes is not None:
        patch["notes"] = req.notes
    if req.selectors is not None:
        patch["selectors"] = req.selectors
    updated = store.patch(profile_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="profile not found")
    return _serialize_profile(updated, include_full=True)


@router.delete("/sites/{profile_id}")
def delete_site(profile_id: str) -> dict:
    ok = get_profile_store().delete(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="profile not found")
    _learn_states.pop(profile_id, None)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Learn / probe lifecycle
# ---------------------------------------------------------------------------


@router.post("/sites/{profile_id}/learn")
async def learn_site(profile_id: str, background: BackgroundTasks) -> dict:
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    background.add_task(_run_learn_task, profile_id)
    _learn_states[profile_id] = LearnState(profile_id=profile_id, phase=LearnPhase.OPENED)
    return {"started": True, "profile": _serialize_profile(profile)}


@router.get("/sites/{profile_id}/learn")
def get_learn_state(profile_id: str) -> dict:
    state = _learn_states.get(profile_id)
    if not state:
        raise HTTPException(status_code=404, detail="no learn cycle running")
    return state.model_dump()


@router.post("/sites/{profile_id}/ask")
async def ask_site(profile_id: str, req: AskRequest) -> dict:
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    if profile.health.status == ProfileHealth.NEEDS_LOGIN:
        raise HTTPException(status_code=409, detail="login required")
    if get_settings_manager().check_hitl_required("web_ai_send"):
        approved = await get_hitl().request_approval(
            action_type="web_ai_send",
            description=f"Send to {profile.label}: {req.prompt[:120]}",
            details={"site_id": profile_id, "prompt": req.prompt},
            risk_level="low",
            timeout=120.0,
        )
        if not approved:
            raise HTTPException(status_code=403, detail="HITL rejected")
    client = WebAIClient(profile=profile, store=store)
    result = await client.ask(req.prompt, timeout_ms=req.timeout_ms)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Social adapter routes (HITL-gated for writes)
# ---------------------------------------------------------------------------


@router.post("/social/{profile_id}/post")
async def social_post(profile_id: str, req: SocialPostRequest) -> dict:
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    if profile.category != SiteCategory.SOCIAL:
        raise HTTPException(status_code=400, detail="not a social profile")
    # We still drive Chrome via WebAIClient's attach helper.
    adapter = SocialAdapter(profile=profile, store=store)
    client = WebAIClient(profile=profile, store=store)
    try:
        async with client._attached_page() as page:  # noqa: SLF001
            result = await adapter.post(page, PostRequest(**req.model_dump()))
        return result.model_dump()
    except Exception as e:  # noqa: BLE001
        log.warning("web_ai.routes.social_post_fail", error=str(e)[:300])
        raise HTTPException(status_code=502, detail=f"social post failed: {e}") from e


@router.get("/social/{profile_id}/feed")
async def social_feed(profile_id: str, limit: int = 20) -> dict:
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    if profile.category != SiteCategory.SOCIAL:
        raise HTTPException(status_code=400, detail="not a social profile")
    client = WebAIClient(profile=profile, store=store)
    adapter = SocialAdapter(profile=profile, store=store)
    try:
        async with client._attached_page() as page:  # noqa: SLF001
            result = await adapter.read_feed(page, limit=limit)
        return result.model_dump()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"feed read failed: {e}") from e


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


@router.get("/presets")
def list_presets() -> dict:
    return {
        "presets": [
            {
                "id": p.id,
                "label": p.label,
                "url": p.url,
                "category": p.category.value,
                "notes": p.notes,
            }
            for p in PRESETS
        ]
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _run_learn_task(profile_id: str) -> None:
    """Background task: run the learner against the live Chrome page."""
    store = get_profile_store()
    profile = store.get(profile_id)
    if not profile:
        return
    learner = SiteAutoLearner(profile=profile, store=store)
    try:
        client = WebAIClient(profile=profile, store=store)
        async with client._attached_page() as page:  # noqa: SLF001
            await page.goto(profile.url, wait_until="domcontentloaded", timeout=30_000)
            state = await learner.learn(page)
        _learn_states[profile_id] = state
    except Exception as e:  # noqa: BLE001
        log.warning("web_ai.routes.learn_fail", profile=profile_id, error=str(e)[:300])
        # Fall back to a heuristic-only run with the in-memory state
        await learner._fail(f"chrome attach failed: {e}")  # noqa: SLF001
        _learn_states[profile_id] = learner.state


def _serialize_profile(profile: SiteProfile, include_full: bool = False) -> dict:
    out = {
        "id": profile.id,
        "label": profile.label,
        "url": profile.url,
        "host": profile.host,
        "category": profile.category.value,
        "include_in_council": profile.include_in_council,
        "health": profile.health.model_dump(),
        "auth": profile.auth.model_dump(),
        "confidence": profile.selectors.confidence,
        "last_verified_at": profile.last_verified_at,
        "is_ready": profile.is_ready(),
    }
    if include_full:
        out["selectors"] = profile.selectors.model_dump()
        out["submit"] = profile.submit.model_dump()
        out["stream_settle"] = profile.stream_settle.model_dump()
        out["calibration"] = profile.calibration.model_dump()
        out["notes"] = profile.notes
    return out


