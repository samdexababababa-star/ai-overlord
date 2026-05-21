# AI Overlord — Phase 3 roadmap

This document is the **handoff plan** for the work that follows PR #3 (one-click launcher + Windows 11 + env-key auto-import, merged into `main` as commit `917d25b`).

If you (a human or another AI) pick this up mid-flight, every section is self-contained: it states what's already in the repo, exactly what's left, the files to touch, and the acceptance criteria. Phases are ordered so that each one builds on the previous and produces a visible deliverable.

Branch: `devin/<timestamp>-phase-3` (one branch, one cumulative PR at the end — or one PR per phase if you prefer; both are fine).

---

## Phase 3.1 — Pixel-art virtual office

**Status before:** the office exists as SVG rectangles + framer-motion in `frontend/src/components/AgentOffice.tsx`. There is no pixel-art, no sprite, no per-agent animation state.

**Goal:** replace the SVG floor with a 2D pixel-art scene where each of the 7 agents (Aiden the Planner, Mira the Researcher, Kade the Coder, Iris the Vision, Vex the Critic, Orin the Executor, Nyra the Conductor) is rendered as an animated sprite that reacts in real time to `MessageBus` events.

**Files to add / change:**
- `frontend/public/sprites/` — PNG sprite sheets, one per agent (16×16 or 32×32 base, e.g. 4 frames × 4 states = `agent_<id>.png`).
- `frontend/public/tiles/` — floor + wall tiles for the 7 rooms.
- `frontend/src/components/PixelOffice.tsx` — new component using `<canvas>` with `imageSmoothingEnabled = false`, redrawn on a 60 fps RAF loop. Reads `useStore(s => s.events)` to pick the current state per agent.
- `frontend/src/components/AgentOffice.tsx` — delete or keep as legacy; route the office view in `App.tsx` to `PixelOffice`.
- `frontend/src/lib/sprite.ts` — small loader/animator (cache the `HTMLImageElement`, current frame, frame index, FPS).
- `frontend/tailwind.config.js` — no change needed; the canvas handles all rendering.

**Sprites:** check in either (a) a permissive asset pack (Kenney.nl 1-bit Pack, CC0) re-skinned by hand, or (b) programmatically generate placeholders via a small Python script in `scripts/gen_sprites.py` that writes PNGs (so the repo never breaks if assets are missing). Option (b) is more reproducible.

**Animation states per agent:** `idle` (slow bob), `thinking` (`…` bubble above head), `talking` (mouth frame swap + faint waveform), `working` (tool icon flashing). Map from events:
- `bus.event.kind === 'agent.start'` → switch that actor to `thinking`.
- `bus.event.kind === 'agent.message'` → switch to `talking` for 1.5 s.
- `bus.event.kind === 'tool.start'` → switch to `working`.
- `bus.event.kind === 'agent.finish'` → return to `idle`.

**Acceptance:**
- Office view renders a pixel-art room layout (no rounded SVG rects anywhere).
- When the user sends a council request, you can visually see at least 3 different agents transition `idle → thinking → talking → idle` over the next 10 seconds.
- No regression in `npm run build`; bundle stays under 600 KB JS.
- New test: a Vitest unit test for `lib/sprite.ts` that asserts state transitions update the current frame index correctly.

---

## Phase 3.2 — Deep reasoning visible in the chat (ToT / Reflexion / Debate)

**Status before:** the `DeliberateReasoner` is wired into the Council and used in `/chat/run` when `complexity > fast_mode_threshold`. The `ReasoningPanel` lets you trigger strategies in isolation, but the regular ChatPanel only exposes `ask` vs `council` — there's no way to force ToT, no live visualisation of the search tree, no trace of intermediate thoughts.

**Goal:** make the reasoning *visible* during a normal chat exchange, so the user can see the agent actually deliberating.

**Backend changes:**
- `backend/app/agents/council.py` — add a `mode` parameter to `run_objective(objective, mode='auto'|'ask'|'council'|'tot'|'reflexion'|'debate'|'constitutional')`. The default `auto` keeps current behaviour; the others force a specific strategy.
- `backend/app/reasoning/*.py` — every strategy already returns intermediate steps; expose them by publishing `reasoning.step` events on the global `MessageBus` (kind: `reasoning.tot.expand`, `reasoning.reflexion.iterate`, `reasoning.debate.round`, etc.) with payloads `{strategy, node_id, parent_id, content, score}`.
- `backend/app/routes/chat.py` — accept the new `mode` field in `/chat/ask` and `/chat/run`. When `mode != 'ask'`, delegate to the reasoner.

