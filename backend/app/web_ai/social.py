"""SocialAdapter — compose / post / read on social platforms.

This is the social half of the Web-AI Mesh. It reuses the same
:class:`SiteProfile` / :class:`SiteProbe` machinery — the only differences
are the roles we look for (``compose_box``, ``post_button``, ``feed_item``,
``media_input``) and the HITL gates that fire before any external write.

By default every state-changing operation is HITL-gated through the
``social_post`` / ``social_dm`` categories. Read-only operations (feed
scrape) are not gated.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from ..agents.bus import Event, get_bus
from ..hitl import get_hitl
from ..log import get_logger
from ..user_settings import get_settings_manager
from .client import PageLike
from .profiles import ProfileStore, SiteProfile, get_profile_store

log = get_logger(__name__)


class PostRequest(BaseModel):
    text: str
    media_paths: list[str] = Field(default_factory=list)


class PostResult(BaseModel):
    ok: bool
    text: str
    posted_at: float = Field(default_factory=time.time)
    error: str = ""
    awaited_hitl: bool = False
    hitl_rejected: bool = False


class FeedItem(BaseModel):
    text: str
    author: str = ""
    timestamp: str = ""


class FeedResult(BaseModel):
    items: list[FeedItem] = Field(default_factory=list)


class SocialAdapter:
    """High-level driver for one social :class:`SiteProfile`."""

    def __init__(
        self,
        profile: SiteProfile,
        store: ProfileStore | None = None,
    ):
        self.profile = profile
        self.store = store or get_profile_store()

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def read_feed(self, page: PageLike, limit: int = 20) -> FeedResult:
        sel = self.profile.selectors.feed_item
        if not sel:
            return FeedResult()
        try:
            rows = await page.evaluate(
                "({sel, limit}) => Array.from(document.querySelectorAll(sel))"
                ".slice(0, limit).map(e => ({"
                "  text: (e.innerText || e.textContent || '').trim().slice(0, 1000),"
                "  author: (e.querySelector('[data-testid=User-Name]')?.innerText "
                "         || e.querySelector('a[href*=\"/in/\"]')?.innerText || '').trim().slice(0, 120),"
                "  timestamp: (e.querySelector('time')?.getAttribute('datetime') || '').slice(0, 64),"
                "}))",
                {"sel": sel, "limit": limit},
            )
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.social.read_fail", profile=self.profile.id, error=str(e)[:200])
            return FeedResult()
        items = [FeedItem(**r) for r in rows if r.get("text")]
        await get_bus().publish(
            Event(
                kind="web_ai.social.read",
                actor=self.profile.id,
                content=f"read {len(items)} feed items",
                meta={"profile_id": self.profile.id, "count": len(items)},
            )
        )
        return FeedResult(items=items)

    # ------------------------------------------------------------------
    # Write path (HITL-gated)
    # ------------------------------------------------------------------

    def needs_approval(self, category: str = "social_post") -> bool:
        return get_settings_manager().check_hitl_required(category)

    async def post(
        self,
        page: PageLike,
        request: PostRequest,
        category: str = "social_post",
        timeout: float = 300.0,
    ) -> PostResult:
        """Gated entry point: ask HITL if required, then execute.

        Returns immediately with ``hitl_rejected=True`` if the user did not
        approve in time.
        """
        hitl = get_hitl()
        awaited = False
        if self.needs_approval(category):
            awaited = True
            approved = await hitl.request_approval(
                action_type=category,
                description=(
                    f"Post on {self.profile.label}: "
                    + (request.text[:140] + ("…" if len(request.text) > 140 else ""))
                ),
                details={
                    "profile_id": self.profile.id,
                    "text": request.text,
                    "media_paths": request.media_paths,
                },
                risk_level="medium",
                timeout=timeout,
            )
            if not approved:
                return PostResult(
                    ok=False,
                    text="",
                    error="HITL rejected or timed out",
                    awaited_hitl=True,
                    hitl_rejected=True,
                )
        result = await self.execute_post(page, request)
        result.awaited_hitl = awaited
        return result

    async def execute_post(self, page: PageLike, request: PostRequest) -> PostResult:
        """Actually run the post — must only be called after HITL approval."""
        sel = self.profile.selectors
        if not sel.compose_box or not sel.post_button:
            return PostResult(ok=False, text="", error="compose/post selectors missing")
        try:
            ok = await page.evaluate(
                "({sel, text}) => {"
                "  const el = document.querySelector(sel);"
                "  if (!el) return false;"
                "  el.focus();"
                "  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {"
                "    el.value = text;"
                "    el.dispatchEvent(new Event('input', {bubbles: true}));"
                "  } else {"
                "    el.textContent = text;"
                "    el.dispatchEvent(new InputEvent('input', {bubbles: true, data: text}));"
                "  }"
                "  return true;"
                "}",
                {"sel": sel.compose_box, "text": request.text},
            )
            if not ok:
                return PostResult(ok=False, text="", error="compose_box not found")
            if request.media_paths and sel.media_input:
                # Caller is responsible for honouring this hook via Playwright's
                # set_input_files API — we expose a method so tests can detect it.
                set_files = getattr(page, "set_input_files", None)
                if callable(set_files):
                    await set_files(sel.media_input, request.media_paths)
            await page.click(sel.post_button, timeout=5000)
            await get_bus().publish(
                Event(
                    kind="web_ai.social.posted",
                    actor=self.profile.id,
                    content=request.text[:140],
                    meta={"profile_id": self.profile.id, "len": len(request.text)},
                )
            )
            return PostResult(ok=True, text=request.text)
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.social.post_fail", error=str(e)[:300])
            return PostResult(ok=False, text="", error=str(e)[:300])
