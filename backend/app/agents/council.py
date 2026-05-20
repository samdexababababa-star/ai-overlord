"""The Council orchestrator.

Implements two modes:

1. **Fast path** — single Conductor call. Used for short factual questions.
2. **Council mode** — Planner → (Researcher/Coder/Vision/Executor in parallel)
   → Critic loop → Conductor. Used for ``/run`` objectives.

All inter-agent traffic is published on the global :class:`MessageBus` so the
UI can animate it. Tool calls are dispatched through the central
:class:`ToolRegistry`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ..log import get_logger
from ..memory import EpisodicMemory
from ..providers import ChatMessage, get_registry
from ..providers.router import ModelRouter, TaskProfile
from ..tools import get_tools
from .bus import Event, MessageBus, get_bus
from .roles import CONDUCTOR, CRITIC, PLANNER, AgentRole

log = get_logger(__name__)


class Council:
    def __init__(self, episodic: EpisodicMemory | None = None, bus: MessageBus | None = None):
        self.episodic = episodic or EpisodicMemory()
        self.bus = bus or get_bus()
        self.tools = get_tools()
        self.router = ModelRouter(get_registry())

    # ------------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------------

    async def ask(self, user_message: str, session: str = "default") -> str:
        """Fast path — single Conductor call with available context."""
        await self._emit("user.message", "user", user_message, {"session": session})
        self.episodic.record(kind="user_msg", actor="user", content=user_message, session=session)
        history = self._history_for(session)
        sys = ChatMessage(
            role="system",
            content=(
                "You are AI Overlord — a helpful, terse desktop assistant. You may call tools when "
                "useful. Reply in the user's language."
            ),
        )
        resp = await self.router.chat(
            [sys, *history, ChatMessage(role="user", content=user_message)],
            profile=TaskProfile(capability="chat"),
            tools=self.tools.specs(),
            tool_choice="auto",
        )
        # Single round of tool calls if requested.
        if resp.tool_calls:
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
        return resp.text

    async def run_objective(self, objective: str, session: str = "default") -> dict[str, Any]:
        """Full council with planner + critic loop."""
        await self._emit("council.start", "system", objective, {"session": session})
        self.episodic.record(
            kind="user_msg", actor="user", content=objective, session=session, meta={"council": True}
        )

        # 1. Planner
        plan = await self._call_role(PLANNER, [
            ChatMessage(role="user", content=f"Objective: {objective}\n\nProduce the plan."),
        ])
        await self._emit("agent.message", PLANNER.id, plan, {"phase": "plan"})

        # 2. Critic on the plan
        crit_in = (
            f"Objective: {objective}\n\nProposed plan:\n{plan}\n\n"
            "Critique the plan as instructed."
        )
        critique = await self._call_role(CRITIC, [ChatMessage(role="user", content=crit_in)])
        await self._emit("agent.message", CRITIC.id, critique, {"phase": "critique"})

        verdict = "APPROVE"
        if "REVISE" in critique.upper():
            verdict = "REVISE"
        elif "BLOCK" in critique.upper():
            verdict = "BLOCK"

        # 3. Revise once if critic asked
        if verdict == "REVISE":
            plan = await self._call_role(
                PLANNER,
                [
                    ChatMessage(
                        role="user",
                        content=(
                            f"Objective: {objective}\n\nYour earlier plan:\n{plan}\n\n"
                            f"Critic feedback:\n{critique}\n\nProduce a revised plan."
                        ),
                    )
                ],
            )
            await self._emit("agent.message", PLANNER.id, plan, {"phase": "plan_revised"})

        # 4. Conductor produces the final synthesis (no autonomous shell/browser yet)
        final = await self._call_role(
            CONDUCTOR,
            [
                ChatMessage(
                    role="user",
                    content=(
                        f"Objective: {objective}\n\nFinal plan:\n{plan}\n\n"
                        f"Critic verdict: {verdict}\n\n"
                        "Write the final response to the user. If BLOCK, explain why and stop."
                    ),
                )
            ],
        )
        await self._emit("agent.message", CONDUCTOR.id, final, {"phase": "synthesis"})
        await self._emit("council.finish", "system", "ok", {"verdict": verdict})

        self.episodic.record(
            kind="assistant_msg",
            actor="conductor",
            content=final,
            session=session,
            meta={"verdict": verdict, "plan": plan, "critique": critique},
        )
        return {"plan": plan, "critique": critique, "verdict": verdict, "final": final}

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
            for e in eps[:-1]  # exclude the one we just inserted
        ]

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
        # Also log to episodic for replay
        with contextlib.suppress(Exception):
            self.episodic.record(
                kind="council_turn",
                actor=actor,
                content=content[:4000],
                meta={"event": kind, **meta},
            )
