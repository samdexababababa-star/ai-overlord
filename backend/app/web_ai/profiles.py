"""Persistent per-site profiles for the Web-AI Mesh.

A :class:`SiteProfile` captures everything we have learned about a single
web UI: how to find the prompt box, how to submit, where the response shows
up, how long to wait, login state, and health telemetry.

Profiles are stored as one JSON file per site under
``data_dir / web_ai / profiles / <slug>.json`` so they survive process
restarts and snapshot rebuilds.
"""

from __future__ import annotations

import enum
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


class SiteCategory(enum.StrEnum):
    AI = "ai"
    SOCIAL = "social"
    CUSTOM = "custom"


class ProfileHealth(enum.StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    DEGRADED = "degraded"
    BROKEN = "broken"
    NEEDS_LOGIN = "needs_login"


class Selectors(BaseModel):
    """CSS selectors discovered for a site.

    ``confidence`` is in [0, 1] — anything below 0.6 means the next probe
    will re-run the vision fallback rather than trust the cached selector.
    """

    prompt_box: str = ""
    send_button: str = ""
    response_root: str = ""
    feed_item: str = ""
    compose_box: str = ""
    post_button: str = ""
    media_input: str = ""
    confidence: float = 0.0


class SubmitConfig(BaseModel):
    """How to submit a prompt — keyboard or click."""

    mode: str = "keyboard"  # "keyboard" or "click"
    key: str = "Enter"
    modifiers: list[str] = Field(default_factory=list)  # e.g. ["Control"]


class StreamSettleConfig(BaseModel):
    """When does the response area count as 'done streaming'?"""

    poll_ms: int = 600
    stable_cycles: int = 4
    max_ms: int = 90_000


class AuthState(BaseModel):
    mode: str = "session"
    needs_login: bool = False
    last_checked_at: float = 0.0


class CalibrationSpec(BaseModel):
    """A canary round-trip used to detect regressions."""

    prompt: str = "PINGPONG"
    expected_substring: str = "PINGPONG"


class ProfileHealthState(BaseModel):
    status: ProfileHealth = ProfileHealth.UNKNOWN
    consecutive_failures: int = 0
    last_success_at: float = 0.0
    last_error: str = ""


def slugify(value: str) -> str:
    """Cheap, deterministic slug for filenames and provider model ids."""
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "site"


def host_of(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.hostname or url
    except Exception:
        return url


class SiteProfile(BaseModel):
    """All the state we keep about one third-party web UI."""

    id: str
    label: str
    url: str
    host: str
    category: SiteCategory = SiteCategory.AI
    discovered_at: float = Field(default_factory=time.time)
    last_verified_at: float = 0.0
    selectors: Selectors = Field(default_factory=Selectors)
    submit: SubmitConfig = Field(default_factory=SubmitConfig)
    stream_settle: StreamSettleConfig = Field(default_factory=StreamSettleConfig)
    auth: AuthState = Field(default_factory=AuthState)
    calibration: CalibrationSpec = Field(default_factory=CalibrationSpec)
    health: ProfileHealthState = Field(default_factory=ProfileHealthState)
    include_in_council: bool = False
    notes: str = ""

    @classmethod
    def new(
        cls,
        *,
        url: str,
        label: str,
        category: SiteCategory = SiteCategory.AI,
        id: str | None = None,  # noqa: A002 — keeps the legacy kw-only name
    ) -> SiteProfile:
        sid = id or slugify(label or host_of(url))
        return cls(
            id=sid,
            label=label or sid,
            url=url,
            host=host_of(url),
            category=category,
        )

    def is_ready(self) -> bool:
        return (
            self.health.status in (ProfileHealth.OK, ProfileHealth.DEGRADED)
            and bool(self.selectors.prompt_box)
            and bool(self.selectors.response_root)
        )


class ProfileStore:
    """One-JSON-per-profile persistent store.

    Parameters
    ----------
    root : Path | None
        Directory to store profiles in. Defaults to
        ``data_dir/web_ai/profiles``.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or (settings.data_dir / "web_ai" / "profiles")
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, SiteProfile] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                profile = SiteProfile(**data)
                self._cache[profile.id] = profile
            except Exception as e:  # noqa: BLE001
                log.warning("web_ai.profile.load_fail", file=str(path), error=str(e)[:200])

    def _path(self, profile_id: str) -> Path:
        return self.root / f"{profile_id}.json"

    def save(self, profile: SiteProfile) -> SiteProfile:
        self._cache[profile.id] = profile
        self._path(profile.id).write_text(
            json.dumps(profile.model_dump(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        log.info(
            "web_ai.profile.saved",
            id=profile.id,
            category=profile.category.value,
            health=profile.health.status.value,
        )
        return profile

    def get(self, profile_id: str) -> SiteProfile | None:
        return self._cache.get(profile_id)

    def list_all(self, category: SiteCategory | None = None) -> list[SiteProfile]:
        profiles = list(self._cache.values())
        if category:
            profiles = [p for p in profiles if p.category == category]
        profiles.sort(key=lambda p: (p.category.value, p.label.lower()))
        return profiles

    def delete(self, profile_id: str) -> bool:
        if profile_id not in self._cache:
            return False
        self._cache.pop(profile_id, None)
        path = self._path(profile_id)
        if path.exists():
            path.unlink()
        return True

    def upsert_from_url(
        self,
        url: str,
        label: str,
        category: SiteCategory = SiteCategory.AI,
        profile_id: str | None = None,
    ) -> SiteProfile:
        sid = profile_id or slugify(label or host_of(url))
        existing = self._cache.get(sid)
        if existing:
            existing.url = url
            existing.label = label or existing.label
            existing.host = host_of(url)
            existing.category = category
            return self.save(existing)
        profile = SiteProfile.new(url=url, label=label, category=category, id=sid)
        return self.save(profile)

    def patch(self, profile_id: str, patch: dict[str, Any]) -> SiteProfile | None:
        profile = self._cache.get(profile_id)
        if not profile:
            return None
        data = profile.model_dump()
        _deep_update(data, patch)
        updated = SiteProfile(**data)
        return self.save(updated)

    def mark_success(self, profile_id: str) -> None:
        profile = self._cache.get(profile_id)
        if not profile:
            return
        profile.health.status = ProfileHealth.OK
        profile.health.consecutive_failures = 0
        profile.health.last_success_at = time.time()
        profile.last_verified_at = time.time()
        self.save(profile)

    def mark_failure(self, profile_id: str, error: str) -> None:
        profile = self._cache.get(profile_id)
        if not profile:
            return
        profile.health.consecutive_failures += 1
        profile.health.last_error = error[:300]
        if profile.health.consecutive_failures >= 3:
            profile.health.status = ProfileHealth.BROKEN
        else:
            profile.health.status = ProfileHealth.DEGRADED
        self.save(profile)


def _deep_update(dest: dict[str, Any], patch: dict[str, Any]) -> None:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dest.get(k), dict):
            _deep_update(dest[k], v)
        else:
            dest[k] = v


_store: ProfileStore | None = None


def get_profile_store() -> ProfileStore:
    global _store
    if _store is None:
        _store = ProfileStore()
    return _store


def reset_profile_store_for_tests(root: Path | None = None) -> ProfileStore:
    """Test-only helper to swap in a clean store."""
    global _store
    _store = ProfileStore(root=root)
    return _store
