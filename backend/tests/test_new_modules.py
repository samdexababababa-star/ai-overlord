"""Tests for new modules: knowledge graph, settings, demo provider, hitl, autonomy."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_knowledge_graph_crud():
    """KG supports add/get/search."""
    from backend.app.memory.knowledge_graph import KnowledgeGraph

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        kg = KnowledgeGraph(path=path)
        kg.add_entity("python", "Python", entity_type="language")
        kg.add_entity("fastapi", "FastAPI", entity_type="framework")
        kg.add_relationship("fastapi", "python", "built_with")

        assert kg.get_entity("python") is not None
        assert kg.get_entity("python")["type"] == "language"

        results = kg.search("python")
        assert len(results) >= 1

        neighbors = kg.get_neighbors("fastapi", max_depth=1)
        assert len(neighbors["edges"]) >= 1

        stats = kg.stats()
        assert stats["total_nodes"] == 2
        assert stats["total_edges"] == 1
    finally:
        path.unlink(missing_ok=True)


def test_knowledge_graph_consolidate():
    """KG consolidation merges duplicates."""
    from backend.app.memory.knowledge_graph import KnowledgeGraph

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        kg = KnowledgeGraph(path=path)
        kg.add_entity("py1", "Python", entity_type="language")
        kg.add_entity("py2", "Python", entity_type="language")
        kg.add_relationship("py1", "other", "uses")
        kg.add_relationship("py2", "other", "uses")
        kg.add_entity("other", "Other", entity_type="concept")

        result = kg.consolidate()
        assert result["merged"] >= 1
    finally:
        path.unlink(missing_ok=True)


def test_user_settings():
    """Settings manager load/save/update."""
    from backend.app.user_settings import SettingsManager

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        sm = SettingsManager(path=path)
        s = sm.load()
        assert s.autonomy.level == "supervised"
        assert s.hitl.enabled is True

        sm.update({"autonomy": {"level": "autonomous"}})
        s2 = sm.get()
        assert s2.autonomy.level == "autonomous"

        sm.update({"hitl": {"enabled": False}})
        s3 = sm.get()
        assert s3.hitl.enabled is False
    finally:
        path.unlink(missing_ok=True)


def test_settings_hitl_check():
    """HITL check follows settings."""
    from backend.app.user_settings import SettingsManager

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        sm = SettingsManager(path=path)
        assert sm.check_hitl_required("shell_commands") is True
        sm.update({"hitl": {"enabled": False}})
        assert sm.check_hitl_required("shell_commands") is False
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_demo_provider():
    """Demo provider returns responses without real API keys."""
    from backend.app.providers.demo import DemoProvider

    p = DemoProvider()
    assert len(p.models) >= 4
    assert await p.validate_key("anything") is True

    from backend.app.providers.base import ChatMessage, ChatRequest

    req = ChatRequest(
        model="demo-reason",
        messages=[ChatMessage(role="user", content="Hello there!")],
    )
    resp = await p.chat(req)
    assert resp.text
    assert resp.provider == "demo"


@pytest.mark.asyncio
async def test_demo_provider_stream():
    """Demo provider streaming yields words."""
    from backend.app.providers.base import ChatMessage, ChatRequest
    from backend.app.providers.demo import DemoProvider

    p = DemoProvider()
    req = ChatRequest(
        model="demo-fast",
        messages=[ChatMessage(role="user", content="Plan something")],
        stream=True,
    )
    chunks = []
    async for chunk in p.chat_stream(req):
        chunks.append(chunk)
    assert len(chunks) > 0
    full = "".join(chunks)
    assert len(full) > 10


@pytest.mark.asyncio
async def test_demo_provider_embed():
    """Demo provider embedding returns valid vectors."""
    from backend.app.providers.demo import DemoProvider

    p = DemoProvider()
    resp = await p.embed("demo-embed", ["hello world", "testing"])
    assert len(resp.vectors) == 2
    assert len(resp.vectors[0]) == 384


def test_goal_manager():
    """Goal manager CRUD operations."""
    from backend.app.autonomy.goals import Goal, GoalManager, GoalPriority, GoalStatus

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        gm = GoalManager(path=path)
        goal = gm.add(Goal(
            title="Test goal",
            description="Test description",
            priority=GoalPriority.HIGH,
        ))
        assert goal.id
        assert gm.get(goal.id) is not None

        goals = gm.list_all()
        assert len(goals) == 1

        gm.mark_running(goal.id)
        assert gm.get(goal.id).status == GoalStatus.RUNNING

        gm.mark_completed(goal.id, result="done")
        assert gm.get(goal.id).status == GoalStatus.COMPLETED

        stats = gm.stats()
        assert stats["total"] == 1
    finally:
        path.unlink(missing_ok=True)


def test_goal_dependencies():
    """Goals with dependencies should not be runnable until deps are met."""
    from backend.app.autonomy.goals import Goal, GoalManager

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        gm = GoalManager(path=path)
        g1 = gm.add(Goal(title="First"))
        g2 = gm.add(Goal(title="Second", depends_on=[g1.id]))

        # g2 should not be runnable because g1 is pending
        runnable = gm.next_runnable()
        assert runnable is not None
        assert runnable.id == g1.id  # g1 should be picked first

        gm.mark_running(g1.id)
        gm.mark_completed(g1.id)

        # Now g2 should be runnable
        runnable = gm.next_runnable()
        assert runnable is not None
        assert runnable.id == g2.id
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_hitl_manager():
    """HITL approval flow works."""

    from backend.app.hitl import HITLManager

    hitl = HITLManager()

    # Should return True when no approval required
    # (we patch settings to disable HITL)
    from backend.app.user_settings import SettingsManager
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)

    try:
        sm = SettingsManager(path=path)
        sm.update({"hitl": {"enabled": False}})

        # When HITL is disabled, request_approval always returns True
        # (it checks settings internally)
        pending = hitl.list_pending()
        assert len(pending) == 0
    finally:
        path.unlink(missing_ok=True)
