"""Autonomy & goal management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..autonomy.goals import Goal, GoalManager, GoalPriority, GoalStatus
from ..autonomy.loop import AutonomyLoop
from ..hitl import get_hitl

router = APIRouter(prefix="/autonomy", tags=["autonomy"])

_goal_mgr = GoalManager()
_loop = AutonomyLoop(goal_manager=_goal_mgr)


class CreateGoalRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    depends_on: list[str] = []
    tags: list[str] = []


class UpdateGoalRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    progress: float | None = None


@router.get("/goals")
def list_goals(status: str | None = None) -> dict:
    st = GoalStatus(status) if status else None
    goals = _goal_mgr.list_all(status=st)
    return {"goals": [g.model_dump() for g in goals]}


@router.post("/goals")
def create_goal(req: CreateGoalRequest) -> dict:
    goal = Goal(
        title=req.title,
        description=req.description,
        priority=GoalPriority(req.priority),
        depends_on=req.depends_on,
        tags=req.tags,
    )
    created = _goal_mgr.add(goal)
    return created.model_dump()


@router.get("/goals/{goal_id}")
def get_goal(goal_id: str) -> dict:
    goal = _goal_mgr.get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="goal not found")
    return goal.model_dump()


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: str, req: UpdateGoalRequest) -> dict:
    patch = {k: v for k, v in req.model_dump().items() if v is not None}
    goal = _goal_mgr.update(goal_id, patch)
    if not goal:
        raise HTTPException(status_code=404, detail="goal not found")
    return goal.model_dump()


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: str) -> dict:
    if not _goal_mgr.remove(goal_id):
        raise HTTPException(status_code=404, detail="goal not found")
    return {"ok": True}


@router.get("/stats")
def goal_stats() -> dict:
    return {
        "goals": _goal_mgr.stats(),
        "loop": _loop.stats.model_dump(),
    }


@router.post("/loop/start")
def start_loop() -> dict:
    _loop.start()
    return {"running": _loop.is_running}


@router.post("/loop/stop")
def stop_loop() -> dict:
    _loop.stop()
    return {"running": _loop.is_running}


@router.get("/loop/status")
def loop_status() -> dict:
    return _loop.stats.model_dump()


# --- HITL endpoints ---


@router.get("/hitl/pending")
def hitl_pending() -> dict:
    hitl = get_hitl()
    return {"actions": [a.model_dump() for a in hitl.list_pending()]}


@router.post("/hitl/approve/{action_id}")
def hitl_approve(action_id: str) -> dict:
    hitl = get_hitl()
    ok = hitl.approve(action_id)
    if not ok:
        raise HTTPException(status_code=404, detail="action not found or already resolved")
    return {"ok": True}


@router.post("/hitl/reject/{action_id}")
def hitl_reject(action_id: str) -> dict:
    hitl = get_hitl()
    ok = hitl.reject(action_id)
    if not ok:
        raise HTTPException(status_code=404, detail="action not found or already resolved")
    return {"ok": True}


@router.post("/hitl/approve-all")
def hitl_approve_all() -> dict:
    hitl = get_hitl()
    count = hitl.approve_all()
    return {"approved": count}


@router.post("/hitl/reject-all")
def hitl_reject_all() -> dict:
    hitl = get_hitl()
    count = hitl.reject_all()
    return {"rejected": count}


@router.get("/hitl/audit")
def hitl_audit(limit: int = 50) -> dict:
    hitl = get_hitl()
    return {"entries": [e.model_dump() for e in hitl.get_audit_log(limit)]}
