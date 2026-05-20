"""LLM provider abstraction layer.

Each provider supplies one or more models. The :class:`ProviderRegistry` holds
all configured keys and supports per-provider failover. The :mod:`router`
module picks a provider+model for a task profile.
"""

from .base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    Provider,
    ProviderError,
    QuotaExhaustedError,
)
from .registry import ProviderRegistry, get_registry
from .router import ModelRouter, TaskProfile

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "EmbeddingResponse",
    "ModelRouter",
    "Provider",
    "ProviderError",
    "ProviderRegistry",
    "QuotaExhaustedError",
    "TaskProfile",
    "get_registry",
]
