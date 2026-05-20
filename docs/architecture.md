# Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Electron Desktop App                              │
│  ┌────────────┐   IPC    ┌──────────────────────────────────────────┐    │
│  │ React UI   │ ◄─────► │ Electron Main (spawns Python backend)    │    │
│  │ Liquid Glass│ HTTP/WS │                                          │    │
│  └────┬───────┘ ──────►  └────────────────┬─────────────────────────┘    │
│       │                                   │                              │
│       │     FastAPI :8765                 ▼                              │
│       │  ┌─────────────────────────────────────────────────────────┐     │
│       │  │  Router /chat /agents /memory /tools /onboarding        │     │
│       │  ├─────────────────────────────────────────────────────────┤     │
│       │  │  Council (Planner/Critic/Conductor/…)                   │     │
│       │  ├─────────────────────────────────────────────────────────┤     │
│       │  │  ModelRouter → ProviderRegistry                         │     │
│       │  │     ├─ MistralProvider  (mistral-* / codestral / pixtral)│    │
│       │  │     ├─ NvidiaProvider   (llama, deepseek, qwen, vision) │     │
│       │  │     ├─ GoogleProvider   (gemini-2.5-*, gemma-3, embed)  │     │
│       │  │     └─ GroqProvider     (llama-3.3-70b, llama-4-scout)  │     │
│       │  ├─────────────────────────────────────────────────────────┤     │
│       │  │  Tools: web_search, browser (CDP), shell, fs, vision    │     │
│       │  ├─────────────────────────────────────────────────────────┤     │
│       │  │  Memory: episodic (SQLite) + semantic (Chroma)          │     │
│       │  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        Your Chrome (launched with --remote-debugging-port=29229)
```

## Provider abstraction

`backend/app/providers/base.py` defines a single :class:`Provider` interface
all backends implement. Each holds **one or more API keys**; on a 429 / quota
error, the key is placed in a 60-second cooldown and the next key is tried.
This is the key-rotation mechanism the user asked for.

The :class:`ProviderRegistry` is the live, in-memory bag of providers. It is
re-built whenever you add or remove a key via the onboarding endpoints.

## Routing

`backend/app/providers/router.py` exposes a :class:`ModelRouter` that picks
the best `(provider, model)` pair for a given :class:`TaskProfile`. Scoring
considers:

- capability match (required)
- cost (`prefer_free=True` pushes free providers up)
- explicit provider preference
- specialist bonus for code / vision / embed tasks

If the chosen model errors out (network, quota, …), the router automatically
re-picks the next-best candidate and tries again — up to 5 candidates per
call.

## Council

`backend/app/agents/council.py` implements two operating modes:

1. **`ask`** — single Conductor call. Used for short questions. Supports
   tool-calling (web search / browser / shell / fs / vision).
2. **`run_objective`** — multi-agent loop: Planner produces a plan, Critic
   scores it (`APPROVE | REVISE | BLOCK`), Planner revises once if needed,
   Conductor synthesizes the final response. All inter-agent traffic is
   published on the :class:`MessageBus`.

The frontend's "Office" view subscribes to that bus over WebSocket
(`/agents/events`) and animates each agent in their dedicated room.

## Memory

- **Episodic** (`memory/episodic.py`) — SQLite-backed append-only log of every
  meaningful event (user messages, assistant replies, tool calls, council
  turns). Used for in-app history and short-term context windows.
- **Semantic** (`memory/semantic.py`) — Chroma persistent collection of
  free-form facts, embedded with whichever embedding-capable provider is
  configured (Mistral embed, NVIDIA NV-EmbedQA, Google text-embedding-004).

Future work: a periodic *consolidation* job that summarizes recent episodes
into long-form semantic notes (analogous to sleep-cycle replay).

## Tools

Each tool implements `name`, `description`, JSON-schema `parameters`, and
`async run(args)`. The registry returns specs in the OpenAI-compatible
function-calling shape so all four providers can use them natively.

Sensitive tools (`shell`, `fs`) mark `requires_confirmation = True`. The UI is
the gate — confirmation flows live in the frontend.

## Liquid-glass UI

`frontend/src/styles/globals.css` defines three glass tokens (`.glass`,
`.glass-strong`, `.glass-inset`) with `backdrop-filter: blur(...) saturate(...)`
and a layered radial-gradient backdrop on the body. Animations use Framer
Motion for spring transitions, layout pulse cues, and the agent avatars'
gentle "thinking" bob in the Office view.

## Auto-improvement (roadmap)

The plan is to spawn a sandboxed git branch (prefix configurable in
`config.py`), let the Coder agent modify code on that branch, run the test
suite, and merge to main only if green. Stubbed for now — the configuration
hook is `OVERLORD_AUTOIMPROVE_ENABLED` and `OVERLORD_AUTOIMPROVE_BRANCH_PREFIX`.

## Browser companion (roadmap)

A Chrome extension paired with the desktop app, talking to the same backend,
will let agents read DOM, click, and harvest content from the *active* tab
rather than spawning a controlled Chrome over CDP. Slot reserved in the
roadmap.
