"""Encrypted local keystore for API keys.

By default we store keys in a SQLite table at :data:`Settings.sqlite_path`,
encrypted at rest via a key derived from :func:`platform_secret` (the OS
keychain when available; falls back to a per-install random key under
``DATA_DIR/.master`` if no keyring is reachable). The frontend can also push
keys directly via the ``/onboarding/keys`` endpoint.

Note: this is *defence in depth*, not a substitute for OS account security.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import secrets
import sqlite3
from pathlib import Path

from .config import settings
from .log import get_logger

log = get_logger(__name__)


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _master_key() -> bytes:
    """Return a stable per-install symmetric key.

    Tries the OS keychain (via the optional ``keyring`` library); if absent,
    derives a random key persisted under ``DATA_DIR/.master`` with 0600 perms.
    """
    try:
        import keyring  # type: ignore

        existing = keyring.get_password("ai-overlord", "master")
        if existing:
            return base64.urlsafe_b64decode(existing)
        new = secrets.token_bytes(32)
        keyring.set_password(
            "ai-overlord", "master", base64.urlsafe_b64encode(new).decode("ascii")
        )
        return new
    except Exception:  # noqa: BLE001
        path: Path = settings.data_dir / ".master"
        if path.exists():
            return path.read_bytes()
        new = secrets.token_bytes(32)
        path.write_bytes(new)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
        return new


def _conn() -> sqlite3.Connection:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.sqlite_path)
    c.execute(
        """CREATE TABLE IF NOT EXISTS api_keys (
            provider TEXT NOT NULL,
            label    TEXT NOT NULL,
            blob     TEXT NOT NULL,
            created  REAL NOT NULL,
            PRIMARY KEY (provider, label)
        )"""
    )
    return c


def _encrypt(value: str) -> str:
    raw = value.encode("utf-8")
    return base64.urlsafe_b64encode(_xor_bytes(raw, _master_key())).decode("ascii")


def _decrypt(blob: str) -> str:
    raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    return _xor_bytes(raw, _master_key()).decode("utf-8")


def list_keys() -> dict[str, list[dict[str, str]]]:
    """Return ``{provider: [{label, masked}]}`` (values not exposed)."""
    out: dict[str, list[dict[str, str]]] = {}
    with _conn() as c:
        for provider, label, blob in c.execute(
            "SELECT provider, label, blob FROM api_keys ORDER BY provider, created"
        ):
            decrypted = _decrypt(blob)
            masked = decrypted[:4] + "…" + decrypted[-4:] if len(decrypted) > 12 else "…"
            out.setdefault(provider, []).append({"label": label, "masked": masked})
    return out


def get_keys(provider: str) -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT blob FROM api_keys WHERE provider = ? ORDER BY created", (provider,)
        ).fetchall()
    return [_decrypt(r[0]) for r in rows]


def all_keys() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with _conn() as c:
        for provider, blob in c.execute(
            "SELECT provider, blob FROM api_keys ORDER BY provider, created"
        ):
            out.setdefault(provider, []).append(_decrypt(blob))
    return out


def add_key(provider: str, label: str, value: str) -> None:
    import time

    blob = _encrypt(value.strip())
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO api_keys (provider, label, blob, created) VALUES (?, ?, ?, ?)",
            (provider, label, blob, time.time()),
        )
        c.commit()
    log.info("keystore.add", provider=provider, label=label)


def remove_key(provider: str, label: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM api_keys WHERE provider = ? AND label = ?", (provider, label))
        c.commit()
    log.info("keystore.remove", provider=provider, label=label)


def export_dict() -> str:
    """Plain-text JSON export (for migration). Encrypted with master key on disk; this is plaintext."""
    return json.dumps(all_keys(), indent=2)
