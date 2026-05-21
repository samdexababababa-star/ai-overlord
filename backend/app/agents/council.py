"""The Council orchestrator — enhanced with advanced reasoning.

Implements three modes:

1. **Fast path** — single Conductor call. Used for short factual questions.
2. **Council mode** — Planner → (Researcher/Coder/Vision/Executor in parallel)
   → Critic loop → Conductor. Used for ``/run`` objectives.
3. **Deep reasoning** — Delegates to the deliberate reasoning engine for
   complex tasks (ToT, Reflexion, Debate, Constitutional).

All inter-agent traffic is published on the global :class:`MessageBus` so the
UI can animate it. Tool calls are dispatched through the central
:class:`ToolRegistry`.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from ..log import get_logger
from ..memory import EpisodicMemory
from ..memory.knowledge_graph import KnowledgeGraph, extract_entities_and_relations
from ..providers import ChatMessage, get_registry
from ..providers.router import ModelRouter, TaskProfile
from ..reasoning.deliberate import DeliberateReasoner
from ..tools import get_tools
from ..user_settings import get_settings_manager
from .bus import Event, MessageBus, get_bus
from .roles import (
    CODER,
    CONDUCTOR,
    CRITIC,
    ORACLE,
    PLANNER,
    RESEARCHER,
    AgentRole,
)

log = get_logger(__name__)


class Council:
    def __init__(self, episodic: EpisodicMemory | None = None, bus: MessageBus | None = None):
        self.episodic = episodic or EpisodicMemory()
        self.bus = bus or get_bus()
        self.tools = get_tools()
        self.router = ModelRouter(get_registry())
        self.reasoner = DeliberateReasoner(self.router)
        self.kg = KnowledgeGraph()

    # ------------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------------

    async def ask(self, user_message: str, session: str = "default") -> str:
        """Fast path — single Conductor call with available context."""
        await self._emit("user.message", "user", user_message, {"session": session})
        self.episodic.record(kind="user_msg", actor="user", content=user_message, session=session)
        history = self._history_for(session)

        # Check for relevant knowledge graph context
        kg_context = self._kg_context(user_message)

        sys_content = (
            "You are AI Overlord — a helpful, terse desktop assistant. You may call tools when "
            "useful. Reply in the user's language."
        )
        if kg_context:
            sys_content += f"\n\nRelevant knowledge:\n{kg_context}"

        sys = ChatMessage(role="system", content=sys_content)
        resp = await self.router.chat(
            [sys, *history, ChatMessage(role="user", content=user_message)],
            profile=TaskProfile(capability="chat"),
            tools=self.tools.specs(),
            tool_choice="auto",
        )

        # Handle tool calls (up to 3 rounds)
        for _ in range(3):
            if not resp.tool_calls:
                break
            tool_results = await self._run_tool_calls(resp.tool_calls, actor="conductor")
            follow_msgs = [
                sys,
                *history,
                ChatMessage(role="user", content=user_message),
                ChatMessage(role="assistant", content=resp.text or "(tool use)"),
            ]
            for tr in tool_results:
                follow_msgs.append(
                    ChatMessage(
                        role="tool",
                        name=tr["name"],
                        tool_call_id=tr["id"],
                        content=tr["content"][:6000],
                    )
                )
            resp = await self.router.chat(
                follow_msgs, profile=TaskProfile(capability="chat")
            )

        await self._emit("agent.message", "conductor", resp.text, {"model": resp.model})
        self.episodic.record(
            kind="assistant_msg",
            actor="conductor",
            content=resp.text,
            session=session,
            meta={"model": resp.model, "provider": resp.provider},
        )

        # Background: extract entities for knowledge graph
        asyncio.create_task(self._extract_knowledge(user_message + "\n" + resp.text))

        return resp.text

    async def run_objective(self, objective: str, session: str = "default") -> dict[str, Any]:
        """Full council with planner + parallel agents + critic loop."""
        await self._emit("council.start", "system", objective, {"session": session})
        self.episodic.record(
            kind="user_msg", actor="user", content=objective, session=session, meta={"council": True}
        )

        # Check settings for reasoning strategy
        sm = get_settings_manager()
        settings = sm.load()

        # 1. Planner decomposes
        plan = await self._call_role(PLANNER, [
            ChatMessage(role="user", content=f"Objective: {objective}\n\nProduce the plan."),
        ])
        await self._emit("agent.message", PLANNER.id, plan, {"phase": "plan"})

        # 2. Parallel execution: Researcher + Coder run simultaneously
        research_result, code_result = await asyncio.gather(
            self._call_role_safe(RESEARCHER, [
                ChatMessage(
                    role="user",
                    content=f"Objective: {objective}\n\nPlan:\n{plan}\n\n"
                    "Research relevant information for this objective.",
                ),
            ]),
            self._call_role_safe(CODER, [
                ChatMessage(
                    role="user",
                    content=f"Objective: {objective}\n\nPlan:\n{plan}\n\n"
                    "If code is needed, produce it. Otherwise say N/A.",
                ),
            ]),
        )
        if research_result:
            await self._emit("agent.message", RESEARCHER.id, research_result, {"phase": "research"})
        if code_result:
            await self._emit("agent.message", CODER.id, code_result, {"phase": "code"})

        # 3. Critic evaluates everything
        critique_input = (
            f"Objective: {objective}\n\n"
            f"Plan:\n{plan}\n\n"
        )
        if research_result:
            critique_input += f"Research findings:\n{research_result[:2000]}\n\n"
        if code_result and code_result.strip() != "N/A":
            critique_input += f"Code produced:\n{code_result[:2000]}\n\n"
        critique_input += "Critique the plan and outputs as instructed."

        critique = await self._call_role(CRITIC, [
            ChatMessage(role="user", content=critique_input),
        ])
        await self._emit("agent.message", CRITIC.id, critique, {"phase": "critique"})

        verdict = "APPROVE"
        if "REVISE" in critique.upper():
            verdict = "REVISE"
        elif "BLOCK" in critique.upper():
            verdict = "BLOCK"

        # 4. Revise if critic asked
        if verdict == "REVISE":
            plan = await self._call_role(
                PLANNER,
                [ChatMessage(
                    role="user",
                    content=(
                        f"Objective: {objective}\n\nYour earlier plan:\n{plan}\n\n"
                        f"Critic feedback:\n{critique}\n\nProduce a revised plan."
                    ),
                )],
            )
            await self._emit("agent.message", PLANNER.id, plan, {"phase": "plan_revised"})

        # 5. Use deep reasoning if enabled and complexity warrants it
        deep_analysis = ""
        if settings.council.enable_tree_of_thoughts or settings.council.enable_reflexion:
            complexity = self.reasoner.analyze_complexity(objective)
            if complexity.estimated_difficulty > settings.council.fast_mode_threshold:
                await self._emit(
                    "agent.thinking", "system",
                    f"Engaging {complexity.recommended_strategy.value} reasoning...",
                    {"difficulty": complexity.estimated_difficulty},
                )
                try:
                    reasoning_result = await self.reasoner.solve(objective)
                    deep_analysis = reasoning_result.answer
                    await self._emit(
                        "agent.message", "reasoner", deep_analysis[:1000],
                        {
                            "strategy": reasoning_result.strategy_used.value,
                            "phase": "deep_reasoning",
                        },
                    )
                except Exception as e:
                    log.warning("council.reasoning_fail", error=str(e)[:200])

        # 5.5 Optional Oracle phase — consult registered Web-AI sites for an
        # external second opinion. Off by default; failures are non-fatal.
        oracle_voices: list[dict[str, str]] = []
        if settings.council.consult_external_oracle:
            try:
                oracle_voices = await self._consult_oracle(
                    objective=objective,
                    plan=plan,
                    critique=critique,
                    deep_analysis=deep_analysis,
                    limit=max(0, settings.council.external_oracle_max),
                )
            except Exception as e:  # noqa: BLE001
                log.warning("council.oracle_fail", error=str(e)[:200])

        # 6. Conductor produces the final synthesis
        synthesis_input = (
            f"Objective: {objective}\n\n"
            f"Final plan:\n{plan}\n\n"
            f"Critic verdict: {verdict}\n\n"
        )
        if research_result:
            synthesis_input += f"Research:\n{research_result[:1500]}\n\n"
        if code_result and code_result.strip() != "N/A":
            synthesis_input += f"Code:\n{code_result[:1500]}\n\n"
        if deep_analysis:
            synthesis_input += f"Deep analysis:\n{deep_analysis[:1500]}\n\n"
        if oracle_voices:
            synthesis_input += "External oracle voices:\n"
            for v in oracle_voices:
                synthesis_input += f"- {v['site']}: {v['answer'][:600]}\n"
            synthesis_input += "\n"
        synthesis_input += "Write the final response to the user. If BLOCK, explain why."

        final = await self._call_role(CONDUCTOR, [
            ChatMessage(role="user", content=synthesis_input),
        ])
        await self._emit("agent.message", CONDUCTOR.id, final, {"phase": "synthesis"})
        await self._emit("council.finish", "system", "ok", {"verdict": verdict})

        self.episodic.record(
            kind="assistant_msg",
            actor="conductor",
            content=final,
            session=session,
            meta={
                "verdict": verdict,
                "plan": plan,
                "critique": critique,
                "research": research_result[:500] if research_result else "",
            },
        )

        asyncio.create_task(self._extract_knowledge(
            f"{objective}\n{plan}\n{final}"
        ))

        return {
            "plan": plan,
            "research": research_result or "",
            "code": code_result or "",
            "critique": critique,
            "verdict": verdict,
            "deep_analysis": deep_analysis,
            "oracle_voices": oracle_voices,
            "final": final,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _history_for(self, session: str, n: int = 12) -> list[ChatMessage]:
        eps = self.episodic.recent(
            session=session, limit=n, kinds=["user_msg", "assistant_msg"]
        )
        return [
            ChatMessage(
                role="user" if e["kind"] == "user_msg" else "assistant",
                content=e["content"],
            )
            for e in eps[:-1]
        ]

    def _kg_context(self, query: str, limit: int = 5) -> str:
        """Retrieve relevant knowledge graph context."""
        results = self.kg.search(query, limit=limit)
        if not results:
            return ""
        lines = []
        for r in results:
            lines.append(f"- {r.get('label', '')} ({r.get('type', '')})")
        return "\n".join(lines)

    async def _call_role(self, role: AgentRole, msgs: list[ChatMessage]) -> str:
        await self._emit("agent.start", role.id, "", {"room": role.room})
        full = [ChatMessage(role="system", content=role.system_prompt), *msgs]
        resp = await self.router.chat(full, profile=role.profile)
        await self._emit(
            "agent.finish",
            role.id,
            "",
            {"model": resp.model, "provider": resp.provider, "tokens": resp.usage},
        )
        return resp.text

    async def _call_role_safe(self, role: AgentRole, msgs: list[ChatMessage]) -> str:
        """Call a role, returning empty string on failure instead of raising."""
        try:
            return await self._call_role(role, msgs)
        except Exception as e:
            log.warning("council.role_fail", role=role.id, error=str(e)[:200])
            return ""

    async def _run_tool_calls(self, calls, actor: str) -> list[dict[str, Any]]:
        results = []
        for tc in calls:
            tool = self.tools.get(tc.name)
            await self._emit(
                "agent.tool_call", actor, tc.name, {"args": tc.arguments, "id": tc.id}
            )
            if tool is None:
                results.append(
                    {"id": tc.id, "name": tc.name, "content": f"unknown tool: {tc.name}"}
                )
                continue
            try:
                tr = await tool.run(tc.arguments or {})
                out = tr.output
            except Exception as e:  # noqa: BLE001
                out = f"tool error: {e}"
            await self._emit("agent.tool_result", actor, tc.name, {"output": out[:1000]})
            results.append({"id": tc.id, "name": tc.name, "content": out})
        return results

    async def _emit(self, kind: str, actor: str, content: str, meta: dict[str, Any]) -> None:
        ev = Event(kind=kind, actor=actor, content=content, meta=meta)  # type: ignore[arg-type]
        await self.bus.publish(ev)
        with contextlib.suppress(Exception):
            self.episodic.record(
                kind="council_turn",
                actor=actor,
                content=content[:4000],
                meta={"event": kind, **meta},
            )

    async def _consult_oracle(
        self,
        objective: str,
        plan: str,
        critique: str,
        deep_analysis: str,
        limit: int,
    ) -> list[dict[str, str]]:
        """Ask up to ``limit`` Web-AI sites (flagged include_in_council) for a
        second opinion. Returns ``[{"site": id, "answer": text}, ...]``."""
        if limit <= 0:
            return []
        # Local import to avoid the council module forcing a hard dep on the
        # web_ai package (and its Playwright import chain) at top level.
        from ..web_ai.client import WebAIClient
        from ..web_ai.profiles import SiteCategory, get_profile_store

        store = get_profile_store()
        candidates = [
            p for p in store.list_all(category=SiteCategory.AI)
            if p.include_in_council and p.is_ready()
        ]
        if not candidates:
            return []
        chosen = candidates[:limit]
        prompt = (
            f"{ORACLE.system_prompt}\n\n"
            f"Objective: {objective}\n\n"
            f"Council plan:\n{plan}\n\n"
            f"Critic notes:\n{critique[:800]}\n"
        )
        if deep_analysis:
            prompt += f"\nDeep reasoning result:\n{deep_analysis[:600]}\n"
        prompt += "\nGive your second opinion as instructed."

        async def _one(profile):  # noqa: ANN001 — internal helper
            client = WebAIClient(profile=profile, store=store)
            await self._emit("agent.start", ORACLE.id, profile.label, {"site_id": profile.id})
            try:
                result = await client.ask(prompt, timeout_ms=60_000)
            except Exception as e:  # noqa: BLE001
                log.warning("council.oracle_call_fail", site=profile.id, error=str(e)[:200])
                return {"site": profile.id, "answer": "", "ok": False}
            await self._emit(
                "agent.finish",
                ORACLE.id,
                result.text[:200],
                {"site_id": profile.id, "elapsed_ms": result.elapsed_ms, "ok": result.ok},
            )
            return {
                "site": profile.id,
                "answer": result.text if result.ok else "",
                "ok": result.ok,
            }

        voices = await asyncio.gather(*(_one(p) for p in chosen), return_exceptions=False)
        return [v for v in voices if v.get("ok") and v.get("answer")]

    async def _extract_knowledge(self, text: str) -> None:
        """Background task: extract entities from conversation for the KG."""
        try:
            sm = get_settings_manager()
            if not sm.load().memory.auto_extract_entities:
                return
            entities, relations = await extract_entities_and_relations(
                text, self.router
            )
            for e in entities:
                self.kg.add_entity(
                    e.get("id", e.get("label", "")),
                    e.get("label", ""),
                    e.get("type", "concept"),
                )
            for r in relations:
                self.kg.add_relationship(
                    r.get("source", ""),
                    r.get("target", ""),
                    r.get("relation", "related_to"),
                )
        except Exception as e:
            log.debug("council.kg_extract_fail", error=str(e)[:200])
