"""Together AI provider — fast open-source model inference.

Docs: https://docs.together.ai/
Free tier with rate limits.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from ..config import ProviderModel
from ..log import get_logger
from ._http import classify_http_error, get_client, key_cycle, mark_quota_exhausted, stream_sse
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


TOGETHER_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        provider="together",
        label="Llama 3.3 70B Turbo",
        capabilities=["chat", "reason"],
        context_window=131_072,
        cost_tier=0,
    ),
    ProviderModel(
        id="Qwen/Qwen2.5-Coder-32B-Instruct",
        provider="together",
        label="Qwen 2.5 Coder 32B",
        capabilities=["chat", "code"],
        context_window=32_768,
        cost_tier=0,
    ),
    ProviderModel(
        id="deepseek-ai/DeepSeek-R1",
        provider="together",
        label="DeepSeek R1",
        capabilities=["chat", "reason", "long_context"],
        context_window=163_840,
        cost_tier=1,
    ),
    ProviderModel(
        id="meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo",
        provider="together",
        label="Llama 3.2 90B Vision",
        capabilities=["chat", "vision"],
        context_window=131_072,
        cost_tier=0,
    ),
    ProviderModel(
        id="togethercomputer/m2-bert-80M-8k-retrieval",
        provider="together",
        label="M2 BERT Retrieval",
        capabilities=["embed"],
        context_window=8_192,
        cost_tier=0,
    ),
]


class TogetherProvider(Provider):
    name = "together"
    base_url = "https://api.together.xyz/v1"

    @property
    def models(self) -> list[ProviderModel]:
        return TOGETHER_MODELS

    def _payload(self, req: ChatRequest) -> dict:
        msgs = []
        for m in req.messages:
            if m.images:
                content: list[dict] = [{"type": "text", "text": m.content}]
                for url in m.images:
                    content.append({"type": "image_url", "image_url": {"url": url}})
                msgs.append({"role": m.role, "content": content})
            else:
                msgs.append({"role": m.role, "content": m.content})
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
            except Exception as e:
                last_err = e
                continue
        raise last_err or ProviderError("together: no usable key")

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

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:
        client = get_client()
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                r = await client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": model, "input": inputs},
                    headers={"Authorization": f"Bearer {key}"},
                )
                if r.status_code >= 400:
                    raise classify_http_error(r.status_code, r.text)
                data = r.json()
                vectors = [item["embedding"] for item in data.get("data", [])]
                return EmbeddingResponse(
                    vectors=vectors, model=model, provider=self.name
                )
            except Exception as e:
                last_err = e
                continue
        raise last_err or ProviderError("together: embed failed")

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
