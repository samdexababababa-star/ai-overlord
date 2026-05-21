"""SiteAutoLearner — discovers a new site's structure end-to-end.

The learner walks a small state machine:

    OPENED → AWAITING_LOGIN → PROBING → CALIBRATING → READY (or FAILED)

Each step is async, idempotent and emits a structured progress event on the
shared :class:`MessageBus` so the UI can render a live trace. The same
state machine is used by the ``/web-ai/sites/{id}/learn`` route (background
task) and by an in-process call from the autonomy loop when a goal asks
"learn Gemini Web".
"""

from __future__ import annotations

import enum
import time
from typing import Any

from pydantic import BaseModel, Field

from ..agents.bus import Event, get_bus
from ..log import get_logger
from .presets import PRESETS_BY_ID, apply_preset
from .probe import ElementRole, SiteProbe
from .profiles import (
    ProfileHealth,
    ProfileStore,
    SiteCategory,
    SiteProfile,
    get_profile_store,
)

log = get_logger(__name__)


class LearnPhase(enum.StrEnum):
    OPENED = "opened"
    AWAITING_LOGIN = "awaiting_login"
    PROBING = "probing"
    CALIBRATING = "calibrating"
    READY = "ready"
    FAILED = "failed"


class LearnState(BaseModel):
    """Public snapshot of the learner's progress."""

    profile_id: str
    phase: LearnPhase = LearnPhase.OPENED
    started_at: float = Field(default_factory=time.time)
    last_update_at: float = Field(default_factory=time.time)
    notes: list[str] = Field(default_factory=list)
    error: str = ""
    discovered_selectors: dict[str, str] = Field(default_factory=dict)
    confidence: float = 0.0


LOGIN_HINTS = (
    "sign in", "log in", "login", "se connecter", "connexion",
    "continue with google", "continue with apple", "create account",
)


class SiteAutoLearner:
    """Discovers how to talk to a third-party AI site.

    Parameters
    ----------
    profile
        The :class:`SiteProfile` to enrich. The learner mutates and persists
        it through ``store.save`` between phases.
    store
        Profile store; defaults to the global singleton.
    probe
        Probing strategy; defaults to one configured for the profile's
        category.
    """

    def __init__(
        self,
        profile: SiteProfile,
        store: ProfileStore | None = None,
        probe: SiteProbe | None = None,
    ):
        self.profile = profile
        self.store = store or get_profile_store()
        self.probe = probe or SiteProbe(
            roles=list(SiteProbe.SOCIAL_ROLES)
            if profile.category == SiteCategory.SOCIAL
            else list(SiteProbe.AI_ROLES)
        )
        self.state = LearnState(profile_id=profile.id)

    # ------------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------------

    async def learn(self, page: Any) -> LearnState:
        """Drive the state machine against a Playwright-like page."""
        # Apply preset hints when nothing has been discovered yet.
        if self.profile.id in PRESETS_BY_ID and not self.profile.selectors.prompt_box:
            apply_preset(self.profile, PRESETS_BY_ID[self.profile.id])
            self.store.save(self.profile)

        await self._set_phase(LearnPhase.OPENED, "Page opened")

        # Step 1 — login check.
        login_required = await self._detect_login(page)
        if login_required:
            self.profile.auth.needs_login = True
            self.profile.health.status = ProfileHealth.NEEDS_LOGIN
            self.store.save(self.profile)
            await self._set_phase(
                LearnPhase.AWAITING_LOGIN,
                "Login required — confirm via HITL when done",
            )
            return self.state
        self.profile.auth.needs_login = False

        # Step 2 — probe.
        await self._set_phase(LearnPhase.PROBING, "Running DOM + heuristic probe")
        result = await self.probe.probe(page)
        if not result.picks:
            self.profile.health.status = ProfileHealth.BROKEN
            self.profile.health.last_error = "no candidate elements found"
            self.store.save(self.profile)
            return await self._fail("no candidate elements found")

        # Update selectors from picks.
        for role_name, picked in result.picks.items():
            setattr(self.profile.selectors, role_name, picked.selector)
        self.profile.selectors.confidence = result.confidence
        self.state.discovered_selectors = {r: p.selector for r, p in result.picks.items()}
        self.state.confidence = result.confidence
        self.store.save(self.profile)
        await self._set_phase(
            LearnPhase.CALIBRATING,
            f"Probed {result.snapshot_count} candidates, confidence={result.confidence:.2f}",
        )

        # Step 3 — calibration only makes sense for AI sites where we have a
        # round-trip we can verify. For social sites we stop after probing.
        if self.profile.category == SiteCategory.SOCIAL:
            self.profile.last_verified_at = time.time()
            self.profile.health.status = ProfileHealth.OK
            self.store.save(self.profile)
            await self._set_phase(LearnPhase.READY, "Social profile ready")
            return self.state

        # AI category — calibration done lazily by the first ask() call in
        # the test harness; here we just mark the profile usable as soon as
        # we have the minimum selector triplet (prompt + response).
        if self.profile.selectors.prompt_box and self.profile.selectors.response_root:
            self.profile.last_verified_at = time.time()
            self.profile.health.status = ProfileHealth.OK
            self.store.save(self.profile)
            await self._set_phase(LearnPhase.READY, "AI profile ready (calibration pending)")
            return self.state
        return await self._fail("missing selectors after probe")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _detect_login(self, page: Any) -> bool:
        """Heuristic: does the page text strongly suggest a login form?"""
        try:
            text = await page.evaluate(
                "() => (document.body && document.body.innerText || '').slice(0, 4000).toLowerCase()"
            )
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.auto_learner.text_fail", error=str(e)[:200])
            return False
        if not isinstance(text, str):
            return False
        if not any(hint in text for hint in LOGIN_HINTS):
            return False
        # Confirm there's *also* a password-style input.
        try:
            has_password = await page.evaluate(
                "() => Boolean(document.querySelector('input[type=password]'))"
            )
        except Exception:
            has_password = False
        return bool(has_password)

    async def _fail(self, reason: str) -> LearnState:
        self.state.phase = LearnPhase.FAILED
        self.state.error = reason
        self.state.last_update_at = time.time()
        self.profile.health.status = ProfileHealth.BROKEN
        self.profile.health.last_error = reason[:300]
        self.store.save(self.profile)
        await self._publish(f"FAILED — {reason}")
        return self.state

    async def _set_phase(self, phase: LearnPhase, message: str) -> None:
        self.state.phase = phase
        self.state.last_update_at = time.time()
        self.state.notes.append(message)
        await self._publish(message)

    async def _publish(self, message: str) -> None:
        bus = get_bus()
        await bus.publish(
            Event(
                kind="web_ai.learn",
                actor="auto_learner",
                content=message,
                meta={
                    "profile_id": self.profile.id,
                    "phase": self.state.phase.value,
                    "confidence": self.state.confidence,
                },
            )
        )


# Convenience: build a learner for a brand-new site URL.
def make_learner_for_url(
    url: str,
    label: str = "",
    category: SiteCategory = SiteCategory.AI,
    profile_id: str | None = None,
) -> SiteAutoLearner:
    store = get_profile_store()
    profile = store.upsert_from_url(url=url, label=label, category=category, profile_id=profile_id)
    return SiteAutoLearner(profile=profile, store=store)


# Re-export so callers don't have to know about the probe module too.
__all__ = [
    "ElementRole",
    "LearnPhase",
    "LearnState",
    "SiteAutoLearner",
    "make_learner_for_url",
]
