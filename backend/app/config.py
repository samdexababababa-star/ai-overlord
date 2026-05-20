"""Runtime configuration & paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


def _data_dir() -> Path:
    """Persistent application data dir.

    Honours `AI_OVERLORD_HOME`; otherwise uses the OS-appropriate default.
    """
    override = os.environ.get("AI_OVERLORD_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif "darwin" in os.sys.platform:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ai-overlord"


DATA_DIR = _data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OVERLORD_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    data_dir: Path = DATA_DIR
    sqlite_path: Path = DATA_DIR / "overlord.sqlite"
    chroma_path: Path = DATA_DIR / "chroma"

    # Browser
    chrome_cdp_url: str = "http://localhost:29229"

    # Council
    council_max_turns: int = 6
    council_critic_threshold: float = 0.5

    # Auto-improvement sandbox
    autoimprove_enabled: bool = False
    autoimprove_branch_prefix: str = "overlord/auto-"


class ProviderModel(BaseModel):
    """A model exposed by one provider, with task affinity & approximate cost."""

    id: str  # API-side id, e.g. "mistral-large-latest"
    provider: str  # "mistral" | "nvidia" | "google" | "groq"
    label: str  # human-friendly
    capabilities: list[
        Literal["chat", "reason", "code", "vision", "embed", "audio", "fast", "long_context"]
    ]
    context_window: int = 32_000
    # Lower is cheaper; used to break ties in router (0 = free, 1 = cheapest paid, ...)
    cost_tier: int = 0
    # Daily quota hint (None = unknown / unlimited)
    daily_request_limit: int | None = None


settings = Settings()
