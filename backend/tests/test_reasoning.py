"""Tests for the reasoning engine modules."""

from __future__ import annotations

from backend.app.reasoning.deliberate import (
    DeliberateReasoner,
    Strategy,
)


def test_complexity_simple():
    """A short factual question should be classified as direct."""
    from backend.app.providers.registry import get_registry
    from backend.app.providers.router import ModelRouter

    reg = get_registry()
    router = ModelRouter(reg)
    reasoner = DeliberateReasoner(router)
    result = reasoner.analyze_complexity("What is 2+2?")
    assert result.estimated_difficulty < 0.3
    assert result.recommended_strategy in (Strategy.DIRECT, Strategy.REFLEXION)


def test_complexity_decomposition():
    """A complex multi-step task should suggest decomposition."""
    from backend.app.providers.registry import get_registry
    from backend.app.providers.router import ModelRouter

    reg = get_registry()
    router = ModelRouter(reg)
    reasoner = DeliberateReasoner(router)
    result = reasoner.analyze_complexity(
        "Analyze the pros and cons of different database architectures, "
        "then design an optimal schema for a social media application. "
        "Compare PostgreSQL vs MongoDB for this use case."
    )
    assert result.estimated_difficulty > 0.3
    assert result.requires_decomposition or result.requires_debate


def test_complexity_safety():
    """Safety-sensitive content should flag as such."""
    from backend.app.providers.registry import get_registry
    from backend.app.providers.router import ModelRouter

    reg = get_registry()
    router = ModelRouter(reg)
    reasoner = DeliberateReasoner(router)
    result = reasoner.analyze_complexity(
        "What are the financial risks of investing in cryptocurrency for children?"
    )
    assert result.safety_sensitive


def test_complexity_precision():
    """Precision tasks should flag correctly."""
    from backend.app.providers.registry import get_registry
    from backend.app.providers.router import ModelRouter

    reg = get_registry()
    router = ModelRouter(reg)
    reasoner = DeliberateReasoner(router)
    result = reasoner.analyze_complexity(
        "Calculate the exact probability using the formula for combinatorics."
    )
    assert result.requires_precision


def test_strategy_enum():
    """All expected strategies exist."""
    assert Strategy.DIRECT == "direct"
    assert Strategy.TREE_OF_THOUGHTS == "tree_of_thoughts"
    assert Strategy.REFLEXION == "reflexion"
    assert Strategy.DEBATE == "debate"
    assert Strategy.CONSTITUTIONAL == "constitutional"
    assert Strategy.FULL_PIPELINE == "full_pipeline"
