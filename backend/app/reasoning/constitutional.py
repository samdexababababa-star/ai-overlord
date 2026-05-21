"""Constitutional AI (Self-Critique) — Bai et al. 2022.

The agent critiques its own output against a set of configurable principles
and iteratively revises until all principles are satisfied (or max revisions).

Default principles cover:
- Factual accuracy
- Logical consistency
- Completeness
- Safety / harmlessness
- Clarity

Reference: https://arxiv.org/abs/2212.08073
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..log import get_logger
from ..providers.base import ChatMessage
from ..providers.router import ModelRouter, TaskProfile

log = get_logger(__name__)

DEFAULT_PRINCIPLES = [
    "The response must be factually accurate and not contain fabricated information.",
    "The reasoning must be logically consistent without contradictions.",
    "The response must fully address all parts of the question or task.",
    "The response must not encourage harmful, illegal, or dangerous activities.",
    "The response must be clear, well-organized, and easy to understand.",
]


class PrincipleViolation(BaseModel):
    principle: str
    violated: bool
    explanation: str = ""


class CritiqueRound(BaseModel):
    round_num: int
    response: str
    violations: list[PrincipleViolation] = Field(default_factory=list)
    all_passed: bool = False
    revision: str = ""


class ConstitutionalResult(BaseModel):
    answer: str
    rounds: list[CritiqueRound] = Field(default_factory=list)
    total_rounds: int
    all_principles_satisfied: bool
    principles_used: list[str] = Field(default_factory=list)


class ConstitutionalCritic:
    """Self-critique and revision against a constitution of principles.

    Parameters
    ----------
    router : ModelRouter
    principles : list[str] | None
        Custom principles. Defaults to the built-in set.
    max_revisions : int
        Maximum revision rounds.
    """

    def __init__(
        self,
        router: ModelRouter,
        principles: list[str] | None = None,
        max_revisions: int = 3,
    ):
        self.router = router
        self.principles = principles or DEFAULT_PRINCIPLES
        self.max_revisions = max_revisions

    async def critique_and_revise(
        self, task: str, initial_response: str
    ) -> ConstitutionalResult:
        """Critique *initial_response* and revise until compliant."""
        rounds: list[CritiqueRound] = []
        current = initial_response

        for round_num in range(1, self.max_revisions + 1):
            violations = await self._critique(task, current)
            all_passed = all(not v.violated for v in violations)

            cr = CritiqueRound(
                round_num=round_num,
                response=current,
                violations=violations,
                all_passed=all_passed,
            )

            if all_passed:
                rounds.append(cr)
                log.info("constitutional.passed", round=round_num)
                break

            revision = await self._revise(task, current, violations)
            cr.revision = revision
            rounds.append(cr)
            current = revision

            log.info(
                "constitutional.revised",
                round=round_num,
                violations_count=sum(1 for v in violations if v.violated),
            )

        return ConstitutionalResult(
            answer=current,
            rounds=rounds,
            total_rounds=len(rounds),
            all_principles_satisfied=rounds[-1].all_passed if rounds else False,
            principles_used=self.principles,
        )

    async def _critique(
        self, task: str, response: str
    ) -> list[PrincipleViolation]:
        """Check response against each principle."""
        principles_text = "\n".join(
            f"{i + 1}. {p}" for i, p in enumerate(self.principles)
        )

        prompt = (
            f"Task: {task}\n\n"
            f"Response to evaluate:\n{response}\n\n"
            f"Constitutional principles:\n{principles_text}\n\n"
            f"For each principle, determine if the response VIOLATES it. "
            f"Format your answer as:\n"
            f"1. PASS or FAIL: <brief explanation>\n"
            f"2. PASS or FAIL: <brief explanation>\n"
            f"..."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.1,
            max_tokens=512,
        )

        violations: list[PrincipleViolation] = []
        lines = resp.text.strip().splitlines()

        for i, principle in enumerate(self.principles):
            violated = False
            explanation = ""
            for line in lines:
                if line.strip().startswith(f"{i + 1}."):
                    content = line.strip()[len(f"{i + 1}."):].strip()
                    violated = "FAIL" in content.upper()
                    explanation = content
                    break
            violations.append(
                PrincipleViolation(
                    principle=principle,
                    violated=violated,
                    explanation=explanation,
                )
            )

        return violations

    async def _revise(
        self,
        task: str,
        response: str,
        violations: list[PrincipleViolation],
    ) -> str:
        """Revise the response to address violations."""
        violation_text = "\n".join(
            f"- {v.principle}: {v.explanation}"
            for v in violations
            if v.violated
        )

        prompt = (
            f"Task: {task}\n\n"
            f"Your previous response:\n{response}\n\n"
            f"The following principles were violated:\n{violation_text}\n\n"
            f"Rewrite your response to address all violations while keeping "
            f"the good parts. The revised response should be complete — do not "
            f"refer to the previous version."
        )

        resp = await self.router.chat(
            [ChatMessage(role="user", content=prompt)],
            profile=TaskProfile(capability="reason"),
            temperature=0.3,
        )
        return resp.text
