"""Web search tool.

Uses DuckDuckGo by default (no API key needed). Optional Tavily API key
(``TAVILY_API_KEY``) gives higher-quality results when configured.
"""

from __future__ import annotations

import os
from typing import Any

from ..log import get_logger
from .registry import Tool, ToolResult

log = get_logger(__name__)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the public web for a query. Returns top results with title, URL, and a snippet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {
                "type": "integer",
                "description": "How many results to return (1-10)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def run(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        n = int(args.get("max_results", 5))
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            return await self._tavily(query, n, tavily_key)
        return await self._ddg(query, n)

    async def _ddg(self, query: str, n: int) -> ToolResult:
        try:
            from duckduckgo_search import DDGS  # type: ignore

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=n):
                    results.append(
                        f"- {r.get('title')} ({r.get('href')})\n  {r.get('body', '')[:300]}"
                    )
            if not results:
                return ToolResult(ok=False, output="no results")
            return ToolResult(ok=True, output="\n".join(results), meta={"engine": "ddg"})
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"web_search error: {e}")

    async def _tavily(self, query: str, n: int, key: str) -> ToolResult:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    "https://api.tavily.com/search",
                    json={"api_key": key, "query": query, "max_results": n},
                )
                r.raise_for_status()
                data = r.json()
                lines = []
                for item in data.get("results", []):
                    lines.append(
                        f"- {item.get('title')} ({item.get('url')})\n  "
                        f"{item.get('content', '')[:300]}"
                    )
                return ToolResult(
                    ok=True,
                    output="\n".join(lines) or "no results",
                    meta={"engine": "tavily"},
                )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"tavily error: {e}")
