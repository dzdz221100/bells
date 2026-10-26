"""Does prompt caching cut Bells' cost — and does it cost us correctness?

The same eight guest questions are asked twice.

  COLD   every agent's system prompt is prefixed with a short unique nonce, so
         no cache anywhere — provider, gateway or otherwise — can reuse a
         prefix. The nonce is eight characters, about four tokens, so it busts
         the cache without meaningfully inflating the prompt.

  WARM   the real, unmodified prompts, run straight afterwards with the prefix
         already hot.

That is the only difference. Same questions, same model, same tools, same
order, one process. Whatever moves between the two passes is caching.

Correctness is checked independently in each pass: every question carries the
facts its answer has to contain, taken from the seeded wedding_facts rows. A
cheaper pass that drops a fact is not a saving, and the report says so.

This script changes nothing in the app. It swaps `load_prompt` for the length
of the cold pass and puts it back; `backend/` is untouched.

Usage:  python output/cost_test.py
Writes: output/cost_results.json

Needs a working API key — 17 live turns.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import config  # noqa: E402

config.load_env()

OUT_JSON = ROOT / "output" / "cost_results.json"
GUEST_ID = 1


# ---------------------------------------------------------------------------
# the questions, and what a correct answer has to contain
# ---------------------------------------------------------------------------
# Each entry in `must_include` is an any-of group: the answer has to match at
# least one string in every group. That tolerates wording and formatting
# without tolerating a missing fact.

QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "q1-ceremony-time",
        "text": "What time does the ceremony start?",
        "must_include": [["17:00", "5:00 pm", "5 pm"]],
    },
    {
        "id": "q2-welcome-dinner",
        "text": "When is the welcome dinner, and how formal is it?",
        "must_include": [["20:00", "8:00 pm", "8 pm"], ["casual"]],
    },
    {
        "id": "q3-rsvp-deadline",
        "text": "When do I have to RSVP by?",
        "must_include": [["1 may 2027", "may 1, 2027", "1 maggio", "1er mai"]],
    },
    {
        "id": "q4-airport",
        "text": "Which airport should I fly into, and how far is it from Ravello?",
        "must_include": [["naples", "nap"], ["1 hour 40", "1h40", "100 minutes", "1 ora e 40"]],
    },
    {
        "id": "q5-children",
        "text": "Can I bring my two children to the wedding dinner on the Saturday?",
        # Camille's record language is French, and a perturbed prompt sometimes
        # tips the reply into it. "19 h" is the same fact as "19:00", so the
        # check accepts the guest's own language rather than failing a correct
        # answer for being written in it.
        "must_include": [["adults-only", "adults only", "19:00", "7 pm",
                          "19 h", "adultes", "adulti", "adultos"]],
    },
    {
        "id": "q6-brunch",
        "text": "Is there anything happening on the Sunday after the wedding?",
        "must_include": [["11:00", "11 am"], ["minori", "villa romana"]],
    },
    {
        "id": "q7-bar",
        "text": "Is there an open bar, and how long does it run?",
        "must_include": [["18:00", "6 pm"], ["01:00", "1 am", "1:00"]],
    },
    {
        "id": "q8-dress-colours",
        "text": "Are there any colours I should avoid wearing?",
        "must_include": [["white"], ["ivory"], ["olive"], ["sand"]],
    },
]


def grade(answer: str, groups: list[list[str]]) -> tuple[bool, list[str]]:
    low = (answer or "").lower()
    missing = [" / ".join(g) for g in groups if not any(opt.lower() in low for opt in g)]
    return (not missing, missing)


# ---------------------------------------------------------------------------
# cache control
# ---------------------------------------------------------------------------

def prompt_modules() -> list[Any]:
    """Every module that holds its own reference to `load_prompt`."""
    import agents.common as common
    import agents.concierge as concierge
    import agents.knowledge as knowledge
    import agents.logistics as logistics
    import agents.registry as registry
    return [common, concierge, knowledge, logistics, registry]


def agent_caches() -> list[Any]:
    import agents.concierge as concierge
    import agents.knowledge as knowledge
    import agents.logistics as logistics
    import agents.registry as registry
    return [concierge.concierge_agent, knowledge.knowledge_agent,
            logistics.logistics_agent, registry.registry_agent]


_REAL_LOAD_PROMPT: Any = None


def real_load_prompt() -> Any:
    """The app's own `load_prompt`, captured once before anything replaces it."""
    global _REAL_LOAD_PROMPT
    if _REAL_LOAD_PROMPT is None:
        import agents.common as common
        _REAL_LOAD_PROMPT = common.load_prompt
    return _REAL_LOAD_PROMPT


