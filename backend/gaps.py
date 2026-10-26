"""The gap query: everything about this wedding that is still unresolved.

Plain SQL and arithmetic, no model involved. The host console's REST routes
and the host concierge agent both read from here, so the couple get the same
numbers whether they look at the dashboard or ask for them in words.
"""

from __future__ import annotations

from typing import Any

from db import connect


def wedding_status(wedding_id: int, db_path: str | None = None) -> dict[str, Any]:
    """Headline counts: who is coming, who is housed, who is flying, what is open."""
    conn = connect(db_path)
    try:
        guests = conn.execute(
            "SELECT rsvp_status, party_size, dietary, plus_one_name, plus_one_dietary,"
            " plus_one_allowed, hotel_id, hotel_booked, arrival_at, shuttle_run_id, language"
            " FROM guests WHERE wedding_id = ?",
            (wedding_id,),
        ).fetchall()
        escalations = dict(conn.execute(
            "SELECT status, COUNT(*) FROM escalations WHERE wedding_id = ? GROUP BY status",
            (wedding_id,),
        ).fetchall())
        facts = conn.execute(
            "SELECT COUNT(*) FROM wedding_facts WHERE wedding_id = ?", (wedding_id,)
        ).fetchone()[0]
        registry = conn.execute(
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN claimed_by_guest_id IS NULL THEN 1 ELSE 0 END) AS available"
            " FROM registry WHERE wedding_id = ?",
            (wedding_id,),
        ).fetchone()
    finally:
        conn.close()

    attending = [g for g in guests if g["rsvp_status"] == "attending"]
    declined = [g for g in guests if g["rsvp_status"] == "declined"]
    pending = [g for g in guests if g["rsvp_status"] == "pending"]

    def seats(rows) -> int:
        return sum(int(r["party_size"] or 1) for r in rows)

    diets: dict[str, int] = {}
    for g in attending:
        for field in ("dietary", "plus_one_dietary"):
            need = (g[field] or "").strip()
            if need and (field == "dietary" or g["plus_one_name"]):
                diets[need] = diets.get(need, 0) + 1

    return {
        "invited": len(guests),
        "attending": len(attending),
        "declined": len(declined),
        "pending_rsvp": len(pending),
        "people_coming": seats(attending),
        "seats_still_unknown": seats(pending),
        "beds_booked": sum(1 for g in attending if g["hotel_booked"]),
        "beds_unbooked": sum(1 for g in attending if not g["hotel_booked"]),
        "flights_known": sum(1 for g in attending if g["arrival_at"]),
        "flights_missing": sum(1 for g in attending if not g["arrival_at"]),
        "on_a_shuttle": sum(1 for g in attending if g["shuttle_run_id"]),
        "awaiting_a_seat": sum(
            1 for g in attending if g["arrival_at"] and not g["shuttle_run_id"]
        ),
        "plus_ones_named": sum(1 for g in attending if g["plus_one_name"]),
        "plus_ones_unnamed": sum(
            1 for g in attending if g["plus_one_allowed"] and not g["plus_one_name"]
        ),
        "dietary": sorted(
            ({"need": k, "people": v} for k, v in diets.items()),
            key=lambda d: (-d["people"], d["need"]),
        ),
        "dietary_people": sum(diets.values()),
        "escalations_open": escalations.get("open", 0),
        "escalations_answered": escalations.get("answered", 0),
        "facts_recorded": facts,
        "registry_total": registry["total"],
        "registry_available": registry["available"] or 0,
        "languages": sorted({g["language"] for g in guests}),
    }


