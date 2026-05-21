"""Web-AI Mesh — auto-learning bridge to other AI web UIs and social networks.

This subsystem lets the Council use third-party AI products that only expose
a browser interface (e.g. a Google AI Pro subscription, Le Chat Premium,
Claude.ai, ChatGPT Web, Perplexity, etc.) as if they were ordinary providers,
and to operate social platforms (compose / post / read feed) with the same
machinery.

The approach combines three techniques from the state of the art:

- **DOM heuristics** (Browser-Use, Skyvern) — quick discovery of candidate
  prompt boxes / send buttons / response areas by walking the page and
  scoring each candidate.
- **Set-of-Marks vision** (WebVoyager, webmarker) — numbered overlays drawn
  on top of each interactive element; a multimodal LLM (Pixtral / Llama
  Vision) picks the right number when DOM heuristics are not confident.
- **Self-healing selectors** (Skyvern, scry) — when a saved selector breaks,
  the probe is re-run automatically and the profile updated.

Each learned site is exposed back to the system as a
:class:`backend.app.providers.base.Provider` (see ``provider.py``), so it
plugs into the existing :class:`ModelRouter`, Council, and reasoning
strategies without any further glue.
"""

from __future__ import annotations

from .auto_learner import LearnPhase, LearnState, SiteAutoLearner
from .client import WebAIClient
from .probe import ProbeResult, ScoredElement, SiteProbe
from .profiles import (
    ProfileHealth,
    ProfileStore,
    Selectors,
    SiteCategory,
    SiteProfile,
    SubmitConfig,
    get_profile_store,
)
from .provider import WebAIProvider, get_web_ai_provider
from .social import SocialAdapter

__all__ = [
    "LearnPhase",
    "LearnState",
    "ProbeResult",
    "ProfileHealth",
    "ProfileStore",
    "ScoredElement",
    "Selectors",
    "SiteAutoLearner",
    "SiteCategory",
    "SiteProbe",
    "SiteProfile",
    "SocialAdapter",
    "SubmitConfig",
    "WebAIClient",
    "WebAIProvider",
    "get_profile_store",
    "get_web_ai_provider",
]
