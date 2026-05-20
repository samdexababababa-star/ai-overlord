"""Shared HTTP helpers for providers.

Wraps an httpx client with sensible defaults and key-rotation semantics.
The :func:`key_cycle` helper iterates through a provider's keys and updates
its cooldown table on quota errors.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator

import httpx

from ..log import get_logger
from .base import AuthError, Provider, QuotaExhaustedError, TransientError

log = get_logger(__name__)

# Shared client; httpx pools connections per-host.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def key_cycle(provider: Provider) -> Iterator[str]:
    """Yield keys in a round-robin, skipping ones currently in cooldown."""
    now = time.time()
    n = len(provider.keys)
    for offset in range(n):
        idx = (provider._cursor + offset) % n
        key = provider.keys[idx]
        if provider._cooldown.get(key, 0) > now:
            continue
        yield key
        # advance cursor so next call starts with the next key
        provider._cursor = (idx + 1) % n


def mark_quota_exhausted(provider: Provider, key: str, cooldown_seconds: int = 60) -> None:
    """Place a key in cooldown after a 429 / quota error."""
    provider._cooldown[key] = time.time() + cooldown_seconds
    log.warning("provider.key.cooldown", provider=provider.name, seconds=cooldown_seconds)


def classify_http_error(status: int, body: str) -> Exception:
    if status in (401, 403):
        return AuthError(f"auth failed: {body[:200]}")
    if status in (402, 429):
        return QuotaExhaustedError(f"quota exhausted: {body[:200]}")
    if status >= 500:
        return TransientError(f"upstream {status}: {body[:200]}")
    return TransientError(f"http {status}: {body[:200]}")


async def stream_sse(
    response: httpx.Response,
) -> AsyncIterator[dict]:
    """Yield parsed JSON objects from a Server-Sent-Events stream.

    Accepts both `data: {...}` lines and bare-newline-delimited JSON. Honours
    the `[DONE]` sentinel used by OpenAI-compatible APIs.
    """
    import json

    async for raw in response.aiter_lines():
        if not raw:
            continue
        line = raw.lstrip()
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            break
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            log.debug("provider.stream.skip", line=line[:120])
            continue
