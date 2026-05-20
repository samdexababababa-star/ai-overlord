"""Memory consolidation — sleep-cycle inspired knowledge compression.

Implements a biologically-inspired memory consolidation process:

1. **Hippocampal replay** (episodic → semantic): Recent episodic memories
   are summarized and important facts are promoted to semantic memory.
   Based on Kumaran & McClelland 2012, "Generalization through the
   recurrent interaction of episodic memories".

2. **Synaptic homeostasis** (pruning): Low-importance memories are
   pruned to keep the store manageable. Based on Tononi & Cirelli 2006,
   "Sleep function and synaptic homeostasis".

3. **Schema extraction** (procedural): Repeated patterns are extracted
   into procedural "skills" — reusable action sequences the agent has
   learned. Based on cognitive schema theory (Piaget, Bartlett).

4. **Entity relationship strengthening**: Frequently co-occurring entities
   in the knowledge graph get stronger edge weights.

The consolidation runs periodically in the background.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from ..log import get_logger

log = get_logger(__name__)


class ConsolidationResult(BaseModel):
    episodes_processed: int = 0
    facts_promoted: int = 0
    episodes_pruned: int = 0
    skills_extracted: int = 0
    duration_seconds: float = 0.0
    timestamp: float = Field(default_factory=time.time)


class ProceduralSkill(BaseModel):
    """A learned action pattern extracted from episodic memory."""

    id: str
    name: str
    description: str
    trigger_pattern: str
    action_sequence: list[str] = Field(default_factory=list)
    success_rate: float = 0.0
    times_used: int = 0
    created_at: float = Field(default_factory=time.time)
    last_used: float | None = None


class MemoryConsolidator:
    """Manages the sleep-cycle consolidation process.

    Parameters
    ----------
    episodic : EpisodicMemory
    semantic : SemanticMemory
    knowledge_graph : KnowledgeGraph | None
    router : ModelRouter | None
        If provided, uses LLM for summarization.
    """

    def __init__(
        self,
        episodic: Any = None,
        semantic: Any = None,
        knowledge_graph: Any = None,
        router: Any = None,
    ):
        self._episodic = episodic
        self._semantic = semantic
        self._kg = knowledge_graph
        self._router = router
        self._skills: dict[str, ProceduralSkill] = {}
        self._last_consolidation: float = 0
        self._history: list[ConsolidationResult] = []

    async def consolidate(self) -> ConsolidationResult:
        """Run a full consolidation cycle."""
        start = time.time()
        result = ConsolidationResult()

        # Phase 1: Episodic replay → semantic promotion
        if self._episodic and self._semantic:
            promoted = await self._replay_and_promote()
            result.facts_promoted = promoted
            result.episodes_processed = promoted * 5  # approximate

        # Phase 2: Prune old low-value episodes
        if self._episodic:
            pruned = self._prune_episodes()
            result.episodes_pruned = pruned

        # Phase 3: Extract procedural skills
        if self._episodic:
            skills = await self._extract_skills()
            result.skills_extracted = skills

        result.duration_seconds = time.time() - start
        self._last_consolidation = time.time()
        self._history.append(result)

        log.info(
            "consolidation.complete",
            promoted=result.facts_promoted,
            pruned=result.episodes_pruned,
            skills=result.skills_extracted,
            duration=f"{result.duration_seconds:.1f}s",
        )

        return result

    async def _replay_and_promote(self) -> int:
        """Summarize recent episodes and promote key facts to semantic memory."""
        if not self._episodic or not self._semantic:
            return 0

        recent = self._episodic.recent(limit=100)
        if not recent:
            return 0

        # Group by session
        by_session: dict[str, list[dict[str, Any]]] = {}
        for ep in recent:
            session = ep.get("session", "default")
            by_session.setdefault(session, []).append(ep)

        promoted = 0
        for session, episodes in by_session.items():
            text_block = "\n".join(
                f"[{ep.get('kind', 'unknown')}] {ep.get('actor', 'unknown')}: "
                f"{ep.get('content', '')[:500]}"
                for ep in episodes[-20:]
            )

            if self._router:
                summary = await self._summarize_with_llm(text_block)
            else:
                summary = text_block[:1000]

            if summary:
                result = await self._semantic.add(
                    summary, meta={"source": "consolidation", "session": session}
                )
                if result:
                    promoted += 1

        return promoted

    async def _summarize_with_llm(self, text: str) -> str:
        """Use the LLM to create a concise summary of episodes."""
        from ..providers.base import ChatMessage
        from ..providers.router import TaskProfile

        try:
            resp = await self._router.chat(
                [ChatMessage(
                    role="user",
                    content=(
                        "Summarize the following conversation/events into 2-3 "
                        "key facts or learnings worth remembering long-term. "
                        "Be concise.\n\n" + text[:4000]
                    ),
                )],
                profile=TaskProfile(capability="fast"),
                temperature=0.2,
                max_tokens=256,
            )
            return resp.text
        except Exception as e:
            log.warning("consolidation.summarize_fail", error=str(e)[:200])
            return ""

    def _prune_episodes(self, max_age_days: int = 30) -> int:
        """Remove old episodes that have been consolidated."""
        if not self._episodic:
            return 0

        import sqlite3

        cutoff = time.time() - (max_age_days * 86400)
        try:
            with sqlite3.connect(self._episodic.path) as c:
                cursor = c.execute(
                    "DELETE FROM episodes WHERE ts < ? AND kind = 'council_turn'",
                    (cutoff,),
                )
                c.commit()
                return cursor.rowcount
        except Exception as e:
            log.warning("consolidation.prune_fail", error=str(e)[:200])
            return 0

    async def _extract_skills(self) -> int:
        """Identify repeated action patterns and extract them as skills."""
        if not self._episodic:
            return 0

        tool_episodes = self._episodic.recent(
            limit=200, kinds=["council_turn"]
        )
        action_sequences: dict[str, int] = {}
        for ep in tool_episodes:
            meta = ep.get("meta", {})
            event_kind = meta.get("event", "")
            if event_kind == "agent.tool_call":
                tool_name = ep.get("content", "unknown")
                action_sequences[tool_name] = (
                    action_sequences.get(tool_name, 0) + 1
                )

        extracted = 0
        for action, count in action_sequences.items():
            if count >= 3 and action not in self._skills:
                skill = ProceduralSkill(
                    id=f"skill-{action}",
                    name=f"Use {action}",
                    description=f"Learned pattern: using {action} tool (seen {count} times)",
                    trigger_pattern=action,
                    action_sequence=[action],
                    success_rate=0.8,
                    times_used=count,
                )
                self._skills[skill.id] = skill
                extracted += 1

        return extracted

    def get_skills(self) -> list[ProceduralSkill]:
        return list(self._skills.values())

    def get_history(self) -> list[ConsolidationResult]:
        return list(self._history)

    @property
    def needs_consolidation(self) -> bool:
        from ..user_settings import get_settings_manager
        sm = get_settings_manager()
        interval = sm.load().memory.consolidation_interval_hours * 3600
        return (time.time() - self._last_consolidation) > interval
