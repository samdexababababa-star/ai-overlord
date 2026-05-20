"""Screen vision tool — captures a screenshot and (optionally) describes it.

Captures with ``mss`` (cross-platform). If a vision-capable model is available
through the router, sends the image for description.
"""

from __future__ import annotations

import base64
import io
from typing import Any

from ..log import get_logger
from .registry import Tool, ToolResult

log = get_logger(__name__)


class ScreenVisionTool(Tool):
    name = "screen_vision"
    description = (
        "Capture a screenshot of the user's primary display. Optionally describe it "
        "by routing through a vision-capable model. action=capture|describe."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["capture", "describe"], "default": "capture"},
            "prompt": {
                "type": "string",
                "description": "What to look for in the image (describe only)",
                "default": "Describe what is on the screen.",
            },
        },
        "required": [],
    }

    def _capture_png(self) -> bytes:
        import mss  # type: ignore
        from PIL import Image  # type: ignore

        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

    async def run(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "capture")
        try:
            png = self._capture_png()
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"capture error: {e}")
        b64 = base64.b64encode(png).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        if action == "capture":
            return ToolResult(
                ok=True,
                output=f"captured screenshot ({len(png)} bytes)",
                meta={"image_data_url": data_url},
            )
        # describe
        from ..providers import ChatMessage, TaskProfile, get_registry
        from ..providers.router import ModelRouter

        prompt = args.get("prompt") or "Describe what is on the screen."
        router = ModelRouter(get_registry())
        try:
            resp = await router.chat(
                [ChatMessage(role="user", content=prompt, images=[data_url])],
                profile=TaskProfile(capability="vision"),
            )
            return ToolResult(
                ok=True,
                output=resp.text,
                meta={"image_data_url": data_url, "model": resp.model, "provider": resp.provider},
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, output=f"vision routing failed: {e}")
