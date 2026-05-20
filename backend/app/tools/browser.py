"""Browser control tool — attaches to a running Chrome over CDP.

Expects Chrome to be launched with ``--remote-debugging-port=29229`` (or
whatever ``OVERLORD_CHROME_CDP_URL`` is set to). See ``docs/architecture.md``
for the bundled launcher.

Operations: open URL, click selector, type, evaluate JS, snapshot text.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ..config import settings
from ..log import get_logger
from .registry import Tool, ToolResult

log = get_logger(__name__)


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Control a Chrome browser attached via CDP. Use action=open|click|type|read|eval|screenshot."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "click", "type", "read", "eval", "screenshot", "close"],
            },
            "url": {"type": "string"},
            "selector": {"type": "string"},
            "text": {"type": "string"},
            "script": {"type": "string"},
            "timeout_ms": {"type": "integer", "default": 10000},
        },
        "required": ["action"],
    }
    requires_confirmation = False

    async def _browser(self):
        from playwright.async_api import async_playwright  # noqa: PLC0415

        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(settings.chrome_cdp_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return pw, browser, page

    async def run(self, args: dict[str, Any]) -> ToolResult:
        action = args["action"]
        timeout = int(args.get("timeout_ms", 10_000))
        try:
            pw, browser, page = await self._browser()
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False,
                output=(
                    f"could not attach to Chrome at {settings.chrome_cdp_url}: {e}. "
                    "Launch Chrome with --remote-debugging-port=29229."
                ),
            )
        try:
            if action == "open":
                await page.goto(args["url"], timeout=timeout)
                return ToolResult(ok=True, output=f"opened {args['url']}")
            if action == "click":
                await page.click(args["selector"], timeout=timeout)
                return ToolResult(ok=True, output=f"clicked {args['selector']}")
            if action == "type":
                await page.fill(args["selector"], args["text"], timeout=timeout)
                return ToolResult(ok=True, output=f"typed into {args['selector']}")
            if action == "read":
                text = await page.evaluate("() => document.body.innerText")
                return ToolResult(ok=True, output=text[:8000])
            if action == "eval":
                result = await page.evaluate(args["script"])
                return ToolResult(ok=True, output=str(result)[:8000])
            if action == "screenshot":
                png = await page.screenshot(full_page=False)
                import base64

                b64 = base64.b64encode(png).decode("ascii")
                return ToolResult(
                    ok=True,
                    output=f"data:image/png;base64,{b64[:200]}…",
                    meta={"image_b64": b64},
                )
            if action == "close":
                await page.close()
                return ToolResult(ok=True, output="closed page")
            return ToolResult(ok=False, output=f"unknown action {action}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"browser error: {e}")
        finally:
            with contextlib.suppress(Exception):
                await browser.close()
            with contextlib.suppress(Exception):
                await pw.stop()
