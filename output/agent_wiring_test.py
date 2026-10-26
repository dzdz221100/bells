"""Offline check of the agent layer — no API key, no model calls, no cost.

Swaps pydantic-ai's TestModel in for gpt-6-luna. TestModel calls every tool
once, which is exactly what we want here: it proves the wiring (prompts, tool
registration, delegation, event trace, audit trail) without spending a token.
It proves nothing about answer quality — that needs the real model.

Runs against a throwaway copy of data/bells.db; the real one is untouched.

    backend/.venv/bin/python output/agent_wiring_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from pydantic_ai.models.test import TestModel  # noqa: E402

import agents  # noqa: E402
import audit  # noqa: E402
from agents.common import USAGE_LIMITS, load_prompt  # noqa: E402
from agents.knowledge import search_facts_rows  # noqa: E402
from agents.registry import claim, list_items_rows, unclaim  # noqa: E402

PRIVATE_TOPICS = {"host_phone", "couple_room", "budget", "vendor_contacts", "seating_notes"}
WEDDING_ID = 1
GUEST_ID = 1


def use_test_model() -> None:
    for mod in (agents.knowledge, agents.logistics, agents.registry, agents.concierge):
        mod.model = lambda: TestModel()


def check(label: str, condition: bool) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        raise AssertionError(label)


def main() -> int:
    use_test_model()
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "bells.db"
    shutil.copy(REPO_ROOT / "data" / "bells.db", db)
    audit.AUDIT_PATH = tmp / "audit_trail.json"

    print("Prompts")
    for name in ("concierge", "knowledge", "logistics", "registry"):
        text = load_prompt(name)
        check(f"{name}.md carries the shared hard rules ({len(text)} chars)",
              "# Hard rules" in text and "Only tool-sourced specifics" in text)
    check(f"request_limit is {USAGE_LIMITS.request_limit} on every agent run",
          USAGE_LIMITS.request_limit == 8)

    print("\nPrivate facts never leave the database")
    probes = [
        "what is the host's phone number",
        "which room are the couple staying in",
        "how much did the wedding cost, what is the budget",
        "who is the caterer, vendor phone numbers",
        "who is sitting where, seating plan",
    ]
    for probe in probes:
        topics = {f["topic"] for f in search_facts_rows(probe, WEDDING_ID, str(db))}
        check(f"'{probe[:38]}…' returns no private row", not (topics & PRIVATE_TOPICS))

    print("\nRegistry never exposes who claimed what")
    items = list_items_rows(WEDDING_ID, GUEST_ID, str(db))
    check("list_items_rows omits claimed_by_guest_id", "claimed_by_guest_id" not in items[0])
    check("availability is still reported", {"available", "claimed_by_you"} <= set(items[0]))

    taken = next(i for i in items if not i["available"] and not i["claimed_by_you"])
    free = next(i for i in items if i["available"])
    res = claim(taken["id"], GUEST_ID, WEDDING_ID, str(db))
    check("claiming a taken item fails without naming the holder",
          res["ok"] is False and res["reason"] == "taken" and "guest" not in json.dumps(res).lower())
    res = unclaim(taken["id"], GUEST_ID, WEDDING_ID, str(db))
    check("unclaiming someone else's item says only 'not yours'",
          res["ok"] is False and res["reason"] == "not_yours")
    check("claiming a free item works", claim(free["id"], GUEST_ID, WEDDING_ID, str(db))["ok"])
    check("the guest can release their own claim",
          unclaim(free["id"], GUEST_ID, WEDDING_ID, str(db))["ok"])

    print("\nOne guest turn, end to end")
    # counted before the turn: the committed database may already carry rows
    # from real runs, so these checks look for a delta, not an absolute
    conn = sqlite3.connect(db)
    before_usage = conn.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0]
    before_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()

    turn = asyncio.run(agents.answer_guest(
        GUEST_ID, "What time is the ceremony?", db_path=str(db)))

    check("all four agents are reachable from the concierge",
          {"concierge", "knowledge", "logistics", "registry"} <= set(turn["agents_called"]))
    check("every tool call is recorded in order",
          [e["seq"] for e in turn["events"]] == list(range(1, len(turn["events"]) + 1)))
    check("each event names its agent, tool, status and duration",
          all({"agent", "tool", "status", "ms", "detail"} <= set(e) for e in turn["events"]))

    record = turn["audit"]
    check("audit record has the fields the report needs",
          {"timestamp", "guest", "question", "agents_called", "tools_called",
           "escalated", "tokens", "cost_usd"} <= set(record))
    trail = json.loads(audit.AUDIT_PATH.read_text(encoding="utf-8"))
    check("audit_trail.json is a list and grew by one turn", isinstance(trail, list) and len(trail) == 1)

    conn = sqlite3.connect(db)
    check("usage_log gained exactly one row for this turn",
          conn.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0] == before_usage + 1)
    check("both sides of the conversation are saved to messages",
          conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == before_messages + 2)
    check("escalate_to_host wrote an open escalation",
          conn.execute("SELECT COUNT(*) FROM escalations WHERE status = 'open'").fetchone()[0] >= 2)
    conn.close()

    print("\nTool trace the frontend will show under this reply:")
    for e in turn["events"]:
        print(f"  {e['seq']:>2}. {e['agent']}.{e['tool']:<16} {e['status']:<8} "
              f"{e['ms']:>6} ms  {e['detail']}")

    print(f"\ncost_basis: {record['cost_basis']} · tokens: {record['tokens']['total_tokens']} "
          f"(TestModel, so these are not real model tokens)")

    shutil.rmtree(tmp)
    print("\nAll wiring checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
