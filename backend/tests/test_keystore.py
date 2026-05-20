"""Keystore round-trip."""

from __future__ import annotations

import os
from pathlib import Path


def test_keystore_roundtrip(tmp_path: Path, monkeypatch):
    """Adding and listing a key returns a masked version, and the registry
    can reload the cleartext value."""
    monkeypatch.setenv("AI_OVERLORD_HOME", str(tmp_path))
    # Re-import config + keystore against the fresh dir
    import importlib

    from backend.app import config as _config

    importlib.reload(_config)
    from backend.app import keystore as _ks

    importlib.reload(_ks)

    _ks.add_key("mistral", "primary", "key-abcdef-12345678")
    listing = _ks.list_keys()
    assert "mistral" in listing
    masked = listing["mistral"][0]["masked"]
    assert masked.endswith("5678")
    assert "abcd" in masked or "key-" in masked

    decrypted = _ks.get_keys("mistral")
    assert decrypted == ["key-abcdef-12345678"]

    _ks.remove_key("mistral", "primary")
    assert _ks.get_keys("mistral") == []

    # Cleanup
    os.environ.pop("AI_OVERLORD_HOME", None)
