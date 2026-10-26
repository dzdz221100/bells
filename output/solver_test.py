"""Evidence run for backend/solver.py — constraints + before/after impact.

Builds a throwaway database (the real data/bells.db is never touched), fills it
with 40 guests landing at random staggered times across two days, solves the
shuttle schedule, asserts every constraint holds, and compares the result with
the naive baseline of one shuttle per booking.

Writes output/solver_results.json for the Impact section of the report.

    backend/.venv/bin/python output/solver_test.py
"""

from __future__ import annotations

import json
import random
import sqlite3
import statistics
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from solver import (  # noqa: E402
    BUFFER_MIN,
    COST_PER_TRANSFER_EUR,
    DEFAULT_CAPACITY,
    MAX_WAIT_MIN,
    MINUTES_PER_ROUND_TRIP,
    explain_run,
    guest_pickup,
    solve_shuttles,
)

SCHEMA = REPO_ROOT / "data" / "schema.sql"
RESULTS = Path(__file__).resolve().parent / "solver_results.json"

RNG_SEED = 409              # fixed so the report's numbers are reproducible
N_GUESTS = 40
CAPACITY = DEFAULT_CAPACITY
WEDDING_ID = 1

# Cost assumptions live in solver.py so the dashboard and this script agree.
LANGUAGES = ["en", "fr", "es", "it", "de"]
CARRIERS = ["AZ", "AF", "LH", "IB", "U2"]
DAYS = ["2027-06-10", "2027-06-11"]


def build_db(path: Path) -> list[dict]:
    """Create a scratch database with N_GUESTS randomly staggered arrivals."""
    rng = random.Random(RNG_SEED)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO weddings (id, couple_names, date, city, country, timezone, currency)"
        " VALUES (?, 'Test Couple', '2027-06-12', 'Ravello', 'Italy', 'Europe/Rome', 'EUR')",
        (WEDDING_ID,),
    )

    guests = []
    for i in range(1, N_GUESTS + 1):
        day = rng.choice(DAYS)
        # staggered across the day: 07:00–23:00, to the nearest 5 minutes
        minute_of_day = rng.randint(7 * 60, 23 * 60) // 5 * 5
        at = datetime.fromisoformat(day) + timedelta(minutes=minute_of_day)
        party = rng.choices([1, 2, 3, 4], weights=[35, 45, 15, 5])[0]
        guests.append({
            "id": i,
            "name": f"Guest {i:02d}",
            "language": rng.choice(LANGUAGES),
            "party_size": party,
            "arrival_flight": f"{rng.choice(CARRIERS)} {rng.randint(1000, 2999)}",
            "arrival_at": at.strftime("%Y-%m-%dT%H:%M"),
        })

    conn.executemany(
        "INSERT INTO guests (id, wedding_id, name, email, language, party_size,"
        " arrival_flight, arrival_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (g["id"], WEDDING_ID, g["name"], f"guest{g['id']:02d}@example.com",
             g["language"], g["party_size"], g["arrival_flight"], g["arrival_at"])
            for g in guests
        ],
    )
    conn.commit()
    conn.close()
    return guests


def naive_baseline(guests: list[dict]) -> dict:
    """One shuttle per booking, each leaving BUFFER_MIN after that guest lands."""
    seats = sum(g["party_size"] for g in guests)
    return {
        "label": "naive: one shuttle per booking",
        "runs": len(guests),
        "seats_moved": seats,
        "total_wait_person_minutes": BUFFER_MIN * seats,
        "max_wait_minutes": BUFFER_MIN,
        "mean_wait_minutes": float(BUFFER_MIN),
        "mean_seats_per_run": round(seats / len(guests), 2),
        "driver_hours": round(len(guests) * MINUTES_PER_ROUND_TRIP / 60, 1),
        "transfer_cost_eur": round(len(guests) * COST_PER_TRANSFER_EUR, 2),
    }


def summarise(result: dict) -> dict:
    waits = [a["wait_minutes"] for a in result["assignments"]]
    runs = result["runs"]
    return {
        "label": "solved: clustered runs",
        "runs": len(runs),
        "seats_moved": result["seats_scheduled"],
        "total_wait_person_minutes": result["total_wait_minutes"],
        "max_wait_minutes": max(waits) if waits else 0,
        "mean_wait_minutes": round(statistics.mean(waits), 1) if waits else 0.0,
        "mean_seats_per_run": round(result["seats_scheduled"] / len(runs), 2) if runs else 0.0,
        "driver_hours": round(len(runs) * MINUTES_PER_ROUND_TRIP / 60, 1),
        "transfer_cost_eur": round(len(runs) * COST_PER_TRANSFER_EUR, 2),
    }


