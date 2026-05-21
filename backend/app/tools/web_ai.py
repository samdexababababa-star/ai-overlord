"""Web-AI Mesh tool — function-callable bridge to learned web AIs.

This is the seam the Council uses when it decides "ask Gemini Web" or
"ask Le Chat" mid-reasoning. Without this tool, the WebAIProvider is only
reachable through the ModelRouter — this tool makes it usable through
plain function-calling too (e.g. by the Executor agent).

Actions
-------
- ``list`` — return all healthy AI profiles the Council can talk to.
- ``ask`` — send ``prompt`` to the named ``site_id``, return the reply.
- ``ask_each`` — broadcast the same prompt to multiple sites in parallel
  and return all answers (useful for Oracle / debate-style aggregation).
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..hitl import get_hitl
from ..log import get_logger
from ..user_settings import get_settings_manager
from ..web_ai.client import WebAIClient
from ..web_ai.profiles import ProfileHealth, SiteCategory, get_profile_store
from .registry import Tool, ToolResult

log = get_logger(__name__)


class WebAITool(Tool):
    name = "web_ai"
    description = (
        "Talk to a registered third-party AI web UI (ChatGPT, Gemini, Claude, "
        "Le Chat, Perplexity, …) through the controlled Chrome instance. "
        "Use action=list to discover available sites, then action=ask to "
        "send a prompt."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "ask", "ask_each"],
                "default": "list",
            },
            "site_id": {
                "type": "string",
                "description": "Profile id (e.g. 'gemini-web'); required for ask.",
            },
            "site_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Targets for ask_each.",
            },
            "prompt": {
                "type": "string",
                "description": "Prompt to send to the web AI.",
            },
            "timeout_ms": {"type": "integer", "default": 90000},
        },
        "required": ["action"],
    }
    requires_confirmation = False

    async def run(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "list")
        if action == "list":
            return self._list()
        if action == "ask":
            return await self._ask(args)
        if action == "ask_each":
            return await self._ask_each(args)
        return ToolResult(ok=False, output=f"unknown action {action}")

    # ------------------------------------------------------------------

    def _list(self) -> ToolResult:
        store = get_profile_store()
        rows = []
        for p in store.list_all(category=SiteCategory.AI):
            rows.append({
                "id": p.id,
                "label": p.label,
                "url": p.url,
                "status": p.health.status.value,
                "confidence": p.selectors.confidence,
                "include_in_council": p.include_in_council,
            })
        text_lines = [
            f"- {r['id']} ({r['label']}) — {r['status']} (conf={r['confidence']:.2f})"
            for r in rows
        ]
        return ToolResult(
            ok=True,
            output="\n".join(text_lines) if text_lines else "No web-AI profiles registered.",
            meta={"sites": rows},
        )

    async def _ask(self, args: dict[str, Any]) -> ToolResult:
        site_id = args.get("site_id")
        prompt = args.get("prompt") or ""
        if not site_id or not prompt:
            return ToolResult(ok=False, output="ask requires both site_id and prompt")
        store = get_profile_store()
        profile = store.get(site_id)
        if not profile:
            return ToolResult(ok=False, output=f"unknown site {site_id}")
        if profile.health.status == ProfileHealth.NEEDS_LOGIN:
            return ToolResult(ok=False, output=f"{site_id} needs login first")

        if get_settings_manager().check_hitl_required("web_ai_send"):
            approved = await get_hitl().request_approval(
                action_type="web_ai_send",
                description=f"Send to {profile.label}: {prompt[:120]}",
                details={"site_id": site_id, "prompt": prompt},
                risk_level="low",
                timeout=120.0,
            )
            if not approved:
                return ToolResult(ok=False, output="HITL rejected web_ai_send")

        client = WebAIClient(profile=profile, store=store)
        result = await client.ask(prompt, timeout_ms=int(args.get("timeout_ms", 90_000)))
        return ToolResult(
            ok=result.ok,
            output=result.text or result.error or "",
            meta={
                "site_id": site_id,
                "elapsed_ms": result.elapsed_ms,
                "retries": result.retries,
                "selector_repaired": result.selector_repaired,
                "error": result.error,
            },
        )

    async def _ask_each(self, args: dict[str, Any]) -> ToolResult:
        sites: list[str] = list(args.get("site_ids") or [])
        prompt = args.get("prompt") or ""
        if not sites or not prompt:
            return ToolResult(ok=False, output="ask_each requires site_ids and prompt")
        # Fan out, await all.
        per_call_args = [
            {"action": "ask", "site_id": s, "prompt": prompt, "timeout_ms": args.get("timeout_ms")}
            for s in sites
        ]
        results = await asyncio.gather(*(self._ask(a) for a in per_call_args))
        merged = "\n\n".join(
            f"### {s}\n{r.output[:2000]}" for s, r in zip(sites, results, strict=False)
        )
        return ToolResult(
            ok=any(r.ok for r in results),
            output=merged,
            meta={
                "per_site": [
                    {"site": s, "ok": r.ok, "meta": r.meta}
                    for s, r in zip(sites, results, strict=False)
                ]
            },
        )