def find_gaps(wedding_id: int, db_path: str | None = None) -> dict[str, Any]:
    """Every outstanding thing, with the names attached.

    The couple can act on a name; they cannot act on a count. So each gap
    carries who it is about, newest deadline first.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT g.id, g.name, g.email, g.language, g.rsvp_status, g.party_size,"
            " g.plus_one_allowed, g.plus_one_name, g.hotel_booked, g.arrival_at,"
            " g.arrival_flight, g.shuttle_run_id, h.name AS hotel_name, h.book_by_date"
            " FROM guests g LEFT JOIN hotels h ON h.id = g.hotel_id"
            " WHERE g.wedding_id = ? ORDER BY g.name",
            (wedding_id,),
        ).fetchall()
        open_esc = conn.execute(
            "SELECT e.id, e.question, e.created_at, g.name AS guest_name"
            " FROM escalations e LEFT JOIN guests g ON g.id = e.guest_id"
            " WHERE e.wedding_id = ? AND e.status = 'open' ORDER BY e.created_at",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()

    def who(r) -> dict[str, Any]:
        return {"guest_id": r["id"], "name": r["name"], "language": r["language"]}

    attending = [r for r in rows if r["rsvp_status"] == "attending"]

    return {
        "not_rsvpd": [who(r) for r in rows if r["rsvp_status"] == "pending"],
        "unbooked_hotel": [
            {**who(r), "hotel": r["hotel_name"], "book_by": r["book_by_date"]}
            for r in attending if not r["hotel_booked"]
        ],
        "no_flight": [who(r) for r in attending if not r["arrival_at"]],
        "awaiting_shuttle_seat": [
            {**who(r), "flight": r["arrival_flight"], "lands": r["arrival_at"]}
            for r in attending if r["arrival_at"] and not r["shuttle_run_id"]
        ],
        "plus_one_unnamed": [
            who(r) for r in attending if r["plus_one_allowed"] and not r["plus_one_name"]
        ],
        "open_escalations": [
            {"id": e["id"], "from": e["guest_name"], "question": e["question"],
             "asked": e["created_at"]}
            for e in open_esc
        ],
    }


# the named segments draft_blast understands without having to think
SEGMENTS = {
    "all": "every guest",
    "attending": "guests who have said yes",
    "not_rsvpd": "guests who have not answered their invitation",
    "declined": "guests who said they cannot come",
    "no_flight": "attending guests who have not sent a flight",
    "unbooked_hotel": "attending guests who have not booked a room",
}


def segment_guests(
    segment: str, wedding_id: int, db_path: str | None = None, limit: int = 12
) -> list[dict[str, Any]]:
    """Resolve a named segment to real guests, with the facts a message needs."""
    where = {
        "all": "1 = 1",
        "attending": "g.rsvp_status = 'attending'",
        "not_rsvpd": "g.rsvp_status = 'pending'",
        "declined": "g.rsvp_status = 'declined'",
        "no_flight": "g.rsvp_status = 'attending' AND (g.arrival_at IS NULL OR g.arrival_at = '')",
        "unbooked_hotel": "g.rsvp_status = 'attending' AND g.hotel_booked = 0",
    }.get(segment)
    if where is None:
        raise ValueError(f"unknown segment {segment!r}")

    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT g.id, g.name, g.email, g.language, g.rsvp_status, g.party_size,"
            " g.plus_one_name, g.hotel_booked, g.arrival_flight, g.arrival_at,"
            " h.name AS hotel_name, h.block_code, h.book_by_date"
            f" FROM guests g LEFT JOIN hotels h ON h.id = g.hotel_id"
            f" WHERE g.wedding_id = ? AND {where} ORDER BY g.name LIMIT ?",
            (wedding_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def search_guests(query: str, wedding_id: int, db_path: str | None = None,
                  limit: int = 12) -> list[dict[str, Any]]:
    """Name or email search across the roster. Host only — never the guest agent."""
    like = f"%{query.strip()}%"
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT g.id, g.name, g.email, g.language, g.rsvp_status, g.party_size,"
            " g.dietary, g.plus_one_name, g.hotel_booked, g.arrival_flight,"
            " g.arrival_at, g.shuttle_run_id, h.name AS hotel_name"
            " FROM guests g LEFT JOIN hotels h ON h.id = g.hotel_id"
            " WHERE g.wedding_id = ? AND (g.name LIKE ? OR g.email LIKE ?)"
            " ORDER BY g.name LIMIT ?",
            (wedding_id, like, like, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
