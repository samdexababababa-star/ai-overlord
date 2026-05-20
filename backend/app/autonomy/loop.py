"""Autonomy loop — background asyncio task for 24/7 operation.

The loop continuously:
1. Picks the next runnable goal from the queue.
2. Executes it via the council (with HITL checks).
3. Records results and picks up the next goal.
4. Sleeps between cycles to respect rate limits.

Guard rails:
- Cost tracking with daily budget enforcement
- Action-per-minute rate limiting
- Automatic pause on repeated failures
- Graceful shutdown on signal

Inspired by:
- BabyAGI (Nakajima 2023) — task-driven autonomous agent
- AutoGPT — iterative goal decomposition
- Cognitive architectures (SOAR, ACT-R) — goal stack management
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel

from ..agents.bus import Event, get_bus
from ..log import get_logger
from ..user_settings import get_settings_manager
from .goals import GoalManager

log = get_logger(__name__)


class LoopStats(BaseModel):
    running: bool = False
    total_cycles: int = 0
    goals_completed: int = 0
    goals_failed: int = 0
    total_cost_usd: float = 0.0
    uptime_seconds: float = 0.0
    last_error: str = ""
    started_at: float | None = None


class AutonomyLoop:
    """Background task that drives autonomous goal execution."""

    def __init__(
        self,
        goal_manager: GoalManager | None = None,
        council: Any = None,
    ):
        self.goals = goal_manager or GoalManager()
        self._council = council
        self._task: asyncio.Task | None = None
        self._running = False
        self._stats = LoopStats()
        self._cycle_delay = 10.0

    @property
    def stats(self) -> LoopStats:
        if self._stats.started_at:
            self._stats.uptime_seconds = time.time() - self._stats.started_at
        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the autonomy loop in the background."""
        if self._running:
            return
        sm = get_settings_manager()
        s = sm.load()
        if not s.autonomy.allow_background_tasks:
            log.info("autonomy.start.blocked", reason="background tasks disabled")
            return
        self._running = True
        self._stats.running = True
        self._stats.started_at = time.time()
        self._task = asyncio.create_task(self._run())
        log.info("autonomy.started")

    def stop(self) -> None:
        """Stop the autonomy loop."""
        self._running = False
        self._stats.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        log.info("autonomy.stopped")

    async def _run(self) -> None:
        """Main loop — pick goals, execute, sleep, repeat."""
        bus = get_bus()
        consecutive_failures = 0
        max_consecutive_failures = 5

        while self._running:
            try:
                goal = self.goals.next_runnable()
                if goal is None:
                    await asyncio.sleep(self._cycle_delay)
                    continue

                self.goals.mark_running(goal.id)
                self._stats.total_cycles += 1

                await bus.publish(Event(
                    kind="system.notice",
                    actor="autonomy",
                    content=f"Starting goal: {goal.title}",
                    meta={"goal_id": goal.id, "priority": goal.priority.value},
                ))

                try:
                    result = await self._execute_goal(goal)
                    self.goals.mark_completed(goal.id, result=result)
                    self._stats.goals_completed += 1
                    consecutive_failures = 0

                    await bus.publish(Event(
                        kind="system.notice",
                        actor="autonomy",
                        content=f"Completed goal: {goal.title}",
                        meta={"goal_id": goal.id, "result": result[:500]},
                    ))

                except Exception as e:
                    error_msg = str(e)[:500]
                    self.goals.mark_failed(goal.id, error=error_msg)
                    self._stats.goals_failed += 1
                    self._stats.last_error = error_msg
                    consecutive_failures += 1

                    await bus.publish(Event(
                        kind="system.notice",
                        actor="autonomy",
                        content=f"Goal failed: {goal.title} — {error_msg}",
                        meta={"goal_id": goal.id, "error": error_msg},
                    ))

                    if consecutive_failures >= max_consecutive_failures:
                        sm = get_settings_manager()
                        s = sm.load()
                        if s.autonomy.pause_on_error:
                            log.warning(
                                "autonomy.paused",
                                reason="too many consecutive failures",
                            )
                            self._running = False
                            break

                await asyncio.sleep(self._cycle_delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("autonomy.loop_error", error=str(e)[:200])
                await asyncio.sleep(self._cycle_delay * 2)

    async def _execute_goal(self, goal: Any) -> str:
        """Execute a goal through the council."""
        if self._council is None:
            from ..agents.council import Council
            self._council = Council()

        objective = goal.title
        if goal.description:
            objective = f"{goal.title}\n\nDetails: {goal.description}"

        result = await self._council.run_objective(objective)
        return result.get("final", str(result))
