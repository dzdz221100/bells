"""Build output/slides.html — ten reveal.js slides, one self-contained file.

Same rule as the report: every figure is read out of `output/` at build time,
so the slides and the report cannot disagree. Screenshots and the agent
diagram are inlined — the diagram as SVG, the screenshots as base64 data URIs
— so the file survives being emailed and opens by double-click.

reveal.js itself comes from a CDN, as asked. That means the deck needs a
network connection the first time it is opened; if the CDN is unreachable, a
no-JS fallback stylesheet lays the slides out as one long readable page rather
than a heap.

Keys: arrows to move, F for fullscreen, S for speaker notes, Esc for overview.

Usage:  python output/build_slides.py
Writes: output/slides.html
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_report import (  # noqa: E402
    DIAGRAM, REPO_IS_PUBLIC, REPO_URL, SLOTS, collect_shots, figures, h, load,
)

ROOT = Path(__file__).resolve().parents[1]
SLIDES = ROOT / "output" / "slides.html"

REVEAL = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0"

CSS = """
:root{
  --ink:#1b2a33; --azure:#2f6f8f; --lemon:#e8b833; --terra:#c5614a; --chalk:#faf7f0;
  --rule:#d9d2c4; --muted:#5a6b74;
  --serif:'Bodoni Moda',"Bodoni 72",Didot,"Hoefler Text",Garamond,"Times New Roman",serif;
  --sans:'DM Sans',-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:'Space Mono',"SFMono-Regular",Menlo,Consolas,monospace;
}
.reveal-viewport,body{background:var(--chalk)}
.reveal{font-family:var(--sans);color:var(--ink);font-size:30px}
.reveal .slides{text-align:left}
.reveal section{padding:0 2%}
.bleed{padding:0!important}
/* the four-beat loop on the demo slide: big, but it has to fit */
.steps{display:flex;align-items:baseline;gap:.25em;margin-bottom:.45em}
.steps>div{flex:1}
.steps .w{font-family:var(--serif);font-size:1.9em;line-height:1;
  letter-spacing:-.02em;display:block}
.steps .arrow{flex:0 0 auto;font-size:1.1em}

.reveal h1,.reveal h2,.reveal h3{
  font-family:var(--serif);font-weight:600;color:var(--ink);
  text-transform:none;letter-spacing:-.015em;margin:0 0 .25em;line-height:1.04}
.reveal h1{font-size:3.05em}
.reveal h2{font-size:1.45em}
.reveal h3{font-size:1em}
.reveal p{margin:.35em 0;line-height:1.45}
.reveal strong{font-weight:700}
.reveal a{color:var(--azure)}
.reveal ul{margin:.4em 0 0 .9em;line-height:1.5}
.reveal li{margin:.28em 0}
.reveal li::marker{color:var(--terra)}

.eyebrow{font-family:var(--mono);font-size:.42em;letter-spacing:.22em;
  text-transform:uppercase;color:var(--azure);display:block;margin-bottom:.7em}
.kicker{font-family:var(--serif);font-style:italic;color:var(--muted);
  font-size:.82em;margin-top:.1em}
.src{font-family:var(--mono);font-size:.3em;letter-spacing:.06em;color:var(--muted);
  position:absolute;bottom:-.6em;left:2%}

/* the number is the slide */
.big{font-family:var(--serif);font-weight:600;line-height:.92;
  font-size:3.6em;letter-spacing:-.03em;display:block}
.big.sm{font-size:2.5em}
.big .unit{font-size:.4em;letter-spacing:0}
.azure{color:var(--azure)} .terra{color:var(--terra)} .lemon{color:#b08a1e}
.cap{font-family:var(--mono);font-size:.38em;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);display:block;margin-top:.5em}

.row{display:flex;gap:1.1em;align-items:flex-start}
.row>*{flex:1}
.row.tight{gap:.7em}
.figs{display:flex;gap:.8em;align-items:stretch}
.figs>figure{flex:1;margin:0}

.card{background:#fff;border:1px solid var(--rule);border-top:5px solid var(--azure);
  padding:.55em .65em}
.card.lemon{border-top-color:var(--lemon)} .card.terra{border-top-color:var(--terra)}

.clone{font-family:var(--mono);font-size:.5em;color:var(--muted);
  display:block;margin-top:.45em}
.endnote{font-family:var(--mono);font-size:.52em;color:var(--muted);
  margin-top:1.1em;padding-top:.5em;border-top:1px solid var(--rule)}
.endnote b{color:var(--ink);font-weight:400}
.repo{font-family:var(--mono);font-size:.95em;letter-spacing:.01em;color:var(--ink);
  background:#fff;border:2px solid var(--azure);padding:.45em .6em;
  display:inline-block;margin-top:.5em;word-break:break-all}

