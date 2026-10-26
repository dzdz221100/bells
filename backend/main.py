"""Bells backend — FastAPI routes for the guest concierge."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic_ai import ModelHTTPError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import audit
import config
import proposals
import sessions
from db import connect
from sessions import Session, require_guest, require_host
from solver import MINUTES_PER_ROUND_TRIP, guest_pickup, schedule_report, solve_shuttles

config.load_env()

app = FastAPI(title="Bells", description="Wedding guest concierge for destination weddings")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEDDING_ID = 1


# --------------------------------------------------------------------------
# read-only routes — these work with no API key
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, object]:
    """Liveness plus non-secret config diagnostics (never includes the key)."""
    return {"status": "ok", **config.env_status()}


@app.get("/api/wedding")
def wedding() -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM weddings WHERE id = ?", (WEDDING_ID,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "no wedding seeded — run `python data/seed.py`")
    return dict(row)


# --------------------------------------------------------------------------
# sign-in
# --------------------------------------------------------------------------

class GuestSignIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class HostSignIn(BaseModel):
    passcode: str = Field(min_length=1, max_length=120)


def _session_payload(s: Session) -> dict[str, Any]:
    return {
        "token": s.token,
        "role": s.role,
        "guest": None if s.role == "host" else {
            "id": s.guest_id, "name": s.guest_name, "language": s.language,
        },
    }


@app.get("/api/auth/options")
def auth_options() -> dict[str, Any]:
    """What the sign-in screen needs. Never includes guest names."""
    return {
        "demo_mode": sessions.using_default_passcode(),
        "demo_host_passcode": sessions.host_passcode()
        if sessions.using_default_passcode() else None,
    }


@app.post("/api/auth/guest")
def signin_guest(req: GuestSignIn) -> dict[str, Any]:
    guest = sessions.find_guest_by_email(req.email, WEDDING_ID)
    if guest is None:
        raise HTTPException(
            404,
            "We can't find that email on the guest list. Use the address the "
            "invitation was sent to, or ask the couple.",
        )
    return _session_payload(sessions.start_guest(guest))


@app.post("/api/auth/guest/demo")
def signin_demo_guest() -> dict[str, Any]:
    """Signs in as one guest picked at random — the roster is never returned."""
    guest = sessions.random_guest(WEDDING_ID)
    if guest is None:
        raise HTTPException(404, "No guests seeded — run `python data/seed.py`")
    return _session_payload(sessions.start_guest(guest))


@app.post("/api/auth/host")
def signin_host(req: HostSignIn) -> dict[str, Any]:
    if req.passcode.strip() != sessions.host_passcode():
        raise HTTPException(401, "That passcode doesn't match.")
    return _session_payload(sessions.start_host())


@app.post("/api/auth/signout")
def signout(s: Session = Depends(sessions.current_session)) -> dict[str, bool]:
    sessions.end(s.token)
    return {"ok": True}


@app.get("/api/auth/me")
def whoami(s: Session = Depends(sessions.current_session)) -> dict[str, Any]:
    return _session_payload(s)


@app.get("/api/host/guests")
def host_guest_list(s: Session = Depends(require_host)) -> list[dict[str, Any]]:
    """The roster — host only. This is what guests used to be able to see."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, email, language, party_size FROM guests"
            " WHERE wedding_id = ? ORDER BY (arrival_at IS NULL), arrival_at, name",
            (WEDDING_ID,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/me/dashboard")
def dashboard(s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Everything the signed-in guest's own cards need, in one request.

    The id comes from the session, never from the URL — there is no route that
    will serve one guest another guest's details.
    """
    guest_id = s.guest_id
    conn = connect()
    try:
        guest = conn.execute(
            "SELECT * FROM guests WHERE id = ? AND wedding_id = ?", (guest_id, WEDDING_ID)
        ).fetchone()
        if guest is None:
            raise HTTPException(404, f"no guest {guest_id}")
        hotel = None
        if guest["hotel_id"]:
            h = conn.execute("SELECT * FROM hotels WHERE id = ?", (guest["hotel_id"],)).fetchone()
            hotel = dict(h) if h else None
        registry = conn.execute(
            "SELECT id, item, url, image_url, price, claimed_by_guest_id FROM registry"
            " WHERE wedding_id = ? ORDER BY id",
            (WEDDING_ID,),
        ).fetchall()
    finally:
        conn.close()

    pickup = guest_pickup(guest_id)

    return {
        "guest": {
            "id": guest["id"],
            "name": guest["name"],
            "language": guest["language"],
            "party_size": guest["party_size"],
            "rsvp_status": guest["rsvp_status"],
            "rsvp_at": guest["rsvp_at"],
            "dietary": guest["dietary"],
            "plus_one_allowed": bool(guest["plus_one_allowed"]),
            "plus_one_name": guest["plus_one_name"],
            "plus_one_dietary": guest["plus_one_dietary"],
            "hotel_booked": bool(guest["hotel_booked"]),
            "arrival_flight": guest["arrival_flight"],
            "arrival_at": guest["arrival_at"],
            "departure_at": guest["departure_at"],
        },
        "hotel": hotel,
        "pickup": {
            "run": pickup.get("run"),
            "minutes_after_landing": pickup.get("minutes_after_landing"),
            "be_at_pickup_by": pickup.get("be_at_pickup_by"),
            "text": pickup.get("text"),
            # one leg of the round trip: how long the drive itself takes
            "drive_minutes": MINUTES_PER_ROUND_TRIP // 2,
        },
        "registry": {
            "total": len(registry),
            "available": sum(1 for r in registry if r["claimed_by_guest_id"] is None),
            "yours": [
                {"id": r["id"], "item": r["item"], "price": r["price"]}
                for r in registry if r["claimed_by_guest_id"] == guest_id
            ],
            # availability only — never who claimed what
            "items": [
                {
                    "id": r["id"],
                    "item": r["item"],
                    "url": r["url"],
                    "image_url": r["image_url"],
                    "price": r["price"],
                    "available": r["claimed_by_guest_id"] is None,
                    "claimed_by_you": r["claimed_by_guest_id"] == guest_id,
                }
                for r in registry
            ],
        },
    }


@app.get("/api/me/messages")
def messages(s: Session = Depends(require_guest)) -> list[dict[str, Any]]:
    guest_id = s.guest_id
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE guest_id = ?"
            " ORDER BY id",
            (guest_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# chat — this one needs the API key
# --------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


# What a guest sees when the provider refuses the prompt, or when it is simply
# unreachable. Neither is the guest's problem and neither is a stack trace.
CONTENT_FILTER_REPLY = (
    "I can\u2019t help with that one \u2014 if it\u2019s something only Elena and "
    "Matteo can answer, I\u2019ll pass it along."
)
UPSTREAM_ERROR_REPLY = (
    "Bells is having trouble reaching its brain. Try again in a moment."
)


def _is_content_filter(exc: ModelHTTPError) -> bool:
    """Azure rejects a prompt with 400 and a 'content_filter' code in the body."""
    if exc.status_code != 400:
        return False
    haystack = f"{getattr(exc, 'provider_error_code', '') or ''} {exc.body!r} {exc}".lower()
    return "content_filter" in haystack or "content filter" in haystack


def _blocked_turn(
    guest_id: int, question: str, answer: str, reason: str, detail: str,
    started: datetime,
) -> dict[str, Any]:
    """Record a refused turn in the audit trail, then shape it like a reply.

    The guest gets a calm sentence; the trail gets the real reason, so there is
    evidence of what was blocked and why without showing a guest an error.
    """
    from agents.concierge import load_guest

    guest = load_guest(guest_id) or {}
    elapsed = round((datetime.now() - started).total_seconds() * 1000, 1)
    event = {
        "seq": 1,
        "agent": "concierge",
        "tool": reason,
        "args": {},
        "status": "blocked",
        "detail": detail,
        "ms": elapsed,
    }
    turn = {
        "guest_id": guest_id,
        "guest_name": guest.get("name", ""),
        "language": guest.get("language", "en"),
        "question": question,
        "answer": answer,
        "events": [event],
        "agents_called": ["concierge"],
        "tools_called": [f"concierge.{reason}"],
        "escalated": False,
        "escalation_ids": [],
        "usage": None,
        "blocked": True,
        "block_reason": reason,
        "block_detail": detail,
        "elapsed_ms": elapsed,
    }
    rec = audit.record_turn(turn, wedding_id=WEDDING_ID)
    return {
        "answer": answer,
        "escalated": False,
        "agents_called": turn["agents_called"],
        "tools_called": turn["tools_called"],
        "events": turn["events"],
        "tokens": rec["tokens"],
        "cost_usd": rec["cost_usd"],
        "cost_basis": rec["cost_basis"],
        "model": rec["model"],
        "elapsed_ms": elapsed,
        "blocked": True,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, s: Session = Depends(require_guest)) -> dict[str, Any]:
    try:
        config.require_api_key()
    except RuntimeError as exc:
        # The readable two-location message from config.py, straight to the UI.
        raise HTTPException(503, str(exc)) from exc

    from agents import answer_guest  # imported here so startup needs no key

    started = datetime.now()
    try:
        turn = await answer_guest(s.guest_id, req.message)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ModelHTTPError as exc:
        # Upstream said no. A guest never sees a 500 or a stack trace for this.
        if _is_content_filter(exc):
            return _blocked_turn(
                s.guest_id, req.message, CONTENT_FILTER_REPLY,
                "content_filter", f"provider rejected the prompt: {exc}", started,
            )
        return _blocked_turn(
            s.guest_id, req.message, UPSTREAM_ERROR_REPLY,
            "upstream_error", f"{type(exc).__name__} {exc.status_code}: {exc}", started,
        )

    rec = turn["audit"]  # not `audit` — that name is the module
    return {
        "answer": turn["answer"],
        "escalated": turn["escalated"],
        "agents_called": turn["agents_called"],
        "tools_called": turn["tools_called"],
        "events": turn["events"],
        "tokens": rec["tokens"],
        "cost_usd": rec["cost_usd"],
        "cost_basis": rec["cost_basis"],
        "model": rec["model"],
        "elapsed_ms": turn["elapsed_ms"],
    }


# --------------------------------------------------------------------------
# host console
# --------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "do", "does", "for", "from",
    "get", "has", "have", "how", "i", "if", "in", "is", "it", "me", "my", "of",
    "on", "or", "our", "should", "that", "the", "there", "they", "this", "to",
    "we", "what", "when", "where", "which", "who", "will", "with", "you", "your",
}


def topic_slug(question: str) -> str:
    """A short, stable topic key derived from the question's own words."""
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower())
             if w not in STOPWORDS and len(w) > 2][:3]
    return "_".join(words) or "host_answer"


