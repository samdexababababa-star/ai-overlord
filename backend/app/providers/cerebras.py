"""Cerebras provider — ultra-fast inference on Wafer-Scale hardware.

Docs: https://cloud.cerebras.ai/docs
Free tier available with daily limits.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import ProviderModel
from ..log import get_logger
from ._http import classify_http_error, get_client, key_cycle, mark_quota_exhausted, stream_sse
from .base import (
    ChatRequest,
    ChatResponse,
    Provider,
    ProviderError,
    QuotaExhaustedError,
)

log = get_logger(__name__)


CEREBRAS_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="llama-3.3-70b",
        provider="cerebras",
        label="Llama 3.3 70B (Cerebras)",
        capabilities=["chat", "reason", "fast"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="llama-4-scout-17b-16e-instruct",
        provider="cerebras",
        label="Llama 4 Scout 17B (Cerebras)",
        capabilities=["chat", "fast"],
        context_window=131_072,
        cost_tier=0,
    ),
    ProviderModel(
        id="qwen-3-32b",
        provider="cerebras",
        label="Qwen 3 32B (Cerebras)",
        capabilities=["chat", "reason", "fast"],
        context_window=32_768,
        cost_tier=0,
    ),
]


class CerebrasProvider(Provider):
    name = "cerebras"
    base_url = "https://api.cerebras.ai/v1"

    @property
    def models(self) -> list[ProviderModel]:
        return CEREBRAS_MODELS

    def _payload(self, req: ChatRequest) -> dict:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        payload: dict = {
            "model": req.model,
            "messages": msgs,
            "temperature": req.temperature,
            "top_p": req.top_p,
            "stream": req.stream,
        }
        if req.max_tokens:
            payload["max_tokens"] = req.max_tokens
        payload.update(req.extra)
        return payload

    async def chat(self, req: ChatRequest) -> ChatResponse:
        client = get_client()
        payload = self._payload(req.model_copy(update={"stream": False}))
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                )
                if r.status_code in (402, 429):
                    mark_quota_exhausted(self, key)
                    last_err = classify_http_error(r.status_code, r.text)
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r.status_code, r.text)
                data = r.json()
                choice = data["choices"][0]
                msg = choice.get("message", {})
                return ChatResponse(
                    text=msg.get("content") or "",
                    model=req.model,
                    provider=self.name,
                    finish_reason=choice.get("finish_reason"),
                    usage=data.get("usage", {}),
                )
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:
                last_err = e
                continue
        raise last_err or ProviderError("cerebras: no usable key")

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        client = get_client()
        payload = self._payload(req.model_copy(update={"stream": True}))
        for key in key_cycle(self):
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                ) as r:
                    if r.status_code >= 400:
                        body = await r.aread()
                        raise classify_http_error(r.status_code, body.decode())
                    async for chunk in stream_sse(r):
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content")
                        )
                        if delta:
                            yield delta
                return
            except Exception:
                continue

    async def validate_key(self, key: str) -> bool:
        try:
            client = get_client()
            r = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            return r.status_code == 200
        except Exception:
            return False
