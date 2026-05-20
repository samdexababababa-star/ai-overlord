"""Google AI Studio provider (Gemini + Gemma via the public generativelanguage API).

Docs:
  - https://ai.google.dev/api/rest
  - https://aistudio.google.com/apikey  (where users obtain keys)

This implementation translates the OpenAI-style :class:`ChatRequest` into the
Gemini wire format and back.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from ..config import ProviderModel
from ..log import get_logger
from ._http import classify_http_error, get_client, key_cycle, mark_quota_exhausted
from .base import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    Provider,
    ProviderError,
    QuotaExhaustedError,
    ToolCall,
)

log = get_logger(__name__)


GOOGLE_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="gemini-2.5-pro",
        provider="google",
        label="Gemini 2.5 Pro",
        capabilities=["chat", "reason", "vision", "long_context"],
        context_window=1_000_000,
        cost_tier=2,
    ),
    ProviderModel(
        id="gemini-2.5-flash",
        provider="google",
        label="Gemini 2.5 Flash",
        capabilities=["chat", "reason", "vision", "fast", "long_context"],
        context_window=1_000_000,
        cost_tier=1,
        daily_request_limit=1_500,
    ),
    ProviderModel(
        id="gemini-2.5-flash-lite",
        provider="google",
        label="Gemini 2.5 Flash-Lite",
        capabilities=["chat", "fast", "vision"],
        context_window=1_000_000,
        cost_tier=0,
        daily_request_limit=500,
    ),
    ProviderModel(
        id="gemma-3-27b-it",
        provider="google",
        label="Gemma 3 27B IT",
        capabilities=["chat", "fast"],
        context_window=128_000,
        cost_tier=0,
        daily_request_limit=1_500,
    ),
    ProviderModel(
        id="text-embedding-004",
        provider="google",
        label="Gemini Text Embedding 004",
        capabilities=["embed"],
        context_window=2_048,
        cost_tier=0,
        daily_request_limit=1_500,
    ),
]


def _to_gemini_contents(req: ChatRequest) -> tuple[list[dict[str, Any]], str | None]:
    """Convert OpenAI-style messages to Gemini `contents` + optional system instruction."""
    system: str | None = None
    contents: list[dict[str, Any]] = []
    for m in req.messages:
        if m.role == "system":
            system = (system + "\n\n" + m.content) if system else m.content
            continue
        role = "user" if m.role in ("user", "tool") else "model"
        parts: list[dict[str, Any]] = []
        if m.content:
            parts.append({"text": m.content})
        for img in m.images:
            if img.startswith("data:"):
                mime, b64 = img.split(",", 1)
                mime = mime[5:].split(";")[0] or "image/png"
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            else:
                parts.append({"file_data": {"file_uri": img, "mime_type": "image/png"}})
        contents.append({"role": role, "parts": parts or [{"text": ""}]})
    return contents, system


class GoogleProvider(Provider):
    name = "google"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def models(self) -> list[ProviderModel]:
        return GOOGLE_MODELS

    def _generation_config(self, req: ChatRequest) -> dict[str, Any]:
        cfg: dict[str, Any] = {
            "temperature": req.temperature,
            "topP": req.top_p,
        }
        if req.max_tokens:
            cfg["maxOutputTokens"] = req.max_tokens
        return cfg

    def _tools_payload(self, req: ChatRequest) -> list[dict] | None:
        if not req.tools:
            return None
        return [
            {
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in req.tools
                ]
            }
        ]

    async def chat(self, req: ChatRequest) -> ChatResponse:
        client = get_client()
        contents, system = _to_gemini_contents(req)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": self._generation_config(req),
        }
        if system:
            body["systemInstruction"] = {"role": "system", "parts": [{"text": system}]}
        tools = self._tools_payload(req)
        if tools:
            body["tools"] = tools
        body.update(req.extra)

        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                url = f"{self.base_url}/models/{req.model}:generateContent"
                r = await client.post(url, json=body, params={"key": key})
                if r.status_code in (402, 429):
                    mark_quota_exhausted(self, key, cooldown_seconds=60)
                    last_err = classify_http_error(r.status_code, r.text)
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r.status_code, r.text)
                data = r.json()
                cand = (data.get("candidates") or [{}])[0]
                parts = cand.get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if "text" in p)
                tool_calls: list[ToolCall] = []
                for p in parts:
                    fc = p.get("functionCall")
                    if fc:
                        tool_calls.append(
                            ToolCall(
                                id=fc.get("name", ""),
                                name=fc.get("name", ""),
                                arguments=fc.get("args", {}) or {},
                            )
                        )
                usage = data.get("usageMetadata", {})
                return ChatResponse(
                    text=text,
                    model=req.model,
                    provider=self.name,
                    finish_reason=cand.get("finishReason"),
                    tool_calls=tool_calls,
                    usage={
                        "prompt_tokens": usage.get("promptTokenCount", 0),
                        "completion_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0),
                    },
                )
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("google: no usable key")

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        client = get_client()
        contents, system = _to_gemini_contents(req)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": self._generation_config(req),
        }
        if system:
            body["systemInstruction"] = {"role": "system", "parts": [{"text": system}]}
        body.update(req.extra)

        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                url = f"{self.base_url}/models/{req.model}:streamGenerateContent"
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    params={"key": key, "alt": "sse"},
                ) as r:
                    if r.status_code in (402, 429):
                        mark_quota_exhausted(self, key)
                        last_err = classify_http_error(r.status_code, "")
                        continue
                    if r.status_code >= 400:
                        raw = await r.aread()
                        raise classify_http_error(r.status_code, raw.decode("utf-8", "ignore"))
                    async for raw in r.aiter_lines():
                        line = raw.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        line = line[5:].strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        for cand in chunk.get("candidates", []):
                            for p in cand.get("content", {}).get("parts", []):
                                t = p.get("text")
                                if t:
                                    yield t
                    return
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("google: no usable key (stream)")

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:
        client = get_client()
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                body = {
                    "requests": [
                        {
                            "model": f"models/{model}",
                            "content": {"parts": [{"text": text}]},
                        }
                        for text in inputs
                    ]
                }
                url = f"{self.base_url}/models/{model}:batchEmbedContents"
                r = await client.post(url, json=body, params={"key": key})
                if r.status_code in (402, 429):
                    mark_quota_exhausted(self, key)
                    last_err = classify_http_error(r.status_code, r.text)
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r.status_code, r.text)
                data = r.json()
                vectors = [e["values"] for e in data.get("embeddings", [])]
                return EmbeddingResponse(vectors=vectors, model=model, provider=self.name)
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("google: embed failed")

    async def validate_key(self, key: str) -> bool:
        client = get_client()
        try:
            r = await client.get(
                f"{self.base_url}/models",
                params={"key": key},
                timeout=10.0,
            )
            return r.status_code == 200
        except Exception:
            return False
