"""FastAPI app smoke tests."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_app_constructs():
    from backend.app.main import create_app

    app = create_app()
    routes = [getattr(r, "path", None) for r in app.routes]
    for expected in (
        "/health",
        "/onboarding/providers",
        "/onboarding/keys",
        "/chat/ask",
        "/chat/run",
        "/agents/roles",
        "/agents/models",
        "/agents/events",
        "/memory/episodic",
        "/tools",
    ):
        assert expected in routes, f"missing route {expected}"


@pytest.mark.asyncio
async def test_provider_info():
    from backend.app.routes.onboarding import providers_info

    info = providers_info()
    assert set(info.keys()) == {"mistral", "nvidia", "google", "groq"}
    for k, v in info.items():
        assert v["label"]
        assert v["console"].startswith("https://")
        assert v["steps"], k


@pytest.mark.asyncio
async def test_council_init():
    from backend.app.agents.council import Council

    c = Council()
    assert c.tools is not None
    assert c.router is not None


@pytest.mark.asyncio
async def test_bus_pubsub():
    from backend.app.agents.bus import Event, MessageBus

    bus = MessageBus()
    q = await bus.subscribe()
    await bus.publish(Event(kind="system.log", content="hello"))
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev.kind == "system.log"
    assert ev.content == "hello"
    await bus.unsubscribe(q)
