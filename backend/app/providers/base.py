"""Common protocol & data models for LLM providers."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..config import ProviderModel


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class AuthError(ProviderError):
    """API key invalid / unauthorized."""


class QuotaExhaustedError(ProviderError):
    """Rate limit or daily quota exhausted — caller should rotate keys."""


class TransientError(ProviderError):
    """Temporary upstream failure; retryable."""


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    # Optional image attachments (data URLs or http URLs) — only honoured by vision-capable models.
    images: list[str] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """A function-calling tool definition (OpenAI-compatible shape)."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.4
    top_p: float = 1.0
    max_tokens: int | None = None
    stream: bool = False
    tools: list[ToolSpec] = Field(default_factory=list)
    tool_choice: Literal["auto", "none", "required"] | None = None
    # Free-form extra params merged into the wire payload (e.g. response_format).
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    # Usage shape varies per provider (Mistral nests prompt_tokens_details, etc.)
    usage: dict[str, Any] = Field(default_factory=dict)


class EmbeddingResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    provider: str


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class Provider(abc.ABC):
    """Abstract provider.

    Subclasses hold a list of API keys and rotate them on quota errors. They
    must implement :py:meth:`chat` and :py:meth:`embed` (or raise
    NotImplementedError if unsupported).
    """

    name: str  # short id: "mistral", "nvidia", "google", "groq"
    base_url: str
    supports_streaming: bool = True

    def __init__(self, keys: list[str]):
        self.keys: list[str] = [k.strip() for k in keys if k and k.strip()]
        self._cursor: int = 0
        # Per-key cooldowns (epoch seconds until they're usable again)
        self._cooldown: dict[str, float] = {}

    @property
    def models(self) -> list[ProviderModel]:
        """Catalog of models exposed by this provider."""
        return []

    @abc.abstractmethod
    async def chat(self, req: ChatRequest) -> ChatResponse:  # pragma: no cover - protocol
        ...

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        """Streaming variant (yields text chunks). Default falls back to non-stream."""
        resp = await self.chat(req.model_copy(update={"stream": False}))
        yield resp.text

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:  # noqa: D401
        raise NotImplementedError(f"{self.name} does not implement embeddings")

    async def validate_key(self, key: str) -> bool:
        """Best-effort liveness/auth check for a single key."""
        return True
