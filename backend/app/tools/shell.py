"""Shell execution tool.

For safety:
  * Disabled by default — must be enabled per-tool-call via UI confirmation.
  * Default timeout 30 s.
  * stdout/stderr truncated to 8 KB.

The frontend's confirmation dialog is the primary gate; do not rely on this
tool alone if you don't want arbitrary commands run.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
from typing import Any

from ..log import get_logger
from .registry import Tool, ToolResult

log = get_logger(__name__)


def _shell_cmd(command: str) -> list[str]:
    if os.name == "nt":
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", command]
    return ["bash", "-lc", command]


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run a shell command on the host (bash on Linux/macOS, PowerShell on Windows). "
        "Returns combined stdout/stderr and the exit code."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command line"},
            "cwd": {"type": "string", "description": "Working directory (optional)"},
            "timeout_seconds": {"type": "integer", "default": 30},
        },
        "required": ["command"],
    }
    requires_confirmation = True

    async def run(self, args: dict[str, Any]) -> ToolResult:
        cmd = args["command"]
        cwd = args.get("cwd") or None
        timeout = int(args.get("timeout_seconds", 30))
        log.info("shell.run", cmd=cmd[:120], cwd=cwd, timeout=timeout)
        try:
            proc = await asyncio.create_subprocess_exec(
                *_shell_cmd(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            text = (stdout or b"").decode("utf-8", "replace")
            return ToolResult(
                ok=(proc.returncode == 0),
                output=text[:8000],
                meta={"exit_code": proc.returncode, "cmd": shlex.join(_shell_cmd(cmd))},
            )
        except TimeoutError:
            with contextlib.suppress(Exception):
                proc.kill()
            return ToolResult(ok=False, output=f"timed out after {timeout}s")
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"shell error: {e}")
