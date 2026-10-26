# Bells 🔔

A wedding guest concierge for destination weddings.

MGT 409 final project — Dariga Zhuman.

Forty people are flying to a village on the Amalfi Coast and every one of them
has the same six questions. Bells answers them. Guests chat with a concierge
agent in whatever language they write in, RSVP, and claim gifts from a
wishlist. The couple run a console that turns every question the agent
*couldn't* answer into a fact it knows forever — so the same question is only
ever answered once, by a human, and never again.

**Live URL: none.** Bells runs locally; there is no deployment. Everything
below is the whole setup.

---

## Run it

Two terminals, about five minutes. **Backend first** — the frontend proxies to
it.

### 0. What you need

- Python 3.11 or newer
- Node 18 or newer
- a `PORTKEY_API_KEY` (preferred) or `OPENAI_API_KEY`

**Nothing else.** The seeded demo wedding is committed to this repo as
`data/bells.db`, so there is no database to create, migrate or populate. Clone,
add a key, run.

### 1. The key — and where to put it

Bells looks for a `.env` file in **two** places, and loads both if both exist:

1. **one folder above** this repo — `../.env`, sitting next to the `bells/`
   folder
2. this repo's own root — `bells/.env`

The repo-root one wins on conflict. If you keep a shared `.env` one level above
your submissions folder, it will be found with no extra setup — that is the
case this is built for.

Copy the template and fill in the key:

```bash
cp .env.example .env
```