**Frontend changes:**
- `frontend/src/components/ChatPanel.tsx` — replace the two-pill toggle with a dropdown: `Ask · Council · Tree of Thoughts · Reflexion · Debate · Constitutional`. Persist the choice in the store.
- `frontend/src/components/ReasoningTrace.tsx` — new component, sits in the chat right rail. Subscribes to `useStore(s => s.events)` filtered by `kind.startsWith('reasoning.')`. Renders:
  - For ToT: a live tree (use `react-flow` if you add a dep, or a hand-rolled SVG; nodes coloured by score).
  - For Reflexion: a vertical timeline of iterations with the verbal feedback shown.
  - For Debate: a left/right split of debater arguments per round + final judge verdict.
- `frontend/src/components/SettingsPanel.tsx` — already has Reasoning toggles; add a "Show reasoning trace" toggle in `ui` section.

**Acceptance:**
- Sending `"Plan a 3-day Lisbon trip on $200"` in `Tree of Thoughts` mode renders an interactive tree with at least 3 levels, scores visible on each node, and the final selected path highlighted.
- Switching to `Reflexion` mode shows 2+ iterations with explicit critique text per iteration.
- Switching to `Debate` mode shows ≥ 2 debaters and a final judge verdict.
- Backend tests: at least one test per strategy verifies that `reasoning.*` events are published on the bus.

---

## Phase 3.3 — Knowledge-graph visualization + automatic ingestion of search results

**Status before:** the KG backend is solid (`memory/knowledge_graph.py`, `/knowledge/*` routes). Entity extraction triggers on conversations. There is **no UI visualisation** of the graph and search results from `tools/web_search.py` are **not** ingested into the KG.

**Goal:** (a) when an agent runs a web search, automatically extract entities from the results and add them to the KG; (b) render the resulting graph in the Memory panel with interactive zoom/click.

**Backend changes:**
- `backend/app/tools/web_search.py` — after the search returns, call `knowledge_graph.ingest_search_results(query, hits)`. Implement that method in `memory/knowledge_graph.py` to:
  - LLM-extract entities & relationships from `title + snippet` per hit.
  - Deduplicate against existing nodes via embedding similarity (use the existing semantic store).
  - Add a "source" edge linking each new entity to a `WebHit` node (with URL + retrieved_at).
- `backend/app/routes/knowledge.py` — add `GET /knowledge/graph/full?limit=200` returning `{nodes: [...], edges: [...]}` in a frontend-friendly shape.
- `backend/app/memory/knowledge_graph.py` — add `as_graph_view(limit, anchor=None)` that returns the top-N most connected nodes plus their neighbours.

**Frontend changes:**
- Add dep `reactflow` (or hand-roll SVG if you want to stay zero-dep).
- `frontend/src/components/KnowledgeGraphView.tsx` — new component that fetches `/knowledge/graph/full` and renders a force-directed layout. Nodes coloured by type (Person · Org · Concept · WebHit · Skill). Click a node → side panel with description + outgoing edges + button "Use as goal context".
- `frontend/src/components/MemoryPanel.tsx` — add a new tab "Graph" alongside the existing Episodic / Semantic ones.

**Acceptance:**
- Running an autonomy goal that triggers a web search results in ≥ 5 new nodes visible in the graph view within 30 s.
- Click on a node opens a side panel with its description and at least one related neighbour.
- Re-searching the same query does **not** create duplicate nodes (dedup test on `ingest_search_results`).

---

## Phase 3.4 — Chrome companion extension

**Status before:** no extension at all.

**Goal:** a small Manifest V3 extension that adds a button "Push to Overlord" (and a context-menu entry) on every page. Clicking sends `{url, title, selection, screenshot_data_url}` to `POST http://127.0.0.1:8765/web/capture`, where the backend ingests it into the KG.

