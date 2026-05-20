"""NVIDIA NIM (build.nvidia.com) provider — OpenAI-compatible.

Docs: https://docs.api.nvidia.com/ and https://build.nvidia.com/
"""

from __future__ import annotations

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


NVIDIA_MODELS: list[ProviderModel] = [
    # Top frontier-grade hosted on NIM free tier
    ProviderModel(
        id="meta/llama-3.3-70b-instruct",
        provider="nvidia",
        label="Llama 3.3 70B Instruct",
        capabilities=["chat", "reason", "long_context"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="nvidia/llama-3.1-nemotron-70b-instruct",
        provider="nvidia",
        label="Nemotron 70B",
        capabilities=["chat", "reason"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="nvidia/llama-3.1-nemotron-ultra-253b-v1",
        provider="nvidia",
        label="Nemotron Ultra 253B",
        capabilities=["chat", "reason", "long_context"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="deepseek-ai/deepseek-r1",
        provider="nvidia",
        label="DeepSeek R1 (reasoning)",
        capabilities=["chat", "reason", "long_context"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="qwen/qwen2.5-72b-instruct",
        provider="nvidia",
        label="Qwen 2.5 72B",
        capabilities=["chat", "reason"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="qwen/qwen2.5-coder-32b-instruct",
        provider="nvidia",
        label="Qwen 2.5 Coder 32B",
        capabilities=["chat", "code"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="meta/llama-3.2-90b-vision-instruct",
        provider="nvidia",
        label="Llama 3.2 90B Vision",
        capabilities=["chat", "vision"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="microsoft/phi-3.5-vision-instruct",
        provider="nvidia",
        label="Phi 3.5 Vision",
        capabilities=["chat", "vision", "fast"],
        context_window=128_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="nvidia/llama-3.2-nv-embedqa-1b-v2",
        provider="nvidia",
        label="NV Embed QA 1B v2",
        capabilities=["embed"],
        context_window=8_192,
        cost_tier=0,
    ),
]


class NvidiaProvider(Provider):
    name = "nvidia"
    base_url = "https://integrate.api.nvidia.com/v1"

    @property
    def models(self) -> list[ProviderModel]:
        return NVIDIA_MODELS

    def _payload(self, req: ChatRequest) -> dict:
        msgs = []
        is_vision_model = req.model.endswith("vision-instruct") or "vision" in req.model
        for m in req.messages:
            if m.images and is_vision_model:
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
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(req.model_copy(update={"stream": False}))
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                r = await client.post(
                    url, json=payload, headers={"Authorization": f"Bearer {key}"}
                )
                if r.status_code in (402, 429):
                    mark_quota_exhausted(self, key, cooldown_seconds=60)
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
        raise last_err or ProviderError("nvidia: no usable key")

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        client = get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(req.model_copy(update={"stream": True}))
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                async with client.stream(
                    "POST", url, json=payload, headers={"Authorization": f"Bearer {key}"}
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
        raise last_err or ProviderError("nvidia: no usable key (stream)")

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:
        client = get_client()
        url = f"{self.base_url}/embeddings"
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                r = await client.post(
                    url,
                    json={"model": model, "input": inputs, "input_type": "query"},
                    headers={"Authorization": f"Bearer {key}"},
                )
                if r.status_code in (402, 429):
                    mark_quota_exhausted(self, key)
                    last_err = classify_http_error(r.status_code, r.text)
                    continue
                if r.status_code >= 400:
                    raise classify_http_error(r.status_code, r.text)
                data = r.json()
                vectors = [d["embedding"] for d in data["data"]]
                return EmbeddingResponse(vectors=vectors, model=model, provider=self.name)
            except QuotaExhaustedError as e:
                last_err = e
                continue
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("nvidia: embed failed")

    async def validate_key(self, key: str) -> bool:
        client = get_client()
        try:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": "meta/llama-3.3-70b-instruct",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=15.0,
            )
            return r.status_code in (200, 400)  # 400 still means auth worked
        except Exception:
            return False