def check_constraints(result: dict, guests: list[dict], db_path: Path) -> list[str]:
    """Assert every constraint. Returns the list of checks that passed."""
    passed: list[str] = []
    runs = result["runs"]
    assignments = result["assignments"]
    by_id = {g["id"]: g for g in guests}

    assert not result["unassigned"], f"guests left unassigned: {result['unassigned']}"
    passed.append("every guest is on a run (none unassigned)")

    assigned_ids = [a["guest_id"] for a in assignments]
    assert len(assigned_ids) == len(set(assigned_ids)), "a guest was placed on two runs"
    assert set(assigned_ids) == set(by_id), "assignment set does not match the guest list"
    passed.append(f"all {len(by_id)} guests assigned exactly once")

    for a in assignments:
        assert BUFFER_MIN <= a["wait_minutes"], (
            f"guest {a['guest_id']} leaves {a['wait_minutes']} min after landing, "
            f"less than the {BUFFER_MIN} min buffer"
        )
    passed.append(f"no run departs sooner than {BUFFER_MIN} min after a passenger lands")

    for a in assignments:
        assert a["wait_minutes"] <= MAX_WAIT_MIN, (
            f"guest {a['guest_id']} waits {a['wait_minutes']} min, over the "
            f"{MAX_WAIT_MIN} min limit"
        )
    passed.append(f"no guest waits more than {MAX_WAIT_MIN} min")

    for r in runs:
        assert r["seats_taken"] <= r["capacity"], (
            f"run {r['id']} carries {r['seats_taken']} of {r['capacity']} seats"
        )
    passed.append(f"no run exceeds {CAPACITY} seats")

    for r in runs:
        depart = datetime.fromisoformat(r["depart_at"])
        last = datetime.fromisoformat(r["last_landing"])
        assert depart == last + timedelta(minutes=BUFFER_MIN), (
            f"run {r['id']} does not leave exactly {BUFFER_MIN} min after its last landing"
        )
    passed.append("every run leaves as early as the buffer allows (wait is minimal for its group)")

    seats_total = sum(g["party_size"] for g in guests)
    lower_bound = -(-seats_total // CAPACITY)  # ceil
    assert len(runs) >= lower_bound, "fewer runs than the capacity lower bound — impossible"
    passed.append(f"run count {len(runs)} respects the capacity lower bound of {lower_bound}")

    assert len(runs) < len(guests), "solver did no better than one shuttle per guest"
    passed.append(f"run count {len(runs)} beats the naive baseline of {len(guests)}")

    # the schedule was actually persisted
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db_runs = conn.execute(
        "SELECT id, seats_taken FROM shuttle_runs WHERE direction = 'arrival'"
    ).fetchall()
    orphans = conn.execute(
        "SELECT COUNT(*) FROM guests WHERE arrival_at IS NOT NULL AND shuttle_run_id IS NULL"
    ).fetchone()[0]
    for r in db_runs:
        counted = conn.execute(
            "SELECT COALESCE(SUM(party_size), 0) FROM guests WHERE shuttle_run_id = ?",
            (r["id"],),
        ).fetchone()[0]
        assert counted == r["seats_taken"], f"run {r['id']} seats_taken is stale"
    conn.close()
    assert len(db_runs) == len(runs), "database run count differs from the returned schedule"
    assert orphans == 0, f"{orphans} guests with an arrival time have no shuttle_run_id"
    passed.append("schedule persisted: shuttle_runs, seats_taken and guests.shuttle_run_id all agree")

    return passed


def optimality_benchmark(trials: int = 200) -> dict:
    """How often does the solver hit the true optimum?

    Brute-forces every possible grouping on small, deliberately tight instances
    (3–6 seats, parties of 1–3) and compares. Real runs have 14 seats, where the
    packing is far looser than this, so treat the match rate as a lower bound.
    """
    from solver import Arrival, Run, _dp_contiguous, _polish_wait, _try_eliminate_runs

    def partitions(items):
        if not items:
            yield []
            return
        first, rest = items[0], items[1:]
        for p in partitions(rest):
            for i in range(len(p)):
                yield p[:i] + [[first] + p[i]] + p[i + 1:]
            yield [[first]] + p

    def brute(arrs, cap):
        best = None
        for p in partitions(list(arrs)):
            runs = [Run(members=g) for g in p]
            if not all(r.feasible(cap) for r in runs):
                continue
            cost = (len(runs), sum(r.wait_person_minutes() for r in runs))
            if best is None or cost < best:
                best = cost
        return best

    rng = random.Random(RNG_SEED)
    matched = run_count_misses = 0
    for _ in range(trials):
        n = rng.randint(2, 7)
        cap = rng.choice([3, 4, 6])
        base = datetime.fromisoformat(DAYS[0]) + timedelta(hours=8)
        arrs = [
            Arrival(i + 1, f"G{i}", base + timedelta(minutes=rng.randrange(0, 180, 5)),
                    rng.randint(1, min(3, cap)), None)
            for i in range(n)
        ]
        arrs.sort(key=lambda a: (a.at, a.guest_id))
        runs = _dp_contiguous(arrs, cap)
        repaired = _try_eliminate_runs(runs, cap)
        if len(repaired) < len(runs):
            runs = repaired
        runs = _polish_wait(runs, cap)
        mine = (len(runs), sum(r.wait_person_minutes() for r in runs))
        opt = brute(arrs, cap)
        if mine == opt:
            matched += 1
        elif mine[0] != opt[0]:
            run_count_misses += 1

    return {
        "trials": trials,
        "matched_brute_force_optimum": matched,
        "match_rate_pct": round(100 * matched / trials, 1),
        "run_count_misses": run_count_misses,
        "note": "Tight small instances (capacity 3–6). Grouping under a capacity "
                "limit is bin-packing, which is NP-hard, so the solver is exact "
                "over contiguous groupings plus a repair pass — not provably "
                "optimal in general.",
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "solver_test.db"
        guests = build_db(db_path)

        result = solve_shuttles(WEDDING_ID, db_path=db_path, capacity=CAPACITY)
        passed = check_constraints(result, guests, db_path)

        before = naive_baseline(guests)
        after = summarise(result)

        samples = [explain_run(r["id"], db_path=db_path) for r in result["runs"][:3]]
        pickup = guest_pickup(result["assignments"][0]["guest_id"], db_path=db_path)

    saved_runs = before["runs"] - after["runs"]
    impact = {
        "runs_saved": saved_runs,
        "runs_saved_pct": round(100 * saved_runs / before["runs"], 1),
        "driver_hours_saved": round(before["driver_hours"] - after["driver_hours"], 1),
        "transfer_cost_saved_eur": round(
            before["transfer_cost_eur"] - after["transfer_cost_eur"], 2),
        "extra_wait_person_minutes": after["total_wait_person_minutes"]
        - before["total_wait_person_minutes"],
        "extra_wait_per_person_minutes": round(
            (after["total_wait_person_minutes"] - before["total_wait_person_minutes"])
            / after["seats_moved"], 1),
        "worst_wait_minutes": after["max_wait_minutes"],
        "wait_limit_minutes": MAX_WAIT_MIN,
    }

    # ---------------- printed report ----------------
    print("=" * 74)
    print(f"  solver_test — {N_GUESTS} guests, {before['seats_moved']} seats, "
          f"random staggered arrivals (seed {RNG_SEED})")
    print("=" * 74)

    print("\nConstraint checks")
    for line in passed:
        print(f"  PASS  {line}")

    print(f"\nSolved in {result['solved_in_ms']} ms (plain Python, no LLM call)")

    rows = [
        ("shuttle runs",            before["runs"],                      after["runs"]),
        ("mean seats per run",      before["mean_seats_per_run"],        after["mean_seats_per_run"]),
        ("total wait (person-min)", before["total_wait_person_minutes"], after["total_wait_person_minutes"]),
        ("mean wait (min)",         before["mean_wait_minutes"],         after["mean_wait_minutes"]),
        ("worst wait (min)",        before["max_wait_minutes"],          after["max_wait_minutes"]),
        ("driver hours",            before["driver_hours"],              after["driver_hours"]),
        ("transfer cost (EUR)",     before["transfer_cost_eur"],         after["transfer_cost_eur"]),
    ]
    print(f"\n{'':<24}{'naive (1/booking)':>20}{'solved':>14}{'change':>14}")
    print("-" * 74)
    for label, b, a in rows:
        if isinstance(b, (int, float)) and b:
            delta = f"{(a - b) / b * 100:+.0f}%"
        else:
            delta = "—"
        print(f"{label:<24}{b:>20}{a:>14}{delta:>14}")

    print(f"\nImpact: {impact['runs_saved']} fewer airport runs "
          f"({impact['runs_saved_pct']}%), {impact['driver_hours_saved']} driver-hours and "
          f"€{impact['transfer_cost_saved_eur']:.0f} saved.")
    print(f"Cost to guests: {impact['extra_wait_per_person_minutes']} extra minutes each "
          f"on average, worst case {impact['worst_wait_minutes']} min "
          f"(limit {MAX_WAIT_MIN}).")

    bench = optimality_benchmark()
    print(f"\nOptimality: matched the brute-force optimum on "
          f"{bench['matched_brute_force_optimum']}/{bench['trials']} tight small instances "
          f"({bench['match_rate_pct']}%), {bench['run_count_misses']} of the misses using "
          f"an extra run.")

    print("\nSample explain_run() output the agent can read aloud:")
    for s in samples:
        print(f"  • {s}")
    print("\nSample guest_pickup() output:")
    print(f"  • {pickup['text']}")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scenario": {
            "guests": N_GUESTS,
            "seats": before["seats_moved"],
            "days": DAYS,
            "rng_seed": RNG_SEED,
            "capacity": CAPACITY,
            "buffer_minutes": BUFFER_MIN,
            "max_wait_minutes": MAX_WAIT_MIN,
        },
        "assumptions": {
            "cost_per_transfer_eur": COST_PER_TRANSFER_EUR,
            "minutes_per_round_trip": MINUTES_PER_ROUND_TRIP,
            "note": "Baseline assumes each booking takes its own transfer, leaving "
                    f"{BUFFER_MIN} min after that guest lands.",
        },
        "solved_in_ms": result["solved_in_ms"],
        "constraints_passed": passed,
        "optimality_benchmark": bench,
        "before": before,
        "after": after,
        "impact": impact,
        "runs": result["runs"],
        "assignments": result["assignments"],
        "sample_explanations": samples,
        "sample_guest_pickup": pickup["text"],
    }
    RESULTS.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
