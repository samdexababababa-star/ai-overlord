"""User settings — persistent configuration store.

Controls all behavioural aspects of the agent:
- Autonomy level (from fully guided to fully autonomous)
- HITL (Human-in-the-Loop) controls per action category
- Council configuration (which strategies to use, depth, etc.)
- Reasoning strategy preferences
- Memory and consolidation settings
- UI preferences
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import settings
from .log import get_logger

log = get_logger(__name__)


class HITLConfig(BaseModel):
    """Human-in-the-Loop configuration per action category."""

    enabled: bool = True
    shell_commands: bool = True
    browser_actions: bool = False
    file_writes: bool = True
    financial_actions: bool = True
    account_creation: bool = True
    email_sending: bool = True
    api_calls: bool = False
    auto_approve_safe: bool = True


class AutonomyConfig(BaseModel):
    """Controls how autonomous the agent is."""

    level: Literal["guided", "supervised", "autonomous"] = "supervised"
    max_actions_per_minute: int = 10
    max_cost_per_day_usd: float = 5.0
    allow_background_tasks: bool = True
    auto_restart_on_failure: bool = True
    pause_on_error: bool = False
    require_approval_above_cost: float = 1.0


class CouncilConfig(BaseModel):
    """Council reasoning configuration."""

    default_strategy: str = "auto"
    enable_tree_of_thoughts: bool = True
    enable_reflexion: bool = True
    enable_debate: bool = True
    enable_constitutional: bool = True
    tot_max_depth: int = 4
    tot_branching_factor: int = 3
    tot_beam_width: int = 2
    reflexion_max_trials: int = 3
    reflexion_threshold: float = 0.8
    debate_num_debaters: int = 3
    debate_max_rounds: int = 3
    constitutional_max_revisions: int = 3
    fast_mode_threshold: float = 0.2


class MemoryConfig(BaseModel):
    """Memory and knowledge management configuration."""

    enable_episodic: bool = True
    enable_semantic: bool = True
    enable_knowledge_graph: bool = True
    enable_procedural: bool = True
    consolidation_interval_hours: float = 6.0
    max_episodic_entries: int = 100_000
    semantic_top_k: int = 5
    auto_extract_entities: bool = True


class UIConfig(BaseModel):
    """UI preferences (stored server-side, synced to frontend)."""

    theme: Literal["dark", "light", "auto"] = "dark"
    language: str = "auto"
    show_agent_thoughts: bool = True
    show_reasoning_details: bool = True
    show_cost_tracker: bool = True
    compact_mode: bool = False
    animations_enabled: bool = True
    notification_sound: bool = True


class UserSettings(BaseModel):
    """Complete user settings."""

    hitl: HITLConfig = Field(default_factory=HITLConfig)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    updated_at: float = Field(default_factory=time.time)
    version: int = 1


class SettingsManager:
    """Persist and manage user settings as JSON."""

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.data_dir / "user_settings.json")
        self._settings: UserSettings | None = None

    def load(self) -> UserSettings:
        if self._settings is not None:
            return self._settings
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._settings = UserSettings(**data)
            except Exception as e:
                log.warning("settings.load_fail", error=str(e)[:200])
                self._settings = UserSettings()
        else:
            self._settings = UserSettings()
        return self._settings

    def save(self, s: UserSettings | None = None) -> None:
        if s is not None:
            self._settings = s
        if self._settings is None:
            return
        self._settings.updated_at = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            self._settings.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def update(self, patch: dict[str, Any]) -> UserSettings:
        """Apply a partial update to settings."""
        current = self.load()
        data = current.model_dump()
        _deep_update(data, patch)
        self._settings = UserSettings(**data)
        self.save()
        return self._settings

    def get(self) -> UserSettings:
        return self.load()

    def check_hitl_required(self, action_type: str) -> bool:
        """Check if HITL confirmation is required for an action type."""
        s = self.load()
        if not s.hitl.enabled:
            return False
        return getattr(s.hitl, action_type, False)

    def check_autonomy_allowed(self, action_type: str) -> bool:
        """Check if an action is allowed under current autonomy settings."""
        s = self.load()
        if s.autonomy.level == "guided":
            return False
        if s.autonomy.level == "supervised":
            return not self.check_hitl_required(action_type)
        return True


def _deep_update(base: dict, patch: dict) -> None:
    """Recursively merge *patch* into *base*."""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


_manager: SettingsManager | None = None


def get_settings_manager() -> SettingsManager:
    global _manager
    if _manager is None:
        _manager = SettingsManager()
    return _manager
