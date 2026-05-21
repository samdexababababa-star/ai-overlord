"""Tool registry + base classes."""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel

from ..providers.base import ToolSpec


class ToolResult(BaseModel):
    ok: bool
    output: str
    meta: dict[str, Any] = {}


class Tool(abc.ABC):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    # If True, must be confirmed in UI before running (overridable per-tool).
    requires_confirmation: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, parameters=self.parameters
        )

    @abc.abstractmethod
    async def run(self, args: dict[str, Any]) -> ToolResult:  # pragma: no cover
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def specs(self) -> list[ToolSpec]:
        return [t.spec() for t in self._tools.values()]


_registry: ToolRegistry | None = None


def get_tools() -> ToolRegistry:
    global _registry
    if _registry is None:
        from .browser import BrowserTool
        from .fs import FilesystemTool
        from .shell import ShellTool
        from .vision import ScreenVisionTool
        from .web_ai import WebAITool
        from .web_search import WebSearchTool

        _registry = ToolRegistry()
        _registry.register(WebSearchTool())
        _registry.register(BrowserTool())
        _registry.register(ShellTool())
        _registry.register(FilesystemTool())
        _registry.register(ScreenVisionTool())
        _registry.register(WebAITool())
    return _registry
