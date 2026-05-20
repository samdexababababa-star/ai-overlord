# AI Overlord

> An autonomous multi-provider AI agent **council** running on your desktop, with a liquid-glass UI, virtual office visualization, persistent memory, and a tools surface (browser, shell, filesystem, vision).

This is a **personal-use research project**. It assumes you have legitimate API keys (or free-tier keys you've personally obtained) for every provider you connect, and that you, the operator, take responsibility for what the agents do on your machine. Don't point this at production credentials, don't use it to harm anyone.

---

## What it is

AI Overlord wires together several free / freemium LLM providers into a single desktop application:

| Provider | Why |
|---|---|
| **[Mistral](https://console.mistral.ai/)** | `mistral-large-latest` (reasoning), `mistral-small-latest` (fast), `codestral-latest` (code), `pixtral-large-latest` (vision), `mistral-embed` (vectors). |
| **[NVIDIA NIM (build.nvidia.com)](https://build.nvidia.com/)** | 80+ free hosted models incl. `meta/llama-3.3-70b-instruct`, `deepseek-ai/deepseek-r1`, `qwen/qwen2.5-coder-32b-instruct`, `meta/llama-3.2-90b-vision-instruct`. |
| **[Google AI Studio](https://aistudio.google.com/apikey)** | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemma-3-27b-it`, `text-embedding-004`. Free tier with daily limits. |
| **[Groq](https://console.groq.com/keys)** | Stupidly fast Llama 3.3 70B inference (~800 t/s). |
| *(optional)* OpenRouter, Cerebras, Together — extensible. |

**Multi-key per provider**: you can paste several keys for any provider; if one is rate-limited or out of quota, the router transparently fails over to the next.

**Smart router**: every call picks the cheapest healthy model that matches the task profile (`reason`, `code`, `vision`, `embed`, `fast`).

**Council (multi-agent)**: complex objectives are decomposed by a **Planner**, executed by an **Executor** (with tools), researched by a **Researcher**, coded by a **Coder**, sanity-checked by a **Critic**, and orchestrated by a **Conductor**. You watch them in a **virtual office** with avatars in separate rooms.

**Memory**: SQLite for episodic & procedural memory, ChromaDB for semantic retrieval, with periodic consolidation (sleep-cycle inspired).

**Tools**: web search, browser control via Playwright (attaches to your Chrome over CDP), shell execution, filesystem, screen vision (Pixtral / Llama Vision).

---

## Quick start

### Prereqs

- **Node.js 20+** (recommended via `nvm`)
- **Python 3.11+** (recommended via `pyenv`)
- **Google Chrome** (any recent version) — used as the controlled browser
- A free Mistral API key from <https://console.mistral.ai/api-keys/> (minimum to start)

### Install

```bash
git clone https://github.com/samdexababababa-star/ai-overlord
cd ai-overlord
./scripts/setup.sh        # creates Python venv, installs backend + frontend deps
```

On Windows / PowerShell:

```powershell
git clone https://github.com/samdexababababa-star/ai-overlord
cd ai-overlord
.\scripts\setup.ps1
```

### Run (dev)

```bash
./scripts/dev.sh           # starts backend (FastAPI on :8765) + Electron with hot reload
```

The first launch opens the **Onboarding Wizard** which walks you through getting each provider's API key, validates each one in real time, and stores them in your OS keychain (`keytar`).

### Build a desktop installer

```bash
cd frontend
pnpm run build           # builds the renderer
pnpm run dist            # produces a .AppImage / .exe / .dmg in frontend/release/
```

---

## Repo layout

```
ai-overlord/
├── backend/                FastAPI app, providers, agents, memory, tools
│   └── app/
│       ├── providers/      mistral.py, nvidia.py, google.py, groq.py + router
│       ├── agents/         council with planner/coder/critic/...
│       ├── memory/         episodic (sqlite) + semantic (chroma)
│       ├── tools/          web_search, browser, shell, fs, vision
│       └── routes/         /chat, /onboarding, /agents, /memory, /tools
├── frontend/               Electron + React + TS + Tailwind + Framer Motion
│   └── src/
│       ├── components/     Onboarding, ChatPanel, AgentOffice, ...
│       └── store/          Zustand state
├── docs/                   architecture notes, provider research
└── scripts/                setup / dev / build helpers
```

---

## Safety & scope

- The agent operates with **your local privileges**. Run it in a user account, not as admin/root.
- Shell tool runs commands under a per-action allowlist + interactive confirmation by default.
- Auto-modifying code happens on a **separate git branch** with automated tests; failures roll back.
- You can pause the council at any time from the UI.

This project deliberately does not include any code that bulk-creates accounts, mass-spams APIs, or evades rate limits. Key rotation is across keys **you legitimately own**.

---

## Roadmap

- [x] Provider abstraction + multi-key failover (Mistral / NVIDIA / Google / Groq)
- [x] Council (Planner / Executor / Critic) + visualisation
- [x] Onboarding wizard + keytar storage
- [x] Memory (episodic + semantic) + retrieval
- [x] Tools: web search, browser (Playwright CDP), shell, filesystem
- [ ] Continuous screen vision loop (Pixtral) — partial
- [ ] Sandboxed auto-improvement (git branch + CI gate) — stub
- [ ] Chrome companion extension
- [ ] Voice in/out (Gemini Live)
- [ ] More providers: OpenRouter, Cerebras, Together

See [docs/architecture.md](docs/architecture.md) for the deep dive.
