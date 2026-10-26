"""Seating plan solver — plain deterministic Python, no LLM involved.

The agent calls this and explains the result; it never decides who sits where.

What it solves
--------------
Every attending guest, plus their named plus-one, gets a seat. The unit of
assignment is a *party*, never a person: a couple is one thing that moves
together and takes two seats.

Hard, never broken:
  * a party sits at one table;
  * two guests marked 'together' sit at the same table;
  * two guests marked 'apart' never do;
  * a table never holds more than its capacity.

Preferred, traded off:
  * a seating_group ("bride family", "work") lands on one table, or two —
    not sprinkled across six.

Method
------
1. Parties become units. Units joined by 'together' are merged into one block
   (union-find), which makes that constraint true by construction rather than
   by luck.
2. 'apart' pairs become edges between blocks. A pair that ends up inside the
   same block is a contradiction — reported, not silently dropped.
3. Blocks are placed largest-first into the table that costs least: a table
   already holding this group is cheap, an empty table is middling, a table
   holding three other groups is dear. Capacity and 'apart' are filters, not
   costs, so a cheap-but-illegal table is never chosen.
4. A local pass then moves single blocks between tables while the total cost
   strictly falls, which is what pulls a scattered group back together.

Nothing random: ties break on id, so the same input gives the same plan.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from db import connect


@dataclass
class Party:
    """One booking: a guest, plus their plus-one if they named one."""
    guest_id: int
    name: str
    seats: int
    group: str | None
    # one entry per seat: (name, dietary need or None)
    members: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class Block:
    """One or more parties that a 'together' constraint has welded into one."""
    key: int
    parties: list[Party]

    @property
    def seats(self) -> int:
        return sum(p.seats for p in self.parties)

    @property
    def guest_ids(self) -> set[int]:
        return {p.guest_id for p in self.parties}

    @property
    def groups(self) -> set[str]:
        return {p.group for p in self.parties if p.group}


class _Union:
    """Union-find over guest ids."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, x: int) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: int) -> int:
        self.add(x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # lower id wins, so the result does not depend on input order
            hi, lo = (ra, rb) if ra > rb else (rb, ra)
            self.parent[hi] = lo


def _load(wedding_id: int, db_path: str | None):
    conn = connect(db_path)
    try:
        guests = conn.execute(
            "SELECT id, name, party_size, dietary, plus_one_name, plus_one_dietary,"
            " seating_group, table_id FROM guests"
            " WHERE wedding_id = ? AND rsvp_status = 'attending' ORDER BY id",
            (wedding_id,),
        ).fetchall()
        tables = conn.execute(
            "SELECT id, name, capacity, shape FROM tables WHERE wedding_id = ? ORDER BY id",
            (wedding_id,),
        ).fetchall()
        cons = conn.execute(
            "SELECT id, guest_a, guest_b, kind, reason FROM seating_constraints"
            " WHERE wedding_id = ? ORDER BY id",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()
    return guests, tables, cons


def _parties(guests) -> list[Party]:
    out = []
    for g in guests:
        members = [(g["name"], (g["dietary"] or "").strip() or None)]
        if g["plus_one_name"]:
            members.append((g["plus_one_name"], (g["plus_one_dietary"] or "").strip() or None))
        seats = max(1, int(g["party_size"] or 1))
        # a party of two who never named their plus-one still needs the chair
        while len(members) < seats:
            members.append((f"guest of {g['name'].split()[0]}", None))
        out.append(Party(
            guest_id=g["id"], name=g["name"], seats=max(seats, len(members)),
            group=g["seating_group"], members=members,
        ))
    return out


def solve_seating(
    wedding_id: int,
    *,
    db_path: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Assign every attending party to a table. Returns the plan and any misses."""
    started = time.perf_counter()
    guests, tables, cons = _load(wedding_id, db_path)

    unsatisfied: list[dict[str, Any]] = []
    parties = _parties(guests)
    by_guest = {p.guest_id: p for p in parties}

    if not tables:
        return {
            "wedding_id": wedding_id, "tables": [], "unseated": [p.name for p in parties],
            "unsatisfied": [{"kind": "setup", "reason": "no tables defined"}],
            "solved_in_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    # ---- 1. weld 'together' pairs into blocks ----------------------------
    uf = _Union()
    for p in parties:
        uf.add(p.guest_id)
    for c in cons:
        if c["kind"] != "together":
            continue
        a, b = c["guest_a"], c["guest_b"]
        if a not in by_guest or b not in by_guest:
            unsatisfied.append({
                "kind": "together", "guest_a": a, "guest_b": b,
                "reason": c["reason"],
                "why": "one of them is not attending, so there is nothing to seat together",
            })
            continue
        uf.union(a, b)

    blocks: dict[int, Block] = {}
    for p in parties:
        root = uf.find(p.guest_id)
        blocks.setdefault(root, Block(key=root, parties=[])).parties.append(p)

    # ---- 2. 'apart' pairs become edges between blocks --------------------
    apart: dict[int, set[int]] = {}
    for c in cons:
        if c["kind"] != "apart":
            continue
        a, b = c["guest_a"], c["guest_b"]
        if a not in by_guest or b not in by_guest:
            continue  # one of them is not coming; nothing to keep apart
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            # a 'together' chain has already welded these two into one block
            unsatisfied.append({
                "kind": "apart", "guest_a": a, "guest_b": b, "reason": c["reason"],
                "why": (f"{by_guest[a].name} and {by_guest[b].name} are tied to the same "
                        "party or 'together' group, so they cannot be separated"),
            })
            continue
        apart.setdefault(ra, set()).add(rb)
        apart.setdefault(rb, set()).add(ra)

    # ---- 3. place blocks, largest first ----------------------------------
    cap = {t["id"]: t["capacity"] for t in tables}
    seated: dict[int, list[Block]] = {t["id"]: [] for t in tables}

    def used(tid: int) -> int:
        return sum(b.seats for b in seated[tid])

    def allowed(block: Block, tid: int) -> bool:
        if used(tid) + block.seats > cap[tid]:
            return False
        enemies = apart.get(block.key, set())
        return not any(other.key in enemies for other in seated[tid])

    def cost(block: Block, tid: int) -> tuple:
        """Lower is better. Group cohesion first, then a tidy fill."""
        here = {g for b in seated[tid] for g in b.groups}
        same_group = bool(block.groups & here)
        empty = not seated[tid]
        # prefer: a table already holding my group > an empty table > a mixed one
        rank = 0 if same_group else (1 if empty else 2 + len(here - block.groups))
        return (rank, -used(tid) if same_group else used(tid), tid)

    order = sorted(blocks.values(), key=lambda b: (-b.seats, sorted(b.groups), b.key))
    unseated: list[Block] = []
    for block in order:
        options = [t["id"] for t in tables if allowed(block, t["id"])]
        if not options:
            unseated.append(block)
            continue
        seated[min(options, key=lambda tid: cost(block, tid))].append(block)

    # ---- 4. local pass: pull scattered groups back together --------------
    def scatter() -> int:
        """How many (group, table) pairs exist beyond one table per group."""
        spread: dict[str, set[int]] = {}
        for tid, blks in seated.items():
            for b in blks:
                for g in b.groups:
                    spread.setdefault(g, set()).add(tid)
        return sum(len(v) - 1 for v in spread.values())

    improved = True
    guard = 0
    while improved and guard < 200:
        improved, guard = False, guard + 1
        best = scatter()
        for tid in sorted(seated):
            for block in sorted(seated[tid], key=lambda b: b.key):
                for other in sorted(seated):
                    if other == tid:
                        continue
                    seated[tid].remove(block)
                    if allowed(block, other):
                        seated[other].append(block)
                        if scatter() < best:
                            improved = True
                            best = scatter()
                            break
                        seated[other].remove(block)
                    seated[tid].append(block)
                if improved:
                    break
            if improved:
                break

    for block in unseated:
        unsatisfied.append({
            "kind": "capacity",
            "reason": f"no table could take {', '.join(p.name for p in block.parties)}",
            "why": (f"the party needs {block.seats} seats together and every table is "
                    "either full or holds someone they must sit apart from"),
        })

    # ---- 5. shape the answer, and write it -------------------------------
    plan = []
    for t in tables:
        blks = sorted(seated[t["id"]], key=lambda b: (sorted(b.groups), b.key))
        people = []
        for b in blks:
            for p in b.parties:
                for i, (member, diet) in enumerate(p.members):
                    people.append({
                        "guest_id": p.guest_id, "name": member,
                        "is_plus_one": i > 0, "group": p.group, "diet": diet,
                    })
        plan.append({
            "table_id": t["id"], "name": t["name"], "capacity": t["capacity"],
            "shape": t["shape"], "seats_used": sum(b.seats for b in blks),
            "groups": sorted({g for b in blks for g in b.groups}),
            "people": people,
        })

    if commit:
        conn = connect(db_path)
        try:
            conn.execute("UPDATE guests SET table_id = NULL WHERE wedding_id = ?", (wedding_id,))
            conn.executemany(
                "UPDATE guests SET table_id = ? WHERE id = ?",
                [(t["table_id"], p["guest_id"]) for t in plan for p in t["people"]
                 if not p["is_plus_one"]],
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "wedding_id": wedding_id,
        "tables": plan,
        "seated_people": sum(len(t["people"]) for t in plan),
        "seated_parties": sum(1 for t in plan for p in t["people"] if not p["is_plus_one"]),
        "total_capacity": sum(t["capacity"] for t in tables),
        "unseated": [p.name for b in unseated for p in b.parties],
        "unsatisfied": unsatisfied,
        "group_scatter": scatter(),
        "solved_in_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def seating_plan(wedding_id: int, *, db_path: str | None = None) -> dict[str, Any]:
    """Read the committed plan back out, without re-solving."""
    conn = connect(db_path)
    try:
        tables = conn.execute(
            "SELECT id, name, capacity, shape FROM tables WHERE wedding_id = ? ORDER BY id",
            (wedding_id,),
        ).fetchall()
        guests = conn.execute(
            "SELECT id, name, party_size, dietary, plus_one_name, plus_one_dietary,"
            " seating_group, table_id FROM guests"
            " WHERE wedding_id = ? AND rsvp_status = 'attending' ORDER BY name",
            (wedding_id,),
        ).fetchall()
        cons = conn.execute(
            "SELECT c.id, c.guest_a, c.guest_b, c.kind, c.reason,"
            " a.name AS name_a, b.name AS name_b, a.table_id AS table_a, b.table_id AS table_b"
            " FROM seating_constraints c"
            " JOIN guests a ON a.id = c.guest_a JOIN guests b ON b.id = c.guest_b"
            " WHERE c.wedding_id = ? ORDER BY c.id",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()

    plan = []
    for t in tables:
        people = []
        for g in guests:
            if g["table_id"] != t["id"]:
                continue
            party = [{"guest_id": g["id"], "name": g["name"], "is_plus_one": False,
                      "group": g["seating_group"],
                      "diet": (g["dietary"] or "").strip() or None}]
            if g["plus_one_name"]:
                party.append({"guest_id": g["id"], "name": g["plus_one_name"],
                              "is_plus_one": True, "group": g["seating_group"],
                              "diet": (g["plus_one_dietary"] or "").strip() or None})
            while len(party) < max(1, int(g["party_size"] or 1)):
                party.append({"guest_id": g["id"],
                              "name": f"guest of {g['name'].split()[0]}",
                              "is_plus_one": True, "group": g["seating_group"], "diet": None})
            people.extend(party)
        plan.append({
            "table_id": t["id"], "name": t["name"], "capacity": t["capacity"],
            "shape": t["shape"], "seats_used": len(people),
            "groups": sorted({p["group"] for p in people if p["group"]}),
            "people": people,
        })

    # a hand-moved guest can break a rule the solver respected; say so loudly
    violations = []
    for c in cons:
        if c["table_a"] is None or c["table_b"] is None:
            continue
        same = c["table_a"] == c["table_b"]
        if c["kind"] == "together" and not same:
            violations.append({"kind": "together", "reason": c["reason"],
                               "who": f"{c['name_a']} and {c['name_b']}",
                               "why": "they are on different tables"})
        if c["kind"] == "apart" and same:
            violations.append({"kind": "apart", "reason": c["reason"],
                               "who": f"{c['name_a']} and {c['name_b']}",
                               "why": "they are on the same table"})

    over = [t for t in plan if t["seats_used"] > t["capacity"]]
    for t in over:
        violations.append({"kind": "capacity", "reason": f"{t['name']} is over capacity",
                           "who": t["name"],
                           "why": f"{t['seats_used']} people in {t['capacity']} seats"})

    unseated = [g["name"] for g in guests if g["table_id"] is None]
    diets: dict[str, int] = {}
    for t in plan:
        for p in t["people"]:
            if p["diet"]:
                diets[p["diet"]] = diets.get(p["diet"], 0) + 1

    return {
        "wedding_id": wedding_id,
        "tables": plan,
        "seated_people": sum(t["seats_used"] for t in plan),
        "total_capacity": sum(t["capacity"] for t in tables),
        "unseated": unseated,
        "violations": violations,
        "constraints": [
            {"id": c["id"], "kind": c["kind"], "reason": c["reason"],
             "a": c["name_a"], "b": c["name_b"],
             "satisfied": (c["table_a"] == c["table_b"]) == (c["kind"] == "together")
                          if c["table_a"] and c["table_b"] else None}
            for c in cons
        ],
        "dietary": sorted(({"need": k, "people": v} for k, v in diets.items()),
                          key=lambda d: (-d["people"], d["need"])),
    }


def move_guest(guest_id: int, table_id: int | None, wedding_id: int,
               *, db_path: str | None = None) -> dict[str, Any]:
    """Drag-and-drop: put one party on a table. Reports what it breaks.

    A human override is allowed to break a rule — they may know something the
    constraints do not — but it is never silent.
    """
    conn = connect(db_path)
    try:
        g = conn.execute(
            "SELECT id, name, party_size FROM guests WHERE id = ? AND wedding_id = ?",
            (guest_id, wedding_id),
        ).fetchone()
        if g is None:
            raise ValueError(f"no guest {guest_id}")
        if table_id is not None:
            t = conn.execute(
                "SELECT id, name, capacity FROM tables WHERE id = ? AND wedding_id = ?",
                (table_id, wedding_id),
            ).fetchone()
            if t is None:
                raise ValueError(f"no table {table_id}")
        conn.execute("UPDATE guests SET table_id = ? WHERE id = ?", (table_id, guest_id))
        conn.commit()
    finally:
        conn.close()

    after = seating_plan(wedding_id, db_path=db_path)
    return {
        "ok": True,
        "moved": g["name"],
        "table_id": table_id,
        "violations": after["violations"],
        "plan": after,
    }


def table_for_guest(guest_id: int, wedding_id: int,
                    *, db_path: str | None = None) -> dict[str, Any] | None:
    """One guest's table and who else is on it. Nothing about anyone's table but theirs."""
    conn = connect(db_path)
    try:
        g = conn.execute(
            "SELECT id, name, table_id, plus_one_name FROM guests WHERE id = ? AND wedding_id = ?",
            (guest_id, wedding_id),
        ).fetchone()
        if g is None or g["table_id"] is None:
            return None
        t = conn.execute("SELECT id, name, capacity, shape FROM tables WHERE id = ?",
                         (g["table_id"],)).fetchone()
        mates = conn.execute(
            "SELECT name, plus_one_name, party_size FROM guests"
            " WHERE table_id = ? AND rsvp_status = 'attending' ORDER BY name",
            (g["table_id"],),
        ).fetchall()
    finally:
        conn.close()

    names: list[str] = []
    for m in mates:
        party = [m["name"]]
        if m["plus_one_name"]:
            party.append(m["plus_one_name"])
        while len(party) < max(1, int(m["party_size"] or 1)):
            party.append(f"guest of {m['name'].split()[0]}")
        names.extend(party)

    return {
        "guest": g["name"],
        "table": {"id": t["id"], "name": t["name"], "shape": t["shape"]},
        # names only: no diets, no groups, nothing about anyone's travel
        "seated_with": [n for n in names if n != g["name"]],
    }
