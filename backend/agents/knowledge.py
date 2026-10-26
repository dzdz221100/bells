"""Knowledge agent — answers only from wedding_facts rows.

The agent has no other tool and no licence to use general knowledge. The
search function below is the only door to the data, and it filters out private
rows in SQL, so a private fact never reaches the model's context at all. That
is deliberate: a rule the model must follow is weaker than a row it never sees.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic_ai import Agent, RunContext

from db import connect

from .common import USAGE_LIMITS, BellsDeps, load_prompt, model

AGENT_NAME = "knowledge"
MAX_FACTS = 5

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "did", "do", "does", "for",
    "from", "get", "has", "have", "how", "i", "if", "in", "is", "it", "me",
    "my", "of", "on", "or", "our", "should", "that", "the", "there", "they",
    "this", "to", "we", "what", "when", "where", "which", "who", "will",
    "with", "you", "your",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def search_facts_rows(query: str, wedding_id: int, db_path: str | None = None) -> list[dict]:
    """Keyword-score the wedding's PUBLIC facts against the query.

    Private rows (is_public = 0) are excluded in the SQL, not in the ranking.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, topic, question_pattern, answer, source, updated_at"
            " FROM wedding_facts WHERE wedding_id = ? AND is_public = 1",
            (wedding_id,),
        ).fetchall()
    finally:
        conn.close()

    wanted = _tokens(query)
    if not wanted:
        return []

    scored: list[tuple[float, dict]] = []
    for r in rows:
        score = (
            3.0 * len(wanted & _tokens(r["question_pattern"]))
            + 2.0 * len(wanted & _tokens(r["topic"].replace("_", " ")))
            + 1.0 * len(wanted & _tokens(r["answer"]))
        )
        if score > 0:
            scored.append((score, {
                "id": r["id"],
                "topic": r["topic"],
                "answer": r["answer"],
                "source": r["source"],
                "updated_at": r["updated_at"],
            }))

    scored.sort(key=lambda s: (-s[0], s[1]["id"]))
    return [row for _, row in scored[:MAX_FACTS]]


@lru_cache(maxsize=1)
def knowledge_agent() -> Agent[BellsDeps, str]:
    agent = Agent(
        model(),
        deps_type=BellsDeps,
        output_type=str,
        name=AGENT_NAME,
        instructions=load_prompt("knowledge"),
    )

    @agent.tool
    async def search_facts(ctx: RunContext[BellsDeps], query: str) -> str:
        """Search the couple's recorded facts. This is your only source.

        Args:
            query: the guest's question, or key words from it.
        """
        deps = ctx.deps
        with deps.events.track(AGENT_NAME, "search_facts", query=query) as ev:
            facts = search_facts_rows(query, deps.wedding_id, deps.db_path)
            ev["detail"] = (
                f"{len(facts)} fact(s): " + ", ".join(f["topic"] for f in facts)
                if facts else "no match"
            )
            if not facts:
                return "NO_FACTS_FOUND — nothing recorded matches that query."
            return "\n\n".join(
                f"[fact {f['id']} · {f['topic']}]\n{f['answer']}" for f in facts
            )

    return agent


async def ask_knowledge(question: str, deps: BellsDeps) -> str:
    result = await knowledge_agent().run(
        question, deps=deps, usage=deps.usage, usage_limits=USAGE_LIMITS
    )
    return result.output
