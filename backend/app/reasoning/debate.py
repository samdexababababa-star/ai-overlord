"""Multi-Agent Debate — Du et al. 2023.

Multiple independent "debater" agents argue different positions on a problem.
After several rounds of debate, a judge synthesizes the arguments into a final
answer. This improves factuality because agents correct each other's errors.

The implementation supports:
- Configurable number of debaters (default 3).
- Multiple debate rounds with cross-reading of opponents' arguments.
- A separate judge model that evaluates the strongest arguments.
- Convergence detection: if all debaters agree, we stop early.

Reference: https://arxiv.org/abs/2305.14325
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..log import get_logger
from ..providers.base import ChatMessage
from ..providers.router import ModelRouter, TaskProfile

log = get_logger(__name__)


class DebaterArgument(BaseModel):
    debater_id: int
    round_num: int
    position: str
    argument: str


class DebateRound(BaseModel):
    round_num: int
    arguments: list[DebaterArgument] = Field(default_factory=list)


class DebateResult(BaseModel):
    answer: str
    rounds: list[DebateRound] = Field(default_factory=list)
    total_rounds: int
    converged: bool
    consensus_round: int | None = None
    judge_reasoning: str = ""


class MultiAgentDebate:
    """Multi-agent debate for improved factuality and reasoning.

    Parameters
    ----------
    router : ModelRouter
    num_debaters : int
        Number of independent debater agents.
    max_rounds : int
        Maximum debate rounds before forcing a judge decision.
    """

    def __init__(
        self,
        router: ModelRouter,
        num_debaters: int = 3,
        max_rounds: int = 3,
    ):
        self.router = router
        self.num_debaters = num_debaters
        self.max_rounds = max_rounds

    async def solve(self, problem: str) -> DebateResult:
        """Run a multi-agent debate on *problem*."""
        rounds: list[DebateRound] = []
        positions: list[str] = []

        # Initial positions — each debater independently
        initial_round = DebateRound(round_num=0)
        for i in range(self.num_debaters):
            position = await self._initial_position(problem, i)
            positions.append(position)
            initial_round.arguments.append(
                DebaterArgument(
                    debater_id=i,
                    round_num=0,
                    position=f"Debater {i + 1}",
                    argument=position,
                )
            )
        rounds.append(initial_round)

        converged = False
        consensus_round = None

        for round_num in range(1, self.max_rounds + 1):
            if await self._check_consensus(positions):
                converged = True
                consensus_round = round_num - 1
                log.info("debate.consensus", round=round_num - 1)
                break

            debate_round = DebateRound(round_num=round_num)
            new_positions: list[str] = []

            for i in range(self.num_debaters):
                others = [
                    positions[j]
                    for j in range(self.num_debaters)
                    if j != i
                ]
                revised = await self._debate_round(
                    problem, positions[i], others, i, round_num
                )
                new_positions.append(revised)
                debate_round.arguments.append(
                    DebaterArgument(
                        debater_id=i,
                        round_num=round_num,
                        position=f"Debater {i + 1}",
                        argument=revised,
                    )
                )

            positions = new_positions
            rounds.append(debate_round)

        answer, reasoning = await self._judge(problem, positions)

        return DebateResult(
            answer=answer,
            rounds=rounds,
            total_rounds=len(rounds),
            converged=converged,
            consensus_round=consensus_round,
            judge_reasoning=reasoning,
        )

    async def _initial_position(self, problem: str, debater_idx: int) -> str:
        """Generate an independent initial position."""
        perspectives = [
            "Focus on the most rigorous logical analysis.",
            "Consider practical implications and real-world evidence.",
            "Play devil's advocate and challenge common assumptions.",
            "Approach from a systems-thinking perspective.",
            "Focus on edge cases and potential failure modes.",
        ]
        perspective = perspectives[debater_idx % len(perspectives)]

        prompt = (
            f"Problem: {problem}\n\n"
            f"Your perspective: {perspective}\n\n"
            f"Provide your initial analysis and answer. Be thorough but concise. "
            f"Support your position with reasoning."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.7 + (debater_idx * 0.1),
        )
        return resp.text

    async def _debate_round(
        self,
        problem: str,
        my_position: str,
        others: list[str],
        debater_idx: int,
        round_num: int,
    ) -> str:
        """Revise position after reading other debaters' arguments."""
        others_text = "\n\n".join(
            f"--- Other Debater {i + 1} ---\n{arg}"
            for i, arg in enumerate(others)
        )

        prompt = (
            f"Problem: {problem}\n\n"
            f"Your previous position:\n{my_position}\n\n"
            f"Other debaters' arguments:\n{others_text}\n\n"
            f"This is debate round {round_num}. "
            f"Consider the other arguments carefully. "
            f"Update your position if you find compelling points. "
            f"Defend your position where you disagree. "
            f"Provide your revised analysis."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.4,
        )
        return resp.text

    async def _check_consensus(self, positions: list[str]) -> bool:
        """Check if debaters have converged to the same answer."""
        if len(positions) < 2:
            return True

        prompt = (
            "Do these positions essentially agree on the same conclusion? "
            "Answer YES or NO.\n\n"
            + "\n\n".join(
                f"Position {i + 1}: {p[:500]}" for i, p in enumerate(positions)
            )
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="fast"),
            temperature=0.0,
            max_tokens=8,
        )
        return "YES" in resp.text.upper()

    async def _judge(
        self, problem: str, final_positions: list[str]
    ) -> tuple[str, str]:
        """A judge model synthesizes the final answer."""
        positions_text = "\n\n".join(
            f"=== Debater {i + 1} Final Position ===\n{p}"
            for i, p in enumerate(final_positions)
        )

        prompt = (
            f"Problem: {problem}\n\n"
            f"After a multi-round debate, here are the final positions:\n\n"
            f"{positions_text}\n\n"
            f"As the judge, synthesize the strongest arguments into a definitive "
            f"answer. Explain your reasoning briefly, then provide the final answer."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.2,
        )

        lines = resp.text.strip().split("\n")
        reasoning = resp.text
        answer = lines[-1] if lines else resp.text

        return answer, reasoning
