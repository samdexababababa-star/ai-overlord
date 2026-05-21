"""Settings API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..user_settings import UserSettings, get_settings_manager

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings() -> dict:
    sm = get_settings_manager()
    return sm.get().model_dump()


@router.patch("")
def update_settings(patch: dict[str, Any]) -> dict:
    sm = get_settings_manager()
    updated = sm.update(patch)
    return updated.model_dump()


@router.post("/reset")
def reset_settings() -> dict:
    sm = get_settings_manager()
    sm.save(UserSettings())
    return sm.get().model_dump()
