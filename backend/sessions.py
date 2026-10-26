"""Sign-in for the two roles: a guest, or the couple.

This is deliberately small. Bells is a demo app, not a product with accounts:
sessions live in memory and vanish when the server restarts, and a guest signs
in with the email on their invitation — no password. What it *does* buy is a
real boundary:

  * the guest list is never served to a guest. Only the couple can see who else
    is invited;
  * a guest session is bound to one guest_id, so the API will not serve another
    guest's dashboard, chat or pickup even if the id is guessed;
  * the agent's deps are built from the session, not from anything the browser
    sends, so a guest cannot ask Bells about someone else by changing a number.

Not production auth: no password hashing, no expiry beyond process lifetime, no
CSRF story. Said plainly here so nobody mistakes it for one.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import Header, HTTPException

from db import connect

Role = Literal["guest", "host"]

DEFAULT_HOST_PASSCODE = "bells"


@dataclass
class Session:
    token: str
    role: Role
    guest_id: int | None = None
    guest_name: str = ""
    language: str = "en"


_SESSIONS: dict[str, Session] = {}


def host_passcode() -> str:
    return os.getenv("BELLS_HOST_PASSCODE") or DEFAULT_HOST_PASSCODE


def using_default_passcode() -> bool:
    """The sign-in screen shows the demo passcode only while it is the default."""
    return host_passcode() == DEFAULT_HOST_PASSCODE


def find_guest_by_email(email: str, wedding_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, name, language FROM guests"
            " WHERE wedding_id = ? AND lower(email) = lower(?)",
            (wedding_id, email.strip()),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def random_guest(wedding_id: int) -> dict | None:
    """A guest at random, for the 'try it' button — never exposes the roster."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, name, language FROM guests WHERE wedding_id = ?"
            " ORDER BY RANDOM() LIMIT 1",
            (wedding_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def start_guest(guest: dict) -> Session:
    s = Session(
        token=secrets.token_urlsafe(24),
        role="guest",
        guest_id=int(guest["id"]),
        guest_name=guest["name"],
        language=guest.get("language") or "en",
    )
    _SESSIONS[s.token] = s
    return s


def start_host() -> Session:
    s = Session(token=secrets.token_urlsafe(24), role="host")
    _SESSIONS[s.token] = s
    return s


def end(token: str) -> None:
    _SESSIONS.pop(token, None)


def _lookup(token: str | None) -> Session:
    if not token or token not in _SESSIONS:
        raise HTTPException(401, "Not signed in.")
    return _SESSIONS[token]


# ----- FastAPI dependencies -------------------------------------------------

def current_session(x_bells_session: str | None = Header(default=None)) -> Session:
    return _lookup(x_bells_session)


def require_guest(x_bells_session: str | None = Header(default=None)) -> Session:
    s = _lookup(x_bells_session)
    if s.role != "guest" or s.guest_id is None:
        raise HTTPException(403, "This is a guest page — sign in with your invitation email.")
    return s


def require_host(x_bells_session: str | None = Header(default=None)) -> Session:
    s = _lookup(x_bells_session)
    if s.role != "host":
        raise HTTPException(403, "Only the couple can open the host console.")
    return s
