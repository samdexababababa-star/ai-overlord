"""Tools available to the agents.

Each tool exposes a `name`, `description`, JSON-schema `parameters`, and an
async `run(args)` callable. The :class:`ToolRegistry` collects them and
publishes :class:`ToolSpec` instances for the providers' function-calling
APIs.
"""

from __future__ import annotations

from .browser import BrowserTool
from .fs import FilesystemTool
from .registry import Tool, ToolRegistry, get_tools
from .shell import ShellTool
from .vision import ScreenVisionTool
from .web_ai import WebAITool
from .web_search import WebSearchTool

__all__ = [
    "BrowserTool",
    "FilesystemTool",
    "ScreenVisionTool",
    "ShellTool",
    "Tool",
    "ToolRegistry",
    "WebAITool",
    "WebSearchTool",
    "get_tools",
]
