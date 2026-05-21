"""Autonomy subsystem — 24/7 background goal execution.

Provides:
- GoalManager: persistent goal queue with priorities and dependencies
- AutonomyLoop: background asyncio task that picks goals, executes them
  via the council, and reports results
- GuardRails: safety checks, cost tracking, error recovery
"""

from .goals import Goal, GoalManager, GoalStatus
from .loop import AutonomyLoop

__all__ = ["Goal", "GoalManager", "GoalStatus", "AutonomyLoop"]