@app.get("/api/host/escalations")
def list_escalations(status: str = "open", s: Session = Depends(require_host)) -> list[dict[str, Any]]:
    """The inbox. `status` is open | answered | dismissed | all."""
    conn = connect()
    try:
        sql = (
            "SELECT e.*, g.name AS guest_name, g.language AS guest_language"
            " FROM escalations e LEFT JOIN guests g ON g.id = e.guest_id"
            " WHERE e.wedding_id = ?"
        )
        params: list[Any] = [WEDDING_ID]
        if status != "all":
            sql += " AND e.status = ?"
            params.append(status)
        rows = conn.execute(sql + " ORDER BY e.created_at DESC, e.id DESC", params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


class ApproveRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    topic: str | None = Field(default=None, max_length=60)
    is_public: bool = True


@app.post("/api/host/escalations/{escalation_id}/approve")
def approve_escalation(escalation_id: int, req: ApproveRequest, s: Session = Depends(require_host)) -> dict[str, Any]:
    """Approve an answer: it becomes a wedding_fact the agent can use forever."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        esc = conn.execute(
            "SELECT * FROM escalations WHERE id = ? AND wedding_id = ?",
            (escalation_id, WEDDING_ID),
        ).fetchone()
        if esc is None:
            raise HTTPException(404, f"no escalation {escalation_id}")
        if esc["status"] != "open":
            raise HTTPException(409, f"escalation {escalation_id} is already {esc['status']}")

        topic = (req.topic or topic_slug(esc["question"])).strip()[:60]
        cur = conn.execute(
            "INSERT INTO wedding_facts (wedding_id, topic, question_pattern, answer,"
            " source, is_public, updated_at) VALUES (?, ?, ?, ?, 'host console', ?, ?)",
            (WEDDING_ID, topic, esc["question"], req.answer.strip(),
             1 if req.is_public else 0, now),
        )
        fact_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE escalations SET status = 'answered', host_answer = ?, resolved_at = ?"
            " WHERE id = ?",
            (req.answer.strip(), now, escalation_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "escalation_id": escalation_id,
        "fact_id": fact_id,
        "topic": topic,
        "is_public": req.is_public,
        "message": "Bells will answer this itself from now on.",
    }


@app.post("/api/host/escalations/{escalation_id}/dismiss")
def dismiss_escalation(escalation_id: int, s: Session = Depends(require_host)) -> dict[str, Any]:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE escalations SET status = 'dismissed', resolved_at = ?"
            " WHERE id = ? AND wedding_id = ? AND status = 'open'",
            (datetime.now().isoformat(timespec="seconds"), escalation_id, WEDDING_ID),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, f"no open escalation {escalation_id}")
    return {"ok": True, "escalation_id": escalation_id}


@app.get("/api/host/impact")
def host_impact(s: Session = Depends(require_host)) -> dict[str, Any]:
    """Automation rate, from the audit trail — one record per real guest turn."""
    trail = [r for r in audit.read_trail() if r.get("type") != "write"]
    turns = len(trail)
    escalated = sum(1 for r in trail if r.get("escalated"))
    answered = turns - escalated

    conn = connect()
    try:
        counts = dict(conn.execute(
            "SELECT status, COUNT(*) FROM escalations WHERE wedding_id = ? GROUP BY status",
            (WEDDING_ID,),
        ).fetchall())
        facts = conn.execute(
            "SELECT COUNT(*) FROM wedding_facts WHERE wedding_id = ?", (WEDDING_ID,)
        ).fetchone()[0]
        from_host = conn.execute(
            "SELECT COUNT(*) FROM wedding_facts WHERE wedding_id = ? AND source = 'host console'",
            (WEDDING_ID,),
        ).fetchone()[0]
        guests_total = conn.execute(
            "SELECT COUNT(*) FROM guests WHERE wedding_id = ?", (WEDDING_ID,)
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "turns": turns,
        "answered_automatically": answered,
        "escalated": escalated,
        "escalation_rate": round(escalated / turns, 4) if turns else None,
        "inbox": {
            "open": counts.get("open", 0),
            "answered": counts.get("answered", 0),
            "dismissed": counts.get("dismissed", 0),
        },
        "facts_total": facts,
        "facts_from_host_console": from_host,
        "guests_total": guests_total,
        # the UI multiplies `answered` by an editable minutes-per-question figure
        "default_minutes_per_question": 3,
    }


@app.get("/api/host/spend")
def host_spend(projection_guests: int = 150,
               s: Session = Depends(require_host)) -> dict[str, Any]:
    """Token and cost totals, plus a per-guest projection.

    Read from output/audit_trail.json, the same record the Impact panel counts,
    so the two panels can never disagree. usage_log holds the same numbers in
    SQL, but `seed.py` drops it — the trail is the durable one.
    """
    trail = [r for r in audit.read_trail() if r.get("type") != "write"]
    basis = trail[-1].get("cost_basis") if trail else "unpriced"

    totals = {"input": 0, "cached": 0, "cache_write": 0, "output": 0}
    cost = 0.0
    priced = False
    guests: set[Any] = set()
    for rec in trail:
        t = rec.get("tokens", {})
        totals["input"] += t.get("input_tokens", 0)
        totals["cached"] += t.get("cached_tokens", 0)
        totals["cache_write"] += t.get("cache_write_tokens", 0)
        totals["output"] += t.get("output_tokens", 0)
        if rec.get("cost_usd") is not None:
            cost += rec["cost_usd"]
            priced = True
        if rec.get("guest_id") is not None:
            guests.add(rec["guest_id"])

    conn = connect()
    try:
        guests_total = conn.execute(
            "SELECT COUNT(*) FROM guests WHERE wedding_id = ?", (WEDDING_ID,)
        ).fetchone()[0]
    finally:
        conn.close()

    uncached = max(0, totals["input"] - totals["cached"])
    total_tokens = totals["input"] + totals["output"]
    guests_seen = len(guests)
    total_cost = round(cost, 6) if priced else None

    per_guest_tokens = round(total_tokens / guests_seen, 1) if guests_seen else None
    per_guest_cost = round(total_cost / guests_seen, 6) if total_cost and guests_seen else None

    return {
        "turns": len(trail),
        "guests_seen": guests_seen,
        "guests_total": guests_total,
        "model": config.MODEL_NAME,
        "tokens": {
            "input": totals["input"],
            "cached": totals["cached"],
            "uncached": uncached,
            "cache_write": totals["cache_write"],
            "output": totals["output"],
            "total": total_tokens,
        },
        "cache_hit_rate": round(totals["cached"] / totals["input"], 4)
        if totals["input"] else None,
        "cost_usd": total_cost,
        "cost_basis": basis,
        "per_guest": {"tokens": per_guest_tokens, "cost_usd": per_guest_cost},
        "projection": {
            "guests": projection_guests,
            "tokens": round(per_guest_tokens * projection_guests) if per_guest_tokens else None,
            "cost_usd": round(per_guest_cost * projection_guests, 2) if per_guest_cost else None,
        },
    }


@app.get("/api/host/shuttles")
def host_shuttles(s: Session = Depends(require_host)) -> dict[str, Any]:
    return schedule_report(WEDDING_ID)


@app.post("/api/host/shuttles/solve")
def host_shuttles_solve(s: Session = Depends(require_host)) -> dict[str, Any]:
    before = schedule_report(WEDDING_ID)
    result = solve_shuttles(WEDDING_ID)
    after = schedule_report(WEDDING_ID)
    return {
        "solved_in_ms": result["solved_in_ms"],
        "unassigned": result["unassigned"],
        "previous_runs": before["solved"]["runs"],
        "report": after,
    }


# --------------------------------------------------------------------------
# registry — the guest's own wishlist page
# --------------------------------------------------------------------------

@app.get("/api/me/registry")
def my_registry(s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Available items, plus the ones this guest took. Never who took the rest."""
    from agents.registry import list_items_rows

    items = list_items_rows(WEDDING_ID, s.guest_id)
    # Every item is returned, including ones already spoken for: the page shows
    # them struck through rather than hiding them. Still no claimer — only the
    # availability flag and "is it yours".
    return {
        "total": len(items),
        "available": sum(1 for i in items if i["available"]),
        "items": items,
        "taken_by_others": sum(
            1 for i in items if not i["available"] and not i["claimed_by_you"]
        ),
        "yours": [i for i in items if i["claimed_by_you"]],
    }


@app.post("/api/me/registry/{item_id}/claim")
def claim_registry_item(item_id: int, s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Mark an item bought. Atomic — two guests cannot both win the same one."""
    from agents.registry import claim

    res = claim(item_id, s.guest_id, WEDDING_ID)
    if not res["ok"]:
        if res["reason"] == "no_such_item":
            raise HTTPException(404, f"No registry item {item_id}.")
        # deliberately does not say who took it
        raise HTTPException(
            409,
            f"Someone else chose “{res['item']}” just now. Have a look at what's left.",
        )
    return res


@app.post("/api/me/registry/{item_id}/unclaim")
def unclaim_registry_item(item_id: int, s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Undo your own claim. Fails the same way whether it is free or someone else's."""
    from agents.registry import unclaim

    res = unclaim(item_id, s.guest_id, WEDDING_ID)
    if not res["ok"]:
        if res["reason"] == "no_such_item":
            raise HTTPException(404, f"No registry item {item_id}.")
        raise HTTPException(409, "That isn't one of your gifts.")
    return res


# --------------------------------------------------------------------------
# RSVP — the guest edits their own, the couple read the totals
# --------------------------------------------------------------------------

class RsvpRequest(BaseModel):
    status: str = Field(pattern="^(attending|declined|pending)$")
    dietary: str | None = Field(default=None, max_length=300)
    bringing_plus_one: bool = False
    plus_one_name: str | None = Field(default=None, max_length=120)
    plus_one_dietary: str | None = Field(default=None, max_length=300)


@app.put("/api/me/rsvp")
def update_rsvp(req: RsvpRequest, s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Save this guest's own RSVP.

    party_size is derived here, never sent by the browser: one, plus one more
    only if the invitation allows a guest AND that guest has been named. It is
    the same number the shuttle solver counts as seats, so a named plus one
    gets a seat and an unnamed one does not.
    """
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        row = conn.execute(
            "SELECT plus_one_allowed FROM guests WHERE id = ? AND wedding_id = ?",
            (s.guest_id, WEDDING_ID),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "guest not found")
        allowed = bool(row["plus_one_allowed"])

        name = (req.plus_one_name or "").strip() or None
        if req.bringing_plus_one and not allowed:
            raise HTTPException(
                409,
                "Your invitation is for you alone. Message the couple if that's "
                "changed and they can add a seat.",
            )
        if not req.bringing_plus_one or req.status != "attending":
            name = None

        p1_diet = (req.plus_one_dietary or "").strip() or None
        if name is None:
            p1_diet = None
        seats = 1 + (1 if name else 0)

        conn.execute(
            "UPDATE guests SET rsvp_status = ?, rsvp_at = ?, party_size = ?,"
            " dietary = ?, plus_one_name = ?, plus_one_dietary = ?"
            " WHERE id = ? AND wedding_id = ?",
            (req.status, None if req.status == "pending" else now, seats,
             (req.dietary or "").strip() or None, name, p1_diet,
             s.guest_id, WEDDING_ID),
        )

        if req.status == "declined":
            # Someone who is not coming should not be holding a seat on a bus.
            # Their flight stays on file, so saying yes again puts them back in
            # the next solve.
            conn.execute(
                "UPDATE guests SET shuttle_run_id = NULL WHERE id = ?", (s.guest_id,)
            )
        # a changed party size changes the seat count on their shuttle
        conn.execute(
            "UPDATE shuttle_runs SET seats_taken = COALESCE(("
            "  SELECT SUM(g.party_size) FROM guests g"
            "  WHERE g.shuttle_run_id = shuttle_runs.id"
            "    AND g.rsvp_status != 'declined'), 0)"
            " WHERE wedding_id = ?",
            (WEDDING_ID,),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "status": req.status,
        "party_size": seats,
        "plus_one_name": name,
    }


@app.get("/api/host/overview")
def host_overview(s: Session = Depends(require_host)) -> dict[str, Any]:
    """Headline numbers for the couple: RSVPs, seats, diets, beds, travel."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT rsvp_status, party_size, dietary, language, hotel_id,"
            " arrival_at, shuttle_run_id, plus_one_allowed, plus_one_name,"
            " plus_one_dietary FROM guests WHERE wedding_id = ?",
            (WEDDING_ID,),
        ).fetchall()
        hotels = conn.execute(
            "SELECT id, name FROM hotels WHERE wedding_id = ? ORDER BY id", (WEDDING_ID,)
        ).fetchall()
        registry = conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN claimed_by_guest_id IS NULL THEN 1 ELSE 0 END) AS available"
            " FROM registry WHERE wedding_id = ?",
            (WEDDING_ID,),
        ).fetchone()
    finally:
        conn.close()

    attending = [r for r in rows if r["rsvp_status"] == "attending"]
    declined = [r for r in rows if r["rsvp_status"] == "declined"]
    pending = [r for r in rows if r["rsvp_status"] == "pending"]

    def seats(group) -> int:
        return sum(int(g["party_size"] or 1) for g in group)

    diets: dict[str, int] = {}
    for g in attending:
        # the guest counts once; their plus one counts separately, with their
        # own needs — the caterer cooks per person, not per invitation
        for field, people in (("dietary", 1), ("plus_one_dietary", 1)):
            d = (g[field] or "").strip()
            if d and (field == "dietary" or g["plus_one_name"]):
                diets[d] = diets.get(d, 0) + people

    languages: dict[str, int] = {}
    for g in rows:
        languages[g["language"]] = languages.get(g["language"], 0) + 1

    hotel_names = {h["id"]: h["name"] for h in hotels}
    beds: dict[str, int] = {}
    for g in attending:
        if g["hotel_id"]:
            name = hotel_names.get(g["hotel_id"], "unknown")
            beds[name] = beds.get(name, 0) + int(g["party_size"] or 1)

    travelling = [g for g in rows if g["arrival_at"]]
    responded = len(attending) + len(declined)

    return {
        "invited": len(rows),
        "rsvp": {
            "attending": len(attending),
            "declined": len(declined),
            "pending": len(pending),
            "response_rate": round(responded / len(rows), 4) if rows else None,
        },
        "seats": {
            "attending": seats(attending),
            "invited": seats(rows),
            "pending": seats(pending),
        },
        "dietary": sorted(
            ({"need": k, "people": v} for k, v in diets.items()),
            key=lambda d: (-d["people"], d["need"]),
        ),
        "dietary_people": sum(diets.values()),
        "plus_ones": {
            "invited": sum(1 for g in rows if g["plus_one_allowed"]),
            "named": sum(1 for g in attending if g["plus_one_name"]),
            "unnamed": sum(
                1 for g in attending if g["plus_one_allowed"] and not g["plus_one_name"]
            ),
        },
        "languages": sorted(
            ({"code": k, "guests": v} for k, v in languages.items()),
            key=lambda d: (-d["guests"], d["code"]),
        ),
        "beds": sorted(
            ({"hotel": k, "people": v} for k, v in beds.items()),
            key=lambda d: -d["people"],
        ),
        "travel": {
            "with_flights": len(travelling),
            "on_a_shuttle": sum(1 for g in travelling if g["shuttle_run_id"]),
            "no_shuttle_yet": sum(1 for g in travelling if not g["shuttle_run_id"]),
        },
        "registry": {
            "total": registry["total"],
            "available": registry["available"],
            "chosen": registry["total"] - (registry["available"] or 0),
        },
    }


