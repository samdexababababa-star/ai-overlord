"""Demo provider — works without any API key.

Returns canned responses that demonstrate the system's capabilities. Useful
for onboarding, UI development, and testing without burning real tokens.

Supports all capabilities (chat, reason, code, vision, embed) with
plausible-looking responses.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import AsyncIterator

from ..config import ProviderModel
from ..log import get_logger
from .base import (
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    Provider,
)

log = get_logger(__name__)


DEMO_MODELS: list[ProviderModel] = [
    ProviderModel(
        id="demo-reason",
        provider="demo",
        label="Demo Reasoner",
        capabilities=["chat", "reason"],
        context_window=32_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="demo-code",
        provider="demo",
        label="Demo Coder",
        capabilities=["chat", "code"],
        context_window=32_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="demo-vision",
        provider="demo",
        label="Demo Vision",
        capabilities=["chat", "vision"],
        context_window=32_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="demo-fast",
        provider="demo",
        label="Demo Fast",
        capabilities=["chat", "fast"],
        context_window=32_000,
        cost_tier=0,
    ),
    ProviderModel(
        id="demo-embed",
        provider="demo",
        label="Demo Embeddings",
        capabilities=["embed"],
        context_window=8_192,
        cost_tier=0,
    ),
]


DEMO_RESPONSES = {
    "greeting": (
        "Hello! I'm the AI Overlord demo agent. I'm running in demo mode — "
        "no real API keys are being used. Connect a real provider "
        "(Mistral, NVIDIA, Google, Groq) for full capabilities."
    ),
    "plan": (
        "Here's a structured plan:\n"
        "1. **Analyze** the problem space and constraints\n"
        "2. **Research** relevant prior work and data\n"
        "3. **Design** the solution architecture\n"
        "4. **Implement** with tests and validation\n"
        "5. **Review** and iterate based on feedback"
    ),
    "critique": (
        "Critique of the proposed plan:\n"
        "- **Strength**: Well-structured approach with clear steps\n"
        "- **Weakness**: Missing risk assessment and fallback strategies\n"
        "- **Risk**: Timeline may be optimistic for step 3\n"
        "- Score: 7/10 (correctness: 8, safety: 7, ambition: 6)\n"
        "- Verdict: APPROVE with minor revisions recommended"
    ),
    "code": (
        '```python\ndef solve(data: list[dict]) -> dict:\n'
        '    """Process and analyze the input data."""\n'
        "    results = {}\n"
        "    for item in data:\n"
        '        key = item.get("id", "unknown")\n'
        "        results[key] = {\n"
        '            "processed": True,\n'
        '            "score": len(str(item)) * 0.1,\n'
        "        }\n"
        "    return results\n```"
    ),
    "vision": (
        "I can see a desktop environment with:\n"
        "- A browser window showing a web application\n"
        "- Several open tabs in the browser\n"
        "- A code editor in the background\n"
        "- The taskbar at the bottom of the screen\n"
        "(Demo mode — connect a real vision model for actual screen analysis)"
    ),
    "default": (
        "I'm processing your request in demo mode. In production with real "
        "API keys, the council would provide a thorough, researched response "
        "using the best available model for this type of task."
    ),
}


def _pick_response(messages: list) -> str:
    """Select a demo response based on message content."""
    if not messages:
        return DEMO_RESPONSES["default"]

    last_msg = ""
    for m in reversed(messages):
        content = m.content if hasattr(m, "content") else str(m.get("content", ""))
        if content:
            last_msg = content.lower()
            break

    if any(w in last_msg for w in ("hello", "hi", "hey", "bonjour")):
        return DEMO_RESPONSES["greeting"]
    if any(w in last_msg for w in ("plan", "decompose", "objective", "strategy")):
        return DEMO_RESPONSES["plan"]
    if any(w in last_msg for w in ("critique", "review", "evaluate", "critic")):
        return DEMO_RESPONSES["critique"]
    if any(w in last_msg for w in ("code", "implement", "function", "class", "script")):
        return DEMO_RESPONSES["code"]
    if any(w in last_msg for w in ("screen", "see", "image", "visual", "screenshot")):
        return DEMO_RESPONSES["vision"]

    return DEMO_RESPONSES["default"]


def _deterministic_embedding(text: str, dim: int = 384) -> list[float]:
    """Generate a deterministic pseudo-embedding from text hash."""
    h = hashlib.sha256(text.encode()).hexdigest()
    seed = int(h[:8], 16)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


class DemoProvider(Provider):
    """Provider that works without any API key."""

    name = "demo"
    base_url = ""
    supports_streaming = True

    def __init__(self, keys: list[str] | None = None):
        super().__init__(keys or ["demo-key"])

    @property
    def models(self) -> list[ProviderModel]:
        return DEMO_MODELS

    async def chat(self, req: ChatRequest) -> ChatResponse:
        response_text = _pick_response(req.messages)
        return ChatResponse(
            text=response_text,
            model=req.model,
            provider=self.name,
            finish_reason="stop",
            usage={
                "prompt_tokens": sum(
                    len(m.content.split()) for m in req.messages
                ),
                "completion_tokens": len(response_text.split()),
                "total_tokens": 0,
            },
        )

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[str]:
        response_text = _pick_response(req.messages)
        words = response_text.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    async def embed(self, model: str, inputs: list[str]) -> EmbeddingResponse:
        vectors = [_deterministic_embedding(text) for text in inputs]
        return EmbeddingResponse(
            vectors=vectors,
            model=model,
            provider=self.name,
        )

    async def validate_key(self, key: str) -> bool:
        return True
