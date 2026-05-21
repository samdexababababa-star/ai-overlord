"""Goal management — persistent priority queue of autonomous objectives.

Goals have:
- Priority levels (critical, high, medium, low, background)
- Dependencies (goal B depends on goal A)
- Status tracking with detailed progress
- Retry logic with exponential backoff
- Cost tracking per goal
"""

from __future__ import annotations

import enum
import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


class GoalStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class GoalPriority(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str = ""
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    progress: float = 0.0
    depends_on: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: str = ""
    error: str = ""
    retry_count: int = 0
    max_retries: int = 3
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class GoalManager:
    """Persistent goal queue with JSON backing store."""

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.data_dir / "goals.json")
        self._goals: dict[str, Goal] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for g in data.get("goals", []):
                    goal = Goal(**g)
                    self._goals[goal.id] = goal
            except Exception as e:
                log.warning("goals.load_fail", error=str(e)[:200])

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"goals": [g.model_dump() for g in self._goals.values()]}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def add(self, goal: Goal) -> Goal:
        self._goals[goal.id] = goal
        self._save()
        log.info("goals.add", id=goal.id, title=goal.title, priority=goal.priority.value)
        return goal

    def get(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def update(self, goal_id: str, patch: dict[str, Any]) -> Goal | None:
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        for k, v in patch.items():
            if hasattr(goal, k):
                setattr(goal, k, v)
        self._save()
        return goal

    def remove(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            del self._goals[goal_id]
            self._save()
            return True
        return False

    def list_all(
        self, status: GoalStatus | None = None, priority: GoalPriority | None = None
    ) -> list[Goal]:
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        if priority:
            goals = [g for g in goals if g.priority == priority]
        priority_order = {
            GoalPriority.CRITICAL: 0,
            GoalPriority.HIGH: 1,
            GoalPriority.MEDIUM: 2,
            GoalPriority.LOW: 3,
            GoalPriority.BACKGROUND: 4,
        }
        goals.sort(key=lambda g: (priority_order.get(g.priority, 5), g.created_at))
        return goals

    def next_runnable(self) -> Goal | None:
        """Return the highest-priority pending goal whose dependencies are met."""
        for goal in self.list_all(status=GoalStatus.PENDING):
            if self._deps_met(goal):
                return goal
        return None

    def _deps_met(self, goal: Goal) -> bool:
        for dep_id in goal.depends_on:
            dep = self._goals.get(dep_id)
            if not dep or dep.status != GoalStatus.COMPLETED:
                return False
        return True

    def mark_running(self, goal_id: str) -> None:
        goal = self._goals.get(goal_id)
        if goal:
            goal.status = GoalStatus.RUNNING
            goal.started_at = time.time()
            self._save()

    def mark_completed(self, goal_id: str, result: str = "") -> None:
        goal = self._goals.get(goal_id)
        if goal:
            goal.status = GoalStatus.COMPLETED
            goal.completed_at = time.time()
            goal.progress = 1.0
            goal.result = result
            self._save()

    def mark_failed(self, goal_id: str, error: str = "") -> None:
        goal = self._goals.get(goal_id)
        if goal:
            goal.retry_count += 1
            if goal.retry_count >= goal.max_retries:
                goal.status = GoalStatus.FAILED
            else:
                goal.status = GoalStatus.PENDING
            goal.error = error
            self._save()

    def stats(self) -> dict[str, int]:
        by_status: dict[str, int] = {}
        for g in self._goals.values():
            by_status[g.status.value] = by_status.get(g.status.value, 0) + 1
        return {
            "total": len(self._goals),
            **by_status,
        }
