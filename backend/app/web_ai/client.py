"""WebAIClient — send a prompt to a learned web-AI and return its reply.

Given a :class:`SiteProfile`, the client attaches Playwright to the running
Chrome over CDP (port configured via ``settings.chrome_cdp_url``), focuses
the prompt box, types the message, submits, polls the response root until
it stabilises, then extracts the assistant's last reply.

The actual Playwright interaction is wrapped in tiny seams (``_focus``,
``_type``, ``_submit``, ``_read_response``, ``_settle_wait``) so the entire
state machine can be exercised against an in-memory ``FakePage`` in tests
without spawning a real browser.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, Protocol

from pydantic import BaseModel

from ..config import settings
from ..log import get_logger
from .probe import SiteProbe
from .profiles import ProfileStore, SiteProfile, get_profile_store

log = get_logger(__name__)


class AskResult(BaseModel):
    ok: bool
    text: str
    elapsed_ms: int
    retries: int = 0
    selector_repaired: bool = False
    error: str = ""


class PageLike(Protocol):
    """Subset of Playwright's Page used by the client (for testability)."""

    async def goto(self, url: str, **kwargs: Any) -> Any: ...
    async def evaluate(self, script: str, *args: Any) -> Any: ...
    async def fill(self, selector: str, value: str, **kwargs: Any) -> Any: ...
    async def click(self, selector: str, **kwargs: Any) -> Any: ...
    async def keyboard_press(self, key: str) -> Any: ...
    async def url(self) -> str: ...