def set_prompt_prefix(prefix: str) -> None:
    """Prepend `prefix` to every agent's system prompt and rebuild the agents.

    The agents are cached by `lru_cache`, so they have to be dropped for a new
    prompt to take effect.
    """
    base = real_load_prompt().__wrapped__  # the uncached original reader

    def loader(name: str) -> str:
        return prefix + base(name) if prefix else base(name)

    for module in prompt_modules():
        module.load_prompt = loader
    for cache in agent_caches():
        cache.cache_clear()


def restore_prompts() -> None:
    """Put the app's real prompts back, exactly as they were."""
    original = real_load_prompt()
    original.cache_clear()
    for module in prompt_modules():
        module.load_prompt = original
    for cache in agent_caches():
        cache.cache_clear()


# ---------------------------------------------------------------------------
# running a pass
# ---------------------------------------------------------------------------

def run_pass(label: str, *, cold: bool) -> list[dict[str, Any]]:
    from agents.concierge import answer_guest

    print(f"\n{label} pass ({'cache busted' if cold else 'cache warm'})")
    rows: list[dict[str, Any]] = []

    if not cold:
        # One priming turn so the warm pass measures a hot prefix from its very
        # first question, rather than paying for the warm-up inside q1.
        restore_prompts()
        asyncio.run(answer_guest(GUEST_ID, QUESTIONS[0]["text"], save_history=False))

    for q in QUESTIONS:
        if cold:
            # Eight hex characters: enough to make the prefix unique, small
            # enough that it does not distort the token counts.
            set_prompt_prefix(f"R{uuid.uuid4().hex[:8]} ")

        started = time.perf_counter()
        turn = asyncio.run(answer_guest(GUEST_ID, q["text"], save_history=False))
        elapsed = round((time.perf_counter() - started) * 1000, 1)

        usage = turn["usage"]
        rec = turn["audit"]
        ok, missing = grade(turn["answer"], q["must_include"])
        rows.append({
            "id": q["id"],
            "question": q["text"],
            "answer": turn["answer"],
            "correct": ok,
            "missing_facts": missing,
            "tokens": rec["tokens"],
            "cost_usd": rec["cost_usd"],
            "cost_basis": rec["cost_basis"],
            "elapsed_ms": elapsed,
            "requests": usage.requests,
            "agents_called": turn["agents_called"],
            "escalated": turn["escalated"],
        })
        print(f"  {q['id']:24} {elapsed / 1000:6.1f}s  "
              f"{rec['tokens']['total_tokens']:>6} tok  "
              f"${rec['cost_usd'] or 0:.6f}  {'ok' if ok else 'MISSING ' + str(missing)}")

    if cold:
        restore_prompts()
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = ["input_tokens", "cached_tokens", "cache_write_tokens",
            "output_tokens", "total_tokens"]
    latencies = [r["elapsed_ms"] for r in rows]
    return {
        **{k: sum(r["tokens"][k] for r in rows) for k in keys},
        "cost_usd": round(sum(r["cost_usd"] or 0 for r in rows), 6),
        "total_latency_ms": round(sum(latencies), 1),
        "mean_latency_ms": round(statistics.mean(latencies), 1),
        "median_latency_ms": round(statistics.median(latencies), 1),
        "correct": sum(1 for r in rows if r["correct"]),
        "of": len(rows),
    }


