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

## Quick start — one-click launcher

> **TL;DR.** Double-click the launcher for your OS. Everything else (venv, dependencies, renderer build, app launch) happens automatically.

| OS | Double-click | What it does |
|---|---|---|
| **Windows 11** | `Start AI Overlord.bat` | Finds Python, runs `launch.py`, installs everything, opens the app. |
| **macOS** | `Start AI Overlord.command` | Same, via `python3 launch.py`. |
| **Linux** | `./start-ai-overlord.sh` | Same. |

The only prerequisites are **Python 3.11+** and **Node.js 18+**. If either is missing the launcher prints a one-line install command (`winget install Python.Python.3.12`, `brew install node python@3.12`, or `apt install nodejs npm python3-venv`).

First launch takes ~1 minute (venv + `npm install` + renderer build). Subsequent launches start in a few seconds.

### On launch

The **Onboarding Wizard** opens and:
- **Auto-detects** any API keys already set in your environment (`MISTRAL_API_KEY`, `GROQ_API_KEY`, `GOOGLE_AI_API_KEY`, …) or a `.env` file at the repo root, and offers to import them with one click.
- **Walks you through** obtaining each provider's free key with deep-links to their console and step-by-step instructions.
- **Validates** each key live against the provider's API before storing it (encrypted) in your OS keychain.
- Offers a **Demo mode** — try the app without any key (mock provider).

### Auto-start at login

In `Settings → System & Startup`, toggle **Open at login** to make AI Overlord launch automatically:
- **Windows 11** writes a `.bat` into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`.
- **macOS** writes `~/Library/LaunchAgents/ai.overlord.startup.plist`.
- **Linux** writes `~/.config/autostart/ai-overlord.desktop`.

Combine with **Start minimized** to launch silently to the system tray.

### Manual install (advanced)

If you prefer to do it yourself:

```bash
git clone https://github.com/samdexababababa-star/ai-overlord
cd ai-overlord
./scripts/setup.sh           # Linux/macOS
# or
.\scripts\setup.ps1          # Windows PowerShell
./scripts/dev.sh             # dev mode with Vite hot reload
```

### Build a desktop installer

```bash
cd frontend
npm run build           # builds the renderer
npm run dist            # produces a .AppImage / .exe / .dmg in frontend/release/
```

### Launcher flags

```
python launch.py --check        # report prereqs and exit
python launch.py --no-electron  # backend only
python launch.py --rebuild      # force renderer rebuild
python launch.py --reset        # wipe .venv + node_modules and re-install
python launch.py --port 8766    # use a custom backend port
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
