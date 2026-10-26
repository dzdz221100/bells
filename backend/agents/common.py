"""Shared plumbing for the Bells agents: prompts, deps, limits, tool events."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from pydantic_ai.usage import RunUsage, UsageLimits

import config

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
HARD_RULES_FILE = PROMPTS_DIR / "hard_rules.md"

# Nothing can loop: at most 8 model requests per agent run. The concierge and
# each specialist get their own budget, enforced by pydantic-ai.
USAGE_LIMITS = UsageLimits(request_limit=8)

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "de": "German",
    "pt": "Portuguese",
    "nl": "Dutch",
    "tr": "Turkish",
}


def language_name(code: str | None) -> str:
    if not code:
        return "English"
    return LANGUAGE_NAMES.get(code.lower(), code)


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Agent instructions = the shared hard rules + that agent's own prompt file.

    Keeping the rules in one file means a safety change lands in all four
    agents at once and cannot drift between them.
    """
    body = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    rules = HARD_RULES_FILE.read_text(encoding="utf-8").strip()
    return f"{rules}\n\n---\n\n{body}"


@lru_cache(maxsize=1)
def model():
    """The one model object, built lazily so importing never needs an API key."""
    return config.build_model()


# --------------------------------------------------------------------------
# tool events — what the frontend lists under each reply
# --------------------------------------------------------------------------

@dataclass
class EventLog:
    """Ordered record of which agent called which tool, and how it went."""

    events: list[dict] = field(default_factory=list)

    @contextmanager
    def track(self, agent: str, tool: str, **args: Any) -> Iterator[dict]:
        started = time.perf_counter()
        event: dict[str, Any] = {
            "seq": len(self.events) + 1,
            "agent": agent,
            "tool": tool,
            "args": {k: _short(v) for k, v in args.items()},
            "status": "ok",
            "detail": "",
        }
        self.events.append(event)
        try:
            yield event
        except Exception as exc:  # the agent still sees the error; we log it
            event["status"] = "error"
            event["detail"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["ms"] = round((time.perf_counter() - started) * 1000, 1)

    @property
    def agents_called(self) -> list[str]:
        seen: list[str] = []
        for e in self.events:
            if e["agent"] not in seen:
                seen.append(e["agent"])
        return seen

    @property
    def tools_called(self) -> list[str]:
        return [f"{e['agent']}.{e['tool']}" for e in self.events]


def _short(value: Any, limit: int = 120) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


# --------------------------------------------------------------------------
# dependencies carried through every agent and tool
# --------------------------------------------------------------------------

@dataclass
class BellsDeps:
    """Shared by the concierge and every specialist it delegates to.

    The specialists get the *same* EventLog and RunUsage objects, so one turn
    produces one ordered trace and one token total.
    """

    wedding_id: int
    guest_id: int | None
    guest_name: str = ""
    language: str = "en"
    db_path: str | None = None
    events: EventLog = field(default_factory=EventLog)
    usage: RunUsage = field(default_factory=RunUsage)
    escalated: bool = False
    escalation_ids: list[int] = field(default_factory=list)

    # host side only: the session that must confirm a write, and what this
    # turn raised. The guest agent never populates these.
    session_token: str | None = None
    proposals: list[dict] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    drafts: list[dict] = field(default_factory=list)