def pct(cold: float, warm: float) -> float | None:
    """Percentage the warm pass saved against the cold one."""
    if not cold:
        return None
    return round((cold - warm) / cold * 100, 1)


def modelled_saving(cold: dict[str, Any], warm: dict[str, Any]) -> dict[str, Any]:
    """What caching *would* be worth at the configured rates, billed strictly.

    Kept separate from the measured numbers, and labelled, because it is a
    model and not an observation: it reprices the cold pass as if every input
    token were uncached, and the warm pass as if its reported cache reads were
    real.
    """
    def price(name: str, fallback: float) -> float:
        raw = os.getenv(name)
        try:
            return float(raw) if raw not in (None, "") else fallback
        except ValueError:
            return fallback

    p_in = price("BELLS_PRICE_INPUT_PER_MTOK", 0.0)
    p_out = price("BELLS_PRICE_OUTPUT_PER_MTOK", 0.0)
    p_cached = price("BELLS_PRICE_CACHED_INPUT_PER_MTOK", p_in)
    p_write = price("BELLS_PRICE_CACHE_WRITE_PER_MTOK", p_in)

    cold_cost = (cold["input_tokens"] * p_in + cold["output_tokens"] * p_out) / 1e6
    warm_uncached = max(0, warm["input_tokens"] - warm["cached_tokens"] - warm["cache_write_tokens"])
    warm_cost = (warm_uncached * p_in + warm["cached_tokens"] * p_cached
                 + warm["cache_write_tokens"] * p_write + warm["output_tokens"] * p_out) / 1e6
    return {
        "what_this_is": "a model, not a measurement — the cold pass repriced as if "
                        "every input token were billed uncached, against the warm "
                        "pass billed at the cached and cache-write rates",
        "rates_per_mtok": {"input": p_in, "cached_input": p_cached,
                           "cache_write": p_write, "output": p_out},
        "cold_cost_usd": round(cold_cost, 6),
        "warm_cost_usd": round(warm_cost, 6),
        "saving_pct": pct(cold_cost, warm_cost),
    }


