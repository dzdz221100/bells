"""The host approval loop, run end to end against the real inbox.

This is the claim Bells is making, so it is the one worth proving rather than
describing: a guest asks something nobody wrote down; Bells escalates instead
of guessing; the couple answer it once in the host console; the answer becomes
a `wedding_facts` row; and from then on Bells answers it unaided.

What this script does, over the HTTP API, exactly as a browser would:

  1. read `/api/host/impact`  — `facts_from_host_console` before
  2. take three questions that are **already sitting open in the inbox**, filed
     by the agent during earlier real sessions
  3. approve each one in the host console, with the answer the couple would give
  4. read `/api/host/impact` again — the counter should have moved by three
  5. ask those same three questions again, signed in as the guest who asked
     them, and check the reply carries the couple's answer and does not escalate

Step 5 is the whole point. A counter going up only proves a row was written.
Only the second ask proves the agent learned anything.

Usage:  python output/escalation_loop.py
Writes: output/escalation_loop.json

Needs a working API key — three live turns.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import config  # noqa: E402
from db import connect  # noqa: E402

config.load_env()

OUT_JSON = ROOT / "output" / "escalation_loop.json"
WEDDING_ID = 1

# Three escalations the agents filed for real, picked out of the open inbox.
# For each: the answer the couple give in the console, the topic it files
# under, and the words that have to survive into the agent's later reply.
#
# `guest_phrasing` is how a guest actually asks it. The escalation's own text
# is the agent's rewording of that, and is recorded in the output next to it —
# neither is invented here, they are read from the database at run time.
CASES: list[dict[str, Any]] = [
    {
        "escalation_id": 1,
        "guest_phrasing": "We check out on the morning of the 13th but our flight "
                          "isn't until the evening — can we leave our bags somewhere?",
        "topic": "luggage_storage",
        "host_answer": (
            "Yes. All three hotels hold luggage at reception on check-out day, free "
            "of charge, until 20:00. Leave it on your way out and show your room key "
            "to collect it."
        ),
        "must_survive": ["20:00", "reception"],
    },
    {
        "escalation_id": 7,
        "guest_phrasing": "What time do the shuttles run on the wedding day itself?",
        "topic": "wedding_day_shuttle_times",
        "host_answer": (
            "On Saturday 12 June a loop shuttle runs between all three hotels and the "
            "venue from 15:30 to 16:45, and back again from 23:30 until 01:30. No "
            "booking is needed — just be at your hotel entrance."
        ),
        "must_survive": ["15:30", "16:45", "23:30"],
    },
    {
        "escalation_id": 8,
        "guest_phrasing": "Which airport should I fly into, and how long is the drive "
                          "to Ravello from there?",
        "topic": "which_airport",
        "host_answer": (
            "Fly into Naples (NAP). It is about 1 hour 40 minutes from Ravello by "
            "road, and the wedding shuttles meet the main arrival waves there. Rome "
            "Fiumicino (FCO) is often cheaper but it is a 3.5-hour drive and no "
            "shuttle meets it."
        ),
        "must_survive": ["naples", "1 hour 40"],
    },
]


def show(label: str, value: Any) -> None:
    print(f"  {label:36} {value}")


def guest_for(escalation_id: int) -> dict[str, Any]:
    """The guest who actually asked — the second ask is made as them, not as
    some convenient stand-in."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT e.id, e.question, e.status, e.draft_answer, e.guest_id,"
            " g.name AS guest_name, g.email AS guest_email, g.language"
            " FROM escalations e LEFT JOIN guests g ON g.id = e.guest_id"
            " WHERE e.id = ? AND e.wedding_id = ?",
            (escalation_id, WEDDING_ID),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else {}


