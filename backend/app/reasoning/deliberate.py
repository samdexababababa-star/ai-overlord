"""Deliberate orchestrator — automatic strategy selection.

Combines Tree of Thoughts, Reflexion, Multi-Agent Debate, and Constitutional AI
into a unified reasoning pipeline. Automatically selects the best strategy
based on task complexity analysis.

Strategy selection is inspired by metacognitive research (Flavell 1979) and
adaptive expertise (Hatano & Inagaki 1986): the system estimates task difficulty
and selects the appropriate level of deliberation.

Complexity heuristics:
- Word count and sentence structure → simple factual vs. complex reasoning
- Presence of multi-step keywords → decomposition needed (ToT)
- Controversial/debate topics → debate approach
- Safety-sensitive content → constitutional critique
- Need for precision → reflexion loop
"""

from __future__ import annotations

import enum
import re
from typing import Any

from pydantic import BaseModel, Field

from ..log import get_logger
from ..providers.base import ChatMessage
from ..providers.router import ModelRouter, TaskProfile
from .constitutional import ConstitutionalCritic, ConstitutionalResult
from .debate import DebateResult, MultiAgentDebate
from .reflexion import ReflexionLoop, ReflexionResult
from .tree_of_thoughts import ToTResult, TreeOfThoughts

log = get_logger(__name__)


class Strategy(enum.StrEnum):
    DIRECT = "direct"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    REFLEXION = "reflexion"
    DEBATE = "debate"
    CONSTITUTIONAL = "constitutional"
    FULL_PIPELINE = "full_pipeline"


class ComplexityAnalysis(BaseModel):
    estimated_difficulty: float  # 0-1
    requires_decomposition: bool
    requires_debate: bool
    safety_sensitive: bool
    requires_precision: bool
    recommended_strategy: Strategy
    reasoning: str = ""


class DeliberateResult(BaseModel):
    answer: str
    strategy_used: Strategy
    complexity: ComplexityAnalysis
    tot_result: ToTResult | None = None
    reflexion_result: ReflexionResult | None = None
    debate_result: DebateResult | None = None
    constitutional_result: ConstitutionalResult | None = None
    direct_response: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


DECOMPOSITION_KEYWORDS = {
    "step by step", "analyze", "compare", "evaluate", "design",
    "architect", "plan", "strategy", "optimize", "debug",
    "investigate", "research", "implement", "build", "create",
}

DEBATE_KEYWORDS = {
    "pros and cons", "argue", "debate", "controversial", "opinion",
    "perspective", "viewpoint", "should we", "is it better",
    "advantages", "disadvantages", "tradeoff", "trade-off",
}

SAFETY_KEYWORDS = {
    "financial", "medical", "legal", "safety", "security",
    "health", "investment", "money", "risk", "dangerous",
    "children", "privacy", "personal data",
}

PRECISION_KEYWORDS = {
    "exact", "precise", "calculate", "compute", "prove",
    "verify", "correct", "accurate", "mathematical", "formula",
    "code", "algorithm", "implementation",
}


