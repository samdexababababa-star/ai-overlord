"""Mistral AI provider.

Docs: https://docs.mistral.ai/api/
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import ProviderModel
from ..log import get_logger
from ._http import (
    classify_http_error,
    get_client,
    key_cycle,
    mark_quota_exhausted,
    stream_sse,
)
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


MISTRAL_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="mistral-large-latest",
        provider="mistral",
        label="Mistral Large",
        capabilities=["chat", "reason", "long_context"],
        context_window=128_000,
        cost_tier=2,
    ),
    ProviderModel(
        id="mistral-medium-latest",
        provider="mistral",
        label="Mistral Medium",
        capabilities=["chat", "reason"],
        context_window=128_000,
        cost_tier=2,
    ),
    ProviderModel(
        id="mistral-small-latest",
        provider="mistral",
        label="Mistral Small",
        capabilities=["chat", "fast"],
        context_window=128_000,
        cost_tier=1,
    ),
    ProviderModel(
        id="ministral-8b-latest",
        provider="mistral",
        label="Ministral 8B",
        capabilities=["chat", "fast"],
        context_window=128_000,
        cost_tier=1,
    ),
    ProviderModel(
        id="ministral-3b-latest",
        provider="mistral",
        label="Ministral 3B",
        capabilities=["chat", "fast"],
        context_window=128_000,
        cost_tier=1,
    ),
    ProviderModel(
        id="codestral-latest",
        provider="mistral",
        label="Codestral",
        capabilities=["chat", "code"],
        context_window=256_000,
        cost_tier=1,
    ),
    ProviderModel(
        id="pixtral-large-latest",
        provider="mistral",
        label="Pixtral Large",
        capabilities=["chat", "vision"],
        context_window=128_000,
        cost_tier=2,
    ),
    ProviderModel(
        id="mistral-embed",
        provider="mistral",
        label="Mistral Embed",
        capabilities=["embed"],
        context_window=8_192,
        cost_tier=1,
    ),
]


class MistralProvider(Provider):
    name = "mistral"
    base_url = "https://api.mistral.ai/v1"

    @property
    def models(self) -> list[ProviderModel]:
        return MISTRAL_MODELS

    def _payload(self, req: ChatRequest) -> dict:
        msgs = []
        for m in req.messages:
            if m.images and any(c == "vision" for model in MISTRAL_MODELS for c in model.capabilities if model.id == req.model):
                content: list[dict] = [{"type": "text", "text": m.content}]
                for url in m.images:
                    content.append({"type": "image_url", "image_url": url})
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
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
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
                tool_calls = []
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
            except ProviderError as e:
                last_err = e
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        raise last_err or ProviderError("mistral: no usable key")

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        client = get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(req.model_copy(update={"stream": True}))
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                ) as r:
                    if r.status_code in (402, 429):
                        mark_quota_exhausted(self, key, cooldown_seconds=60)
                        last_err = classify_http_error(r.status_code, await r.aread() and "")
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
        raise last_err or ProviderError("mistral: no usable key (stream)")

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:
        client = get_client()
        url = f"{self.base_url}/embeddings"
        last_err: Exception | None = None
        for key in key_cycle(self):
            try:
                r = await client.post(
                    url,
                    json={"model": model, "input": inputs},
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
        raise last_err or ProviderError("mistral: embed failed")

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