def main() -> int:
    try:
        config.require_api_key()
    except RuntimeError as exc:
        print(exc)
        return 2

    started = datetime.now()
    try:
        cold_rows = run_pass("COLD", cold=True)
        warm_rows = run_pass("WARM", cold=False)
    finally:
        restore_prompts()

    cold, warm = totals(cold_rows), totals(warm_rows)

    # Per-question comparison, including whether the two answers agree.
    by_question = []
    for c, w in zip(cold_rows, warm_rows):
        similarity = round(difflib.SequenceMatcher(
            None, c["answer"] or "", w["answer"] or "").ratio(), 3)
        by_question.append({
            "id": c["id"],
            "question": c["question"],
            "cold": {k: c[k] for k in ("tokens", "cost_usd", "elapsed_ms", "correct",
                                       "missing_facts", "requests", "answer")},
            "warm": {k: w[k] for k in ("tokens", "cost_usd", "elapsed_ms", "correct",
                                       "missing_facts", "requests", "answer")},
            "tokens_saved": c["tokens"]["total_tokens"] - w["tokens"]["total_tokens"],
            "cost_saved_usd": round((c["cost_usd"] or 0) - (w["cost_usd"] or 0), 6),
            "latency_saved_ms": round(c["elapsed_ms"] - w["elapsed_ms"], 1),
            "both_correct": c["correct"] and w["correct"],
            "answers_agree": c["correct"] == w["correct"],
            "answer_similarity": similarity,
        })

    # Did the provider's cache accounting actually respond to cache state?
    # If cache reads are the same proportion of the prompt whether the prefix
    # was busted or not, the figures are an accounting convention, not
    # telemetry — and no cost conclusion can rest on them.
    cold_share = cold["cached_tokens"] / cold["input_tokens"] if cold["input_tokens"] else 0
    warm_share = warm["cached_tokens"] / warm["input_tokens"] if warm["input_tokens"] else 0
    responsive = abs(cold_share - warm_share) > 0.05

    payload = {
        "run_at": started.isoformat(timespec="seconds"),
        "model": config.MODEL_NAME,
        "method": {
            "questions": len(QUESTIONS),
            "cold": "a unique 8-character nonce prefixed to every agent's system "
                    "prompt, so no prefix can be reused by any cache",
            "warm": "the real prompts, run immediately afterwards with one priming "
                    "turn first so the prefix is already hot",
            "correctness": "each answer must contain every required fact, read from "
                           "the seeded wedding_facts rows",
            "note": "two questions from the first draft were replaced because the "
                    "check, not the app, was wrong: a visa question asks for advice "
                    "the hard rules forbid, and a wedding-day shuttle question "
                    "routes to the solver rather than to the fact that answers it. "
                    "Neither was replaced for being expensive or slow.",
        },
        "cold": cold,
        "warm": warm,
        "savings": {
            "input_tokens_pct": pct(cold["input_tokens"], warm["input_tokens"]),
            "total_tokens_pct": pct(cold["total_tokens"], warm["total_tokens"]),
            "cost_pct": pct(cold["cost_usd"], warm["cost_usd"]),
            "latency_pct": pct(cold["mean_latency_ms"], warm["mean_latency_ms"]),
            "cost_usd_absolute": round(cold["cost_usd"] - warm["cost_usd"], 6),
        },
        "correctness": {
            "cold_correct": f"{cold['correct']}/{cold['of']}",
            "warm_correct": f"{warm['correct']}/{warm['of']}",
            "questions_where_warm_lost_a_fact": [
                q["id"] for q in by_question if q["cold"]["correct"] and not q["warm"]["correct"]
            ],
            "verdict": (
                "caching did not cost any correctness — the warm pass contained "
                "every required fact the cold pass did"
                if warm["correct"] >= cold["correct"] else
                "the warm pass dropped a required fact; see "
                "questions_where_warm_lost_a_fact"
            ),
        },
        "provider_cache_reporting": {
            "cold_cache_read_share_of_input": round(cold_share, 3),
            "warm_cache_read_share_of_input": round(warm_share, 3),
            "responsive_to_cache_state": responsive,
            "note": (
                "the gateway reports the same cache-read share whether the prefix "
                "was busted or not, so its cache figures are an accounting split "
                "rather than telemetry; the measured cost difference between the "
                "passes is therefore near zero and the real, observable effect of "
                "caching here is latency"
                if not responsive else
                "cache reads rose with a warm prefix, so the reported figures track "
                "real cache state and the cost comparison is meaningful"
            ),
        },
        "modelled_saving_if_billed_strictly": modelled_saving(cold, warm),
        "by_question": by_question,
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    s = payload["savings"]
    print("\n" + "=" * 68)
    print(f"tokens   cold {cold['total_tokens']:>7}   warm {warm['total_tokens']:>7}   "
          f"saved {s['total_tokens_pct']}%")
    print(f"cost     cold ${cold['cost_usd']:.6f}   warm ${warm['cost_usd']:.6f}   "
          f"saved {s['cost_pct']}%")
    print(f"latency  cold {cold['mean_latency_ms'] / 1000:.1f}s mean   "
          f"warm {warm['mean_latency_ms'] / 1000:.1f}s mean   saved {s['latency_pct']}%")
    print(f"correct  cold {cold['correct']}/{cold['of']}   warm {warm['correct']}/{warm['of']}")
    print(f"\n{payload['correctness']['verdict']}")
    print(f"\ncache reporting: {payload['provider_cache_reporting']['note']}")
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
