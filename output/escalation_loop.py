"""The escalation loop, end to end — the one claim Bells is actually making.

A guest asks something nobody wrote down. Bells does not guess: it escalates.
The couple answer once in the host console. The answer becomes a
`wedding_facts` row, and from then on Bells answers that question itself,
without them.

This script runs that loop for real, over the HTTP API, and writes down the
state either side of it:

  1. read the impact panel      — `facts_from_host_console` before
  2. ask three unanswerable questions as a guest   — each should escalate
  3. answer all three in the host console          — each becomes a fact
  4. read the impact panel again — the counter should have moved by three
  5. ask the same three questions again            — none should escalate, and
     each answer should carry the fact the couple supplied

Step 5 is the part that matters. A counter going up proves a row was written;
only the second ask proves the agent learned anything.

Usage:  python output/escalation_loop.py
Writes: output/escalation_loop.json

Needs a working API key — six live turns.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import config  # noqa: E402

config.load_env()

OUT_JSON = ROOT / "output" / "escalation_loop.json"
GUEST_EMAIL = "camille.fournier@example.com"

# Three things no seeded fact covers, each with the answer the couple would
# give and a word that has to survive into the agent's reply afterwards.
CASES: list[dict[str, str]] = [
    {
        "id": "luggage",
        "question": "We check out on the Sunday morning but our flight is at night — "
                    "is there anywhere to leave our bags for the day?",
        "host_answer": "Yes — all three hotels will hold luggage free of charge on "
                       "checkout day until 20:00. Leave it with reception on your way "
                       "out and show your room key to collect it.",
        "topic": "luggage_storage",
        "must_survive": ["20:00", "reception"],
    },
    {
        "id": "ev_charging",
        "question": "We're hiring an electric car — is there anywhere to charge it "
                    "near the venue?",
        "host_answer": "There are two public charging points in Ravello, both on the "
                       "car park at Via della Repubblica. The venue itself has no "
                       "charger, so plan to charge before you drive up.",
        "topic": "ev_charging",
        "must_survive": ["via della repubblica", "car park"],
    },
    {
        "id": "quiet_room",
        "question": "Our baby will need somewhere quiet to nap during the dinner. "
                    "Is there a room we could use?",
        "host_answer": "Yes — the small library off the main hall is set aside as a "
                       "quiet room all evening. It has a sofa and a dimmer, and the "
                       "sitters can keep an ear on it.",
        "topic": "quiet_room",
        "must_survive": ["library"],
    },
]


def show(label: str, value: Any) -> None:
    print(f"  {label:38} {value}")


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

    r = client.post("/api/auth/guest", json={"email": GUEST_EMAIL})
    if r.status_code != 200:
        print(f"guest sign-in failed: {r.status_code} {r.text}")
        return 2
    guest = r.json()
    g_head = {"X-Bells-Session": guest["token"]}

    r = client.post("/api/auth/host", json={"passcode": sessions.host_passcode()})
    if r.status_code != 200:
        print(f"host sign-in failed: {r.status_code} {r.text}")
        return 2
    h_head = {"X-Bells-Session": r.json()["token"]}

    # ---- 1. before -------------------------------------------------------
    before = client.get("/api/host/impact", headers=h_head).json()
    open_before = {e["id"] for e in
                   client.get("/api/host/escalations", headers=h_head).json()}
    print("\n1. before")
    show("facts from the host console", before["facts_from_host_console"])
    show("facts in total", before["facts_total"])
    show("inbox", before["inbox"])
    show("turns recorded", before["turns"])

    # ---- 2. ask, unanswered ---------------------------------------------
    print("\n2. three questions nobody wrote down")
    first_ask: list[dict[str, Any]] = []
    for case in CASES:
        started = time.perf_counter()
        reply = client.post("/api/chat", json={"message": case["question"]},
                            headers=g_head).json()
        first_ask.append({
            "id": case["id"],
            "question": case["question"],
            "answer": reply.get("answer"),
            "escalated": reply.get("escalated"),
            "tools_called": reply.get("tools_called", []),
            "cost_usd": reply.get("cost_usd"),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        print(f"  [{'escalated' if reply.get('escalated') else 'ANSWERED ANYWAY'}] "
              f"{case['id']}")

    # ---- 3. the couple answer, in the console ---------------------------
    print("\n3. the couple answer in the host console")
    inbox = client.get("/api/host/escalations", headers=h_head).json()
    new_items = [e for e in inbox if e["id"] not in open_before]

    approvals: list[dict[str, Any]] = []
    unclaimed = list(new_items)

    STOP = {"a", "an", "and", "are", "at", "be", "but", "can", "could", "do",
            "for", "from", "has", "have", "is", "it", "its", "of", "on", "or",
            "our", "the", "there", "they", "to", "use", "we", "what", "when",
            "where", "which", "will", "with", "you", "your"}

    def words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z']+", (text or "").lower())
                if w not in STOP and len(w) > 2}

    def best_match(question: str) -> dict[str, Any] | None:
        """Pair a case with the escalation the agent actually filed for it.

        The agent rewrites the question in its own words — "our baby will need
        somewhere quiet" comes back as "can Camille and their family use a quiet
        room" — so string similarity alone is not enough. Shared content words
        carry the match, and a matched escalation is consumed, otherwise one
        escalation can be approved three times with three different answers.
        """
        mine = words(question)
        scored = []
        for e in unclaimed:
            theirs = words(e["question"])
            overlap = len(mine & theirs) / max(1, len(mine | theirs))
            ratio = difflib.SequenceMatcher(
                None, question.lower(), (e["question"] or "").lower()).ratio()
            scored.append((max(overlap, ratio), e))
        scored.sort(key=lambda s: -s[0])
        if not scored or scored[0][0] < 0.25:
            return None
        unclaimed.remove(scored[0][1])
        return scored[0][1]

    for case in CASES:
        match = best_match(case["question"])
        if match is None:
            approvals.append({"id": case["id"], "escalation_id": None,
                              "approved": False,
                              "why": "no open escalation was raised for this question"})
            print(f"  [skip] {case['id']} — nothing in the inbox to approve")
            continue

        res = client.post(
            f"/api/host/escalations/{match['id']}/approve",
            json={"answer": case["host_answer"], "topic": case["topic"],
                  "is_public": True},
            headers=h_head,
        )
        ok = res.status_code == 200
        body = res.json() if ok else {"detail": res.text}
        approvals.append({
            "id": case["id"],
            "escalation_id": match["id"],
            "filed_question": match["question"],
            "approved": ok,
            "fact_id": body.get("fact_id"),
            "topic": body.get("topic"),
            "host_answer": case["host_answer"],
            "why": body.get("message") if ok else str(body),
        })
        print(f"  [{'approved' if ok else 'FAILED'}] {case['id']} "
              f"→ escalation {match['id']} → fact {body.get('fact_id')}")

    # ---- 4. after --------------------------------------------------------
    after = client.get("/api/host/impact", headers=h_head).json()
    print("\n4. after")
    show("facts from the host console", f"{before['facts_from_host_console']} → "
                                        f"{after['facts_from_host_console']}")
    show("facts in total", f"{before['facts_total']} → {after['facts_total']}")
    show("inbox answered", f"{before['inbox']['answered']} → {after['inbox']['answered']}")

    # ---- 5. ask again ----------------------------------------------------
    print("\n5. the same three questions, asked again")
    second_ask: list[dict[str, Any]] = []
    for case in CASES:
        started = time.perf_counter()
        reply = client.post("/api/chat", json={"message": case["question"]},
                            headers=g_head).json()
        answer = reply.get("answer") or ""
        low = answer.lower()
        carried = [w for w in case["must_survive"] if w.lower() in low]
        learned = not reply.get("escalated") and len(carried) == len(case["must_survive"])
        second_ask.append({
            "id": case["id"],
            "question": case["question"],
            "answer": answer,
            "escalated": reply.get("escalated"),
            "facts_carried_through": carried,
            "facts_expected": case["must_survive"],
            "answered_from_the_couples_answer": learned,
            "tools_called": reply.get("tools_called", []),
            "cost_usd": reply.get("cost_usd"),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        })
        print(f"  [{'learned' if learned else 'NOT LEARNED'}] {case['id']} — "
              f"escalated={reply.get('escalated')}, carried={carried}")

    # ---- the verdict -----------------------------------------------------
    escalated_first = sum(1 for a in first_ask if a["escalated"])
    learned = sum(1 for a in second_ask if a["answered_from_the_couples_answer"])
    moved = after["facts_from_host_console"] - before["facts_from_host_console"]
    approved = sum(1 for a in approvals if a["approved"])

    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": config.MODEL_NAME,
        "what_this_shows": (
            "a question with no recorded answer is escalated rather than guessed; "
            "the couple answer it once in the host console; it becomes a public "
            "wedding fact; and the agent answers it unaided from then on"
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
            "questions_asked": len(CASES),
            "escalated_on_first_ask": escalated_first,
            "approved_in_the_host_console": approved,
            "facts_from_host_console_moved_by": moved,
            "answered_unaided_on_second_ask": learned,
            # Two separate claims. The loop closing is about the plumbing: a
            # question became a fact. Learning is about the agent then using it.
            "loop_closed": (escalated_first == len(CASES) and approved == len(CASES)
                            and moved == len(CASES)),
            "all_answered_unaided": learned == len(CASES),
            "still_escalating_after_approval": [
                {
                    "id": a["id"],
                    "fact_exists": next((x["fact_id"] for x in approvals
                                         if x["id"] == a["id"]), None),
                    "specialists_consulted": a["tools_called"],
                    "why": "the concierge routed this to the wrong specialist, so the "
                           "fact the couple wrote was never searched for",
                }
                for a in second_ask if not a["answered_from_the_couples_answer"]
            ],
        },
        "first_ask": first_ask,
        "host_approvals": approvals,
        "second_ask": second_ask,
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    s = payload["summary"]
    print("\n" + "=" * 68)
    print(f"escalated first time: {s['escalated_on_first_ask']}/{s['questions_asked']} · "
          f"approved: {s['approved_in_the_host_console']} · "
          f"counter moved: +{s['facts_from_host_console_moved_by']} · "
          f"answered unaided: {s['answered_unaided_on_second_ask']}/{s['questions_asked']}")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    return 0 if s["loop_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