# --------------------------------------------------------------------------
# travel — the guest ticks off their own to-do list
# --------------------------------------------------------------------------

class TravelRequest(BaseModel):
    """Every field optional: the task strip sends only what it just resolved."""

    hotel_booked: bool | None = None
    arrival_flight: str | None = Field(default=None, max_length=24)
    arrival_at: str | None = Field(default=None, max_length=24)


@app.put("/api/me/travel")
def update_travel(req: TravelRequest, s: Session = Depends(require_guest)) -> dict[str, Any]:
    """Mark the room booked, or hand in a flight.

    A new flight is solved immediately, so the guest sees their pickup appear
    in the same breath as they tell us when they land.
    """
    sets: list[str] = []
    args: list[Any] = []

    if req.hotel_booked is not None:
        sets.append("hotel_booked = ?")
        args.append(1 if req.hotel_booked else 0)

    new_flight = False
    if req.arrival_flight is not None or req.arrival_at is not None:
        if not (req.arrival_flight or "").strip() or not (req.arrival_at or "").strip():
            raise HTTPException(422, "A flight needs both its number and when it lands.")
        try:
            datetime.fromisoformat(req.arrival_at)
        except ValueError as exc:
            raise HTTPException(422, "That landing time isn't a date and time.") from exc
        sets += ["arrival_flight = ?", "arrival_at = ?"]
        args += [req.arrival_flight.strip(), req.arrival_at.strip()]
        new_flight = True

    if not sets:
        raise HTTPException(422, "Nothing to update.")

    conn = connect()
    try:
        conn.execute(
            f"UPDATE guests SET {', '.join(sets)} WHERE id = ? AND wedding_id = ?",
            (*args, s.guest_id, WEDDING_ID),
        )
        conn.commit()
    finally:
        conn.close()

    solved = None
    if new_flight:
        # they now have a landing time and no seat — put them on a bus
        solved = solve_shuttles(WEDDING_ID)["solved_in_ms"]

    return {
        "ok": True,
        "hotel_booked": req.hotel_booked,
        "arrival_flight": req.arrival_flight,
        "solved_in_ms": solved,
        "pickup": guest_pickup(s.guest_id).get("run"),
    }


