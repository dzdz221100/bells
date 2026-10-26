"""Check that no number in the prose contradicts a number in a screenshot.

The rule: a figure quoted in the text must be the figure visible in the
screenshot on the same page. Screenshots are frozen; the audit trail is not.
So both documents quote `figures_pinned.json`, pinned from the same trail the
screenshots were captured against, and this script fails if either document
has drifted.

Two checks, and they are deliberately different:

  * **no contradiction** (both documents) — no figure from an earlier trail may
    survive anywhere. This is the rule itself. A page saying "189 of 222" beside
    a console screenshot reading "193 of 226" is the exact failure being
    prevented.
  * **completeness** (report only) — the report is the document that has to
    carry every figure. The deck quotes a headline subset and leaves the rest to
    the screenshots it shows, which is correct for slides.

Usage:  python output/check_figures.py
Exit:   0 if consistent, 1 if not.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PIN = OUT / "figures_pinned.json"
REPORT = OUT / "report.html"
SLIDES = OUT / "slides.html"

# Figures that were true of an earlier trail. Any of these appearing now means
# a document was not rebuilt, or was rebuilt against a trail that had moved on
# from the screenshots. Written as regexes with boundaries so a digit run
# inside a larger number never trips them.
SUPERSEDED = [
    r"\b131 turns\b", r"\b219 turns\b", r"\b222 turns\b",
    r"\b186 answered\b", r"\b189 answered\b", r"\b189 of 222\b",
    r"\b90\.1%", r"\b84\.9%", r"\b85\.1%", r"\b14\.9%",
    r"\b72\.3%", r"\b74\.0%", r"\b73\.7%",
    r"\$0\.04245\b", r"\$0\.071068\b", r"\$0\.0717\b", r"\$0\.0711\b",
    r"\b567 minutes\b", r"\b558 minutes\b", r"\b9\.3 hours\b", r"\b9\.4 hours\b",
    r"\b9\.5 hours\b",
]


def text_of(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    # strip the base64 payloads first, or a digit run inside an image trips this
    raw = re.sub(r'src="data:[^"]+"', 'src="[image]"', raw)
    raw = re.sub(r"<style>.*?</style>", " ", raw, flags=re.S)
    raw = re.sub(r"<script>.*?</script>", " ", raw, flags=re.S)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    # "73.5 %" and "$ 0.00032" happen when markup splits a number from its unit
    # for styling; on screen they are one figure.
    plain = re.sub(r"(\d)\s+%", r"\1%", plain)
    plain = re.sub(r"\$\s+(\d)", r"$\1", plain)
    return re.sub(r"\s+", " ", plain)


def main() -> int:
    if not PIN.exists():
        print(f"no {PIN.relative_to(ROOT)} — run: python output/build_report.py --pin")
        return 1
    p = json.loads(PIN.read_text(encoding="utf-8"))

    required = [
        ("turns", str(p["turns"])),
        ("answered automatically", str(p["answered"])),
        ("escalated", str(p["escalated"])),
        ("escalation rate", f'{p["escalation_pct"]}%'),
        ("minutes saved", str(p["minutes_saved"])),
        ("hours saved", f'{p["hours_saved"]} hours'),
        ("facts Bells knows", str(p["facts_total"])),
        ("facts from the console", str(p["facts_from_console"])),
        ("cache hit rate", f'{p["cache_hit_pct"]}%'),
        ("total cost", f'${p["cost_usd"]:.4f}'),
        ("cost per question", f'${p["cost_per_turn"]:.5f}'),
    ]
    # what the deck has to carry in its own text; the rest it shows in pictures
    slide_headlines = ["turns", "answered automatically", "cache hit rate",
                       "total cost", "cost per question", "minutes saved",
                       "facts Bells knows"]

    failures: list[str] = []
    for doc in (REPORT, SLIDES):
        if not doc.exists():
            failures.append(f"{doc.name}: not built")
            continue
        body = text_of(doc)

        for pattern in SUPERSEDED:
            hit = re.search(pattern, body)
            if hit:
                where = body[max(0, hit.start() - 60):hit.end() + 40]
                failures.append(f"{doc.name}: contradicts the screenshots — "
                                f"{hit.group(0)!r} in “…{where.strip()}…”")

        wanted = required if doc is REPORT else [
            r for r in required if r[0] in slide_headlines]
        for label, value in wanted:
            if value not in body:
                failures.append(f"{doc.name}: missing {label} = {value}")

    print(f"pinned from {PIN.relative_to(ROOT)} · {p['turns']} turns · "
          f"{p['answered']} answered · {p['escalated']} escalated "
          f"({p['escalation_pct']}%) · {p['minutes_saved']} min "
          f"({p['hours_saved']} h) · {p['facts_total']} facts "
          f"({p['facts_from_console']} from the console) · "
          f"{p['cache_hit_pct']}% cached · ${p['cost_usd']:.4f} · "
          f"${p['cost_per_turn']:.5f} per question")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  {f}")
        return 1

    print("\nreport.html carries every pinned figure; slides.html carries the "
          "headline set; neither contradicts the screenshots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