**Files to add:**
- `extension/manifest.json` (MV3, permissions: `activeTab`, `contextMenus`, `scripting`, `storage`, `<all_urls>`).
- `extension/background.js` — service worker; sets up the context-menu, handles the POST.
- `extension/content.js` — content script that grabs the selection.
- `extension/popup.html` + `extension/popup.js` — small popup with one button + recent-captures list.
- `extension/icons/` — 16/32/48/128 PNG.
- `backend/app/routes/web_capture.py` — new route `POST /web/capture` that takes `{url, title, selection, screenshot}` and calls `knowledge_graph.ingest_web_capture(...)`.
- `backend/app/main.py` — register the new router. CORS already allows `localhost` origins; add `chrome-extension://*` to the allowlist if needed.

**Acceptance:**
- Loading the unpacked extension into Chrome, clicking the button on `https://en.wikipedia.org/wiki/Lisbon`, waiting ~5 s, and opening the Overlord Memory → Graph tab shows a new `WebHit` node for that URL with at least one extracted entity attached.
- Capture works even without an internet round-trip beyond the extension's own request to `127.0.0.1:8765`.

---

## Phase 3.5 — Auto-improvement sandbox: wired + UI

**Status before:** `backend/app/autonomy/self_improve.py` exists (179 lines, has git-branch + tests + rollback logic). It's not exposed via any route, not wired into autonomy, and `autoimprove_enabled` defaults to `False`.

**Goal:** expose it safely behind explicit user opt-in.

**Backend changes:**
- `backend/app/routes/self_improve.py` — new router:
  - `POST /self-improve/propose` — body `{goal: str}` → runs the planner to generate a unified diff, runs the test suite in a sandbox branch, returns `{branch, diff, test_output, ok}` without merging.
  - `POST /self-improve/accept` — body `{branch}` → merges into the current working branch (still local; the user pushes if they want).
  - `POST /self-improve/reject` — body `{branch}` → deletes the branch.
  - `GET /self-improve/history` — list past attempts with their test outcomes.
- `backend/app/main.py` — register the router only if `settings.autoimprove_enabled` is true (env-driven).
- HITL: any `accept` must go through `hitl.requires_approval(...)` so the user sees an approval card.

**Frontend changes:**
- `frontend/src/components/SelfImprovePanel.tsx` — new view (add a sidebar entry `Self-improve`, gated by a settings toggle `Show self-improve panel`). Form: "What should I improve?" → shows the proposed diff in a Monaco-style viewer, test output below, two buttons `Accept` / `Reject`.
- `frontend/src/components/SettingsPanel.tsx` — add a toggle `Enable auto-improvement (advanced)` under a new `Experimental` section. Stays off by default with a red warning text.

**Acceptance:**
- With the feature off, the new route returns 403 and the UI tab is hidden.
- With it on, asking it to "rename function get_keys to fetch_keys in keystore.py" produces a diff that touches exactly the right files and the test suite still passes in the sandbox before being merged.
- Rejecting a proposal cleans up the sandbox branch (verified via `git branch --list overlord/auto-*`).

---

## Cross-cutting tasks (do these at the very end)

1. Update `README.md` to mention each new phase.
2. Update `docs/phase-3-roadmap.md` (this file) with status checkboxes as you complete each phase.
3. Re-run `python -m pytest backend/tests -q`, `ruff check backend/app backend/tests`, `npm run build`.
4. Open a single PR (or one per phase if you prefer) targeting `main`; verify CI is green.

---

## Important constraints (do not violate)

- **Optional guard-rails stay optional.** HITL toggles in Settings must remain user-disableable; the only new HITL gate that *must* default to ON is for `self-improve/accept` and for any new financial/account-creation action, but the user must still be able to disable it.
- **No telemetry, no external calls without consent.** The Chrome extension only talks to `127.0.0.1`.
- **Backend deps must stay slim.** Don't pull in heavyweight graph libs server-side; the heavy lifting lives in the renderer.
- **Don't regress the launcher.** `python launch.py --check` must still pass on Linux/macOS/Windows.

---

## How to resume if context runs out

If you are picking this up from scratch:
1. Read `docs/phase-3-roadmap.md` (this file).
2. Look at `git log --oneline main..HEAD` on `devin/<timestamp>-phase-3` to see what's already pushed.
3. Run `python launch.py --check` to confirm the dev env is healthy.
4. Re-run `python -m pytest backend/tests -q` to confirm the baseline is green.
5. Continue from the first phase that isn't fully ticked off in the "Acceptance" boxes.
