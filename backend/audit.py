"""Audit trail — one JSON record per guest turn.

Appends to output/audit_trail.json and mirrors the token counts into the
usage_log table so the tokenomics page can read them with SQL.

Prices come from the environment, per million tokens, so this file never has
to guess a rate:

    BELLS_PRICE_INPUT_PER_MTOK=0.10          # required
    BELLS_PRICE_OUTPUT_PER_MTOK=0.50         # required
    BELLS_PRICE_CACHED_INPUT_PER_MTOK=0.01   # optional, defaults to the input rate
    BELLS_PRICE_CACHE_WRITE_PER_MTOK=0.125   # optional, defaults to the input rate

They ship with values in `.env.example` because published list prices are not
secrets. Leave either required one unset and cost_usd is null with
`cost_basis: "unpriced"`, which is honest rather than wrong. Token counts are
real either way.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from db import connect

AUDIT_PATH = config.REPO_ROOT / "output" / "audit_trail.json"


def _price(env_name: str) -> float | None:
    raw = os.getenv(env_name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def compute_cost(usage: Any) -> tuple[float | None, str]:
    """Cost in USD from env-configured per-million-token rates, or None."""
    if getattr(usage, "cost", None):
        return float(usage.cost), "provider"

    p_in = _price("BELLS_PRICE_INPUT_PER_MTOK")
    p_out = _price("BELLS_PRICE_OUTPUT_PER_MTOK")
    if p_in is None or p_out is None:
        return None, "unpriced"
    p_cached = _price("BELLS_PRICE_CACHED_INPUT_PER_MTOK")
    if p_cached is None:
        p_cached = p_in
    p_write = _price("BELLS_PRICE_CACHE_WRITE_PER_MTOK")
    if p_write is None:
        p_write = p_in

    # input_tokens is the whole prompt. Cache reads and cache writes are both
    # already inside it and are billed at their own rates, so the fresh
    # (uncached) remainder is what is left after taking both out.
    total_in = getattr(usage, "input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_tokens", 0) or 0
    cache_write = getattr(usage, "cache_write_tokens", 0) or 0
    uncached = max(0, total_in - cache_read - cache_write)
    out = getattr(usage, "output_tokens", 0) or 0

    cost = (
        uncached * p_in
        + cache_read * p_cached
        + cache_write * p_write
        + out * p_out
    ) / 1_000_000
    return round(cost, 6), "configured_rates"


def usage_dict(usage: Any) -> dict[str, Any]:
    return {
        "requests": getattr(usage, "requests", 0) or 0,
        "tool_calls": getattr(usage, "tool_calls", 0) or 0,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "cached_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_write_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def record_turn(
    turn: dict[str, Any],
    *,
    db_path: str | None = None,
    wedding_id: int | None = None,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    """Append one turn to the audit trail and the usage_log table."""
    usage = turn.get("usage")
    tokens = usage_dict(usage)
    cost, basis = compute_cost(usage)

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "guest_id": turn.get("guest_id"),
        "guest": turn.get("guest_name"),
        "language": turn.get("language"),
        "question": turn.get("question"),
        "answer": turn.get("answer"),
        "agents_called": turn.get("agents_called", []),
        "tools_called": turn.get("tools_called", []),
        "events": turn.get("events", []),
        "escalated": bool(turn.get("escalated")),
        "escalation_ids": turn.get("escalation_ids", []),
        # set when the provider refused the prompt or was unreachable; the
        # guest saw a calm sentence, this is the real reason
        "blocked": bool(turn.get("blocked")),
        "block_reason": turn.get("block_reason"),
        "block_detail": turn.get("block_detail"),
        "model": config.MODEL_NAME,
        "tokens": tokens,
        "cost_usd": cost,
        "cost_basis": basis,
        "elapsed_ms": turn.get("elapsed_ms"),
    }

    _append_json(record, audit_path or AUDIT_PATH)

    try:
        _write_usage_log(record, db_path, wedding_id or 1)
    except Exception as exc:  # never fail a guest's reply over bookkeeping
        record["usage_log_error"] = f"{type(exc).__name__}: {exc}"

    return record


def _append_json(record: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trail: list[dict] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                trail = loaded
        except json.JSONDecodeError:
            # Corrupt trail: keep it rather than lose it, and start a new one.
            path.rename(path.with_suffix(f".corrupt-{int(datetime.now().timestamp())}.json"))
    trail.append(record)
    path.write_text(json.dumps(trail, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_usage_log(record: dict[str, Any], db_path: str | None, wedding_id: int) -> None:
    t = record["tokens"]
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO usage_log (wedding_id, guest_id, agent, model, input_tokens,"
            " cached_tokens, cache_write_tokens, output_tokens, cost_usd, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                wedding_id,
                record.get("guest_id"),
                "+".join(record.get("agents_called") or ["concierge"]),
                record["model"],
                t["input_tokens"],
                t["cached_tokens"],
                t["cache_write_tokens"],
                t["output_tokens"],
                record["cost_usd"] or 0.0,
                record["timestamp"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def read_trail(audit_path: Path | None = None) -> list[dict]:
    path = audit_path or AUDIT_PATH
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def record_write(entry: dict[str, Any], audit_path: Path | None = None) -> dict[str, Any]:
    """Append a confirmed host write, with the values either side of it.

    Separate from record_turn: a write is not a conversation turn, costs no
    tokens, and is the thing an auditor actually wants to read — who changed
    what, from what, to what, and who said yes.
    """
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": "write",
        "kind": entry.get("kind"),
        "summary": entry.get("summary"),
        "proposal_id": entry.get("proposal_id"),
        "confirmed_by": entry.get("confirmed_by"),
        "before": entry.get("before"),
        "after": entry.get("after"),
        "result": entry.get("result"),
    }
    _append_json(record, audit_path or AUDIT_PATH)
    return record


def writes(audit_path: Path | None = None) -> list[dict]:
    """Every confirmed host write, newest last — the change log."""
    return [r for r in read_trail(audit_path) if r.get("type") == "write"]


def blocked_turns(audit_path: Path | None = None) -> list[dict]:
    """Every turn the provider refused — the safety evidence, in one call."""
    return [r for r in read_trail(audit_path) if r.get("blocked")]


def summarise(audit_path: Path | None = None) -> dict[str, Any]:
    """Totals for the tokenomics section of the report."""
    trail = [r for r in read_trail(audit_path) if r.get("type") != "write"]
    if not trail:
        return {"turns": 0}
    totals = {k: sum(r["tokens"].get(k, 0) for r in trail) for k in trail[0]["tokens"]}
    priced = [r["cost_usd"] for r in trail if r.get("cost_usd") is not None]
    return {
        "turns": len(trail),
        "escalated": sum(1 for r in trail if r["escalated"]),
        "blocked": sum(1 for r in trail if r.get("blocked")),
        "tokens": totals,
        "mean_total_tokens_per_turn": round(totals["total_tokens"] / len(trail), 1),
        "cost_usd": round(sum(priced), 6) if priced else None,
        "cost_basis": trail[-1].get("cost_basis"),
        "agents_used": sorted({a for r in trail for a in r["agents_called"]}),
    }
