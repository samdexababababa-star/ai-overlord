"""Sandboxed self-improvement — the agent modifies its own code safely.

Safety model (inspired by "Voyager" — Wang et al. 2023):
1. All modifications happen on a separate git branch.
2. Tests must pass before changes are considered.
3. If tests fail, the branch is abandoned (rollback).
4. The user can review and merge at any time.
5. Each improvement cycle has a bounded scope.

This module manages the git workflow and test execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import time
import uuid

from pydantic import BaseModel, Field

from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


class ImprovementAttempt(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    branch_name: str
    description: str
    files_changed: list[str] = Field(default_factory=list)
    test_passed: bool = False
    test_output: str = ""
    created_at: float = Field(default_factory=time.time)
    merged: bool = False
    rolled_back: bool = False


class SelfImprover:
    """Manages sandboxed self-improvement cycles.

    Parameters
    ----------
    repo_path : str | None
        Path to the repo. Defaults to the current repo root.
    branch_prefix : str
        Prefix for auto-improvement branches.
    test_command : str
        Command to run tests.
    """

    def __init__(
        self,
        repo_path: str | None = None,
        branch_prefix: str | None = None,
        test_command: str = "python -m pytest -x --tb=short",
    ):
        self.repo_path = repo_path or str(
            os.environ.get("AI_OVERLORD_REPO", os.getcwd())
        )
        self.branch_prefix = branch_prefix or settings.autoimprove_branch_prefix
        self.test_command = test_command
        self._history: list[ImprovementAttempt] = []

    def _run_git(self, *args: str) -> tuple[int, str]:
        """Run a git command and return (returncode, output)."""
        try:
            r = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return r.returncode, (r.stdout + r.stderr).strip()
        except Exception as e:
            return 1, str(e)

    def create_branch(self, description: str) -> ImprovementAttempt:
        """Create a new improvement branch."""
        branch = f"{self.branch_prefix}{int(time.time())}-{uuid.uuid4().hex[:6]}"
        self._run_git("checkout", "-b", branch)

        attempt = ImprovementAttempt(
            branch_name=branch,
            description=description,
        )
        self._history.append(attempt)
        log.info("self_improve.branch_created", branch=branch)
        return attempt

    async def run_tests(self, attempt: ImprovementAttempt) -> bool:
        """Run tests on the current branch."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.test_command.split(),
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = (stdout or b"").decode("utf-8", "replace")
            passed = proc.returncode == 0

            attempt.test_passed = passed
            attempt.test_output = output[:8000]

            log.info(
                "self_improve.tests",
                branch=attempt.branch_name,
                passed=passed,
            )
            return passed
        except Exception as e:
            attempt.test_output = f"Test execution error: {e}"
            attempt.test_passed = False
            return False

    def commit_changes(
        self, attempt: ImprovementAttempt, message: str
    ) -> bool:
        """Stage and commit all changes."""
        rc, _ = self._run_git("add", "-A")
        if rc != 0:
            return False
        rc, _ = self._run_git("commit", "-m", message)
        if rc != 0:
            return False

        rc, diff = self._run_git("diff", "--name-only", "HEAD~1")
        if rc == 0:
            attempt.files_changed = [
                f for f in diff.splitlines() if f.strip()
            ]
        return True

    def rollback(self, attempt: ImprovementAttempt) -> None:
        """Abandon the improvement branch and return to main."""
        current_branch = self._get_current_branch()
        if current_branch == attempt.branch_name:
            self._run_git("checkout", "main")
            with contextlib.suppress(Exception):
                self._run_git("branch", "-D", attempt.branch_name)
        attempt.rolled_back = True
        log.info("self_improve.rollback", branch=attempt.branch_name)

    def _get_current_branch(self) -> str:
        rc, out = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return out.strip() if rc == 0 else "unknown"

    async def attempt_improvement(
        self, description: str, code_changes: dict[str, str]
    ) -> ImprovementAttempt:
        """Full improvement cycle: branch → apply changes → test → commit or rollback."""
        attempt = self.create_branch(description)

        for filepath, content in code_changes.items():
            full_path = os.path.join(self.repo_path, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            attempt.files_changed.append(filepath)

        passed = await self.run_tests(attempt)

        if passed:
            self.commit_changes(attempt, f"auto-improve: {description}")
            log.info("self_improve.success", branch=attempt.branch_name)
        else:
            self.rollback(attempt)
            log.info("self_improve.failed", branch=attempt.branch_name)

        return attempt

    def get_history(self) -> list[ImprovementAttempt]:
        return list(self._history)
