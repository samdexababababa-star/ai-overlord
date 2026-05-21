"""Tree of Thoughts (ToT) — Yao et al. 2023.

Implements BFS-based deliberate reasoning where:
1. The problem is decomposed into intermediate "thought steps".
2. At each step, *k* candidate continuations are generated.
3. A heuristic evaluator scores each candidate (sure / maybe / impossible).
4. Only the top-*b* (beam width) candidates survive to the next step.
5. The final answer is the highest-scoring complete chain.

This is far more powerful than simple chain-of-thought because it explores
multiple reasoning paths and prunes dead ends early.

Reference: https://arxiv.org/abs/2305.10601
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from ..log import get_logger
from ..providers.base import ChatMessage
from ..providers.router import ModelRouter, TaskProfile

log = get_logger(__name__)


class ThoughtNode(BaseModel):
    """A single node in the thought tree."""

    id: str
    depth: int
    thought: str
    score: float = 0.0
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    is_terminal: bool = False


class ToTResult(BaseModel):
    """Result of a Tree of Thoughts exploration."""

    answer: str
    best_chain: list[str]
    total_nodes_explored: int
    max_depth_reached: int
    all_paths: list[dict[str, Any]] = Field(default_factory=list)


class TreeOfThoughts:
    """BFS-based Tree of Thoughts reasoner.

    Parameters
    ----------
    router : ModelRouter
        Used to dispatch LLM calls.
    max_depth : int
        Maximum number of reasoning steps.
    branching_factor : int
        How many candidate thoughts to generate per step (k).
    beam_width : int
        How many candidates to keep at each level (b).
    """

    def __init__(
        self,
        router: ModelRouter,
        max_depth: int = 4,
        branching_factor: int = 3,
        beam_width: int = 2,
    ):
        self.router = router
        self.max_depth = max_depth
        self.branching_factor = branching_factor
        self.beam_width = beam_width
        self._nodes: dict[str, ThoughtNode] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"tot-{self._counter}"

    async def solve(self, problem: str) -> ToTResult:
        """Run BFS Tree of Thoughts on *problem*."""
        self._nodes.clear()
        self._counter = 0

        root = ThoughtNode(id=self._next_id(), depth=0, thought=problem, score=1.0)
        self._nodes[root.id] = root
        current_level = [root]

        for depth in range(1, self.max_depth + 1):
            candidates: list[ThoughtNode] = []
            expand_tasks = [
                self._expand(node, depth, problem) for node in current_level
            ]
            results = await asyncio.gather(*expand_tasks)
            for children in results:
                candidates.extend(children)

            if not candidates:
                break

            score_tasks = [
                self._evaluate(node, problem) for node in candidates
            ]
            scores = await asyncio.gather(*score_tasks)
            for node, score in zip(candidates, scores, strict=False):
                node.score = score

            candidates.sort(key=lambda n: n.score, reverse=True)
            current_level = candidates[: self.beam_width]

            for node in current_level:
                self._nodes[node.id] = node

            if any(n.is_terminal for n in current_level):
                break

        best = max(self._nodes.values(), key=lambda n: n.score)
        chain = self._trace_chain(best.id)
        answer = await self._synthesize(problem, chain)

        return ToTResult(
            answer=answer,
            best_chain=[self._nodes[nid].thought for nid in chain],
            total_nodes_explored=len(self._nodes),
            max_depth_reached=max(n.depth for n in self._nodes.values()),
            all_paths=self._collect_paths(),
        )

    async def _expand(
        self, parent: ThoughtNode, depth: int, problem: str
    ) -> list[ThoughtNode]:
        """Generate *branching_factor* candidate thoughts from *parent*."""
        chain = self._trace_chain(parent.id)
        chain_text = "\n".join(
            f"Step {i}: {self._nodes[nid].thought}"
            for i, nid in enumerate(chain, 1)
        )

        prompt = (
            f"Problem: {problem}\n\n"
            f"Reasoning so far:\n{chain_text}\n\n"
            f"Generate {self.branching_factor} distinct next reasoning steps. "
            f"Each should explore a different angle or approach. "
            f"Format: one step per line, prefixed with a number.\n"
            f"If you believe the problem is fully solved, write SOLUTION: <answer>."
        )
        try:
            resp = await self.router.chat(
                [ChatMessage(role="user", content=prompt)],
                profile=TaskProfile(capability="reason"),
                temperature=0.8,
                max_tokens=1024,
            )
        except Exception as e:
            log.warning("tot.expand.fail", error=str(e)[:200])
            return []

        children: list[ThoughtNode] = []
        for line in resp.text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            for prefix in ("1.", "2.", "3.", "4.", "5.", "-", "*"):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break

            is_terminal = line.upper().startswith("SOLUTION:")
            if is_terminal:
                line = line[len("SOLUTION:"):].strip()

            node = ThoughtNode(
                id=self._next_id(),
                depth=depth,
                thought=line,
                parent_id=parent.id,
                is_terminal=is_terminal,
            )
            parent.children.append(node.id)
            children.append(node)
            if len(children) >= self.branching_factor:
                break

        return children

    async def _evaluate(self, node: ThoughtNode, problem: str) -> float:
        """Score a thought node on a 0-1 scale using the LLM as evaluator."""
        chain = self._trace_chain(node.id)
        chain_text = "\n".join(
            f"Step {i}: {self._nodes[nid].thought}"
            for i, nid in enumerate(chain, 1)
        )

        prompt = (
            f"Problem: {problem}\n\n"
            f"Reasoning path:\n{chain_text}\n\n"
            f"Evaluate this reasoning path. Rate it as one of:\n"
            f"- SURE (this path is correct and promising) → 1.0\n"
            f"- LIKELY (probably right, some uncertainty) → 0.7\n"
            f"- MAYBE (could go either way) → 0.4\n"
            f"- UNLIKELY (probably wrong) → 0.2\n"
            f"- IMPOSSIBLE (definitely wrong or contradictory) → 0.0\n\n"
            f"Reply with just the label."
        )

        try:
            resp = await self.router.chat(
                [ChatMessage(role="user", content=prompt)],
                profile=TaskProfile(capability="reason"),
                temperature=0.1,
                max_tokens=32,
            )
            text = resp.text.strip().upper()
            score_map = {
                "SURE": 1.0,
                "LIKELY": 0.7,
                "MAYBE": 0.4,
                "UNLIKELY": 0.2,
                "IMPOSSIBLE": 0.0,
            }
            for label, score in score_map.items():
                if label in text:
                    return score
            return 0.4
        except Exception:
            return 0.4

    async def _synthesize(self, problem: str, chain: list[str]) -> str:
        """Produce a final answer from the best reasoning chain."""
        chain_text = "\n".join(
            f"Step {i}: {self._nodes[nid].thought}"
            for i, nid in enumerate(chain, 1)
        )
        prompt = (
            f"Problem: {problem}\n\n"
            f"Best reasoning chain:\n{chain_text}\n\n"
            f"Based on this reasoning, provide the final answer. Be precise and complete."
        )
        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.2,
        )
        return resp.text

    def _trace_chain(self, node_id: str) -> list[str]:
        """Walk from root to *node_id*."""
        chain: list[str] = []
        current = node_id
        while current:
            chain.append(current)
            node = self._nodes.get(current)
            if node is None:
                break
            current = node.parent_id  # type: ignore[assignment]
        chain.reverse()
        return chain

    def _collect_paths(self) -> list[dict[str, Any]]:
        """Return all explored paths for visualization."""
        leaves = [n for n in self._nodes.values() if not n.children]
        paths = []
        for leaf in leaves:
            chain = self._trace_chain(leaf.id)
            paths.append({
                "steps": [self._nodes[nid].thought for nid in chain],
                "score": leaf.score,
                "depth": leaf.depth,
                "terminal": leaf.is_terminal,
            })
        return paths