# --------------------------------------------------------------------------
# host concierge — chat, proposals, drafts
# --------------------------------------------------------------------------

# Drafts live in memory beside the sessions: they are unsent work, not records.
# Keyed by session, because one couple's unsent drafts are nobody else's
# business — and because a stale set from a previous session showing up in a
# new one is how somebody ends up approving the same message twice.
_DRAFTS: dict[str, dict[str, dict[str, Any]]] = {}


def _session_drafts(token: str) -> dict[str, dict[str, Any]]:
    return _DRAFTS.setdefault(token, {})


def _store_drafts(token: str, drafts: list[dict[str, Any]]) -> None:
    """Add new drafts, superseding any unsent draft for the same guest+segment.

    Asking twice for the same reminder should rewrite it, not queue a second
    copy of it.
    """
    store = _session_drafts(token)
    incoming = {(d["segment"], d["guest_id"]) for d in drafts}
    for key, existing in list(store.items()):
        if existing["status"] == "draft" and (existing["segment"], existing["guest_id"]) in incoming:
            del store[key]
    for d in drafts:
        store[d["id"]] = d


class HostChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.post("/api/host/chat")
async def host_chat(req: HostChatRequest, s: Session = Depends(require_host)) -> dict[str, Any]:
    try:
        config.require_api_key()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    from agents import answer_host

    started = datetime.now()
    try:
        turn = await answer_host(req.message, s.token)
    except ModelHTTPError as exc:
        if _is_content_filter(exc):
            return _blocked_turn(0, req.message, CONTENT_FILTER_REPLY,
                                 "content_filter", f"provider rejected the prompt: {exc}", started)
        return _blocked_turn(0, req.message, UPSTREAM_ERROR_REPLY,
                             "upstream_error", f"{type(exc).__name__} {exc.status_code}: {exc}",
                             started)

    _store_drafts(s.token, turn["drafts"])

    rec = turn["audit"]
    return {
        "answer": turn["answer"],
        "proposals": turn["proposals"],
        "committed": turn["committed"],
        "drafts": turn["drafts"],
        "agents_called": turn["agents_called"],
        "tools_called": turn["tools_called"],
        "events": turn["events"],
        "tokens": rec["tokens"],
        "cost_usd": rec["cost_usd"],
        "cost_basis": rec["cost_basis"],
        "model": rec["model"],
        "elapsed_ms": turn["elapsed_ms"],
    }


