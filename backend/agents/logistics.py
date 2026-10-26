"""Logistics agent — shuttles and hotels, every time string from the solver.

The model never computes a schedule. solver.py does that in deterministic
Python; this agent only reads the result back out and puts it into a sentence.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_ai import Agent, RunContext

from db import connect
from solver import explain_run, guest_pickup, solve_shuttles

from .common import USAGE_LIMITS, BellsDeps, load_prompt, model

AGENT_NAME = "logistics"


def hotels_rows(wedding_id: int, db_path: str | None = None) -> list[dict]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name, address, block_code, nightly_rate, book_by_date, url,"
            " distance_km FROM hotels WHERE wedding_id = ? ORDER BY nightly_rate DESC",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def runs_rows(wedding_id: int, db_path: str | None = None) -> list[dict]:
    """Shuttle runs with seat counts — never with passenger names."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, direction, depart_at, from_loc, to_loc, capacity, seats_taken"
            " FROM shuttle_runs WHERE wedding_id = ? ORDER BY depart_at",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _unscheduled_count(wedding_id: int, db_path: str | None = None) -> int:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM guests WHERE wedding_id = ? AND arrival_at IS NOT NULL"
            " AND arrival_at != '' AND shuttle_run_id IS NULL"
            "   AND rsvp_status != 'declined'",
            (wedding_id,),
        ).fetchone()[0]
    finally:
        conn.close()


@lru_cache(maxsize=1)
def logistics_agent() -> Agent[BellsDeps, str]:
    agent = Agent(
        model(),
        deps_type=BellsDeps,
        output_type=str,
        name=AGENT_NAME,
        instructions=load_prompt("logistics"),
    )

    @agent.tool
    async def get_pickup(ctx: RunContext[BellsDeps], guest_id: int | None = None) -> str:
        """The current guest's own airport pickup.

        Args:
            guest_id: optional; it must be the guest you are helping. Looking up
                anyone else is refused.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "get_pickup", guest_id=guest_id) as ev:
            if deps.guest_id is None:
                ev["detail"] = "no guest in session"
                return "REFUSED — there is no guest in this session to look up."
            if guest_id is not None and int(guest_id) != int(deps.guest_id):
                # Not an error the model should retry — a boundary it cannot cross.
                ev["status"] = "refused"
                ev["detail"] = f"asked for guest {guest_id}, session is {deps.guest_id}"
                return (
                    "REFUSED — you may only look up the pickup of the guest you are "
                    "helping. Tell the guest you cannot share another guest's travel "
                    "details and offer to pass a message to the couple."
                )
            info = guest_pickup(deps.guest_id, db_path=deps.db_path)
            ev["detail"] = (
                f"run {info['run']['id']} at {info['run']['depart_at']}"
                if info.get("run") else "no shuttle booked"
            )
            return info["text"]

    @agent.tool
    async def list_runs(ctx: RunContext[BellsDeps]) -> str:
        """Every shuttle run with seats taken and seats free. No passenger names."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "list_runs") as ev:
            runs = runs_rows(deps.wedding_id, deps.db_path)
            ev["detail"] = f"{len(runs)} run(s)"
            if not runs:
                return "NO_RUNS — no shuttle runs are scheduled."
            return "\n".join(
                f"run {r['id']} · {r['direction']} · departs {r['depart_at']} · "
                f"{r['from_loc']} → {r['to_loc']} · "
                f"{r['seats_taken']}/{r['capacity']} seats taken"
                for r in runs
            )

    @agent.tool
    async def get_hotels(ctx: RunContext[BellsDeps]) -> str:
        """The room blocks: rate, block code, booking deadline, distance."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "get_hotels") as ev:
            hotels = hotels_rows(deps.wedding_id, deps.db_path)
            ev["detail"] = f"{len(hotels)} hotel(s)"
            if not hotels:
                return "NO_HOTELS — no room blocks are recorded."
            lines = []
            for h in hotels:
                rate = f"{h['nightly_rate']:.0f} per night" if h["nightly_rate"] else "rate not listed"
                deadline = h["book_by_date"] or "no deadline listed"
                lines.append(
                    f"{h['name']} · {h['address']} · {rate} · block code "
                    f"{h['block_code'] or 'none'} · book by {deadline} · "
                    f"{h['distance_km']} km from the venue · {h['url'] or ''}".strip()
                )
            return "\n".join(lines)

    @agent.tool(name="solve_shuttles")
    async def solve_shuttles_tool(ctx: RunContext[BellsDeps]) -> str:
        """Recompute the shuttle schedule. Only does work if someone is unscheduled."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "solve_shuttles") as ev:
            pending = _unscheduled_count(deps.wedding_id, deps.db_path)
            if pending == 0:
                ev["detail"] = "already scheduled; returned existing runs"
                runs = runs_rows(deps.wedding_id, deps.db_path)
                return "Schedule is already up to date.\n" + "\n".join(
                    f"run {r['id']} · {r['direction']} · departs {r['depart_at']} · "
                    f"{r['seats_taken']}/{r['capacity']} seats taken"
                    for r in runs
                )
            result = solve_shuttles(deps.wedding_id, db_path=deps.db_path)
            ev["detail"] = (
                f"{pending} unscheduled → {len(result['runs'])} run(s) in "
                f"{result['solved_in_ms']} ms"
            )
            return "\n".join(
                explain_run(r["id"], db_path=deps.db_path) for r in result["runs"]
            )

    return agent


async def ask_logistics(question: str, deps: BellsDeps) -> str:
    result = await logistics_agent().run(
        question, deps=deps, usage=deps.usage, usage_limits=USAGE_LIMITS
    )
    return result.output
