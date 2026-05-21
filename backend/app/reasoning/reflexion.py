"""Reflexion — Shinn et al. 2023.

Implements verbal reinforcement learning where the agent:
1. Attempts to solve the task.
2. Evaluates its own output (or receives external feedback).
3. Generates a verbal self-reflection identifying what went wrong.
4. Retries with the accumulated reflections as additional context.

This loop continues until the evaluator is satisfied or max_trials is reached.
The key insight from the paper is that verbal reflections are more informative
than scalar rewards — they tell the agent *what* to change, not just *that*
something was wrong.

Reference: https://arxiv.org/abs/2303.11366
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..log import get_logger
from ..providers.base import ChatMessage
from ..providers.router import ModelRouter, TaskProfile

log = get_logger(__name__)


class ReflexionTrial(BaseModel):
    """One attempt in the reflexion loop."""

    trial_number: int
    response: str
    evaluation: str
    score: float
    reflection: str
    passed: bool


class ReflexionResult(BaseModel):
    """Final output of the reflexion loop."""

    answer: str
    trials: list[ReflexionTrial] = Field(default_factory=list)
    total_trials: int
    final_score: float
    converged: bool


class ReflexionLoop:
    """Iterative self-reflection loop.

    Parameters
    ----------
    router : ModelRouter
    max_trials : int
        Maximum number of retry attempts.
    pass_threshold : float
        Score (0-1) above which we accept the answer.
    """

    def __init__(
        self,
        router: ModelRouter,
        max_trials: int = 3,
        pass_threshold: float = 0.8,
    ):
        self.router = router
        self.max_trials = max_trials
        self.pass_threshold = pass_threshold

    async def solve(self, task: str, context: str = "") -> ReflexionResult:
        """Run the reflexion loop on *task*."""
        trials: list[ReflexionTrial] = []
        reflections: list[str] = []
        best_answer = ""
        best_score = 0.0

        for trial_num in range(1, self.max_trials + 1):
            response = await self._attempt(task, context, reflections)
            evaluation, score = await self._evaluate(task, response)

            passed = score >= self.pass_threshold
            reflection = ""
            if not passed and trial_num < self.max_trials:
                reflection = await self._reflect(task, response, evaluation)
                reflections.append(reflection)

            trial = ReflexionTrial(
                trial_number=trial_num,
                response=response,
                evaluation=evaluation,
                score=score,
                reflection=reflection,
                passed=passed,
            )
            trials.append(trial)

            if score > best_score:
                best_score = score
                best_answer = response

            log.info(
                "reflexion.trial",
                trial=trial_num,
                score=score,
                passed=passed,
            )

            if passed:
                break

        return ReflexionResult(
            answer=best_answer,
            trials=trials,
            total_trials=len(trials),
            final_score=best_score,
            converged=any(t.passed for t in trials),
        )

    async def _attempt(
        self, task: str, context: str, reflections: list[str]
    ) -> str:
        """Generate an answer, incorporating past reflections."""
        system = (
            "You are a careful reasoner. Learn from any past mistakes noted below. "
            "Provide the best possible answer."
        )
        reflection_block = ""
        if reflections:
            numbered = "\n".join(
                f"Reflection #{i}: {r}" for i, r in enumerate(reflections, 1)
            )
            reflection_block = (
                f"\n\nPast reflections (learn from these):\n{numbered}\n"
            )

        user_msg = f"Task: {task}"
        if context:
            user_msg = f"Context: {context}\n\n{user_msg}"
        user_msg += reflection_block

        resp = await self.router.chat(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user_msg),
            ],
            profile=TaskProfile(capability="reason"),
            temperature=0.4,
        )
        return resp.text

    async def _evaluate(self, task: str, response: str) -> tuple[str, float]:
        """Evaluate the response quality on a 0-1 scale."""
        prompt = (
            f"Task: {task}\n\n"
            f"Response:\n{response}\n\n"
            "Evaluate this response on these dimensions:\n"
            "1. Correctness: Is it factually accurate?\n"
            "2. Completeness: Does it fully address the task?\n"
            "3. Clarity: Is it well-structured and clear?\n"
            "4. Reasoning: Is the logic sound?\n\n"
            "Provide a brief evaluation, then end with SCORE: X.X (0.0 to 1.0)."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.1,
            max_tokens=512,
        )

        text = resp.text
        score = 0.5
        if "SCORE:" in text.upper():
            try:
                score_str = text.upper().split("SCORE:")[-1].strip().split()[0]
                score = float(score_str)
                score = max(0.0, min(1.0, score))
            except (ValueError, IndexError):
                pass

        return text, score

    async def _reflect(
        self, task: str, response: str, evaluation: str
    ) -> str:
        """Generate a verbal reflection on what went wrong."""
        prompt = (
            f"Task: {task}\n\n"
            f"Your previous response:\n{response}\n\n"
            f"Evaluation:\n{evaluation}\n\n"
            "Reflect on what went wrong. Identify specific mistakes, gaps, or "
            "weaknesses. Be concrete about what to change in the next attempt. "
            "Write 2-4 sentences of actionable self-critique."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.3,
            max_tokens=256,
        )
        return resp.text
