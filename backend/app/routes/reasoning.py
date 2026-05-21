"""Reasoning engine API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..providers import get_registry
from ..providers.router import ModelRouter
from ..reasoning.deliberate import DeliberateReasoner, Strategy

router = APIRouter(prefix="/reasoning", tags=["reasoning"])


class SolveRequest(BaseModel):
    task: str
    strategy: str | None = None
    context: str = ""


@router.post("/solve")
async def solve(req: SolveRequest) -> dict:
    reg = get_registry()
    if not reg.has_any():
        raise HTTPException(status_code=412, detail="no providers configured")

    router_obj = ModelRouter(reg)
    reasoner = DeliberateReasoner(router_obj)

    override = None
    if req.strategy:
        try:
            override = Strategy(req.strategy)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"unknown strategy: {req.strategy}. "
                f"valid: {[s.value for s in Strategy]}",
            ) from e

    result = await reasoner.solve(req.task, strategy_override=override, context=req.context)
    return result.model_dump()


@router.post("/analyze")
async def analyze_complexity(req: SolveRequest) -> dict:
    reg = get_registry()
    router_obj = ModelRouter(reg)
    reasoner = DeliberateReasoner(router_obj)
    analysis = reasoner.analyze_complexity(req.task)
    return analysis.model_dump()


@router.get("/strategies")
def list_strategies() -> dict:
    return {
        "strategies": [
            {
                "id": s.value,
                "label": s.value.replace("_", " ").title(),
                "description": _STRATEGY_DESCRIPTIONS.get(s.value, ""),
            }
            for s in Strategy
        ]
    }


_STRATEGY_DESCRIPTIONS = {
    "direct": "Single-shot response — fast, low cost.",
    "tree_of_thoughts": "Explores multiple reasoning branches via BFS (Yao et al. 2023).",
    "reflexion": "Iterative self-critique with verbal reinforcement (Shinn et al. 2023).",
    "debate": "Multiple agents argue positions and converge (Du et al. 2023).",
    "constitutional": "Self-critique against a set of principles (Bai et al. 2022).",
    "full_pipeline": "Combines ToT → Reflexion → Constitutional for maximum quality.",
}
