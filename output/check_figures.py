"""Check that report.html and slides.html quote the pinned figures, and only those.

The rule this enforces: a number in the text must match the number visible in
the screenshot on the same page. Screenshots are frozen; the audit trail is
not. So the documents quote `figures_pinned.json`, and this script fails if
either document still contains a figure from some other moment.

It looks for two things:

  * every pinned figure appears in both documents, in the form it is written;
  * no *stale* figure appears — a value that was true of an earlier trail and
    would now contradict the console in the picture.

Usage:  python output/check_figures.py
Exit:   0 if both documents are consistent, 1 if not.
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
DOCS = [OUT / "report.html", OUT / "slides.html"]


def text_of(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    # drop the base64 payloads before searching, or a stray digit run inside an
    # image would count as a figure
    raw = re.sub(r'src="data:[^"]+"', 'src="[image]"', raw)
    raw = re.sub(r"<style>.*?</style>", " ", raw, flags=re.S)
    raw = re.sub(r"<script>.*?</script>", " ", raw, flags=re.S)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    # "73.7 %" and "$ 0.00032" happen when markup splits a number from its
    # unit for styling; they are the same figure on screen.
    plain = re.sub(r"(\d)\s+%", r"\1%", plain)
    plain = re.sub(r"\$\s+(\d)", r"$\1", plain)
    return re.sub(r"\s+", " ", plain)


def main() -> int:
    if not PIN.exists():
        print(f"no {PIN.relative_to(ROOT)} — run: python output/build_report.py --pin")
        return 1
    p = json.loads(PIN.read_text(encoding="utf-8"))

    # what each document must say, and what it must no longer say
    must: list[tuple[str, str]] = [
        ("turns", str(p["turns"])),
        ("answered automatically", str(p["answered"])),
        ("escalated", str(p["escalated"])),
        ("escalation rate", f'{p["escalation_pct"]}%'),
        ("minutes saved", str(p["minutes_saved"])),
        ("facts Bells knows", str(p["facts_total"])),
        ("facts from the console", str(p["facts_from_console"])),
        ("cache hit rate", f'{p["cache_hit_pct"]}%'),
        ("cost per question", f'${p["cost_per_turn"]:.5f}'),
    ]
    # figures from earlier trails that must not survive anywhere
    stale = ["131 turns", "219", "186", "90.1%", "84.9%", "85.1%",
             "72.3%", "74.0%", "$0.04245", "$0.071068", "9.3 hours", "9.5 hours"]

    failures: list[str] = []
    for doc in DOCS:
        if not doc.exists():
            failures.append(f"{doc.name}: not built")
            continue
        body = text_of(doc)
        for label, value in must:
            if value not in body:
                failures.append(f"{doc.name}: missing {label} = {value}")
        for old in stale:
            if old in body:
                failures.append(f"{doc.name}: still contains stale figure {old!r}")

    print(f"pinned {PIN.relative_to(ROOT)} · {p['turns']} turns, "
          f"{p['answered']} answered, {p['escalation_pct']}% escalated, "
          f"{p['minutes_saved']} min, {p['facts_total']} facts "
          f"({p['facts_from_console']} from the console), "
          f"{p['cache_hit_pct']}% cache, ${p['cost_usd']:.4f}")
    if failures:
        print("\nINCONSISTENT:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nreport.html and slides.html both quote the pinned figures, "
          "and no stale figure survives in either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
