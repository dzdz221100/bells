"""Host concierge — the couple's side, with write permissions.

Same pattern as the guest concierge: one agent, a handful of tools, an ordered
event trace, and the audit trail. Two things differ.

First, it may read the whole roster. The guest agent is walled off from other
guests by SQL; this one is not, because it is the couple's own data.

Second, it can change things — but never directly. Every write tool validates
its arguments, works out the before and after, and parks a proposal in
`proposals.py`. The agent then describes what is about to happen and stops. A
human presses "Do it" (or says yes, and the agent calls `commit_proposal`),
and the server runs the SQL. The model is never the thing that decides consent
was given.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent, RunContext

import gaps
import proposals
from db import connect

from .common import USAGE_LIMITS, BellsDeps, EventLog, load_prompt, model

AGENT_NAME = "host"
WEDDING_ID = 1


def _slug(text: str, words: int = 3) -> str:
    import re
    skip = {"the", "a", "an", "is", "are", "to", "for", "of", "and", "what", "when", "do"}
    out = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in skip and len(w) > 2]
    return "_".join(out[:words]) or "host_note"


def _fact(fact_id: int) -> dict | None:
    conn = connect()
    try:
        r = conn.execute(
            "SELECT id, topic, question_pattern, answer, source, is_public, updated_at"
            " FROM wedding_facts WHERE id = ? AND wedding_id = ?", (fact_id, WEDDING_ID)
        ).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def _registry_item(item_id: int) -> dict | None:
    conn = connect()
    try:
        r = conn.execute(
            "SELECT r.id, r.item, r.url, r.price, r.claimed_by_guest_id, g.name AS claimed_by"
            " FROM registry r LEFT JOIN guests g ON g.id = r.claimed_by_guest_id"
            " WHERE r.id = ? AND r.wedding_id = ?", (item_id, WEDDING_ID)
        ).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


@lru_cache(maxsize=1)
def host_agent() -> Agent[BellsDeps, str]:
    agent = Agent(
        model(),
        deps_type=BellsDeps,
        output_type=str,
        name=AGENT_NAME,
        instructions=load_prompt("host_concierge"),
    )

    # ---------------- reading ----------------

    @agent.tool
    async def wedding_status(ctx: RunContext[BellsDeps]) -> str:
        """Headline counts: RSVPs, beds, flights, shuttles, diets, open questions."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "wedding_status") as ev:
            st = gaps.wedding_status(deps.wedding_id, deps.db_path)
            ev["detail"] = f"{st['attending']}/{st['invited']} attending"
            lines = [
                f"invited {st['invited']} · attending {st['attending']} "
                f"({st['people_coming']} people) · declined {st['declined']} "
                f"· no reply {st['pending_rsvp']} (up to {st['seats_still_unknown']} more seats)",
                f"rooms: {st['beds_booked']} booked, {st['beds_unbooked']} not",
                f"flights: {st['flights_known']} known, {st['flights_missing']} missing; "
                f"{st['on_a_shuttle']} on a shuttle, {st['awaiting_a_seat']} awaiting a seat",
                f"plus ones: {st['plus_ones_named']} named, {st['plus_ones_unnamed']} unnamed",
                f"open questions from guests: {st['escalations_open']}",
                f"facts Bells knows: {st['facts_recorded']}",
                f"registry: {st['registry_available']} of {st['registry_total']} available",
            ]
            if st["dietary"]:
                lines.append("diets: " + ", ".join(
                    f"{d['need']} ×{d['people']}" for d in st["dietary"]))
            return "\n".join(lines)

    @agent.tool
    async def find_gaps(ctx: RunContext[BellsDeps]) -> str:
        """Everything still outstanding, with names. Use this for "who still...?"."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "find_gaps") as ev:
            g = gaps.find_gaps(deps.wedding_id, deps.db_path)
            ev["detail"] = ", ".join(f"{k}={len(v)}" for k, v in g.items() if v) or "nothing open"
            if not any(g.values()):
                return "NO_GAPS — everything is answered, booked and seated."
            out = []
            names = lambda rows: ", ".join(r["name"] for r in rows) or "—"
            if g["not_rsvpd"]:
                out.append(f"No RSVP ({len(g['not_rsvpd'])}): {names(g['not_rsvpd'])}")
            if g["unbooked_hotel"]:
                out.append(f"No room booked ({len(g['unbooked_hotel'])}): " + ", ".join(
                    f"{r['name']} [{r['hotel']}, by {r['book_by']}]" for r in g["unbooked_hotel"]))
            if g["no_flight"]:
                out.append(f"No flight sent ({len(g['no_flight'])}): {names(g['no_flight'])}")
            if g["awaiting_shuttle_seat"]:
                out.append(f"Flight but no shuttle seat ({len(g['awaiting_shuttle_seat'])}): "
                           + ", ".join(f"{r['name']} [{r['flight']} {r['lands']}]"
                                       for r in g["awaiting_shuttle_seat"]))
            if g["plus_one_unnamed"]:
                out.append(f"Plus one not named ({len(g['plus_one_unnamed'])}): "
                           f"{names(g['plus_one_unnamed'])}")
            if g["open_escalations"]:
                out.append("Open questions: " + "; ".join(
                    f"#{e['id']} {e['from']}: “{e['question']}”" for e in g["open_escalations"]))
            return "\n".join(out)

    @agent.tool
    async def search_guests(ctx: RunContext[BellsDeps], query: str) -> str:
        """Find a guest by name or email. The couple may see the whole roster.

        Args:
            query: part of a name or email address.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "search_guests", query=query) as ev:
            rows = gaps.search_guests(query, deps.wedding_id, deps.db_path)
            ev["detail"] = f"{len(rows)} match(es)"
            if not rows:
                return f"NO_MATCH — nobody on the list matches {query!r}."
            return "\n".join(
                f"[{r['id']}] {r['name']} <{r['email']}> · {r['language']} · {r['rsvp_status']}"
                f" · party {r['party_size']}"
                + (f" · +1 {r['plus_one_name']}" if r["plus_one_name"] else "")
                + (f" · {r['hotel_name']}{' (booked)' if r['hotel_booked'] else ' (not booked)'}"
                   if r["hotel_name"] else "")
                + (f" · {r['arrival_flight']} {r['arrival_at']}" if r["arrival_flight"] else " · no flight")
                + (f" · diet: {r['dietary']}" if r["dietary"] else "")
                for r in rows
            )

    @agent.tool
    async def list_registry(ctx: RunContext[BellsDeps]) -> str:
        """The gift list with ids, prices and who has claimed what.

        The couple own this list, so unlike the guest-facing registry agent
        this one may say who claimed an item — they need it to say thank you.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "list_registry") as ev:
            conn = connect(deps.db_path)
            try:
                rows = conn.execute(
                    "SELECT r.id, r.item, r.price, r.claimed_by_guest_id, g.name AS claimed_by"
                    " FROM registry r LEFT JOIN guests g ON g.id = r.claimed_by_guest_id"
                    " WHERE r.wedding_id = ? ORDER BY r.id", (deps.wedding_id,)
                ).fetchall()
            finally:
                conn.close()
            free = sum(1 for r in rows if not r["claimed_by_guest_id"])
            ev["detail"] = f"{len(rows)} item(s), {free} free"
            return "\n".join(
                f"[{r['id']}] {r['item']} · {r['price']:.0f} · "
                + (f"claimed by {r['claimed_by']}" if r["claimed_by_guest_id"] else "available")
                for r in rows
            )

    # ---------------- writing: all of these only ever propose ----------------

    def _propose(deps: BellsDeps, kind: str, summary: str, detail: dict,
                 before: dict, after: dict) -> str:
        p = proposals.create(kind, summary, detail=detail, before=before, after=after,
                             session_token=deps.session_token or "")
        deps.proposals.append({
            "id": p.id, "kind": p.kind, "summary": p.summary,
            "detail": p.detail, "before": p.before, "after": p.after,
        })
        return (f"PROPOSED [{p.id}] — {summary}\n"
                "Nothing has changed yet. Tell the couple exactly what will change and stop; "
                "they confirm with the button, or say yes and you call commit_proposal.")

    @agent.tool
    async def add_fact(ctx: RunContext[BellsDeps], topic: str, answer: str,
                       question_pattern: str | None = None) -> str:
        """Propose a new fact for Bells to answer guests from.

        Args:
            topic: a short slug, e.g. 'ceremony_time'.
            answer: what Bells should tell guests, in the couple's own words.
            question_pattern: the guest phrasings this answers. Optional.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "add_fact", topic=topic) as ev:
            topic = (topic or _slug(answer)).strip()[:60]
            ev["detail"] = f"propose fact '{topic}'"
            return _propose(
                deps, "add_fact", f"Teach Bells a new fact: “{answer[:90]}”",
                {"topic": topic, "answer": answer.strip(),
                 "question_pattern": (question_pattern or answer)[:300]},
                before={"fact": None},
                after={"topic": topic, "answer": answer.strip()},
            )

    @agent.tool
    async def update_fact(ctx: RunContext[BellsDeps], fact_id: int, answer: str) -> str:
        """Propose a correction to a fact Bells already tells guests.

        Args:
            fact_id: the id of the existing fact.
            answer: the corrected wording.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "update_fact", fact_id=fact_id) as ev:
            old = _fact(fact_id)
            if old is None:
                ev["detail"] = "no such fact"
                return f"NO_SUCH_FACT — there is no fact {fact_id}."
            ev["detail"] = f"propose edit to '{old['topic']}'"
            return _propose(
                deps, "update_fact",
                f"Change “{old['topic']}” from “{old['answer'][:60]}…” to “{answer[:60]}…”",
                {"fact_id": fact_id, "answer": answer.strip()},
                before={"fact_id": fact_id, "topic": old["topic"], "answer": old["answer"]},
                after={"fact_id": fact_id, "topic": old["topic"], "answer": answer.strip()},
            )

    @agent.tool
    async def add_registry_item(ctx: RunContext[BellsDeps], item: str,
                                url: str | None = None, price: float | None = None) -> str:
        """Propose a new gift for the registry.

        Args:
            item: what it is.
            url: where to buy it. Optional.
            price: in the wedding's currency. Optional.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "add_registry_item", item=item) as ev:
            ev["detail"] = f"propose adding '{item[:40]}'"
            money = f" ({price:.0f})" if price else ""
            return _propose(
                deps, "add_registry_item", f"Add “{item}”{money} to the registry",
                {"item": item.strip(), "url": (url or "").strip() or None, "price": price},
                before={"item": None},
                after={"item": item.strip(), "url": url, "price": price},
            )

    @agent.tool
    async def remove_registry_item(ctx: RunContext[BellsDeps], item_id: int) -> str:
        """Propose removing a gift. Refuses outright if a guest already claimed it.

        Args:
            item_id: the registry item's id.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "remove_registry_item", item_id=item_id) as ev:
            row = _registry_item(item_id)
            if row is None:
                ev["detail"] = "no such item"
                return f"NO_SUCH_ITEM — there is no registry item {item_id}."
            if row["claimed_by_guest_id"]:
                # the one case where the host may hear a guest's name: they are
                # about to delete a gift that person has already bought
                ev["status"] = "refused"
                ev["detail"] = "already claimed"
                return (
                    f"REFUSED — “{row['item']}” has already been claimed by "
                    f"{row['claimed_by']}. Deleting it would lose a gift someone has "
                    f"bought. Tell the couple to thank {row['claimed_by']} instead, and "
                    "offer to take a different item off the list."
                )
            ev["detail"] = f"propose removing '{row['item'][:40]}'"
            return _propose(
                deps, "remove_registry_item", f"Remove “{row['item']}” from the registry",
                {"item_id": item_id},
                before={"item_id": item_id, "item": row["item"], "price": row["price"]},
                after={"item_id": item_id, "item": None},
            )

    @agent.tool
    async def resolve_escalation(ctx: RunContext[BellsDeps], escalation_id: int,
                                 answer: str) -> str:
        """Propose answering a guest's open question and recording it as a fact.

        Args:
            escalation_id: the open escalation's id.
            answer: what the couple want to tell them.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "resolve_escalation", id=escalation_id) as ev:
            conn = connect(deps.db_path)
            try:
                row = conn.execute(
                    "SELECT e.id, e.question, e.status, g.name AS guest"
                    " FROM escalations e LEFT JOIN guests g ON g.id = e.guest_id"
                    " WHERE e.id = ? AND e.wedding_id = ?", (escalation_id, WEDDING_ID)
                ).fetchone()
            finally:
                conn.close()
            if row is None:
                ev["detail"] = "no such escalation"
                return f"NO_SUCH_ESCALATION — there is no open question {escalation_id}."
            if row["status"] != "open":
                ev["detail"] = f"already {row['status']}"
                return f"ALREADY_{row['status'].upper()} — question {escalation_id} is closed."
            ev["detail"] = f"propose answering #{escalation_id}"
            return _propose(
                deps, "resolve_escalation",
                f"Answer {row['guest']}’s question and teach Bells the answer",
                {"escalation_id": escalation_id, "question": row["question"],
                 "answer": answer.strip(), "topic": _slug(row["question"])},
                before={"escalation_id": escalation_id, "status": "open", "answer": None},
                after={"escalation_id": escalation_id, "status": "answered",
                       "answer": answer.strip()},
            )

    @agent.tool
    async def resolve_shuttles(ctx: RunContext[BellsDeps]) -> str:
        """Propose re-running the shuttle solver — after a flight has changed."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "resolve_shuttles") as ev:
            from solver import schedule_report
            before = schedule_report(deps.wedding_id, db_path=deps.db_path)
            waiting = len(before["unscheduled"])
            ev["detail"] = f"{before['solved']['runs']} runs now, {waiting} unseated"
            return _propose(
                deps, "resolve_shuttles",
                f"Re-run the shuttle solver ({before['solved']['runs']} runs now, "
                f"{waiting} guest(s) without a seat)",
                {},
                before={"runs": before["solved"]["runs"], "unscheduled": before["unscheduled"]},
                after={"runs": "recomputed"},
            )

    @agent.tool
    async def commit_proposal(ctx: RunContext[BellsDeps], proposal_id: str) -> str:
        """Carry out a proposal the couple have just said yes to.

        Only call this when their message is a clear yes to that exact change.

        Args:
            proposal_id: the id from the PROPOSED line.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "commit_proposal", id=proposal_id) as ev:
            try:
                res = proposals.commit(proposal_id, confirmed_by="host (said yes in chat)")
            except (KeyError, ValueError) as exc:
                ev["status"] = "refused"
                ev["detail"] = str(exc)
                return f"CANNOT_COMMIT — {exc}"
            ev["detail"] = f"committed {res['kind']}"
            deps.committed.append(proposal_id)
            return f"DONE — {res['summary']}."

    # ---------------- messaging ----------------

    @agent.tool
    async def draft_blast(ctx: RunContext[BellsDeps], segment: str, intent: str) -> str:
        """Draft one message per recipient. Sends nothing.

        Args:
            segment: 'all', 'attending', 'not_rsvpd', 'declined', 'no_flight',
                'unbooked_hotel', or a plain description of who you mean.
            intent: what the couple want to say, in their words.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "draft_blast", segment=segment) as ev:
            from .blast import write_drafts
            try:
                drafts = await write_drafts(segment, intent, deps)
            except ValueError as exc:
                ev["status"] = "refused"
                ev["detail"] = str(exc)
                return f"UNKNOWN_SEGMENT — {exc}"
            ev["detail"] = f"{len(drafts)} draft(s) for '{segment}'"
            if not drafts:
                return f"NO_RECIPIENTS — nobody is in the '{segment}' group right now."
            deps.drafts.extend(drafts)
            preview = "\n".join(f"· {d['name']} ({d['language']}): {d['message'][:70]}…"
                                for d in drafts[:3])
            return (f"DRAFTED {len(drafts)} message(s) for '{segment}'. Nothing has been "
                    f"sent — they are in the messages panel for approval.\n{preview}")

    return agent


async def ask_host(question: str, deps: BellsDeps) -> str:
    result = await host_agent().run(
        question, deps=deps, usage=deps.usage, usage_limits=USAGE_LIMITS
    )
    return result.output


async def answer_host(question: str, session_token: str, *,
                      db_path: str | None = None) -> dict[str, Any]:
    """One host turn, end to end: reply, proposals raised, drafts written."""
    import audit

    deps = BellsDeps(
        wedding_id=WEDDING_ID,
        guest_id=None,
        guest_name="the couple",
        language="en",
        db_path=db_path,
        events=EventLog(),
        session_token=session_token,
    )

    started = datetime.now()
    answer = await ask_host(question, deps)

    turn = {
        "guest_id": None,
        "guest_name": "host",
        "language": "en",
        "question": question,
        "answer": answer,
        "events": deps.events.events,
        "agents_called": deps.events.agents_called,
        "tools_called": deps.events.tools_called,
        "escalated": False,
        "escalation_ids": [],
        "usage": deps.usage,
        "elapsed_ms": round((datetime.now() - started).total_seconds() * 1000, 1),
    }
    rec = audit.record_turn(turn, db_path=db_path, wedding_id=WEDDING_ID)
    return {
        **turn,
        "audit": rec,
        "proposals": deps.proposals,
        "committed": deps.committed,
        "drafts": deps.drafts,
    }
