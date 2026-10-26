"""Proposals: the host agent asks, a human says yes, the server does it.

The agent never mutates anything. Every write tool validates its arguments,
works out exactly what would change, and parks a proposal here. The change
itself only happens when `commit()` is called — from the console's "Do it"
button, or from the agent after the couple say yes in words.

That split is deliberate. If committing were a tool, the model would hold the
authority to decide when consent was given. Here the model can only ever
describe; the authority sits with whoever presses the button, and the SQL that
runs is written down in this file rather than chosen at inference time.

Every commit writes a before/after record to the audit trail.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import audit
from db import connect

WEDDING_ID = 1


@dataclass
class Proposal:
    id: str
    kind: str                       # add_fact, remove_registry_item, ...
    summary: str                    # one line a human can approve or refuse
    detail: dict[str, Any]          # what the couple should see before saying yes
    before: dict[str, Any]          # state now, for the audit record
    after: dict[str, Any]           # state proposed, for the audit record
    session_token: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    status: str = "pending"         # pending | committed | cancelled


_PROPOSALS: dict[str, Proposal] = {}


def create(kind: str, summary: str, *, detail: dict, before: dict, after: dict,
           session_token: str) -> Proposal:
    p = Proposal(
        id=secrets.token_urlsafe(9), kind=kind, summary=summary,
        detail=detail, before=before, after=after, session_token=session_token,
    )
    _PROPOSALS[p.id] = p
    return p


def get(proposal_id: str) -> Proposal | None:
    return _PROPOSALS.get(proposal_id)


def pending_for(session_token: str) -> list[Proposal]:
    return [p for p in _PROPOSALS.values()
            if p.session_token == session_token and p.status == "pending"]


def cancel(proposal_id: str) -> Proposal | None:
    p = _PROPOSALS.get(proposal_id)
    if p and p.status == "pending":
        p.status = "cancelled"
    return p


# --------------------------------------------------------------------------
# the committers — one per kind, all plain SQL
# --------------------------------------------------------------------------

def _commit_add_fact(d: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO wedding_facts (wedding_id, topic, question_pattern, answer,"
            " source, is_public, updated_at) VALUES (?, ?, ?, ?, 'host concierge', 1, ?)",
            (WEDDING_ID, d["topic"], d["question_pattern"], d["answer"], now),
        )
        conn.commit()
        return {"fact_id": int(cur.lastrowid)}
    finally:
        conn.close()


def _commit_update_fact(d: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        conn.execute(
            "UPDATE wedding_facts SET answer = ?, updated_at = ?"
            " WHERE id = ? AND wedding_id = ?",
            (d["answer"], now, d["fact_id"], WEDDING_ID),
        )
        conn.commit()
        return {"fact_id": d["fact_id"]}
    finally:
        conn.close()


def _commit_add_registry_item(d: dict) -> dict:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO registry (wedding_id, item, url, price) VALUES (?, ?, ?, ?)",
            (WEDDING_ID, d["item"], d.get("url"), d.get("price")),
        )
        conn.commit()
        return {"item_id": int(cur.lastrowid)}
    finally:
        conn.close()


def _commit_remove_registry_item(d: dict) -> dict:
    conn = connect()
    try:
        conn.execute("DELETE FROM registry WHERE id = ? AND wedding_id = ?",
                     (d["item_id"], WEDDING_ID))
        conn.commit()
        return {"item_id": d["item_id"]}
    finally:
        conn.close()


def _commit_resolve_escalation(d: dict) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO wedding_facts (wedding_id, topic, question_pattern, answer,"
            " source, is_public, updated_at) VALUES (?, ?, ?, ?, 'host concierge', 1, ?)",
            (WEDDING_ID, d["topic"], d["question"], d["answer"], now),
        )
        fact_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE escalations SET status = 'answered', host_answer = ?, resolved_at = ?"
            " WHERE id = ? AND wedding_id = ?",
            (d["answer"], now, d["escalation_id"], WEDDING_ID),
        )
        conn.commit()
        return {"fact_id": fact_id, "escalation_id": d["escalation_id"]}
    finally:
        conn.close()


def _commit_resolve_shuttles(d: dict) -> dict:
    from solver import solve_shuttles
    result = solve_shuttles(WEDDING_ID)
    return {
        "runs": len(result["runs"]),
        "solved_in_ms": result["solved_in_ms"],
        "unassigned": result["unassigned"],
    }


COMMITTERS: dict[str, Callable[[dict], dict]] = {
    "add_fact": _commit_add_fact,
    "update_fact": _commit_update_fact,
    "add_registry_item": _commit_add_registry_item,
    "remove_registry_item": _commit_remove_registry_item,
    "resolve_escalation": _commit_resolve_escalation,
    "resolve_shuttles": _commit_resolve_shuttles,
}


def commit(proposal_id: str, *, confirmed_by: str = "host console") -> dict[str, Any]:
    """Carry out a pending proposal and write it to the audit trail."""
    p = _PROPOSALS.get(proposal_id)
    if p is None:
        raise KeyError(f"no proposal {proposal_id}")
    if p.status != "pending":
        raise ValueError(f"proposal {proposal_id} is already {p.status}")

    committer = COMMITTERS.get(p.kind)
    if committer is None:
        raise ValueError(f"nothing knows how to commit {p.kind!r}")

    result = committer(p.detail)
    p.status = "committed"

    audit.record_write({
        "kind": p.kind,
        "summary": p.summary,
        "proposal_id": p.id,
        "confirmed_by": confirmed_by,
        "before": p.before,
        "after": {**p.after, **result},
        "result": result,
    })
    return {"ok": True, "kind": p.kind, "summary": p.summary, **result}
