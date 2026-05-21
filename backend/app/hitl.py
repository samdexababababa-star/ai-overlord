"""Human-in-the-Loop (HITL) action approval system.

When HITL is enabled (default for risky actions), the agent prepares an action
description and waits for user approval before executing. Actions are queued
and the frontend displays them for review.

Features:
- Per-category HITL toggles (shell, browser, financial, account creation, etc.)
- Bulk approval/rejection
- Auto-approve for safe categories when configured
- Audit log of all approved/rejected actions
- Timeout-based auto-reject for safety
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from .log import get_logger
from .user_settings import get_settings_manager

log = get_logger(__name__)


class PendingAction(BaseModel):
    """An action awaiting user approval."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    action_type: str
    description: str
    details: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    created_at: float = Field(default_factory=time.time)
    timeout_seconds: float = 300.0
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    resolved_at: float | None = None
    resolved_by: str | None = None


class ActionAuditEntry(BaseModel):
    """Audit log entry for a resolved action."""

    action_id: str
    action_type: str
    description: str
    status: str
    created_at: float
    resolved_at: float
    resolved_by: str


class HITLManager:
    """Manages pending actions and their approval flow."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingAction] = {}
        self._waiters: dict[str, asyncio.Event] = {}
        self._audit: list[ActionAuditEntry] = []
        self._max_audit = 1000

    def requires_approval(self, action_type: str) -> bool:
        """Check if an action type requires HITL approval."""
        sm = get_settings_manager()
        return sm.check_hitl_required(action_type)

    async def request_approval(
        self,
        action_type: str,
        description: str,
        details: dict[str, Any] | None = None,
        risk_level: str = "medium",
        timeout: float = 300.0,
    ) -> bool:
        """Queue an action for approval and wait for the user's decision.

        Returns True if approved, False if rejected or timed out.
        """
        if not self.requires_approval(action_type):
            return True

        action = PendingAction(
            action_type=action_type,
            description=description,
            details=details or {},
            risk_level=risk_level,  # type: ignore[arg-type]
            timeout_seconds=timeout,
        )
        event = asyncio.Event()
        self._pending[action.id] = action
        self._waiters[action.id] = event

        log.info(
            "hitl.request",
            action_id=action.id,
            action_type=action_type,
            risk=risk_level,
        )

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            result = self._pending[action.id].status == "approved"
        except TimeoutError:
            action.status = "expired"
            action.resolved_at = time.time()
            action.resolved_by = "timeout"
            result = False
        finally:
            self._record_audit(action)
            self._pending.pop(action.id, None)
            self._waiters.pop(action.id, None)

        return result

    def approve(self, action_id: str, by: str = "user") -> bool:
        """Approve a pending action."""
        action = self._pending.get(action_id)
        if not action or action.status != "pending":
            return False
        action.status = "approved"
        action.resolved_at = time.time()
        action.resolved_by = by
        event = self._waiters.get(action_id)
        if event:
            event.set()
        log.info("hitl.approved", action_id=action_id)
        return True

    def reject(self, action_id: str, by: str = "user") -> bool:
        """Reject a pending action."""
        action = self._pending.get(action_id)
        if not action or action.status != "pending":
            return False
        action.status = "rejected"
        action.resolved_at = time.time()
        action.resolved_by = by
        event = self._waiters.get(action_id)
        if event:
            event.set()
        log.info("hitl.rejected", action_id=action_id)
        return True

    def approve_all(self, by: str = "user") -> int:
        """Approve all pending actions."""
        count = 0
        for aid in list(self._pending.keys()):
            if self.approve(aid, by):
                count += 1
        return count

    def reject_all(self, by: str = "user") -> int:
        """Reject all pending actions."""
        count = 0
        for aid in list(self._pending.keys()):
            if self.reject(aid, by):
                count += 1
        return count

    def list_pending(self) -> list[PendingAction]:
        """List all pending actions."""
        now = time.time()
        result = []
        for action in self._pending.values():
            if action.status == "pending":
                if now - action.created_at > action.timeout_seconds:
                    action.status = "expired"
                    action.resolved_at = now
                    action.resolved_by = "timeout"
                    self._record_audit(action)
                else:
                    result.append(action)
        return result

    def get_audit_log(self, limit: int = 50) -> list[ActionAuditEntry]:
        return self._audit[-limit:]

    def _record_audit(self, action: PendingAction) -> None:
        entry = ActionAuditEntry(
            action_id=action.id,
            action_type=action.action_type,
            description=action.description,
            status=action.status,
            created_at=action.created_at,
            resolved_at=action.resolved_at or time.time(),
            resolved_by=action.resolved_by or "unknown",
        )
        self._audit.append(entry)
        if len(self._audit) > self._max_audit:
            self._audit = self._audit[-self._max_audit:]


_hitl: HITLManager | None = None


def get_hitl() -> HITLManager:
    global _hitl
    if _hitl is None:
        _hitl = HITLManager()
    return _hitl
