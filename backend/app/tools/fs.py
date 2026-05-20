"""Filesystem tool — read/list/write within the user's home tree.

For sanity we resolve paths and reject anything that escapes the user's home
directory unless ``OVERLORD_ALLOW_ANYWHERE=1``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..log import get_logger
from .registry import Tool, ToolResult

log = get_logger(__name__)


def _resolve(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _allowed(p: Path) -> bool:
    if os.environ.get("OVERLORD_ALLOW_ANYWHERE") == "1":
        return True
    home = Path.home().resolve()
    try:
        p.relative_to(home)
        return True
    except ValueError:
        return False


class FilesystemTool(Tool):
    name = "fs"
    description = (
        "Read, write, list, or delete files under the user's home directory. "
        "Use action=read|write|append|list|delete."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "append", "list", "delete", "mkdir"],
            },
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["action", "path"],
    }
    requires_confirmation = True

    async def run(self, args: dict[str, Any]) -> ToolResult:
        action = args["action"]
        p = _resolve(args["path"])
        if not _allowed(p):
            return ToolResult(ok=False, output=f"path outside home not allowed: {p}")
        try:
            if action == "read":
                if not p.exists():
                    return ToolResult(ok=False, output="not found")
                data = p.read_text(encoding="utf-8", errors="replace")
                return ToolResult(ok=True, output=data[:32_000])
            if action == "list":
                if not p.exists() or not p.is_dir():
                    return ToolResult(ok=False, output="not a directory")
                items = sorted(c.name + ("/" if c.is_dir() else "") for c in p.iterdir())
                return ToolResult(ok=True, output="\n".join(items[:1000]))
            if action == "write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args.get("content", ""), encoding="utf-8")
                return ToolResult(ok=True, output=f"wrote {len(args.get('content',''))} chars")
            if action == "append":
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a", encoding="utf-8") as f:
                    f.write(args.get("content", ""))
                return ToolResult(ok=True, output="appended")
            if action == "delete":
                if p.is_file():
                    p.unlink()
                    return ToolResult(ok=True, output="deleted")
                return ToolResult(ok=False, output="not a regular file (refusing dir delete)")
            if action == "mkdir":
                p.mkdir(parents=True, exist_ok=True)
                return ToolResult(ok=True, output="created")
            return ToolResult(ok=False, output=f"unknown action {action}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"fs error: {e}")
