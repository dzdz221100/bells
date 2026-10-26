"""Registry agent — availability only, never who claimed what.

`claimed_by_guest_id` is never selected into the model's context except to
compare it with the current guest. The agent cannot leak a name it was never
given.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from pydantic_ai import Agent, RunContext

from db import connect

from .common import USAGE_LIMITS, BellsDeps, load_prompt, model

AGENT_NAME = "registry"


def list_items_rows(wedding_id: int, guest_id: int | None, db_path: str | None = None) -> list[dict]:
    """Items with availability. The only identity exposed is the current guest's."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, item, url, image_url, price, claimed_by_guest_id FROM registry"
            " WHERE wedding_id = ? ORDER BY id",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "item": r["item"],
            "url": r["url"],
            "image_url": r["image_url"],
            "price": r["price"],
            "available": r["claimed_by_guest_id"] is None,
            "claimed_by_you": guest_id is not None and r["claimed_by_guest_id"] == guest_id,
        }
        for r in rows
    ]


def claim(item_id: int, guest_id: int, wedding_id: int, db_path: str | None = None) -> dict:
    """Claim an item. Atomic: the UPDATE only fires if it is still unclaimed."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, item, price, claimed_by_guest_id FROM registry"
            " WHERE id = ? AND wedding_id = ?",
            (item_id, wedding_id),
        ).fetchone()
        if row is None:
            return {"ok": False, "reason": "no_such_item"}
        if row["claimed_by_guest_id"] == guest_id:
            return {"ok": True, "already_yours": True, "item": row["item"], "price": row["price"]}

        cur = conn.execute(
            "UPDATE registry SET claimed_by_guest_id = ?, claimed_at = ?"
            " WHERE id = ? AND wedding_id = ? AND claimed_by_guest_id IS NULL",
            (guest_id, datetime.now().isoformat(timespec="seconds"), item_id, wedding_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "reason": "taken", "item": row["item"]}
        return {"ok": True, "item": row["item"], "price": row["price"]}
    finally:
        conn.close()


def unclaim(item_id: int, guest_id: int, wedding_id: int, db_path: str | None = None) -> dict:
    """Release an item — only if this guest is the one holding it."""
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, item, claimed_by_guest_id FROM registry WHERE id = ? AND wedding_id = ?",
            (item_id, wedding_id),
        ).fetchone()
        if row is None:
            return {"ok": False, "reason": "no_such_item"}
        cur = conn.execute(
            "UPDATE registry SET claimed_by_guest_id = NULL, claimed_at = NULL"
            " WHERE id = ? AND wedding_id = ? AND claimed_by_guest_id = ?",
            (item_id, wedding_id, guest_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            # Deliberately the same answer whether it is unclaimed or someone
            # else's — otherwise this is an oracle for who claimed what.
            return {"ok": False, "reason": "not_yours", "item": row["item"]}
        return {"ok": True, "item": row["item"]}
    finally:
        conn.close()


@lru_cache(maxsize=1)
def registry_agent() -> Agent[BellsDeps, str]:
    agent = Agent(
        model(),
        deps_type=BellsDeps,
        output_type=str,
        name=AGENT_NAME,
        instructions=load_prompt("registry"),
    )

    @agent.tool
    async def list_items(ctx: RunContext[BellsDeps]) -> str:
        """Every registry item with price, link and whether it is still available."""
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "list_items") as ev:
            items = list_items_rows(deps.wedding_id, deps.guest_id, deps.db_path)
            free = sum(1 for i in items if i["available"])
            ev["detail"] = f"{len(items)} item(s), {free} available"
            if not items:
                return "NO_ITEMS — the registry is empty."
            lines = []
            for i in items:
                state = "available" if i["available"] else "already taken"
                if i["claimed_by_you"]:
                    state = "claimed by this guest"
                price = f"{i['price']:.0f}" if i["price"] is not None else "price not listed"
                lines.append(f"[{i['id']}] {i['item']} · {price} · {state} · {i['url'] or ''}".strip())
            return "\n".join(lines)

    @agent.tool
    async def claim_item(ctx: RunContext[BellsDeps], item_id: int, guest_id: int | None = None) -> str:
        """Claim a registry item for the guest you are helping.

        Args:
            item_id: the number in square brackets from list_items.
            guest_id: optional; must be the guest you are helping.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "claim_item", item_id=item_id) as ev:
            if deps.guest_id is None:
                ev["detail"] = "no guest in session"
                return "REFUSED — there is no guest in this session to claim for."
            if guest_id is not None and int(guest_id) != int(deps.guest_id):
                ev["status"] = "refused"
                ev["detail"] = f"asked to act as guest {guest_id}"
                return "REFUSED — you may only claim items for the guest you are helping."

            res = claim(item_id, deps.guest_id, deps.wedding_id, deps.db_path)
            ev["detail"] = res.get("reason") or ("already yours" if res.get("already_yours") else "claimed")
            if not res["ok"]:
                if res["reason"] == "no_such_item":
                    return f"NO_SUCH_ITEM — there is no registry item {item_id}."
                return (
                    f"TAKEN — '{res['item']}' was claimed by someone else before this "
                    "request. Do not say who. Offer the guest what is still available."
                )
            if res.get("already_yours"):
                return f"ALREADY_YOURS — this guest had already claimed '{res['item']}'."
            price = f"{res['price']:.0f}" if res["price"] is not None else "price not listed"
            return f"CLAIMED — '{res['item']}' ({price}) is now reserved for this guest."

    @agent.tool
    async def unclaim_item(ctx: RunContext[BellsDeps], item_id: int, guest_id: int | None = None) -> str:
        """Release an item the guest you are helping claimed earlier.

        Args:
            item_id: the number in square brackets from list_items.
            guest_id: optional; must be the guest you are helping.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "unclaim_item", item_id=item_id) as ev:
            if deps.guest_id is None:
                ev["detail"] = "no guest in session"
                return "REFUSED — there is no guest in this session."
            if guest_id is not None and int(guest_id) != int(deps.guest_id):
                ev["status"] = "refused"
                ev["detail"] = f"asked to act as guest {guest_id}"
                return "REFUSED — you may only release items the current guest claimed."

            res = unclaim(item_id, deps.guest_id, deps.wedding_id, deps.db_path)
            ev["detail"] = res.get("reason") or "unclaimed"
            if not res["ok"]:
                if res["reason"] == "no_such_item":
                    return f"NO_SUCH_ITEM — there is no registry item {item_id}."
                return (
                    f"NOT_YOURS — '{res['item']}' is not one of this guest's claims. "
                    "Do not say whether anyone else has claimed it."
                )
            return f"RELEASED — '{res['item']}' is available again."

    return agent


async def ask_registry(question: str, deps: BellsDeps) -> str:
    result = await registry_agent().run(
        question, deps=deps, usage=deps.usage, usage_limits=USAGE_LIMITS
    )
    return result.output
