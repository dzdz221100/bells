"""Airport shuttle solver — plain deterministic Python, no LLM involved.

The agent calls this as a tool; it never reasons about the schedule itself.
Given every guest who has told us an arrival time, group them into as few
shuttle runs as possible without making anyone wait too long.

Guests who have declined their invitation are not passengers: they are
excluded everywhere here, so declining frees the seat they were holding.

Constraints
-----------
1. A run departs no earlier than ``BUFFER_MIN`` (30) minutes after the LAST
   guest on it lands — bags, passport queue, finding the driver.
2. No guest waits more than ``MAX_WAIT_MIN`` (90) minutes from their own
   landing to their run's departure.
3. A run carries at most ``capacity`` seats (default 14). A booking's
   ``party_size`` counts as that many seats.

Because a run leaves exactly ``BUFFER_MIN`` after its last arrival, (1) and (2)
together mean the landings on a single run span at most 60 minutes.

Objective: minimise the number of runs first, then total guest wait time
(counted per person, i.e. weighted by party_size).

Method
------
Guests are sorted by landing time and a dynamic program finds the exactly
optimal split into *contiguous* groups: ``dp[i]`` = best (runs, wait) for the
first i guests, with transitions from every feasible group ending at i. That is
O(n^2) and exact over contiguous groupings.

With varying party sizes a *non-contiguous* grouping can occasionally do better
(it is bin-packing underneath, which is NP-hard), so a cheap repair pass then
tries to empty the smallest run into the others. The result is optimal or
near-optimal, and always feasible — every constraint is re-checked before the
schedule is written.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from db import connect  # noqa: F401  (re-exported: callers use solver.connect)

BUFFER_MIN = 30        # earliest a run may leave after its last guest lands
MAX_WAIT_MIN = 90      # longest any one guest may wait at the airport
MAX_SPAN_MIN = MAX_WAIT_MIN - BUFFER_MIN   # 60: landing spread within one run
DEFAULT_CAPACITY = 14

DEFAULT_FROM = "Naples International Airport (NAP)"
DEFAULT_TO = "Ravello town square (hotel drop-offs)"

# Assumptions behind the host console's savings figures. Stated here so the
# report and the dashboard cite the same two numbers.
COST_PER_TRANSFER_EUR = 140.0  # quoted private transfer, Naples airport -> Ravello
MINUTES_PER_ROUND_TRIP = 200   # 1h40 each way, airport <-> Ravello

TS_FMT = "%Y-%m-%dT%H:%M"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _fmt(dt: datetime) -> str:
    return dt.strftime(TS_FMT)


def _clock(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _day(dt: datetime) -> str:
    return f"{dt.strftime('%A')} {dt.day} {dt.strftime('%B')}"


@dataclass
class Arrival:
    guest_id: int
    name: str
    at: datetime
    seats: int
    flight: str | None


@dataclass
class Run:
    members: list[Arrival] = field(default_factory=list)

    @property
    def last_landing(self) -> datetime:
        return max(a.at for a in self.members)

    @property
    def first_landing(self) -> datetime:
        return min(a.at for a in self.members)

    @property
    def depart_at(self) -> datetime:
        """Leave as early as the buffer allows — that minimises everyone's wait."""
        return self.last_landing + timedelta(minutes=BUFFER_MIN)

    @property
    def seats(self) -> int:
        return sum(a.seats for a in self.members)

    def wait_person_minutes(self) -> int:
        depart = self.depart_at
        return sum(a.seats * int((depart - a.at).total_seconds() // 60) for a in self.members)

    def feasible(self, capacity: int) -> bool:
        if not self.members:
            return False
        if self.seats > capacity:
            return False
        depart = self.depart_at
        return all(
            BUFFER_MIN <= (depart - a.at).total_seconds() / 60 <= MAX_WAIT_MIN
            for a in self.members
        )


# --------------------------------------------------------------------------
# the optimiser
# --------------------------------------------------------------------------

def _group_wait(group: list[Arrival]) -> int:
    last = max(a.at for a in group)
    depart = last + timedelta(minutes=BUFFER_MIN)
    return sum(a.seats * int((depart - a.at).total_seconds() // 60) for a in group)


def _dp_contiguous(arrivals: list[Arrival], capacity: int) -> list[Run]:
    """Exactly optimal split into contiguous-in-time groups.

    Cost is the lexicographic pair (number of runs, total person-minutes waited).
    """
    n = len(arrivals)
    INF = (float("inf"), float("inf"))
    best: list[tuple] = [(0, 0)] + [INF] * n
    cut: list[int] = [0] * (n + 1)

    for i in range(1, n + 1):
        seats = 0
        for j in range(i - 1, -1, -1):
            seats += arrivals[j].seats
            if seats > capacity:
                break  # only gets worse as the group grows leftwards
            span = (arrivals[i - 1].at - arrivals[j].at).total_seconds() / 60
            if span > MAX_SPAN_MIN:
                break  # ditto: arrivals are sorted
            prev = best[j]
            if prev[0] == float("inf"):
                continue
            cand = (prev[0] + 1, prev[1] + _group_wait(arrivals[j:i]))
            if cand < best[i]:
                best[i] = cand
                cut[i] = j

    if best[n][0] == float("inf"):  # pragma: no cover - guarded by caller
        raise ValueError("no feasible schedule; a booking must exceed capacity")

    runs: list[Run] = []
    i = n
    while i > 0:
        j = cut[i]
        runs.append(Run(members=list(arrivals[j:i])))
        i = j
    runs.reverse()
    return runs


# (guest order, target order) heuristics tried when re-homing a run.
_GUEST_ORDERS = {
    "seats_desc": lambda ms: sorted(ms, key=lambda a: (-a.seats, a.at, a.guest_id)),
    "seats_asc": lambda ms: sorted(ms, key=lambda a: (a.seats, a.at, a.guest_id)),
    "time_asc": lambda ms: sorted(ms, key=lambda a: (a.at, a.guest_id)),
}


def _target_order(trial: list[Run], guest: Arrival, mode: str) -> list[Run]:
    if mode == "best_fit":      # leave the roomy runs roomy
        return sorted(trial, key=lambda r: -r.seats)
    if mode == "worst_fit":     # spread the load
        return sorted(trial, key=lambda r: r.seats)
    # nearest in time — least extra waiting
    return sorted(trial, key=lambda r: abs((r.last_landing - guest.at).total_seconds()))


def _try_eliminate_runs(runs: list[Run], capacity: int) -> list[Run]:
    """Repair pass: can a whole run be emptied into the others?

    Contiguous grouping is exactly optimal only when every booking is the same
    size; with mixed party sizes this is bin-packing underneath, so a run can
    sometimes be dissolved into the gaps left in its neighbours. Several
    placement heuristics are tried in a fixed order (so the result stays
    deterministic) and a move is accepted only when it removes a run.
    """
    runs = [Run(members=list(r.members)) for r in runs]
    improved = True
    while improved and len(runs) > 1:
        improved = False
        for victim in sorted(runs, key=lambda r: (r.seats, len(r.members), r.first_landing)):
            others = [r for r in runs if r is not victim]
            for guest_order in _GUEST_ORDERS.values():
                for target_mode in ("best_fit", "worst_fit", "nearest"):
                    trial = [Run(members=list(r.members)) for r in others]
                    placed_all = True
                    for guest in guest_order(victim.members):
                        for target in _target_order(trial, guest, target_mode):
                            if Run(members=target.members + [guest]).feasible(capacity):
                                target.members.append(guest)
                                break
                        else:
                            placed_all = False
                            break
                    if placed_all:
                        runs = trial
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return runs


def _polish_wait(runs: list[Run], capacity: int) -> list[Run]:
    """Move single guests between existing runs while total wait strictly drops.

    Never changes the number of runs (a run is never emptied here).
    """
    runs = [Run(members=list(r.members)) for r in runs]
    improved = True
    while improved:
        improved = False
        for src in runs:
            if len(src.members) <= 1:
                continue  # emptying a run is the repair pass's job, not ours
            for guest in list(src.members):
                base = sum(r.wait_person_minutes() for r in runs)
                for dst in runs:
                    if dst is src:
                        continue
                    new_src = Run(members=[m for m in src.members if m is not guest])
                    new_dst = Run(members=dst.members + [guest])
                    if not (new_src.feasible(capacity) and new_dst.feasible(capacity)):
                        continue
                    delta = (new_src.wait_person_minutes() + new_dst.wait_person_minutes()) - (
                        src.wait_person_minutes() + dst.wait_person_minutes()
                    )
                    if delta < 0:
                        src.members = new_src.members
                        dst.members = new_dst.members
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return runs


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def solve_shuttles(
    wedding_id: int,
    *,
    db_path: Path | str | None = None,
    capacity: int = DEFAULT_CAPACITY,
    commit: bool = True,
) -> dict:
    """Cluster arriving guests into shuttle runs and write the schedule.

    Replaces the wedding's existing *arrival* runs. Departure runs are left
    alone. Returns the schedule, the per-guest assignments, the total wait and
    how long the solve took.
    """
    started = time.perf_counter()
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name, arrival_at, party_size, arrival_flight FROM guests"
            " WHERE wedding_id = ? AND arrival_at IS NOT NULL AND arrival_at != ''"
            "   AND rsvp_status != 'declined'"
            " ORDER BY arrival_at, id",
            (wedding_id,),
        ).fetchall()

        locs = conn.execute(
            "SELECT from_loc, to_loc FROM shuttle_runs"
            " WHERE wedding_id = ? AND direction = 'arrival' LIMIT 1",
            (wedding_id,),
        ).fetchone()
        from_loc = locs["from_loc"] if locs else DEFAULT_FROM
        to_loc = locs["to_loc"] if locs else DEFAULT_TO

        arrivals: list[Arrival] = []
        unassigned: list[dict] = []
        for r in rows:
            seats = max(1, int(r["party_size"] or 1))
            if seats > capacity:
                unassigned.append({
                    "guest_id": r["id"],
                    "name": r["name"],
                    "arrival_at": r["arrival_at"],
                    "reason": f"party of {seats} exceeds the {capacity}-seat shuttle capacity",
                })
                continue
            arrivals.append(Arrival(r["id"], r["name"], _parse(r["arrival_at"]), seats,
                                    r["arrival_flight"]))

        runs: list[Run] = []
        if arrivals:
            arrivals.sort(key=lambda a: (a.at, a.guest_id))
            runs = _dp_contiguous(arrivals, capacity)
            repaired = _try_eliminate_runs(runs, capacity)
            if len(repaired) < len(runs):
                runs = repaired
            runs = _polish_wait(runs, capacity)
            runs.sort(key=lambda r: r.depart_at)

        # Every constraint is re-checked here, so an unsound optimiser can never
        # write a schedule that strands someone.
        for run in runs:
            if not run.feasible(capacity):
                raise AssertionError(f"infeasible run produced: {run.members}")

        run_payload: list[dict] = []
        assignments: list[dict] = []
        total_wait = 0
        total_wait_bookings = 0

        if commit:
            conn.execute(
                "UPDATE guests SET shuttle_run_id = NULL WHERE wedding_id = ?"
                " AND shuttle_run_id IN (SELECT id FROM shuttle_runs"
                "   WHERE wedding_id = ? AND direction = 'arrival')",
                (wedding_id, wedding_id),
            )
            conn.execute(
                "DELETE FROM shuttle_runs WHERE wedding_id = ? AND direction = 'arrival'",
                (wedding_id,),
            )

        for run in runs:
            depart = run.depart_at
            run_id: int | None = None
            if commit:
                cur = conn.execute(
                    "INSERT INTO shuttle_runs (wedding_id, direction, depart_at,"
                    " from_loc, to_loc, capacity, seats_taken)"
                    " VALUES (?, 'arrival', ?, ?, ?, ?, ?)",
                    (wedding_id, _fmt(depart), from_loc, to_loc, capacity, run.seats),
                )
                run_id = int(cur.lastrowid)
                conn.executemany(
                    "UPDATE guests SET shuttle_run_id = ? WHERE id = ?",
                    [(run_id, a.guest_id) for a in run.members],
                )

            members = sorted(run.members, key=lambda a: (a.at, a.guest_id))
            waits = []
            for a in members:
                wait = int((depart - a.at).total_seconds() // 60)
                waits.append(wait)
                total_wait += wait * a.seats
                total_wait_bookings += wait
                assignments.append({
                    "guest_id": a.guest_id,
                    "name": a.name,
                    "arrival_flight": a.flight,
                    "arrival_at": _fmt(a.at),
                    "party_size": a.seats,
                    "run_id": run_id,
                    "depart_at": _fmt(depart),
                    "wait_minutes": wait,
                })

            run_payload.append({
                "id": run_id,
                "direction": "arrival",
                "depart_at": _fmt(depart),
                "from_loc": from_loc,
                "to_loc": to_loc,
                "capacity": capacity,
                "seats_taken": run.seats,
                "guest_ids": [a.guest_id for a in members],
                "first_landing": _fmt(run.first_landing),
                "last_landing": _fmt(run.last_landing),
                "max_wait_minutes": max(waits) if waits else 0,
            })

        if commit:
            conn.commit()
    finally:
        conn.close()

    return {
        "wedding_id": wedding_id,
        "capacity": capacity,
        "runs": run_payload,
        "assignments": assignments,
        "total_wait_minutes": total_wait,                 # person-minutes
        "total_wait_minutes_per_booking": total_wait_bookings,
        "guests_scheduled": len(assignments),
        "seats_scheduled": sum(r["seats_taken"] for r in run_payload),
        "unassigned": unassigned,
        "solved_in_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def schedule_report(
    wedding_id: int,
    *,
    db_path: Path | str | None = None,
    capacity: int = DEFAULT_CAPACITY,
) -> dict:
    """Read the committed arrival schedule back out, with the naive baseline.

    Read-only — it never re-solves. The host console calls this to draw the
    timeline and the before/after comparison.
    """
    conn = connect(db_path)
    try:
        runs = conn.execute(
            "SELECT * FROM shuttle_runs WHERE wedding_id = ? AND direction = 'arrival'"
            " ORDER BY depart_at",
            (wedding_id,),
        ).fetchall()
        members = conn.execute(
            "SELECT id, name, party_size, arrival_at, arrival_flight, shuttle_run_id"
            " FROM guests WHERE wedding_id = ? AND arrival_at IS NOT NULL"
            " AND arrival_at != '' AND rsvp_status != 'declined'"
            " ORDER BY arrival_at, id",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()

    by_run: dict[int, list] = {}
    for g in members:
        if g["shuttle_run_id"] is not None:
            by_run.setdefault(g["shuttle_run_id"], []).append(g)

    run_payload = []
    total_wait = 0
    all_waits: list[int] = []
    for r in runs:
        depart = _parse(r["depart_at"])
        people = by_run.get(r["id"], [])
        rows = []
        for g in people:
            landing = _parse(g["arrival_at"])
            wait = int((depart - landing).total_seconds() // 60)
            seats = max(1, int(g["party_size"] or 1))
            total_wait += wait * seats
            all_waits.extend([wait] * seats)
            rows.append({
                "guest_id": g["id"],
                "name": g["name"],
                "party_size": seats,
                "arrival_flight": g["arrival_flight"],
                "arrival_at": g["arrival_at"],
                "wait_minutes": wait,
            })
        run_payload.append({
            "id": r["id"],
            "depart_at": r["depart_at"],
            "from_loc": r["from_loc"],
            "to_loc": r["to_loc"],
            "capacity": r["capacity"],
            "seats_taken": r["seats_taken"],
            "members": rows,
            "max_wait_minutes": max((m["wait_minutes"] for m in rows), default=0),
            "first_landing": min((m["arrival_at"] for m in rows), default=None),
            "last_landing": max((m["arrival_at"] for m in rows), default=None),
        })

    bookings = len(members)
    seats = sum(max(1, int(g["party_size"] or 1)) for g in members)
    unscheduled = [g["name"] for g in members if g["shuttle_run_id"] is None]

    solved_runs = len(run_payload)
    baseline = {
        "label": "one transfer per booking",
        "runs": bookings,
        "total_wait_person_minutes": BUFFER_MIN * seats,
        "max_wait_minutes": BUFFER_MIN if bookings else 0,
        "driver_hours": round(bookings * MINUTES_PER_ROUND_TRIP / 60, 1),
        "transfer_cost_eur": round(bookings * COST_PER_TRANSFER_EUR, 2),
    }
    solved = {
        "label": "solved: clustered runs",
        "runs": solved_runs,
        "total_wait_person_minutes": total_wait,
        "max_wait_minutes": max(all_waits, default=0),
        "driver_hours": round(solved_runs * MINUTES_PER_ROUND_TRIP / 60, 1),
        "transfer_cost_eur": round(solved_runs * COST_PER_TRANSFER_EUR, 2),
    }

    return {
        "wedding_id": wedding_id,
        "capacity": capacity,
        "runs": run_payload,
        "bookings": bookings,
        "seats": seats,
        "unscheduled": unscheduled,
        "baseline": baseline,
        "solved": solved,
        "savings": {
            "runs": baseline["runs"] - solved["runs"],
            "runs_pct": round(100 * (baseline["runs"] - solved["runs"]) / baseline["runs"], 1)
            if baseline["runs"] else 0.0,
            "driver_hours": round(baseline["driver_hours"] - solved["driver_hours"], 1),
            "transfer_cost_eur": round(
                baseline["transfer_cost_eur"] - solved["transfer_cost_eur"], 2),
            "extra_wait_person_minutes": solved["total_wait_person_minutes"]
            - baseline["total_wait_person_minutes"],
        },
        "assumptions": {
            "cost_per_transfer_eur": COST_PER_TRANSFER_EUR,
            "minutes_per_round_trip": MINUTES_PER_ROUND_TRIP,
            "buffer_minutes": BUFFER_MIN,
            "max_wait_minutes": MAX_WAIT_MIN,
        },
    }


def explain_run(run_id: int, *, db_path: Path | str | None = None) -> str:
    """One short paragraph about a run, written to be read aloud."""
    conn = connect(db_path)
    try:
        run = conn.execute("SELECT * FROM shuttle_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return f"There is no shuttle run number {run_id}."
        members = conn.execute(
            "SELECT name, party_size, arrival_at, arrival_flight FROM guests"
            " WHERE shuttle_run_id = ? ORDER BY arrival_at, id",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    depart = _parse(run["depart_at"])
    direction = run["direction"]

    if not members:
        return (
            f"The {_clock(depart)} shuttle on {_day(depart)} leaves {run['from_loc']} "
            f"for {run['to_loc']}. Nobody is booked on it yet — "
            f"all {run['capacity']} seats are free."
        )

    names = [m["name"] for m in members]
    if len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} and {names[1]}"
    else:
        who = ", ".join(names[:-1]) + f" and {names[-1]}"

    seats = sum(int(m["party_size"] or 1) for m in members)
    free = int(run["capacity"]) - seats

    if direction == "departure":
        return (
            f"The {_clock(depart)} shuttle on {_day(depart)} leaves {run['from_loc']} "
            f"for {run['to_loc']}, carrying {seats} of {run['capacity']} seats: {who}. "
            f"{'No seats left' if free <= 0 else f'{free} seats still free'}."
        )

    last = max(_parse(m["arrival_at"]) for m in members)
    waits = [int((depart - _parse(m["arrival_at"])).total_seconds() // 60) for m in members]
    last_flight = next(
        (m["arrival_flight"] for m in members if _parse(m["arrival_at"]) == last), None
    )
    flight_bit = f" (flight {last_flight})" if last_flight else ""

    return (
        f"Shuttle {run_id} leaves {run['from_loc']} at {_clock(depart)} on {_day(depart)}, "
        f"half an hour after the last passenger on it lands at {_clock(last)}{flight_bit}. "
        f"It takes {who} to {run['to_loc']} — {seats} of {run['capacity']} seats, "
        f"{'full' if free <= 0 else f'{free} still free'}. "
        f"The longest anyone waits at the airport is {max(waits)} minutes."
    )


def guest_pickup(guest_id: int, *, db_path: Path | str | None = None) -> dict:
    """Where and when this guest gets picked up, and how long they will wait."""
    conn = connect(db_path)
    try:
        g = conn.execute(
            "SELECT id, name, arrival_at, arrival_flight, party_size, shuttle_run_id,"
            " rsvp_status FROM guests WHERE id = ?",
            (guest_id,),
        ).fetchone()
        if g is None:
            return {"found": False, "text": f"No guest with id {guest_id}."}
        run = None
        if g["shuttle_run_id"] is not None:
            run = conn.execute(
                "SELECT * FROM shuttle_runs WHERE id = ?", (g["shuttle_run_id"],)
            ).fetchone()
    finally:
        conn.close()

    if run is None:
        if g["rsvp_status"] == "declined":
            text = (
                f"{g['name']} has told the couple they cannot come, so no shuttle "
                "seat is held for them. If that changes, they can update their "
                "RSVP and a seat will be found on the next schedule."
            )
        elif g["arrival_at"]:
            text = f"{g['name']} is not on a shuttle yet."
        else:
            text = (
                f"{g['name']} has not told us an arrival time yet, so there is no "
                "shuttle booked."
            )
        return {
            "found": True,
            "guest_id": g["id"],
            "name": g["name"],
            "arrival_at": g["arrival_at"],
            "run": None,
            "text": text,
        }

    depart = _parse(run["depart_at"])
    landing = _parse(g["arrival_at"]) if g["arrival_at"] else None
    wait = int((depart - landing).total_seconds() // 60) if landing else None
    be_there_by = depart - timedelta(minutes=10)

    if wait is None:
        text = (
            f"{g['name']}, your shuttle leaves {run['from_loc']} at {_clock(depart)} "
            f"on {_day(depart)}."
        )
    else:
        flight_bit = f" on flight {g['arrival_flight']}" if g["arrival_flight"] else ""
        text = (
            f"{g['name']}, you land at {_clock(landing)} on {_day(landing)}{flight_bit}. "
            f"Your shuttle leaves {run['from_loc']} at {_clock(depart)} — that is "
            f"{wait} minutes after you touch down, which is time for passport control "
            f"and bags. Please be at the pickup point by {_clock(be_there_by)}. "
            f"It drops you at {run['to_loc']}."
        )

    return {
        "found": True,
        "guest_id": g["id"],
        "name": g["name"],
        "party_size": g["party_size"],
        "arrival_flight": g["arrival_flight"],
        "arrival_at": g["arrival_at"],
        "run": {
            "id": run["id"],
            "direction": run["direction"],
            "depart_at": run["depart_at"],
            "from_loc": run["from_loc"],
            "to_loc": run["to_loc"],
            "capacity": run["capacity"],
            "seats_taken": run["seats_taken"],
        },
        "pickup_at": run["depart_at"],
        "minutes_after_landing": wait,
        "be_at_pickup_by": _fmt(be_there_by),
        "text": text,
    }


if __name__ == "__main__":
    import json

    result = solve_shuttles(1)
    print(json.dumps({k: v for k, v in result.items() if k != "assignments"},
                     indent=2, ensure_ascii=False))
    for r in result["runs"]:
        print("\n" + explain_run(r["id"]))