class WebAIClient:
    """High-level driver that turns a profile into a callable AI."""

    def __init__(
        self,
        profile: SiteProfile,
        store: ProfileStore | None = None,
        probe: SiteProbe | None = None,
        chrome_cdp_url: str | None = None,
    ):
        self.profile = profile
        self.store = store or get_profile_store()
        self.probe = probe or SiteProbe(roles=list(SiteProbe.AI_ROLES))
        self.chrome_cdp_url = chrome_cdp_url or settings.chrome_cdp_url

    # ------------------------------------------------------------------
    # High-level entrypoint
    # ------------------------------------------------------------------

    async def ask(self, prompt: str, timeout_ms: int | None = None) -> AskResult:
        """Send ``prompt`` to the site and return the assistant's reply."""
        timeout = timeout_ms or self.profile.stream_settle.max_ms
        start = time.time()
        result = await self._ask_once(prompt, timeout, attempt=0)
        if not result.ok:
            # Self-heal: re-probe the page, update selectors, retry once.
            log.info(
                "web_ai.client.retry_after_heal",
                profile=self.profile.id,
                error=result.error,
            )
            try:
                async with self._attached_page() as page:
                    snapshot = await self.probe.probe(page)
                if "prompt_box" in snapshot.picks:
                    self.profile.selectors.prompt_box = snapshot.picks["prompt_box"].selector
                if "send_button" in snapshot.picks:
                    self.profile.selectors.send_button = snapshot.picks["send_button"].selector
                if "response_root" in snapshot.picks:
                    self.profile.selectors.response_root = snapshot.picks["response_root"].selector
                self.profile.selectors.confidence = snapshot.confidence
                self.store.save(self.profile)
                retried = await self._ask_once(prompt, timeout, attempt=1)
                retried.selector_repaired = True
                retried.elapsed_ms = int((time.time() - start) * 1000)
                if retried.ok:
                    self.store.mark_success(self.profile.id)
                else:
                    self.store.mark_failure(self.profile.id, retried.error)
                return retried
            except Exception as e:  # noqa: BLE001
                err = f"self-heal failed: {e}"
                self.store.mark_failure(self.profile.id, err)
                return AskResult(
                    ok=False,
                    text="",
                    elapsed_ms=int((time.time() - start) * 1000),
                    retries=1,
                    error=err,
                )
        self.store.mark_success(self.profile.id)
        result.elapsed_ms = int((time.time() - start) * 1000)
        return result

    # ------------------------------------------------------------------
    # Single attempt (page-aware logic split out so tests can drive it)
    # ------------------------------------------------------------------

    async def _ask_once(self, prompt: str, timeout_ms: int, attempt: int) -> AskResult:
        try:
            async with self._attached_page() as page:
                return await self._drive_page(page, prompt, timeout_ms, attempt)
        except Exception as e:  # noqa: BLE001
            return AskResult(
                ok=False,
                text="",
                elapsed_ms=0,
                retries=attempt,
                error=str(e)[:300],
            )

    async def drive_page(
        self,
        page: PageLike,
        prompt: str,
        timeout_ms: int | None = None,
        attempt: int = 0,
    ) -> AskResult:
        """Public test seam — drives an externally supplied page."""
        timeout = timeout_ms or self.profile.stream_settle.max_ms
        return await self._drive_page(page, prompt, timeout, attempt)

    async def _drive_page(
        self,
        page: PageLike,
        prompt: str,
        timeout_ms: int,
        attempt: int,
    ) -> AskResult:
        prof = self.profile
        if not prof.selectors.prompt_box:
            return AskResult(ok=False, text="", elapsed_ms=0, retries=attempt, error="no prompt_box selector")

        # Step 0: navigate if we're not on the right page already.
        try:
            current = await page.url() if callable(getattr(page, "url", None)) else page.url  # type: ignore[union-attr]
        except Exception:
            current = ""
        if prof.host and prof.host not in str(current or ""):
            await page.goto(prof.url, wait_until="domcontentloaded", timeout=timeout_ms)

        # Step 1: focus + type into the prompt box.
        ok_focus = await self._focus(page, prof.selectors.prompt_box)
        if not ok_focus:
            return AskResult(ok=False, text="", elapsed_ms=0, retries=attempt, error="prompt_box not focusable")
        await self._type(page, prof.selectors.prompt_box, prompt)

        # Step 2: submit.
        ok_submit = await self._submit(page, prof)
        if not ok_submit:
            return AskResult(ok=False, text="", elapsed_ms=0, retries=attempt, error="submit failed")

        # Step 3: wait for response root to stabilise.
        text, stable = await self._wait_for_settle(page, prof)
        if not stable:
            return AskResult(ok=False, text=text, elapsed_ms=0, retries=attempt, error="response never settled")
        return AskResult(ok=True, text=text, elapsed_ms=0, retries=attempt)

    # ------------------------------------------------------------------
    # Page operation seams (overridden by tests with simple fakes)
    # ------------------------------------------------------------------

    async def _focus(self, page: PageLike, selector: str) -> bool:
        try:
            ok = await page.evaluate(
                "(sel) => { const e = document.querySelector(sel); if (!e) return false; "
                "e.focus(); return true; }",
                selector,
            )
            return bool(ok)
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.client.focus_fail", selector=selector, error=str(e)[:200])
            return False

    async def _type(self, page: PageLike, selector: str, text: str) -> None:
        # contenteditable can't be filled via Playwright's fill(); use JS.
        await page.evaluate(
            "({sel, text}) => {"
            "  const el = document.querySelector(sel);"
            "  if (!el) return false;"
            "  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {"
            "    el.focus();"
            "    el.value = text;"
            "    el.dispatchEvent(new Event('input', {bubbles: true}));"
            "    el.dispatchEvent(new Event('change', {bubbles: true}));"
            "  } else {"
            "    el.focus();"
            "    el.textContent = text;"
            "    el.dispatchEvent(new InputEvent('input', {bubbles: true, data: text}));"
            "  }"
            "  return true;"
            "}",
            {"sel": selector, "text": text},
        )

    async def _submit(self, page: PageLike, profile: SiteProfile) -> bool:
        try:
            if profile.submit.mode == "click" and profile.selectors.send_button:
                await page.click(profile.selectors.send_button, timeout=5000)
                return True
            # Keyboard mode (default).
            key = profile.submit.key or "Enter"
            modifiers = profile.submit.modifiers
            combo = "+".join([*modifiers, key]) if modifiers else key
            press = getattr(page, "keyboard_press", None)
            if callable(press):
                await press(combo)
                return True
            # Fallback for the real Playwright Page object (has page.keyboard.press()).
            kb = getattr(page, "keyboard", None)
            if kb is not None:
                await kb.press(combo)
                return True
            # Last-ditch: click the send button even though submit.mode wasn't 'click'.
            if profile.selectors.send_button:
                await page.click(profile.selectors.send_button, timeout=5000)
                return True
            return False
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.client.submit_fail", error=str(e)[:200])
            return False

    async def _read_response(self, page: PageLike, selector: str) -> str:
        if not selector:
            return ""
        try:
            return await page.evaluate(
                "(sel) => { const e = document.querySelector(sel); "
                "return e ? (e.innerText || e.textContent || '') : ''; }",
                selector,
            ) or ""
        except Exception as e:  # noqa: BLE001
            log.warning("web_ai.client.read_fail", selector=selector, error=str(e)[:200])
            return ""

    async def _wait_for_settle(
        self,
        page: PageLike,
        profile: SiteProfile,
    ) -> tuple[str, bool]:
        cfg = profile.stream_settle
        deadline = time.time() + cfg.max_ms / 1000
        last = ""
        stable_count = 0
        while time.time() < deadline:
            text = await self._read_response(page, profile.selectors.response_root)
            if text and text == last:
                stable_count += 1
                if stable_count >= cfg.stable_cycles:
                    return text, True
            else:
                stable_count = 0 if text != last else stable_count
                last = text
            await asyncio.sleep(cfg.poll_ms / 1000)
        return last, False

    # ------------------------------------------------------------------
    # Playwright attach (skipped in tests by injecting a custom drive_page)
    # ------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def _attached_page(self):
        from playwright.async_api import async_playwright  # noqa: PLC0415

        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(self.chrome_cdp_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            yield page
        finally:
            with contextlib.suppress(Exception):
                await browser.close()
            with contextlib.suppress(Exception):
                await pw.stop()