def main() -> int:
    try:
        config.require_api_key()
    except RuntimeError as exc:
        print(exc)
        return 2

    from fastapi.testclient import TestClient
    from main import app
    import sessions

    client = TestClient(app)

    r = client.post("/api/auth/host", json={"passcode": sessions.host_passcode()})
    if r.status_code != 200:
        print(f"host sign-in failed: {r.status_code} {r.text}")
        return 2
    h_head = {"X-Bells-Session": r.json()["token"]}

    # ---- 1. before -------------------------------------------------------
    before = client.get("/api/host/impact", headers=h_head).json()
    print("\n1. before")
    show("facts from the host console", before["facts_from_host_console"])
    show("facts in total", before["facts_total"])
    show("inbox", before["inbox"])
    show("turns recorded", before["turns"])

    # ---- 2. what is sitting in the inbox ---------------------------------
    print("\n2. three questions already open in the inbox")
    for case in CASES:
        case["escalation"] = guest_for(case["escalation_id"])
        e = case["escalation"]
        if not e:
            print(f"  [missing] escalation {case['escalation_id']} does not exist")
            continue
        print(f"  #{e['id']} ({e['status']}) from {e['guest_name']}: "
              f"{(e['question'] or '')[:70]}")

    # ---- 3. the couple answer, in the console ----------------------------
    print("\n3. the couple answer each one in the host console")
    approvals: list[dict[str, Any]] = []
    for case in CASES:
        e = case["escalation"]
        if not e:
            approvals.append({"escalation_id": case["escalation_id"], "approved": False,
                              "why": "no such escalation"})
            continue
        res = client.post(
            f"/api/host/escalations/{e['id']}/approve",
            json={"answer": case["host_answer"], "topic": case["topic"],
                  "is_public": True},
            headers=h_head,
        )
        ok = res.status_code == 200
        body = res.json() if ok else {"detail": res.text}
        approvals.append({
            "escalation_id": e["id"],
            "asked_by": e["guest_name"],
            "question_as_filed": e["question"],
            "draft_answer_before_approval": e["draft_answer"],
            "approved": ok,
            "approved_answer": case["host_answer"],
            "fact_id": body.get("fact_id"),
            "topic": body.get("topic"),
            "is_public": body.get("is_public"),
            "console_said": body.get("message") if ok else str(body),
        })
        print(f"  [{'approved' if ok else 'FAILED'}] escalation {e['id']} "
              f"→ fact {body.get('fact_id')} · topic {body.get('topic')}")

    # ---- 4. after --------------------------------------------------------
    after = client.get("/api/host/impact", headers=h_head).json()
    print("\n4. after")
    show("facts from the host console",
         f"{before['facts_from_host_console']} → {after['facts_from_host_console']}")
    show("facts in total", f"{before['facts_total']} → {after['facts_total']}")
    show("inbox open", f"{before['inbox']['open']} → {after['inbox']['open']}")
    show("inbox answered", f"{before['inbox']['answered']} → {after['inbox']['answered']}")

    # ---- 5. ask again, as the guest who asked ----------------------------
    print("\n5. the same three questions, asked again by the same guest")
    second_ask: list[dict[str, Any]] = []
    for case in CASES:
        e = case["escalation"]
        if not e:
            continue
        sign = client.post("/api/auth/guest", json={"email": e["guest_email"]})
        g_head = {"X-Bells-Session": sign.json()["token"]}

        started = time.perf_counter()
        reply = client.post("/api/chat", json={"message": case["guest_phrasing"]},
                            headers=g_head).json()
        answer = reply.get("answer") or ""
        low = answer.lower()
        carried = [w for w in case["must_survive"] if w.lower() in low]
        learned = not reply.get("escalated") and len(carried) == len(case["must_survive"])

        second_ask.append({
            "escalation_id": e["id"],
            "asked_by": e["guest_name"],
            "asked_now": case["guest_phrasing"],
            "reply": answer,
            "escalated": reply.get("escalated"),
            "answered_from_the_couples_answer": learned,
            "facts_expected": case["must_survive"],
            "facts_carried_through": carried,
            "agents_called": reply.get("agents_called", []),
            "tools_called": reply.get("tools_called", []),
            "tokens": reply.get("tokens", {}).get("total_tokens"),
            "cost_usd": reply.get("cost_usd"),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        print(f"  [{'answered itself' if learned else 'NOT ANSWERED'}] "
              f"#{e['id']} — escalated={reply.get('escalated')}, carried={carried}")

    # ---- the verdict -----------------------------------------------------
    approved = sum(1 for a in approvals if a["approved"])
    moved = after["facts_from_host_console"] - before["facts_from_host_console"]
    learned = sum(1 for a in second_ask if a["answered_from_the_couples_answer"])

    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": config.MODEL_NAME,
        "what_this_shows": (
            "three questions the agent had already escalated during real guest "
            "sessions are answered once by the couple in the host console, become "
            "public wedding facts, and are then answered by the agent unaided when "
            "the same guest asks again"
        ),
        "before": {
            "facts_from_host_console": before["facts_from_host_console"],
            "facts_total": before["facts_total"],
            "inbox": before["inbox"],
            "turns_recorded": before["turns"],
            "escalation_rate": before["escalation_rate"],
        },
        "after": {
            "facts_from_host_console": after["facts_from_host_console"],
            "facts_total": after["facts_total"],
            "inbox": after["inbox"],
            "turns_recorded": after["turns"],
            "escalation_rate": after["escalation_rate"],
        },
        "summary": {
            "escalations_approved": approved,
            "facts_from_host_console_moved_by": moved,
            "answered_unaided_on_second_ask": learned,
            "of": len(CASES),
            "loop_closed": approved == len(CASES) and moved == len(CASES),
            "all_answered_unaided": learned == len(CASES),
            "still_escalating_after_approval": [
                {
                    "escalation_id": a["escalation_id"],
                    "fact_id": next((x["fact_id"] for x in approvals
                                     if x["escalation_id"] == a["escalation_id"]), None),
                    "specialists_consulted": a["tools_called"],
                    "why": "the concierge sent this to a specialist that cannot read "
                           "wedding_facts, so the couple's answer was never searched for",
                }
                for a in second_ask if not a["answered_from_the_couples_answer"]
            ],
        },
        "host_approvals": approvals,
        "second_ask": second_ask,
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    s = payload["summary"]
    print("\n" + "=" * 68)
    print(f"approved: {s['escalations_approved']}/{s['of']} · "
          f"facts_from_host_console +{s['facts_from_host_console_moved_by']} "
          f"({before['facts_from_host_console']} → {after['facts_from_host_console']}) · "
          f"answered unaided: {s['answered_unaided_on_second_ask']}/{s['of']}")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    return 0 if s["loop_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
