"""Groq provider — OpenAI-compatible.

Insanely fast inference (~800 tok/s for Llama 3.3 70B). Free tier with daily
limits. Docs: https://console.groq.com/docs/api-reference
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
    ToolCall,
)

log = get_logger(__name__)


GROQ_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="llama-3.3-70b-versatile",
        provider="groq",
        label="Llama 3.3 70B Versatile",
        capabilities=["chat", "reason", "fast", "long_context"],
        context_window=131_072,
        cost_tier=0,
        daily_request_limit=14_400,
    ),
    ProviderModel(
        id="llama-3.1-8b-instant",
        provider="groq",
        label="Llama 3.1 8B Instant",
        capabilities=["chat", "fast"],
        context_window=131_072,
        cost_tier=0,
        daily_request_limit=14_400,
    ),
    ProviderModel(
        id="meta-llama/llama-4-scout-17b-16e-instruct",
        provider="groq",
        label="Llama 4 Scout 17B",
        capabilities=["chat", "fast", "long_context"],
        context_window=131_072,
        cost_tier=0,
    ),
    ProviderModel(
        id="qwen/qwen3-32b",
        provider="groq",
        label="Qwen 3 32B",
        capabilities=["chat", "reason"],
        context_window=131_072,
        cost_tier=0,
    ),
]


class GroqProvider(Provider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1"

    @property
    def models(self) -> list[ProviderModel]:
        return GROQ_MODELS

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
        if req.tools:
            payload["tools"] = [
                {"type": "function", "function": t.model_dump()} for t in req.tools
            ]
            if req.tool_choice:
                payload["tool_choice"] = req.tool_choice
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
                tool_calls: list[ToolCall] = []
                for tc in msg.get("tool_calls", []) or []:
                    import json
                    fn = tc.get("function", {})
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except Exception:
                        args = {"_raw": args_raw}
                    tool_calls.append(
                        ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
                    )
                return ChatResponse(
                    text=msg.get("content") or "",
                    model=req.model,
                    provider=self.name,
                    finish_reason=choice.get("finish_reason"),
                    tool_calls=tool_calls,
                    usage=data.get("usage", {}),
                )
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("groq: no usable key")

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        client = get_client()
        payload = self._payload(req.model_copy(update={"stream": True}))
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                ) as r:
                    if r.status_code in (402, 429):
                        mark_quota_exhausted(self, key)
                        last_err = classify_http_error(r.status_code, "")
                        continue
                    if r.status_code >= 400:
                        body = await r.aread()
                        raise classify_http_error(r.status_code, body.decode("utf-8", "ignore"))
                    async for chunk in stream_sse(r):
                        try:
                            delta = chunk["choices"][0].get("delta", {})
                            piece = delta.get("content") or ""
                            if piece:
                                yield piece
                        except (KeyError, IndexError):
                            continue
                    return
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("groq: no usable key (stream)")

    async def validate_key(self, key: str) -> bool:
        client = get_client()
        try:
            r = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10.0,
            )
            return r.status_code == 200
        except Exception:
            return False
