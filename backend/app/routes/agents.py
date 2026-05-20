"""Agents & council introspection."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..agents import ROLES, get_bus
from ..providers import get_registry

router = APIRouter(tags=["agents"])


@router.get("/agents/roles")
def list_roles() -> dict:
    return {
        "roles": [r.model_dump() for r in ROLES.values()],
    }


@router.get("/agents/models")
def list_models() -> dict:
    reg = get_registry()
    return {
        "providers": [p.name for p in reg.providers()],
        "models": [m.model_dump() for m in reg.all_models()],
    }


@router.websocket("/agents/events")
async def events_ws(ws: WebSocket) -> None:
    """Stream all council events to subscribers."""
    await ws.accept()
    bus = get_bus()
    q = await bus.subscribe()
    try:
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=15.0)
                await ws.send_text(ev.model_dump_json())
            except TimeoutError:
                await ws.send_text('{"kind":"system.log","actor":"system","content":"ping"}')
    except WebSocketDisconnect:
        pass
    finally:
        await bus.unsubscribe(q)