The key is never printed or logged, including by the health route.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn main:app --reload --port 8000
```

Leave it running. Check it in another terminal:

```bash
curl http://localhost:8000/api/health
```

That reports the model, which `.env` files were found, and whether a key is
present — never the key itself. If `api_key_present` is `false`, step 1 did not
take, and `env_files_searched` in that same response tells you the two exact
paths it looked at.

Port 8000 has to be free: the frontend's dev proxy points at it by name. If
something else is already there, stop it first — changing the port means
changing [`frontend/vite.config.ts`](frontend/vite.config.ts) too.

### 3. Frontend — in a second terminal

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

### 4. Sign in

Bells has two front doors, both behind the sign-in screen at `/`:

- **As a guest** — press **“Just show me”** to be signed in as a random guest,
  or use the email an invitation went to, e.g.
  `camille.fournier@example.com`. A guest sees only their own booking; the
  guest list is never served to them.
- **As the couple** — the passcode is `bells`. The console is at `/host`.

Sessions are in memory and bound to one guest id, so no URL will serve one
guest another guest's dashboard, chat or pickup. Restarting the backend
invalidates every token; the frontend notices the 401 and returns you to
sign-in rather than half-loading. It is **not** production auth — no passwords,
no expiry, no CSRF story — and
[`backend/sessions.py`](backend/sessions.py) says so at the top.

### 5. Optional — regenerate the database

Only if you want to wipe it. The committed one is already seeded.

```bash
backend/.venv/bin/python data/seed.py
```

The seed is deterministic — same bytes every run. It creates one wedding:
**Elena & Matteo, 12 June 2027, Ravello on the Amalfi Coast, Italy** — with 40
guests across 5 languages (en/fr/es/it/de), 12 of them on staggered flights
into Naples over two days, 3 hotels with room-block codes and booking
deadlines, 8 shuttle runs, 6 dinner tables with seating constraints, 35
`wedding_facts` rows (5 of them `is_public = 0`, e.g. the host's phone number,
for testing that the agent refuses to leak them), 15 registry items with 4
claimed, and 2 host escalations.

`wedding_facts` is the single source of truth: the agent answers **only** from
rows in that table, and only those with `is_public = 1`.

### 6. Optional — reproduce the evidence

Each of these makes live model calls and writes its results into `output/`.
The results of the last run are already committed, so you can read them without
spending anything.

```bash
backend/.venv/bin/python output/solver_test.py        # no key needed
backend/.venv/bin/python output/agent_wiring_test.py  # no key needed
backend/.venv/bin/python output/safety_test.py        # ~15 live turns
backend/.venv/bin/python output/cost_test.py          # ~17 live turns
backend/.venv/bin/python output/escalation_loop.py    # ~6 live turns
```

See [Evidence](#evidence) for what each one proves.

---

## Evidence

Everything in `output/` was produced by running the real app, not by
describing it.

| file | what it shows |
| --- | --- |
| `safety_results.md` / `.json` | 12 hostile probes against the live agents: 6 privacy, 3 indirect prompt injection, 2 content-filter, 1 runaway-delegation. Every probe records the question, the reply and the verdict. |
| `cost_results.json` | the same 8 questions asked twice — once with every prompt cache busted, once warm — comparing tokens, cost, latency and whether the answers stayed correct. |
| `escalation_loop.json` | the host approval loop run end to end: three unanswerable questions escalate, the couple answer them in the console, and the agent answers them unaided afterwards. |
| `solver_results.json` | the shuttle solver checked against brute-force optimal. |
| `audit_trail.json` | every model turn and every confirmed host write, with tokens and cost. |
| `screenshots/` | screenshots of the running app, added by hand. |

---

## The guest side

The guest side is built for a phone, three months out, in another country —
so it answers "what do I have to do, and when" before anything else.

- **Wedding** — **Your three things** sits directly under the hero: what this
  guest still owes, computed from their own row. Unanswered RSVP, an unbooked
  room with the days left on the block, a missing flight. Each one resolves in
  place without leaving the page, and sending a flight solves a shuttle seat on
  the spot. When nothing is left it collapses to one line: *"You're all set."*
  Below that: the journey timeline (land → passport and bags → pickup →
  arrive, with the guest's own times), the hotel and block code, the registry,
  and the RSVP detail.
- **Gift registry** — the full wishlist, each item a real product at a real
  shop, shown as a 4:5 photograph. Tap
  *I'm buying this*, confirm, and the gift leaves everyone else's list, so two
  guests can never buy the same thing. Yours moves to a **Your gifts** section
  with an *Undo*. Who chose what is never shown — not even to the couple.

**RSVP** lives on the guest's own page as a single line once answered —
*"You and Antoine Fournier are coming"* with a **Change** button. Opening it
asks three things: coming or not, what you can't eat, and whether you're
bringing your plus one. The plus one is a **name**, not a headcount, with their
own dietary needs, because "2" tells the caterer and the seating plan nothing.

**Declining changes what the app shows and what the data holds.** A guest who
says they can't come loses their hotel card and their pickup card — neither is
held for them any more — and their shuttle seat is released server-side, so a
bus is not reserved for someone who isn't coming. The solver, the seat counts
and the host's totals all exclude declined guests. The registry and the chat
stay, because people who can't come still send gifts and still have questions.
Saying yes again puts them back in the next solve.

`party_size` is derived on the server — one, plus one more only if the
invitation says "and guest" *and* that guest has been named. It is the same
number the shuttle solver counts as seats, so an unnamed plus one gets no seat
and no plate, and the host console says how many of those there are.

The app itself is in English, and the chat says so: *write in any language and
Bells replies in the one you used*. The guest list spans English, Italian,
French, Spanish and German, and the concierge follows whichever language a
guest actually writes in.

**The concierge is never something you scroll to find.** On desktop it docks as
a sticky right-hand column; on a phone a bar pinned to the bottom reads *"Ask
Bells anything"* and opens a sheet. The suggested questions are contextual —
booking leads if the room is unbooked, the pickup leads in the week before the
flight, and after a reply the chips become follow-ups to what was just said.

Every assistant reply is rendered through `react-markdown`; the guest's own
messages are not parsed. Under each reply, an **open-by-default** line reads
*"Bells asked 2 agents · 2 tools · 6,744 tokens · $0.00061"* and expands to the
ordered tool trace.

---

## Layout

```
bells/
  backend/      FastAPI + PydanticAI (own .venv)
    config.py   env loading, model name, build_model(), require_api_key()
    main.py     API routes: guest + /api/host/*
    agents/     concierge, knowledge, logistics, registry + prompts/
    solver.py   deterministic shuttle solver (no LLM)
    audit.py    one audit record per turn
    sessions.py guest/host sign-in and the per-session boundary
  frontend/     React + Vite + TypeScript
    views/      SignInView, GuestView (/), HostView (/host)
  data/         schema.sql, seed.py, bells.db (committed, pre-seeded)
  output/       evidence: screenshots, token counts, test results
  .env.example
  AI_prompts.md prompt log
```

## Host console — `/host`

The couple's side, and the core of the idea: Bells does not just answer, it
**learns from the couple in one click**.

- **Inbox** — every question Bells couldn't answer, with its draft. *Approve*,
  *Edit & approve* or *Dismiss*. Approving writes the answer into
  `wedding_facts` as a new row (`source = 'host console'`), so the next guest
  who asks gets it straight from Bells. The toast says so: *"Bells will answer
  this itself from now on."*
- **Impact strip** — questions answered automatically, escalation rate, minutes
  saved, and how many facts Bells knows. The minutes-saved assumption (3 min per
  answered question) is **shown and editable on screen**, so the figure in the
  report can be traced to a number you can change and re-read.
- **Spend** — total tokens, cached vs uncached, cost, cost per guest, and a
  straight-line projection for 150 guests.
- **Guest list** — RSVPs at a glance: attending / declined / no reply, heads at
  the tables, the catering breakdown by dietary need (guests and their plus
  ones counted as separate people, because the caterer cooks per person), beds
  per hotel, plus ones named vs still unnamed, who is travelling and who has no
  shuttle seat, and the language split. Every number is counted live from
  `guests`.
- **Shuttles** — the solved runs as a timeline with passengers and seat fill, a
  *Re-solve* button, and the solver's before/after table against the naive
  one-transfer-per-booking baseline.

Impact and Spend both read `output/audit_trail.json`, so they can never
disagree, and they are zero until real turns have run — the numbers are
measured, never seeded. (`usage_log` holds the same figures in SQL, but
`seed.py` drops that table; the trail is the durable record.)

### Picture credits

The hero photograph and the Capri gift image are freely licensed works from
Wikimedia Commons, used under their terms with attribution:

| Image | Photographer | Licence | Source |
|---|---|---|---|
| Hero — Positano | Tanzania | CC BY-SA 4.0 | [Commons](https://commons.wikimedia.org/wiki/File:Province_of_Salerno_-_Positano_-_20200718143423.jpg) |
| Registry — Capri | Norbert Nagel | CC BY-SA 3.0 | [Commons](https://commons.wikimedia.org/wiki/File:Capri_island_-_Campania_-_Italy_-_July_12th_2013_-_16.jpg) |

Both are **CC BY-SA**: credit the photographer, and anything derived from the
image itself carries the same licence. The credit above satisfies that.

### Where the registry photographs come from

Each product image is the `og:image` published by that retailer's own product
page — the picture you get when you paste the link into a chat app — fetched
once by [`data/fetch_images.py`](data/fetch_images.py), resized to 800px and
saved as WebP under `frontend/public/registry/`. **This is a course demo**: the
images are used to illustrate a student project, each item links back to the
shop it came from, and nothing is served from their servers at run time.

The fetcher is an authoring tool, run by hand, **never called at request
time**. The WebP files are committed, so a fresh clone shows a full registry
offline with no API key.

```bash
backend/.venv/bin/python data/fetch_images.py          # dry run
backend/.venv/bin/python data/fetch_images.py --write  # save paths to the db
```

All fifteen items now carry a photograph. Two did not at first: KitchenAid
blocks scripted requests outright, so the stand mixer was swapped for a knife
set from a shop that serves its own images; and the Capri boat day is an
experience with no product page, so it uses the freely licensed photograph
credited above.

The drawn thumbnails in
[`GiftImage.tsx`](frontend/src/components/GiftImage.tsx) remain the fallback —
they appear if a committed file ever goes missing, so nothing renders a broken
image.

## The couple's concierge — `/host`

The same agent pattern as the guest side, with the two differences that matter:
it may read the whole roster, and it can change things.

**Reading** — `wedding_status()`, `find_gaps()`, `search_guests()`,
`list_registry()`. These run freely. `find_gaps()` is the one that earns its
keep: it returns every outstanding thing *with the names attached*, because the
couple can act on a name and cannot act on a percentage.

**Writing** — `add_fact`, `update_fact`, `add_registry_item`,
`remove_registry_item`, `resolve_escalation`, `resolve_shuttles`. None of these
change anything. Each validates its arguments, works out the before and after,
and parks a **proposal**. The console renders it as a card with **Do it** and
**Cancel**; the couple never have to type "yes".

The split is deliberate and it is the point of the design:

> The agent can only ever *describe* a change. The SQL that runs lives in
> [`proposals.py`](backend/proposals.py) and is chosen by the proposal's `kind`,
> not at inference time. Consent is a button press, not something a model
> decides it has heard.

Every confirmed write is logged with `before` and `after` values —
`audit.writes()` returns the change log.

**Guardrails that fire on their own**: `remove_registry_item` refuses outright
if a guest has already claimed the gift, and tells the couple who to thank
instead. Committing twice returns `409`.

**Messages** — `draft_blast(segment, intent)` writes **one message per
recipient**, in that recipient's own language, referencing their real
situation (their hotel, their block code, their deadline). It sends nothing.
Drafts land in the Messages panel grouped by segment, each editable inline,
with approve / skip / approve-all.

**Nothing is ever actually sent.** Approving marks a message ready and records
it; there is no WhatsApp or email sender wired up anywhere, and the place one
would go is marked with a comment in `main.py`. A course demo must not be able
to message real guests.

Things the couple can type:

```
add that the ceremony starts at 4 and cocktails at 5
who still hasn't told us if they're coming?
remind everyone who hasn't rsvp'd, gently, we need numbers by friday
take the stand mixer off the registry
Camille's flight moved to the evening, redo the shuttles
```

## Agents

One guest-facing boss over three specialists, all on `gpt-6-luna`, all capped
at `UsageLimits(request_limit=8)`.

| agent | file | tools |
|---|---|---|
| **Concierge** (guest-facing) | [`agents/concierge.py`](backend/agents/concierge.py) | `ask_knowledge`, `ask_logistics`, `ask_registry`, `escalate_to_host` |
| Knowledge | [`agents/knowledge.py`](backend/agents/knowledge.py) | `search_facts` |
| Logistics | [`agents/logistics.py`](backend/agents/logistics.py) | `get_pickup`, `list_runs`, `get_hotels`, `search_facts`, `solve_shuttles` |
| Registry | [`agents/registry.py`](backend/agents/registry.py) | `list_items`, `claim_item`, `unclaim_item` |

The concierge replies in the guest's own language (from `guests.language`)
while the specialists work in English over English-language facts.

Logistics reads `wedding_facts` through the same filtered query the knowledge
agent uses. It has to: a guest asking about luggage storage or which airport to
use is routed to logistics, and the answer to that lives in a fact the couple
wrote — not in the shuttle tables. Without it, a question the couple had
*already answered in the console* was escalated to them a second time.
`output/escalation_loop.json` is the before and after of exactly that.

Prompts live in [`backend/agents/prompts/`](backend/agents/prompts). Every
agent's instructions are [`hard_rules.md`](backend/agents/prompts/hard_rules.md)
plus its own file, so a safety change lands in all four at once and cannot
drift between them.

Three of the hard rules are enforced in SQL, not just in the prompt:

- private facts (`is_public = 0`) are filtered out in the query, so they never
  enter the model's context;
- `claimed_by_guest_id` is never selected into context, so the registry agent
  cannot name a claimer it was never told;
- `get_pickup` refuses any `guest_id` other than the one in the session.

Every tool call is logged to an ordered event trace (agent, tool, args, status,
duration, detail) that is returned with each reply for the UI to list, and
[`backend/audit.py`](backend/audit.py) appends one record per turn to
`output/audit_trail.json` and mirrors the token counts into `usage_log`.

`cost_usd` is `null` with `cost_basis: "unpriced"` unless you set
`BELLS_PRICE_INPUT_PER_MTOK` / `BELLS_PRICE_OUTPUT_PER_MTOK` (and optionally
`BELLS_PRICE_CACHED_INPUT_PER_MTOK`) in `.env`. Token counts are real either way.

Check the wiring with no API key and no token spend:

```bash
backend/.venv/bin/python output/agent_wiring_test.py
```

## Shuttle solver

[`backend/solver.py`](backend/solver.py) is plain deterministic Python — **no
LLM**. The agent calls it as a tool; it never reasons about the timetable
itself. `solve_shuttles(wedding_id)` clusters arriving guests into as few runs
as possible subject to: a run leaves 30 min after its last passenger lands,
nobody waits more than 90 min, and no run exceeds 14 seats. `explain_run()` and
`guest_pickup()` return guest-readable sentences.

Regenerate the evidence (uses a throwaway database — `data/bells.db` is never
touched):

```bash
backend/.venv/bin/python output/solver_test.py
```

It asserts every constraint, benchmarks against brute force, and writes
[`output/solver_results.json`](output/solver_results.json). On 40 guests /
75 seats: **40 runs → 15 runs (−62%), €5,600 → €2,100, 133.3 → 50.0
driver-hours**, at a cost of 16 extra minutes of waiting per person on average
(worst case 85 min, under the 90 min limit). Solve time ~3 ms. The cost
assumptions — €140 per private Naples→Ravello transfer, 200 min per round trip
— live in `solver.py` so the dashboard and the evidence script cite the same
two numbers.

## Model

Routed through Portkey (`https://api.portkey.ai/v1`) using
`OpenAIResponsesModel`. Default model is **`gpt-6-luna`**, the only model the
course key allows; override with an `OPENAI_MODEL` env var.