class DeliberateReasoner:
    """Metacognitive reasoning orchestrator.

    Analyzes task complexity and delegates to the appropriate strategy.
    For maximum quality, use ``strategy_override=Strategy.FULL_PIPELINE``
    to run all strategies and synthesize.

    Parameters
    ----------
    router : ModelRouter
    """

    def __init__(self, router: ModelRouter):
        self.router = router
        self.tot = TreeOfThoughts(router, max_depth=3, branching_factor=3, beam_width=2)
        self.reflexion = ReflexionLoop(router, max_trials=3, pass_threshold=0.8)
        self.debate = MultiAgentDebate(router, num_debaters=3, max_rounds=2)
        self.constitutional = ConstitutionalCritic(router, max_revisions=2)

    def analyze_complexity(self, task: str) -> ComplexityAnalysis:
        """Heuristic task complexity analysis."""
        lower = task.lower()
        word_count = len(task.split())
        sentence_count = len(re.split(r'[.!?]+', task))

        has_decomposition = any(kw in lower for kw in DECOMPOSITION_KEYWORDS)
        has_debate = any(kw in lower for kw in DEBATE_KEYWORDS)
        has_safety = any(kw in lower for kw in SAFETY_KEYWORDS)
        has_precision = any(kw in lower for kw in PRECISION_KEYWORDS)

        difficulty = 0.0
        difficulty += min(word_count / 100, 0.3)
        difficulty += min(sentence_count / 10, 0.2)
        difficulty += 0.15 if has_decomposition else 0.0
        difficulty += 0.1 if has_debate else 0.0
        difficulty += 0.1 if has_safety else 0.0
        difficulty += 0.15 if has_precision else 0.0
        difficulty = min(difficulty, 1.0)

        if difficulty < 0.2:
            strategy = Strategy.DIRECT
        elif has_debate and has_decomposition:
            strategy = Strategy.FULL_PIPELINE
        elif has_decomposition:
            strategy = Strategy.TREE_OF_THOUGHTS
        elif has_debate:
            strategy = Strategy.DEBATE
        elif has_precision:
            strategy = Strategy.REFLEXION
        elif has_safety:
            strategy = Strategy.CONSTITUTIONAL
        elif difficulty > 0.6:
            strategy = Strategy.FULL_PIPELINE
        else:
            strategy = Strategy.REFLEXION

        return ComplexityAnalysis(
            estimated_difficulty=round(difficulty, 2),
            requires_decomposition=has_decomposition,
            requires_debate=has_debate,
            safety_sensitive=has_safety,
            requires_precision=has_precision,
            recommended_strategy=strategy,
            reasoning=(
                f"difficulty={difficulty:.2f}, decomp={has_decomposition}, "
                f"debate={has_debate}, safety={has_safety}, precision={has_precision}"
            ),
        )

    async def solve(
        self,
        task: str,
        strategy_override: Strategy | None = None,
        context: str = "",
    ) -> DeliberateResult:
        """Solve *task* using the best available reasoning strategy."""
        complexity = self.analyze_complexity(task)
        strategy = strategy_override or complexity.recommended_strategy

        log.info(
            "deliberate.start",
            strategy=strategy.value,
            difficulty=complexity.estimated_difficulty,
        )

        result = DeliberateResult(
            answer="",
            strategy_used=strategy,
            complexity=complexity,
        )

        if strategy == Strategy.DIRECT:
            result.direct_response = await self._direct(task, context)
            result.answer = result.direct_response

        elif strategy == Strategy.TREE_OF_THOUGHTS:
            tot_result = await self.tot.solve(task)
            result.tot_result = tot_result
            result.answer = tot_result.answer

        elif strategy == Strategy.REFLEXION:
            ref_result = await self.reflexion.solve(task, context)
            result.reflexion_result = ref_result
            result.answer = ref_result.answer

        elif strategy == Strategy.DEBATE:
            deb_result = await self.debate.solve(task)
            result.debate_result = deb_result
            result.answer = deb_result.answer

        elif strategy == Strategy.CONSTITUTIONAL:
            initial = await self._direct(task, context)
            const_result = await self.constitutional.critique_and_revise(
                task, initial
            )
            result.constitutional_result = const_result
            result.answer = const_result.answer

        elif strategy == Strategy.FULL_PIPELINE:
            result = await self._full_pipeline(task, context, complexity)

        return result

    async def _direct(self, task: str, context: str = "") -> str:
        """Simple single-shot answer."""
        msgs = []
        if context:
            msgs.append(
                ChatMessage(role="system", content=f"Context: {context}")
            )
        msgs.append(ChatMessage(role="user", content=task))

        resp = await self.router.chat(
            msgs,
            profile=TaskProfile(capability="reason"),
            temperature=0.3,
        )
        return resp.text

    async def _full_pipeline(
        self,
        task: str,
        context: str,
        complexity: ComplexityAnalysis,
    ) -> DeliberateResult:
        """Run multiple strategies and synthesize the best answer."""
        result = DeliberateResult(
            answer="",
            strategy_used=Strategy.FULL_PIPELINE,
            complexity=complexity,
        )

        # Phase 1: ToT for structured exploration
        tot_result = await self.tot.solve(task)
        result.tot_result = tot_result

        # Phase 2: Reflexion on the ToT answer
        ref_result = await self.reflexion.solve(
            task, context=f"Previous analysis:\n{tot_result.answer}"
        )
        result.reflexion_result = ref_result

        # Phase 3: Constitutional check on the refined answer
        const_result = await self.constitutional.critique_and_revise(
            task, ref_result.answer
        )
        result.constitutional_result = const_result
        result.answer = const_result.answer

        return result
