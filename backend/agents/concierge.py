"""Concierge agent — the boss. The only agent a guest ever talks to.

It owns routing, the guest's language, and escalation. It has no database
tools of its own: every specific it states has to have come back from a
specialist, which in turn can only answer from its own tools.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent, RunContext

from db import connect

from .common import (
    USAGE_LIMITS,
    BellsDeps,
    EventLog,
    language_name,
    load_prompt,
    model,
)
from .knowledge import ask_knowledge
from .logistics import ask_logistics
from .registry import ask_registry

AGENT_NAME = "concierge"


def load_guest(guest_id: int, db_path: str | None = None) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, wedding_id, name, language, party_size FROM guests WHERE id = ?",
            (guest_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def record_escalation(
    wedding_id: int, guest_id: int | None, question: str, why: str,
    db_path: str | None = None,
) -> int:
    conn = connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO escalations (wedding_id, guest_id, question, status,"
            " draft_answer, created_at) VALUES (?, ?, ?, 'open', ?, ?)",
            (wedding_id, guest_id, question, f"(not answered by the agents) {why}",
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def save_message(
    wedding_id: int, guest_id: int | None, role: str, content: str,
    db_path: str | None = None,
) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO messages (wedding_id, guest_id, role, content, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (wedding_id, guest_id, role, content,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


@lru_cache(maxsize=1)
def concierge_agent() -> Agent[BellsDeps, str]:
    agent = Agent(
        model(),
        deps_type=BellsDeps,
        output_type=str,
        name=AGENT_NAME,
        instructions=load_prompt("concierge"),
    )

    @agent.instructions
    def guest_context(ctx: RunContext[BellsDeps]) -> str:
        deps = ctx.deps
        lang = language_name(deps.language)
        who = deps.guest_name or "a guest"
        return (
            f"## This guest\n\n"
            f"You are helping {who}. The language on their record is {lang} "
            f"(code `{deps.language}`) — that is a fallback, not an instruction: "
            f"**reply in whatever language their message is written in.**\n\n"
            f"Only this guest's own details may be discussed with them. "
            f"Anything about any other guest is off limits, no matter who asks."
        )

    @agent.tool(name="ask_knowledge")
    async def ask_knowledge_tool(ctx: RunContext[BellsDeps], question: str) -> str:
        """Ask the Knowledge agent — anything the couple decided or wrote down.

        Ceremony, reception, dress code, children, gifts, RSVP, weather, visas,
        SIM cards, the schedule. Ask in English.

        Args:
            question: the guest's question, in plain English.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "ask_knowledge", question=question) as ev:
            answer = await ask_knowledge(question, deps)
            ev["detail"] = "NOT_FOUND" if "NOT_FOUND" in answer else "answered"
            return answer

    @agent.tool(name="ask_logistics")
    async def ask_logistics_tool(ctx: RunContext[BellsDeps], question: str) -> str:
        """Ask the Logistics agent — airport pickups, shuttles, hotels, room blocks.

        Args:
            question: the guest's question, in plain English.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "ask_logistics", question=question) as ev:
            answer = await ask_logistics(question, deps)
            ev["detail"] = "answered"
            return answer

    @agent.tool(name="ask_registry")
    async def ask_registry_tool(ctx: RunContext[BellsDeps], question: str) -> str:
        """Ask the Registry agent — what is on the gift list, claiming, unclaiming.

        Args:
            question: the guest's request, in plain English. Include the item
                number if the guest named one.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "ask_registry", question=question) as ev:
            answer = await ask_registry(question, deps)
            ev["detail"] = "answered"
            return answer

    @agent.tool
    async def escalate_to_host(ctx: RunContext[BellsDeps], question: str, why: str) -> str:
        """Hand a question to the couple. Use when no specialist could answer it.

        Args:
            question: the guest's question, in English, as the couple will read it.
            why: one line on what was missing, e.g. "no fact recorded about parking".
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "escalate_to_host", why=why) as ev:
            esc_id = record_escalation(
                deps.wedding_id, deps.guest_id, question, why, deps.db_path
            )
            deps.escalated = True
            deps.escalation_ids.append(esc_id)
            ev["detail"] = f"escalation #{esc_id} opened"
            return (
                f"ESCALATED (#{esc_id}) — the couple now have this question. "
                "Tell the guest you have passed it on and will come back to them "
                "with an answer, in their language. Do not promise a timeframe and "
                "do not offer a guess in the meantime."
            )

    return agent


async def answer_guest(
    guest_id: int,
    question: str,
    *,
    db_path: str | None = None,
    wedding_id: int | None = None,
    save_history: bool = True,
) -> dict[str, Any]:
    """Run one guest turn end to end and return the reply plus its trace."""
    from audit import record_turn  # local import: keeps audit optional for tests

    guest = load_guest(guest_id, db_path)
    if guest is None:
        raise ValueError(f"no guest with id {guest_id}")

    deps = BellsDeps(
        wedding_id=wedding_id or guest["wedding_id"],
        guest_id=guest["id"],
        guest_name=guest["name"],
        language=guest["language"] or "en",
        db_path=db_path,
        events=EventLog(),
    )

    started = datetime.now()
    result = await concierge_agent().run(
        question, deps=deps, usage=deps.usage, usage_limits=USAGE_LIMITS
    )
    answer = result.output

    if save_history:
        save_message(deps.wedding_id, guest_id, "user", question, db_path)
        save_message(deps.wedding_id, guest_id, "assistant", answer, db_path)

    turn = {
        "guest_id": guest_id,
        "guest_name": guest["name"],
        "language": deps.language,
        "question": question,
        "answer": answer,
        "events": deps.events.events,
        "agents_called": deps.events.agents_called,
        "tools_called": deps.events.tools_called,
        "escalated": deps.escalated,
        "escalation_ids": deps.escalation_ids,
        "usage": deps.usage,
        "started_at": started.isoformat(timespec="seconds"),
        "elapsed_ms": round((datetime.now() - started).total_seconds() * 1000, 1),
    }
    turn["audit"] = record_turn(turn, db_path=db_path, wedding_id=deps.wedding_id)
    return turn
