"""In-process asyncio message bus.

Used by the council to publish trace events that the frontend subscribes to
over WebSocket — this is how the virtual-office view animates agent activity.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

EventKind = Literal[
    "agent.start",
    "agent.thinking",
    "agent.message",
    "agent.tool_call",
    "agent.tool_result",
    "agent.finish",
    "council.start",
    "council.finish",
    "user.message",
    "system.log",
    "system.notice",
    "web_ai.learn",
    "web_ai.ask",
    "web_ai.social.read",
    "web_ai.social.posted",
]


class Event(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = Field(default_factory=time.time)
    kind: EventKind
    actor: str = "system"
    content: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class MessageBus:
    """Pub-sub bus where each subscriber gets its own queue."""

    def __init__(self) -> None:
        self._subs: list[asyncio.Queue[Event]] = []
        self._lock = asyncio.Lock()
        self._history: list[Event] = []
        self._history_cap = 1_000

    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_cap:
                self._history = self._history[-self._history_cap :]
            subs = list(self._subs)
        for q in subs:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)

    async def subscribe(self) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=1024)
        async with self._lock:
            self._subs.append(q)
            # Replay last 100 events so new subscribers get context
            for ev in self._history[-100:]:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:  # noqa: PERF203
                    break
        return q

    async def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        async with self._lock:
            if q in self._subs:
                self._subs.remove(q)


_bus: MessageBus | None = None


def get_bus() -> MessageBus:
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