@app.get("/api/host/proposals")
def list_proposals(s: Session = Depends(require_host)) -> list[dict[str, Any]]:
    return [
        {"id": p.id, "kind": p.kind, "summary": p.summary, "detail": p.detail,
         "before": p.before, "after": p.after, "created_at": p.created_at}
        for p in proposals.pending_for(s.token)
    ]


@app.post("/api/host/proposals/{proposal_id}/confirm")
def confirm_proposal(proposal_id: str, s: Session = Depends(require_host)) -> dict[str, Any]:
    """The couple pressed "Do it". This is the only place a host write happens."""
    p = proposals.get(proposal_id)
    if p is None:
        raise HTTPException(404, "That change has expired — ask again.")
    if p.session_token != s.token:
        raise HTTPException(403, "That change belongs to a different session.")
    try:
        return proposals.commit(proposal_id, confirmed_by="host console button")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/host/proposals/{proposal_id}/cancel")
def cancel_proposal(proposal_id: str, s: Session = Depends(require_host)) -> dict[str, Any]:
    p = proposals.cancel(proposal_id)
    if p is None:
        raise HTTPException(404, "No such change.")
    return {"ok": True, "id": p.id, "status": p.status}


@app.get("/api/host/drafts")
def list_drafts(s: Session = Depends(require_host)) -> dict[str, Any]:
    drafts = sorted(_session_drafts(s.token).values(), key=lambda d: (d["segment"], d["name"]))
    by_segment: dict[str, list] = {}
    for d in drafts:
        by_segment.setdefault(d["segment"], []).append(d)
    return {
        "total": len(drafts),
        "awaiting": sum(1 for d in drafts if d["status"] == "draft"),
        "segments": [{"segment": k, "intent": v[0]["intent"], "drafts": v}
                     for k, v in by_segment.items()],
    }


