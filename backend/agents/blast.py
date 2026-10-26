"""Drafting a message to many guests, one message at a time.

A blast here is not one text copied to forty people. Each recipient gets a
message written for their situation — the person who hasn't booked a room is
told which hotel and by when; the person with no flight is asked for a flight —
and in the language on their record.

Nothing is sent. The drafts go to the messages panel, where the couple approve
them one by one. There is no sender wired up anywhere in this file.
"""

from __future__ import annotations

import json
import re
import secrets
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent

import gaps

from .common import USAGE_LIMITS, BellsDeps, language_name, model

AGENT_NAME = "blast"

# One model call writes the whole batch, so a reminder to eight people costs
# one request rather than eight. Above this we refuse rather than quietly
# truncating the couple's list.
MAX_RECIPIENTS = 12

INSTRUCTIONS = """
You write short personal messages from a couple to their wedding guests.

You are given the couple's intent and a list of recipients. Each recipient has
their own situation — no room booked, no flight sent, no reply to the
invitation — and their own language.

Write ONE message per recipient:

- in that recipient's language (the code is given: en, fr, es, it, de);
- addressing them by first name;
- referring to their actual situation, with the real details you are given
  (hotel name, block code, deadline date). Never invent a detail you were not
  given;
- carrying the couple's intent and tone. If they ask for gentle, be gentle;
- two or three sentences. A message, not a letter. No subject line, no
  signature block — these go out as a text.

Return a JSON array and nothing else. Each element:
{"guest_id": <int>, "message": "<the message>"}

Return exactly one element per recipient, in the order given.
""".strip()


@lru_cache(maxsize=1)
def blast_agent() -> Agent[None, str]:
    return Agent(model(), output_type=str, name=AGENT_NAME, instructions=INSTRUCTIONS)


def _situation(g: dict) -> str:
    """The facts about this guest that a message might need to mention."""
    bits = [f"RSVP: {g['rsvp_status']}"]
    if g.get("plus_one_name"):
        bits.append(f"plus one: {g['plus_one_name']}")
    if g.get("hotel_name"):
        state = "booked" if g.get("hotel_booked") else "NOT booked"
        bits.append(f"hotel: {g['hotel_name']} ({state}"
                    + (f", block {g['block_code']}" if g.get("block_code") else "")
                    + (f", book by {g['book_by_date']}" if g.get("book_by_date") else "") + ")")
    if g.get("arrival_flight"):
        bits.append(f"flight: {g['arrival_flight']} landing {g['arrival_at']}")
    else:
        bits.append("no flight sent")
    return "; ".join(bits)


def _resolve_segment(segment: str) -> str:
    """Map free text onto a known segment, or raise."""
    s = (segment or "").strip().lower()
    if s in gaps.SEGMENTS:
        return s
    # the agent is allowed to describe the group instead of naming it
    if re.search(r"(not|haven'?t|hasn'?t|no).*(rsvp|repl|answer)", s):
        return "not_rsvpd"
    if re.search(r"(no|without|missing).*(flight|arriv)", s):
        return "no_flight"
    if re.search(r"(not|haven'?t|hasn'?t|no).*(book|room|hotel)", s):
        return "unbooked_hotel"
    if "declin" in s or "can'?t come" in s:
        return "declined"
    if "attend" in s or "coming" in s or "yes" in s:
        return "attending"
    if s in ("everyone", "everybody", "all guests"):
        return "all"
    raise ValueError(
        f"{segment!r} is not a group I can resolve. Use one of: "
        + ", ".join(gaps.SEGMENTS)
    )


async def write_drafts(segment: str, intent: str, deps: BellsDeps) -> list[dict[str, Any]]:
    """One draft per recipient. Returns them; sends nothing, stores nothing."""
    key = _resolve_segment(segment)
    recipients = gaps.segment_guests(key, deps.wedding_id, deps.db_path,
                                     limit=MAX_RECIPIENTS + 1)
    if not recipients:
        return []
    if len(recipients) > MAX_RECIPIENTS:
        raise ValueError(
            f"that group has more than {MAX_RECIPIENTS} people. Narrow it down — "
            "drafting personally for a crowd this size is not useful, and the "
            "couple have to read every one."
        )

    roster = "\n".join(
        f"- guest_id={g['id']} | {g['name']} | language={g['language']} "
        f"({language_name(g['language'])}) | {_situation(g)}"
        for g in recipients
    )
    prompt = (
        f"The couple want to say:\n\"{intent}\"\n\n"
        f"Recipients ({len(recipients)}):\n{roster}\n\n"
        "Write one message each, in each recipient's own language. JSON array only."
    )

    result = await blast_agent().run(prompt, usage=deps.usage, usage_limits=USAGE_LIMITS)
    text = result.output.strip()
    # models like to fence their JSON
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()

    try:
        parsed = json.loads(text)
        by_id = {int(d["guest_id"]): str(d["message"]).strip() for d in parsed}
    except Exception:
        # one bad batch should not lose the couple's work: fall back to a
        # single message each rather than nothing at all
        by_id = {}

    drafts = []
    for g in recipients:
        message = by_id.get(g["id"])
        if not message:
            continue
        drafts.append({
            "id": secrets.token_urlsafe(8),
            "guest_id": g["id"],
            "name": g["name"],
            "email": g["email"],
            "language": g["language"],
            "segment": key,
            "intent": intent,
            "situation": _situation(g),
            "message": message,
            "status": "draft",     # draft | approved | sent | skipped
        })
    return drafts