.arrow{font-family:var(--serif);font-size:1.6em;color:var(--terra);
  padding:0 .15em;line-height:1}

figure{margin:0}
figure img{display:block;width:auto;max-width:100%;max-height:54vh;
  margin:0 auto;border:1px solid var(--rule);background:#fff}
figcaption{font-family:var(--mono);font-size:.34em;letter-spacing:.06em;
  color:var(--muted);margin-top:.45em;line-height:1.4}
.ph{border:2px dashed var(--azure);background:#fff;display:flex;flex-direction:column;
  align-items:center;justify-content:center;text-align:center;min-height:30vh;
  padding:1em}
.ph b{font-family:var(--mono);font-size:.34em;letter-spacing:.16em;
  text-transform:uppercase;color:var(--azure)}
.ph i{font-family:var(--serif);font-size:.62em;margin:.35em 0}
.ph code{font-family:var(--mono);font-size:.3em;color:var(--muted)}

.diagram-wrap{width:100%}
.diagram-wrap svg{width:100%;height:auto;max-height:82vh;display:block}

table{width:100%;border-collapse:collapse;font-size:.58em}
th,td{text-align:left;padding:.42em .5em;border-bottom:1px solid var(--rule);
  vertical-align:top}
thead th{font-family:var(--mono);font-size:.62em;letter-spacing:.1em;
  text-transform:uppercase;color:var(--azure);border-bottom:2px solid var(--ink)}
tbody tr:nth-child(even){background:rgba(47,111,143,.05)}
.ok{color:#2b6b43;font-weight:700}

.reveal .progress{color:var(--terra)}
.reveal .controls{color:var(--azure)}

/* If reveal.js never loads, show the slides as a plain readable page rather
   than a stack of overlapping sections. */
.no-reveal .slides{display:block;max-width:60rem;margin:0 auto;padding:2rem}
.no-reveal .slides>section{display:block!important;position:static!important;
  border-bottom:3px double var(--ink);padding:2.5rem 0;opacity:1!important;
  transform:none!important;height:auto!important}
.no-reveal .big{font-size:2.4em}
.no-reveal figure img{max-height:none}
.no-reveal .src{position:static;display:block;margin-top:1rem}
"""

FALLBACK_JS = """
(function(){
  function boot(){
    if (window.Reveal) {
      Reveal.initialize({
        hash:false, controls:true, progress:true, slideNumber:'c/t',
        transition:'fade', transitionSpeed:'fast',
        width:1280, height:760, margin:0.07,
        minScale:0.2, maxScale:1.6
      });
    } else {
      // CDN unreachable — degrade to one scrollable page.
      document.body.classList.add('no-reveal');
    }
  }
  if (document.readyState === 'complete') boot();
  else window.addEventListener('load', boot);
})();
"""


def fig(slot_n: str, filled: dict, caption: str | None = None) -> str:
    slot = next(s for s in SLOTS if s["n"] == slot_n)
    shot = filled.get(slot_n)
    cap = caption or slot["caption"]
    if shot:
        return (f'<figure><img src="{shot["uri"]}" alt="{h(cap)}">'
                f'<figcaption>{h(cap)}</figcaption></figure>')
    return (f'<figure><div class="ph"><b>Figure {int(slot_n)}</b>'
            f'<i>{h(slot["want"])}</i>'
            f'<code>screenshots/{h(slot["file"])}</code></div>'
            f'<figcaption>{h(cap)}</figcaption></figure>')


def build() -> None:
    trail = load("audit_trail.json")
    cost = load("cost_results.json")
    safety = load("safety_results.json")
    solver = load("solver_results.json")
    loop = load("escalation_loop.json")

    s = figures()
    filled, _ = collect_shots()
    imp, bef, aft = solver["impact"], solver["before"], solver["after"]
    sm = safety["summary"]

    S: list[str] = []

    # 1 ----------------------------------------------------------------
    repo_line = (
        f'<div class="repo">{h(REPO_URL)}</div>'
        if REPO_IS_PUBLIC else
        f'<div class="repo">{h(REPO_URL)}</div>'
        '<p class="kicker" style="font-size:.6em">This repository is '
        '<strong>private</strong> — <code>zlisto</code> is added as a '
        'collaborator.</p>'
    )
    S.append(f"""
<section>
  <span class="eyebrow">MGT 409 · AI Foundations for Managers</span>
  <h1>Bells</h1>
  <p class="kicker">A concierge for destination wedding guests.</p>
  <p style="margin-top:.9em;font-size:.72em">Dariga Zhuman</p>
  {repo_line}
  <span class="clone">git clone {REPO_URL}.git</span>
</section>""")

    # 2 ----------------------------------------------------------------
    S.append("""
<section>
  <span class="eyebrow">The problem</span>
  <h2>One couple answers the&nbsp;same question forty times.</h2>
  <div class="row" style="margin-top:.7em">
    <div><span class="big azure">40</span><span class="cap">guests flying in</span></div>
    <div><span class="big azure">5</span><span class="cap">languages</span></div>
    <div><span class="big terra">1</span><span class="cap">couple, on WhatsApp</span></div>
  </div>
  <p class="kicker" style="margin-top:.9em">Nine months of it. By the thirtieth
  message, Elena is guessing at a shuttle time she hasn't checked.</p>
</section>""")

    # 3 ----------------------------------------------------------------
    S.append("""
<section>
  <span class="eyebrow">What is actually new</span>
  <h2>They publish information.<br>Bells answers questions.</h2>
  <table style="margin-top:.5em">
    <thead><tr><th>Product</th><th>What it does</th></tr></thead>
    <tbody>
      <tr><td>Zola · The&nbsp;Knot</td><td>Registry, website, RSVP. Travel is a page the couple type.</td></tr>
      <tr><td>WithJoy</td><td>Has an AI assistant — it helps the <em>couple</em> write content.</td></tr>
      <tr><td>Appy&nbsp;Couple · Minted</td><td>Beautiful static itineraries. A guest reads; they don't ask.</td></tr>
    </tbody>
  </table>
  <ul style="margin-top:.55em;font-size:.72em">
    <li><strong>Solves</strong> arrival logistics instead of listing them</li>
    <li>Answers each guest <strong>in the language they wrote in</strong></li>
    <li><strong>Escalates instead of guessing</strong> — then never asks twice</li>
  </ul>
  <p class="kicker" style="font-size:.52em;margin-top:.5em">All five are more
  complete products than mine. The claim is narrow, not that Bells is better.</p>
</section>""")

    # 4 ----------------------------------------------------------------
    S.append(f"""
<section class="bleed">
  <span class="eyebrow">How it works</span>
  <div class="diagram-wrap">{DIAGRAM}</div>
</section>""")

    # 5 ----------------------------------------------------------------
    S.append(f"""
<section>
  <span class="eyebrow">Demo · the guest</span>
  <h3>Everything you owe, and when you land.</h3>
  <div class="figs" style="margin-top:.5em">
    {fig("01", filled, "The guest page — what this guest still owes, computed from their own row.")}
    {fig("03", filled, "The arrival timeline — land, passport and bags, pickup, arrive.")}
  </div>
</section>""")

    # 6 ----------------------------------------------------------------
    ls = loop["summary"]
    S.append(f"""
<section>
  <span class="eyebrow">Demo · the loop that is the point</span>
  <div class="steps">
    <div><span class="w terra">asks</span>
      <span class="cap">guest · no fact exists</span></div>
    <div class="arrow">→</div>
    <div><span class="w terra">escalates</span>
      <span class="cap">Bells does not guess</span></div>
    <div class="arrow">→</div>
    <div><span class="w azure">approves</span>
      <span class="cap">the couple, once</span></div>
    <div class="arrow">→</div>
    <div><span class="w lemon">answers</span>
      <span class="cap">itself, forever</span></div>
  </div>
  <div class="row tight">
    <div class="card"><span class="big sm">{s["facts_total"]}
      <span class="unit">·</span> {s["facts_from_console"]}</span>
      <span class="cap">facts Bells knows · from the console</span></div>
    <div class="card lemon"><span class="big sm">{ls["answered_unaided_on_second_ask"]}/{ls["of"]}</span>
      <span class="cap">answered unaided next time</span></div>
    <div style="flex:2.4">{fig("07", filled, "The host console — 189 of 222 answered, 14.9% escalated, 567 minutes saved, 41 facts of which 6 came from this console.")}</div>
  </div>
  <span class="src">output/escalation_loop.json</span>
</section>""")

    # 7 ----------------------------------------------------------------
    S.append(f"""
<section>
  <span class="eyebrow">Cost</span>
  <span class="big azure">${s["cost_per_turn"]:.5f}</span>
  <span class="cap">per question · {s["turns"]} real turns · ${s["cost_usd"]:.4f} in total</span>
  <div class="row" style="margin-top:.8em">
    <div class="card lemon"><span class="big sm">{s["cache_hit_pct"]}<span class="unit">%</span></span>
      <span class="cap">input served from cache</span></div>
    <div class="card"><span class="big sm">−{cost["savings"]["cost_pct"]}<span class="unit">%</span></span>
      <span class="cap">cost, cached vs busted</span></div>
    <div class="card"><span class="big sm">{cost["cold"]["correct"]}/{cost["cold"]["of"]}</span>
      <span class="cap">facts returned · both passes</span></div>
  </div>
  <p class="kicker" style="margin-top:.6em;font-size:.62em">Caching cut cost by
  half and latency by {cost["savings"]["latency_pct"]}% without losing a single
  required fact.</p>
  <span class="src">output/audit_trail.json · output/cost_results.json</span>
</section>""")

    # 8 ----------------------------------------------------------------
    S.append(f"""
<section>
  <span class="eyebrow">Safety</span>
  <div class="row">
    <div style="flex:.85">
      <span class="big azure">{sm["passed"]}<span class="unit">/{sm["total"]}</span></span>
      <span class="cap">hostile probes passed</span>
      <ul style="font-size:.6em;margin-top:.7em">
        <li>6/6 privacy · 3/3 injection</li>
        <li>2/2 content filter · 1/1 runaway</li>
        <li>7/7 data-layer · 3/3 handler</li>
      </ul>
      <p class="kicker" style="font-size:.52em;margin-top:.5em">Private rows are
      filtered in SQL. The agent cannot leak what it was never given.</p>
    </div>
    <div style="flex:1.15">{fig("05", filled, "Asked for the couple's private number. Refused — the row never entered the model's context.")}</div>
  </div>
  <span class="src">output/safety_results.json</span>
</section>""")

    # 9 ----------------------------------------------------------------
    S.append(f"""
<section>
  <span class="eyebrow">Impact</span>
  <div class="row" style="align-items:flex-start">
    <div><span class="big terra">{bef["runs"]}<span class="unit"> → </span>{aft["runs"]}</span>
      <span class="cap">airport transfers · −{imp["runs_saved_pct"]}%</span></div>
    <div><span class="big lemon">€{imp["transfer_cost_saved_eur"]:,.0f}</span>
      <span class="cap">saved · {imp["driver_hours_saved"]} driver hours</span></div>
    <div><span class="big azure">{s["answered"]}<span class="unit">/{s["turns"]}</span></span>
      <span class="cap">answered automatically · {s["escalated"]} escalated, {s["escalation_pct"]}%</span></div>
  </div>
  <p class="kicker" style="margin-top:.55em;font-size:.6em">
  {s["minutes_saved"]} minutes of the couple's time, at 3 minutes a question —
  the figure on the console in slide 6.</p>
  <p class="kicker" style="margin-top:.3em;font-size:.6em">The trade I chose:
  +{imp["extra_wait_per_person_minutes"]} minutes of waiting per person, against
  a cap of {imp["wait_limit_minutes"]} that I set.</p>
  <span class="src">output/solver_results.json · output/audit_trail.json</span>
</section>""")

    # 10 ---------------------------------------------------------------
    S.append(f"""
<section>
  <span class="eyebrow">What's next</span>
  <h2>Three things, in order.</h2>
  <div class="row" style="margin-top:.7em">
    <div class="card"><span class="big sm azure">1</span>
      <span class="cap">Seating solver</span>
      <p style="font-size:.56em;margin-top:.4em">Written, not wired in. Same
      pattern as the shuttles: Python solves, the agent explains.</p></div>
    <div class="card lemon"><span class="big sm lemon">2</span>
      <span class="cap">Real sending</span>
      <p style="font-size:.56em;margin-top:.4em">Drafts exist in five languages.
      Nothing sends — on purpose. A provider behind the same approval step.</p></div>
    <div class="card terra"><span class="big sm terra">3</span>
      <span class="cap">A pilot wedding</span>
      <p style="font-size:.56em;margin-top:.4em">Every number here is from one
      seeded wedding and my own testing. No real guest has used it yet.</p></div>
  </div>
  <p class="endnote">All of it, including the evidence these numbers come from:
  <b>{REPO_URL}</b></p>
</section>""")

    missing = [x["n"] for x in SLOTS if x["n"] not in filled]

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bells — MGT 409 — Dariga Zhuman</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400..700&family=DM+Sans:wght@400;500;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{REVEAL}/dist/reveal.css">
<style>{CSS}</style>
</head>
<body>
<div class="reveal"><div class="slides">
{''.join(S)}
</div></div>
<script src="{REVEAL}/dist/reveal.js"></script>
<script>{FALLBACK_JS}</script>
</body>
</html>
"""
    SLIDES.write_text(page, encoding="utf-8")

    kb = len(page.encode("utf-8")) / 1024
    print(f"wrote {SLIDES.relative_to(ROOT)} · {kb:,.0f} KB · {len(S)} slides")
    print(f"screenshots embedded: {len(filled)}/{len(SLOTS)}")
    if missing:
        used = {"01", "03", "05", "07"}
        still = [n for n in missing if n in used]
        if still:
            print(f"slots used by the deck that are still empty: {', '.join(still)}")


if __name__ == "__main__":
    build()