class DraftEdit(BaseModel):
    message: str | None = Field(default=None, max_length=2000)


@app.post("/api/host/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, req: DraftEdit, s: Session = Depends(require_host)) -> dict[str, Any]:
    """Approve one message. It is marked sent; no sender is wired up.

    This is where a real integration would go — see the comment below.
    """
    d = _session_drafts(s.token).get(draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    if req.message is not None and req.message.strip():
        d["message"] = req.message.strip()
        d["edited"] = True

    # ------------------------------------------------------------------
    # A real send would happen here: WhatsApp Business / Twilio for a phone
    # number, or an email provider for d["email"]. Deliberately not wired —
    # this project must never message anybody's real guests by accident, and
    # a send is not something a demo should be able to do at all.
    #     send_whatsapp(to=guest_phone(d["guest_id"]), body=d["message"])
    #     send_email(to=d["email"], subject=..., body=d["message"])
    # ------------------------------------------------------------------

    d["status"] = "sent"
    d["sent_at"] = datetime.now().isoformat(timespec="seconds")
    audit.record_write({
        "kind": "message_approved",
        "summary": f"Approved the message to {d['name']} ({d['segment']})",
        "proposal_id": d["id"],
        "confirmed_by": "host console",
        "before": {"status": "draft"},
        "after": {"status": "sent", "message": d["message"], "guest_id": d["guest_id"],
                  "delivered": False, "note": "no sender wired up; marked sent only"},
    })
    return {"ok": True, "id": d["id"], "status": d["status"], "delivered": False}


@app.post("/api/host/drafts/{draft_id}/skip")
def skip_draft(draft_id: str, s: Session = Depends(require_host)) -> dict[str, Any]:
    d = _session_drafts(s.token).get(draft_id)
    if d is None:
        raise HTTPException(404, "No such draft.")
    d["status"] = "skipped"
    return {"ok": True, "id": d["id"], "status": d["status"]}


@app.post("/api/host/drafts/approve-all")
def approve_all_drafts(segment: str | None = None,
                       s: Session = Depends(require_host)) -> dict[str, Any]:
    done = 0
    for d in list(_session_drafts(s.token).values()):
        if d["status"] != "draft":
            continue
        if segment and d["segment"] != segment:
            continue
        approve_draft(d["id"], DraftEdit(), s)
        done += 1
    return {"ok": True, "approved": done, "delivered": False}
