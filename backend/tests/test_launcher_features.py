"""Tests for the launcher-related features: env import, startup config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_startup_config_defaults():
    """The StartupConfig schema must expose the four startup toggles."""
    from backend.app.user_settings import StartupConfig, UserSettings

    s = StartupConfig()
    assert s.open_at_login is False
    assert s.start_minimized is False
    assert s.auto_start_backend is True
    assert s.auto_start_autonomy is False

    full = UserSettings()
    assert full.startup.open_at_login is False
    # Round-trip through model_dump
    data = full.model_dump()
    assert "startup" in data
    assert data["startup"]["auto_start_backend"] is True


def test_env_var_map_covers_all_providers():
    """Every supported provider must have at least one env var entry."""
    from backend.app.routes.onboarding import ENV_VAR_MAP

    providers = set(ENV_VAR_MAP.values())
    expected = {"mistral", "nvidia", "google", "groq", "openrouter", "cerebras", "together"}
    assert expected.issubset(providers), f"missing providers in ENV_VAR_MAP: {expected - providers}"


def test_load_dotenv_parser(tmp_path: Path):
    """The stdlib dotenv parser must handle common formats."""
    from backend.app.routes.onboarding import _load_dotenv

    p = tmp_path / ".env"
    p.write_text(
        '# comment\n'
        'MISTRAL_API_KEY=abc123\n'
        'export GROQ_API_KEY="gsk_xyz"\n'
        "OPENROUTER_API_KEY='sk-or-789'\n"
        "EMPTY=\n"
        "BAD_LINE_NO_EQUALS\n",
        encoding="utf-8",
    )
    parsed = _load_dotenv(p)
    assert parsed["MISTRAL_API_KEY"] == "abc123"
    assert parsed["GROQ_API_KEY"] == "gsk_xyz"
    assert parsed["OPENROUTER_API_KEY"] == "sk-or-789"
    assert "EMPTY" not in parsed
    assert "BAD_LINE_NO_EQUALS" not in parsed


def test_load_dotenv_missing_file(tmp_path: Path):
    """A missing file should return an empty dict, not raise."""
    from backend.app.routes.onboarding import _load_dotenv

    assert _load_dotenv(tmp_path / "missing.env") == {}


@pytest.mark.asyncio
async def test_env_detect_picks_up_system_env(monkeypatch: pytest.MonkeyPatch):
    """Setting an env var should make it visible via env-detect."""
    from backend.app.routes.onboarding import _detect_env_keys, env_detect

    monkeypatch.setenv("MISTRAL_API_KEY", "sk-test-very-long-key-1234567890")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-something-here-abcdefg")

    detected = _detect_env_keys()
    assert "MISTRAL_API_KEY" in detected
    assert detected["MISTRAL_API_KEY"]["provider"] == "mistral"
    assert "CEREBRAS_API_KEY" in detected
    assert detected["CEREBRAS_API_KEY"]["provider"] == "cerebras"

    payload = env_detect()
    found_providers = {k["provider"] for k in payload["keys"]}
    assert {"mistral", "cerebras"}.issubset(found_providers)
    # Masking applied
    for k in payload["keys"]:
        if k["env_var"] == "MISTRAL_API_KEY":
            assert "…" in k["masked"]
            assert "sk-test-very-long-key" not in k["masked"]


def test_launcher_script_exists_and_is_python():
    """The cross-platform launcher must be present and importable as text."""
    root = Path(__file__).resolve().parents[2]
    launch = root / "launch.py"
    assert launch.exists(), "launch.py must live at the repo root"
    body = launch.read_text(encoding="utf-8")
    assert "AI Overlord one-click launcher" in body
    for flag in ("--no-electron", "--rebuild", "--reset", "--check", "--port"):
        assert flag in body, f"launcher missing flag {flag}"


def test_launcher_wrappers_exist():
    """Each OS gets a one-click double-clickable wrapper."""
    root = Path(__file__).resolve().parents[2]
    assert (root / "Start AI Overlord.bat").exists()
    assert (root / "Start AI Overlord.command").exists()
    assert (root / "start-ai-overlord.sh").exists()
    # Unix wrappers should be executable
    if os.name != "nt":
        sh = root / "start-ai-overlord.sh"
        mac = root / "Start AI Overlord.command"
        assert os.access(sh, os.X_OK), "Linux launcher must be executable"
        assert os.access(mac, os.X_OK), "macOS launcher must be executable"
