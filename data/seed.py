"""Seed data/bells.db with one realistic demo wedding.

Deterministic: running it twice produces the same database. It drops and
recreates every table from schema.sql, so it is safe to re-run.

Run from anywhere:
    backend/.venv/bin/python data/seed.py
"""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "bells.db"
SCHEMA_PATH = DATA_DIR / "schema.sql"

WEDDING_ID = 1
NOW = "2026-10-20T09:00:00"  # fixed "last updated" stamp so seeds are reproducible


# --------------------------------------------------------------------------
# The wedding
# --------------------------------------------------------------------------

WEDDING = {
    "id": WEDDING_ID,
    "couple_names": "Elena & Matteo",
    "date": "2027-06-12",
    "city": "Ravello, Amalfi Coast",
    "country": "Italy",
    "timezone": "Europe/Rome",
    "currency": "EUR",
}


# --------------------------------------------------------------------------
# Hotels — (id, name, address, block_code, nightly_rate, book_by, url, km)
#
# These are real hotels on the Amalfi Coast and the links are live Booking.com
# searches for them. The room-block codes, nightly rates and booking deadlines
# are demo values invented for this project — swap in the couple's real block
# details before sending this to anyone.
# --------------------------------------------------------------------------

BOOKING = "https://www.booking.com/searchresults.html?ss="

HOTELS = [
    (1, "Palazzo Avino", "Via San Giovanni del Toro 28, Ravello", "BELLS-PA",
     520.0, "2027-04-15", BOOKING + "Palazzo+Avino+Ravello", 0.5),
    (2, "Hotel Rufolo", "Via San Francesco 1, Ravello", "BELLS-RUF",
     260.0, "2027-04-30", BOOKING + "Hotel+Rufolo+Ravello", 0.3),
    (3, "Hotel Villa Romana", "Via Lama 1, Minori", "BELLS-VR",
     150.0, "2027-05-10", BOOKING + "Hotel+Villa+Romana+Minori", 7.2),
]


# --------------------------------------------------------------------------
# Shuttle runs — (id, direction, depart_at, from, to, capacity)
# seats_taken is computed from the guests assigned below.
# --------------------------------------------------------------------------

AIRPORT = "Naples International Airport (NAP)"
HUB = "Ravello town square (hotel drop-offs)"

SHUTTLES = [
    (1, "arrival", "2027-06-10T11:30", AIRPORT, HUB, 14),
    (2, "arrival", "2027-06-10T16:00", AIRPORT, HUB, 14),
    (3, "arrival", "2027-06-10T21:15", AIRPORT, HUB, 8),
    (4, "arrival", "2027-06-11T10:45", AIRPORT, HUB, 14),
    (5, "arrival", "2027-06-11T15:30", AIRPORT, HUB, 14),
    (6, "departure", "2027-06-14T06:00", HUB, AIRPORT, 14),
    (7, "departure", "2027-06-14T11:00", HUB, AIRPORT, 14),
    (8, "departure", "2027-06-14T17:30", HUB, AIRPORT, 8),
]


# --------------------------------------------------------------------------
# Guests — (name, language, party_size, dietary, hotel_id)
# 40 guests across 5 languages. The first 12 also get flights (below).
#
# `party_size` here means what the invitation allows: 2 = "and guest". Whether
# that seat is actually used depends on PLUS_ONES below — a guest who has not
# named anyone counts as one person until they do.
# --------------------------------------------------------------------------

GUESTS = [
    # travelling guests (flights assigned below, in this order)
    ("Camille Fournier",        "fr", 2, None,              1),
    ("Mateo Herrera",           "es", 2, "no pork",         1),
    ("Nadia Whitfield",         "en", 1, "vegetarian",      2),
    ("Giulia Ferrari",          "it", 2, None,              2),
    ("Lukas Brenner",           "de", 2, "gluten-free",     1),
    ("Lucía Navarro",           "es", 1, "pescatarian",     3),
    ("Théo Marchand",           "fr", 2, None,              3),
    ("Grace Ellery",            "en", 2, None,              1),
    ("Alessandro Conti",        "it", 2, None,              1),
    ("Pablo Ortega",            "es", 1, "no shellfish",    3),
    ("Élodie Rousseau",         "fr", 2, None,              2),
    ("Niklas Wagner",           "de", 2, "vegan",           3),
    # local / already-in-country / driving guests
    ("Marco Bianchi",           "it", 2, None,              2),
    ("Chiara Bianchi",          "it", 1, None,              2),
    ("Luca Esposito",           "it", 2, None,              3),
    ("Francesca Romano",        "it", 2, "pescatarian",     3),
    ("Davide Greco",            "it", 1, None,              3),
    ("Sofia Marino",            "it", 2, None,              1),
    ("Matteo Rizzo",            "it", 2, None,              1),
    ("Valentina Costa",         "it", 2, "no nuts",         1),
    ("Pietro Gallo",            "it", 1, None,              1),
    ("Inés Delgado",            "es", 2, None,              3),
    ("Javier Romero",           "es", 2, None,              3),
    ("Carmen Vidal",            "es", 1, None,              2),
    ("Sofía Márquez",           "es", 2, None,              1),
    ("Hugo Lefèvre",            "fr", 2, None,              1),
    ("Margaux Bernard",         "fr", 1, "vegetarian",      2),
    ("Antoine Girard",          "fr", 2, None,              3),
    ("Juliette Moreau",         "fr", 2, "lactose-free",    3),
    ("Imogen Clarke",           "en", 2, None,              1),
    ("Declan O'Rourke",         "en", 2, None,              1),
    ("Rosie Bennett",           "en", 1, "vegan",           2),
    ("Daniel Okonkwo",          "en", 2, None,              2),
    ("Johanna Weiss",           "de", 2, None,              2),
    ("Felix Baumann",           "de", 1, None,              3),
    ("Marlene Keller",          "de", 2, "gluten-free",     3),
    ("Jonas Richter",           "de", 2, None,              1),
    ("Tessa Hargreaves",        "en", 1, None,              2),
    ("Owen Hartley",            "en", 2, "no pork",         2),
    ("Paula Ruiz",              "es", 2, None,              1),
]

# (arrival_flight, arrival_at, departure_at, shuttle_run_id) for the first 12 guests.
# Staggered across two days: 7 land on Jun 10, 5 on Jun 11.
TRAVEL = [
    ("AF 1278", "2027-06-10T10:05", "2027-06-14T12:40", 1),
    ("IB 3246", "2027-06-10T10:50", "2027-06-14T12:10", 1),
    ("U2 4515", "2027-06-10T14:30", "2027-06-14T08:05", 2),
    ("AZ 1272", "2027-06-10T15:10", "2027-06-14T13:25", 2),
    ("LH 1986", "2027-06-10T15:25", "2027-06-14T13:50", 2),
    ("FR 8214", "2027-06-10T20:35", "2027-06-14T19:30", 3),
    ("AF 1280", "2027-06-10T20:50", "2027-06-14T19:55", 3),
    ("BA 2608", "2027-06-11T09:40", "2027-06-14T12:40", 4),
    ("AZ 1274", "2027-06-11T10:15", "2027-06-14T08:05", 4),
    ("IB 3248", "2027-06-11T10:20", "2027-06-14T12:10", 4),
    ("AF 1282", "2027-06-11T14:45", "2027-06-14T19:30", 5),
    ("LH 1988", "2027-06-11T15:00", "2027-06-14T13:50", 5),
]

# Plus ones already named by the guest. Everyone invited with "and guest"
# (party_size 2 above) may name one; these have. The rest are invited to but
# have not said who yet, which is exactly what the host console should surface.
PLUS_ONES = {
    1:  ("Antoine Fournier", None),
    2:  ("Lucía Herrera", None),
    4:  ("Paolo Ferrari", None),
    5:  ("Anja Brenner", "gluten-free"),
    7:  ("Camille Marchand", None),
    8:  ("Oliver Ellery", None),
    9:  ("Beatrice Conti", None),
    12: ("Mia Wagner", "vegan"),
    13: ("Giorgia Bianchi", None),
    15: ("Elisa Esposito", None),
    16: ("Stefano Romano", "pescatarian"),
    18: ("Enzo Marino", None),
    20: ("Nico Costa", "no nuts"),
    23: ("Lucía Romero", None),
    25: ("Diego Márquez", None),
    26: ("Claire Lefèvre", None),
    29: ("Paul Moreau", "lactose-free"),
    30: ("Harry Clarke", None),
    34: ("Stefan Weiss", None),
    37: ("Lena Richter", None),
    40: ("Andrés Ruiz", None),
}

# RSVP state. Most have replied; a handful are still pending, two declined —
# so the host console has something real to show on day one.
# Guests who have not booked their room yet — the task strip nags these.
NOT_BOOKED = {1, 3, 8, 11, 16, 23, 30, 35}

RSVP_DECLINED = {17, 24, 33}
RSVP_PENDING = {6, 10, 19, 22, 28, 31, 36, 39}
RSVP_AT = "2027-04-12T10:00:00"

GUEST_NOTES = {
    3:  "Travelling solo, first time in Italy.",
    9:  "The groom's cousin — doing the second reading.",
    11: "Bringing her violin for the ceremony music.",
    12: "Vegan — confirmed with the caterer.",
    14: "Local, offering spare seats in her car.",
    21: "Wheelchair user — step-free route needed at the ceremony.",
    27: "Arriving early, staying on after the wedding.",
    35: "Photographer's brother, helping with the drone.",
}


# --------------------------------------------------------------------------
# Tables — (id, name, capacity, shape)
# --------------------------------------------------------------------------

TABLES = [
    (1, "Limone",    10, "round"),
    (2, "Gelsomino", 10, "round"),
    (3, "Ulivo",     10, "round"),
    (4, "Bouganville", 8, "round"),
    (5, "Capri",      8, "round"),
    (6, "Faraglioni", 8, "long"),
]

# Which side of the room each guest belongs to. The solver keeps a group on
# one or two tables rather than sprinkling it across six.
SEATING_GROUPS = {
    "bride family":       [1, 11, 26, 27, 28, 29],
    "groom family":       [4, 9, 13, 14, 18, 19],
    "university friends": [3, 8, 30, 31, 32, 33, 38],
    "work":               [2, 6, 10, 22, 23, 24, 25, 40],
    "school friends":     [5, 12, 34, 35, 36, 37],
    "neighbours":         [7, 15, 16, 17, 20, 21, 39],
}

# Who must sit together, and who must not. Both are hard: the solver reports
# anything it cannot satisfy rather than quietly breaking it.
# (guest_a, guest_b, kind, reason)
CONSTRAINTS = [
    (13, 14, "together", "Marco and Chiara Bianchi are married"),
    (18, 19, "together", "Sofia and Matteo grew up together"),
    (3,  30, "together", "Nadia asked to be seated with Imogen"),
    (26, 27, "together", "Hugo and Margaux travel together"),
    (9,  19, "apart",    "the groom's father and his ex-wife — do not reseat"),
    (22, 25, "apart",    "Inés and Sofía fell out last summer"),
    (5,  12, "apart",    "Lukas and Niklas are competitive about everything"),
    (2,  40, "apart",    "Mateo and Paula are newly separated"),
]

# --------------------------------------------------------------------------
# Wedding facts — the agent's ONLY source of truth.
# (topic, question_pattern, answer, source, is_public)
# --------------------------------------------------------------------------

FACTS = [
    ("ceremony_time",
     "what time is the ceremony; when does it start; when should I arrive",
     "The ceremony begins at 17:00 on Saturday 12 June 2027 on the garden "
     "terrace at Palazzo Fiore, looking over the Gulf of Salerno. Please be "
     "seated by 16:40 — the aisle closes once the bride is announced.",
     "bride", 1),

    ("ceremony_venue",
     "where is the ceremony; venue address; how do I get to the venue",
     "Villa Cimbrone, Via Santa Chiara 26, Ravello. It is a ten-minute walk "
     "from Ravello's main square along a flat pedestrian lane — no steps on "
     "that route, but allow a little longer than the map says.",
     "venue contract", 1),

    ("reception",
     "when is dinner; what happens after the ceremony; is there an afterparty",
     "Aperitivo on the lemon terrace from 18:00, dinner at 19:30, dancing "
     "until 01:00. The afterparty moves down to the bar on the square "
     "afterwards — optional, pay your own tab.", "bride", 1),

    ("dress_code",
     "what is the dress code; what should I wear; can I wear white",
     "Garden formal. Men: linen or a light suit, no tie needed. Women: midi or "
     "long dress. Please avoid white or ivory. Bring flat or block-heeled "
     "shoes — the terrace is old stone and gravel, and stiletto heels sink "
     "into it.", "bride", 1),

    ("dress_code_colours",
     "what colours should I avoid; is there a palette",
     "No white, ivory or cream. The wedding party wears olive and sand, so "
     "guests are asked to avoid those two shades. Everything else is welcome.",
     "bride", 1),

    ("welcome_dinner",
     "is there a welcome dinner; what happens on Friday",
     "Welcome dinner on Friday 11 June at 20:00 in the courtyard at Villa "
     "delle Rose, Scala. Casual dress. All guests are invited, including "
     "children.", "groom", 1),

    ("brunch",
     "is there a brunch; what happens on Sunday",
     "Farewell brunch on Sunday 13 June, 11:00–14:00 on the sea terrace at "
     "Hotel Villa Romana in Minori. Drop in any time — no seating plan.",
     "bride", 1),

    ("kids_policy",
     "can I bring my kids; are children invited; is there childcare",
     "Children are warmly welcome at the welcome dinner and the brunch. The "
     "ceremony and dinner on Saturday are adults-only after 19:00. Two vetted "
     "sitters are available at Palazzo Avino from 18:30 — book by 1 May 2027 "
     "through the host.", "bride", 1),

    ("plus_ones",
     "can I bring a plus one; is my partner invited",
     "Plus-ones were named on your invitation. If your invitation says 'and "
     "guest', you may bring one person — tell the host their name by 1 May "
     "2027 so the seating plan and shuttle seats can be set.", "bride", 1),

    ("gifts",
     "what should I bring as a gift; is there a registry; cash gift",
     "Your presence is the gift. If you would like to give something, there is "
     "a small registry (see the registry page in this app) or a honeymoon "
     "fund. A cash gift in an envelope — a busta — is completely normal here, "
     "and there is a gift table by the entrance.", "groom", 1),

    ("registry_shipping",
     "where do I ship the registry gift; delivery address",
     "Registry items ship to the couple's home address in Milan — the address "
     "is filled in automatically at checkout on the registry links. Please do "
     "not ship anything to the hotels.", "groom", 1),

    ("rsvp",
     "how do I RSVP; what is the RSVP deadline; I need to change my RSVP",
     "RSVP deadline is 1 May 2027. To change your RSVP, dietary needs or party "
     "size after that date, message the host through this app — the caterer "
     "takes final numbers on 29 May.", "bride", 1),

    ("dietary",
     "I have an allergy; vegetarian options; gluten free",
     "The dinner menu has vegetarian, vegan, gluten-free and dairy-free "
     "options, all labelled at the buffet. Nut-free plates are made separately "
     "on request. Tell the host your needs by 29 May 2027.", "caterer email", 1),

    ("alcohol",
     "is there alcohol; open bar; can I bring my own drinks",
     "Open bar from 18:00 to 01:00: local Campania wine, beer, limoncello and "
     "soft drinks. Spirits are pay-your-own after midnight. Outside drinks are "
     "not allowed on the terrace.", "venue contract", 1),

    ("weather",
     "what is the weather like; how hot is it; do I need a jacket",
     "Mid-June on the Amalfi Coast is 26–30 °C by day and around 19 °C after "
     "sunset, almost always dry. The terrace is breezy once the sun goes down "
     "— bring a light wrap or jacket for the evening, and sunscreen and a hat "
     "for the daytime events.", "host research", 1),

    ("visas",
     "do I need a visa; visa for Italy; Schengen",
     "Italy is in the Schengen area. EU and EEA citizens need only an ID card. "
     "UK, US, Canadian, Australian and most Latin American passport holders "
     "can visit for up to 90 days without a visa, but from 2026 non-EU "
     "visitors may need an ETIAS travel authorisation — check the official "
     "ETIAS site before you fly. Other nationalities should check their own "
     "rules. This is guidance, not legal advice.", "host research", 1),

    ("passport_validity",
     "how long must my passport be valid; passport rules",
     "For Schengen, a non-EU passport must have been issued within the last "
     "10 years and be valid for at least 3 months beyond the day you leave "
     "Italy.", "host research", 1),

    ("flights_airport",
     "which airport should I fly into; nearest airport",
     "Fly into Naples (NAP), about 1 hour 40 minutes from Ravello by road. "
     "Rome Fiumicino (FCO) is often cheaper but a 3.5-hour drive — the wedding "
     "shuttles do not serve it.", "host research", 1),

    ("airport_transfers",
     "how do I get from the airport; is there a shuttle; taxi cost",
     "Free wedding shuttles meet the main arrival waves on 10 and 11 June — "
     "see the shuttle page in this app for times and to claim a seat. Outside "
     "those times, a private transfer from Naples to Ravello is about €140, or "
     "take the train to Salerno and the SITA bus up the coast.",
     "host research", 1),

    ("ferries",
     "is there a ferry; can I come by boat; ferry from Salerno",
     "In summer, ferries run from Salerno to Amalfi roughly hourly and the "
     "crossing takes about 35 minutes. From Amalfi it is a 25-minute bus or "
     "taxi up to Ravello. Ferries are cancelled in rough weather, so do not "
     "plan your wedding-day travel around one.", "host research", 1),

    ("shuttles_wedding_day",
     "how do I get to the ceremony; shuttle on the wedding day",
     "On 12 June a loop shuttle runs between all three hotels and the venue "
     "from 15:30 to 16:45, and back again from 23:30 until 01:30. No booking "
     "needed — just turn up at your hotel entrance.", "venue contract", 1),

    ("driving_parking",
     "can I drive; is there parking; ZTL",
     "Driving is not recommended. Ravello's centre is a ZTL — a restricted "
     "traffic zone — and the cameras fine you automatically if you enter "
     "without a permit. Public parking at the town garage is about €5 an hour "
     "and fills by mid-morning in June. Use the shuttles.", "host research", 1),

    ("hotels",
     "where should I stay; is there a room block; hotel discount",
     "Three hotels hold room blocks for this wedding at three price points — "
     "see the hotels page in this app for rates, block codes and booking "
     "deadlines. Quote the block code when you book; after the deadline the "
     "rooms go back to general sale.", "host", 1),

    ("sim_cards",
     "do I need a SIM card; mobile data; wifi",
     "All three hotels have free wifi. EU and UK phone plans mostly roam in "
     "Italy at no extra cost — check yours before you travel. Otherwise an "
     "Italian tourist SIM is about €20 for 20 GB at the Naples arrivals hall, "
     "and an eSIM bought before you fly is usually cheaper.",
     "host research", 1),

    ("money",
     "what currency; can I pay by card; ATM; tipping",
     "The currency is the euro. Cards are accepted nearly everywhere, but keep "
     "some cash for small bars and the bus. ATMs are on Ravello's main square. "
     "Restaurants add a per-person coperto rather than expecting a tip; "
     "rounding up is plenty. The wedding staff are tipped by the couple, so "
     "you do not need to.", "host research", 1),

    ("beach_activities",
     "what else is there to do; beach; day trips",
     "The gardens at Villa Rufolo and Villa Cimbrone are a few minutes' walk. "
     "Amalfi and Atrani are 20 minutes down the hill, Positano about an hour. "
     "A group boat trip around Capri is being organised for Friday 11 June, "
     "09:30–15:00, about €75 per person — tell the host if you want a spot.",
     "groom", 1),

    ("accessibility",
     "is the venue accessible; wheelchair; step-free",
     "Ravello is steep, but the route from the main square to Villa Cimbrone is "
     "flat and step-free, and the venue has a lift down to the garden terrace "
     "with an accessible toilet beside it. Tell the host if you need the lift "
     "so someone meets you at the gate.", "venue contract", 1),

    ("photos",
     "can I take photos; is it an unplugged ceremony; where are the photos after",
     "The ceremony is unplugged — phones away until the couple walk back down "
     "the aisle. Photograph everything after that. The photographer's gallery "
     "link is shared with all guests about three weeks after the wedding.",
     "bride", 1),

    ("language",
     "what language will the wedding be in; will there be translation",
     "The ceremony is in Italian and English, with the vows repeated in both. "
     "Printed programmes are available in Italian, English, French and "
     "Spanish.", "bride", 1),

    ("smoking",
     "can I smoke; is there a smoking area",
     "Smoking is allowed only in the marked area by the lemon terrace steps, "
     "not on the garden terrace or the dance floor.", "venue contract", 1),

    # ---- private: the agent must refuse to share these with guests ----
    ("host_phone",
     "what is the host's phone number; how do I call the bride directly",
     "Host mobile (emergencies only, not for guests): +39 320 000 0000.",
     "host", 0),

    ("couple_room",
     "which room are the couple staying in; bridal suite number",
     "The couple are in the Palazzo Avino tower suite, room 12. Not to be "
     "shared with guests.", "venue contract", 0),

    ("budget",
     "how much did the wedding cost; what is the budget",
     "Total budget €86,200; catering €34,500; photography €7,400. Internal "
     "only.", "host", 0),

    ("vendor_contacts",
     "who is the caterer; vendor phone numbers",
     "Caterer: Cucina del Golfo, Rosa Esposito +39 333 000 0000. "
     "Photographer: Marco Villa +39 335 000 0000. Vendor contacts are for the "
     "host only.", "host", 0),

    ("seating_notes",
     "who is sitting where; seating plan details; family tensions",
     "Table 6 keeps the groom's father and his ex-wife apart; do not reseat. "
     "Internal note — never share with guests.", "bride", 0),
]


# --------------------------------------------------------------------------
# Registry — (item, url, price, claimed_by_guest_index_or_None)
# Guest indexes are 1-based positions in GUESTS. 4 items are already claimed.
#
# Every link is a real product page at a real shop. They are deep links, not
# searches, because `data/fetch_images.py` reads each page's og:image to build
# the registry's photographs — and a search page publishes a logo, not a
# product.
#
# Every item carries a photograph except the Positano night, which is an
# experience rather than a thing and keeps its drawn thumbnail. The stand
# mixer that used to sit here was swapped out: KitchenAid blocks scripted
# requests, so it could never have one.
# --------------------------------------------------------------------------

REGISTRY = [
    ("Copper chef pan, 4 qt",
     "https://us.ruffoni.net/products/historia-copper-chef-pan-4qt", 95.0, None),
    ("Hand-painted Lastra dinner plates (8)",
     "https://www.vietri.com/products/lastra-european-dinner-plate", 240.0, 2),
    ("Espresso machine", "https://www.delonghi.com/", 420.0, None),
    ("Linen sheet set, king",
     "https://www.parachutehome.com/products/linen-sheet-set-white-f-q", 180.0, 7),
    ("Cast-iron casserole, 5 L",
     "https://greatjonesgoods.com/products/the-dutchess", 160.0, None),
    ("Oak serving board",
     "https://hawkinsnewyork.com/products/organic-cutting-board-oak", 65.0, None),
    ("Tufted runner rug",
     "https://fermliving.com/products/stille-tufted-runner-dark-pecan", 310.0, None),
    ("Honeymoon: one night in Positano",
     "https://www.booking.com/city/it/positano.html", 150.0, 13),
    ("Honeymoon: boat day around Capri",
     "https://www.getyourguide.com/capri-l1082/", 200.0, None),
    ("Countertop oven",
     "https://fromourplace.com/products/wonder-oven-pro", 325.0, None),
    ("Barocco liquor glasses (set of 6)",
     "https://www.vietri.com/products/barocco-amber-liquor-glass", 70.0, 25),
    ("Linen quilted throw",
     "https://hawkinsnewyork.com/products/simple-linen-quilted-throw-olive", 85.0, None),
    ("Classic cookbooks, boxed set",
     "https://juniperbooks.com/products/classic-cookbooks-set", 55.0, None),
    ("Portable garden lamp",
     "https://fermliving.com/products/arum-portable-lamp-cashmere", 90.0, None),
    ("Italy Picnic, framed print",
     "https://theposterclub.com/products/aoa-atelier-italy-picnic", 130.0, None),
]

# item position (1-based) -> the committed photo under frontend/public.
# Written by `data/fetch_images.py --write`, then pasted here so the paths
# survive a re-seed. Items missing from this map draw their own thumbnail.
IMAGES: dict[int, str] = {
    1: "/registry/1.webp",
    2: "/registry/2.webp",
    3: "/registry/3.webp",
    4: "/registry/4.webp",
    5: "/registry/5.webp",
    6: "/registry/6.webp",
    7: "/registry/7.webp",
    8: "/registry/8.webp",
    9: "/registry/9.webp",
    10: "/registry/10.webp",
    11: "/registry/11.webp",
    12: "/registry/12.webp",
    13: "/registry/13.webp",
    14: "/registry/14.webp",
    15: "/registry/15.webp",
}

CLAIMED_AT = {
    2:  "2027-03-02T18:40:00",
    7:  "2027-03-11T09:15:00",
    13: "2027-04-01T21:02:00",
    25: "2027-04-19T12:30:00",
}


# --------------------------------------------------------------------------
# A couple of escalations so the host console is not empty on first run.
# --------------------------------------------------------------------------

ESCALATIONS = [
    (1, 9, "Can we leave our luggage somewhere on the day we check out?", "open",
     "Palazzo Avino holds luggage at reception until 18:00 on check-out day. "
     "(Draft — please confirm whether the other two hotels do the same.)",
     None, "2027-04-20T08:12:00", None),
    (2, 3, "Can I check in early at Hotel Rufolo on 10 June?", "answered",
     "Standard check-in is 14:00; early check-in depends on availability.",
     "I asked the hotel — they will hold your room from 11:00 on 10 June, free "
     "of charge. Just mention the BELLS-RUF block at the desk.",
     "2027-04-18T16:05:00", "2027-04-18T19:40:00"),
]


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def slugify(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(c.lower() if c.isalnum() else "." for c in stripped).strip(".")


def email_for(name: str) -> str:
    return f"{slugify(name).replace('..', '.')}@example.com"


def phone_for(index: int) -> str:
    """Deterministic, obviously-fake demo number."""
    return f"+39 320 {100 + index:03d} {1000 + index * 7:04d}"


def build_guest_rows() -> list[tuple]:
    rows = []
    for i, (name, lang, party, diet, hotel_id) in enumerate(GUESTS, start=1):
        flight = arrival = departure = None
        run_id = None
        if i <= len(TRAVEL):
            flight, arrival, departure, run_id = TRAVEL[i - 1]
        if i in RSVP_DECLINED:
            status, at = "declined", RSVP_AT
        elif i in RSVP_PENDING:
            status, at = "pending", None
        else:
            status, at = "attending", RSVP_AT

        allowed = 1 if party >= 2 else 0
        p1_name, p1_diet = PLUS_ONES.get(i, (None, None))
        if not allowed or status != "attending":
            p1_name, p1_diet = None, None
        seats = 1 + (1 if p1_name else 0)

        booked = 0 if (i in NOT_BOOKED or status != "attending") else 1
        group = next((g for g, ids in SEATING_GROUPS.items() if i in ids), None)
        rows.append((
            i, WEDDING_ID, name, email_for(name), lang, seats, status, at, diet,
            allowed, p1_name, p1_diet,
            phone_for(i), flight, arrival, departure, hotel_id, booked, group, run_id,
            GUEST_NOTES.get(i),
        ))
    return rows


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        conn.execute(
            "INSERT INTO weddings (id, couple_names, date, city, country, timezone, currency)"
            " VALUES (:id, :couple_names, :date, :city, :country, :timezone, :currency)",
            WEDDING,
        )

        conn.executemany(
            "INSERT INTO hotels (id, wedding_id, name, address, block_code,"
            " nightly_rate, book_by_date, url, distance_km)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(h[0], WEDDING_ID, *h[1:]) for h in HOTELS],
        )

        conn.executemany(
            "INSERT INTO shuttle_runs (id, wedding_id, direction, depart_at,"
            " from_loc, to_loc, capacity, seats_taken) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            [(s[0], WEDDING_ID, *s[1:]) for s in SHUTTLES],
        )

        conn.executemany(
            "INSERT INTO tables (id, wedding_id, name, capacity, shape)"
            " VALUES (?, ?, ?, ?, ?)",
            [(t[0], WEDDING_ID, *t[1:]) for t in TABLES],
        )

        guest_rows = build_guest_rows()
        conn.executemany(
            "INSERT INTO guests (id, wedding_id, name, email, language, party_size,"
            " rsvp_status, rsvp_at, dietary, plus_one_allowed, plus_one_name,"
            " plus_one_dietary, phone, arrival_flight, arrival_at,"
            " departure_at, hotel_id, hotel_booked, seating_group, shuttle_run_id, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            guest_rows,
        )

        # seats_taken follows from who is actually on each run
        conn.execute(
            "UPDATE shuttle_runs SET seats_taken = COALESCE(("
            "  SELECT SUM(g.party_size) FROM guests g WHERE g.shuttle_run_id = shuttle_runs.id"
            "    AND g.rsvp_status != 'declined'"
            "), 0)"
        )
        over = conn.execute(
            "SELECT id, seats_taken, capacity FROM shuttle_runs WHERE seats_taken > capacity"
        ).fetchall()
        if over:
            raise AssertionError(f"shuttle runs oversubscribed: {over}")

        conn.executemany(
            "INSERT INTO wedding_facts (wedding_id, topic, question_pattern, answer,"
            " source, is_public, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(WEDDING_ID, *f, NOW) for f in FACTS],
        )

        conn.executemany(
            "INSERT INTO registry (id, wedding_id, item, url, image_url, price,"
            " claimed_by_guest_id, claimed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (i, WEDDING_ID, item, url, IMAGES.get(i), price, guest_id,
                 CLAIMED_AT.get(guest_id) if guest_id else None)
                for i, (item, url, price, guest_id) in enumerate(REGISTRY, start=1)
            ],
        )

        conn.executemany(
            "INSERT INTO seating_constraints (wedding_id, guest_a, guest_b, kind, reason)"
            " VALUES (?, ?, ?, ?, ?)",
            [(WEDDING_ID, *c) for c in CONSTRAINTS],
        )

        conn.executemany(
            "INSERT INTO escalations (id, wedding_id, guest_id, question, status,"
            " draft_answer, host_answer, created_at, resolved_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(e[0], WEDDING_ID, *e[1:]) for e in ESCALATIONS],
        )

        conn.commit()
    finally:
        conn.close()

    report()


def report() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        def one(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]

        print(f"Seeded {DB_PATH}")
        print(f"  wedding       : {WEDDING['couple_names']} — {WEDDING['date']}, "
              f"{WEDDING['city']}, {WEDDING['country']}")
        print(f"  guests        : {one('SELECT COUNT(*) FROM guests')} "
              f"({one('SELECT COUNT(DISTINCT language) FROM guests')} languages, "
              f"{one('SELECT SUM(party_size) FROM guests')} seats)")
        print(f"  with flights  : {one('SELECT COUNT(*) FROM guests WHERE arrival_flight IS NOT NULL')}")
        print(f"  tables        : {one('SELECT COUNT(*) FROM tables')} "
              f"({one('SELECT SUM(capacity) FROM tables')} seats) · "
              f"{one('SELECT COUNT(*) FROM seating_constraints')} constraints")
        print(f"  rooms booked  : "
              f"{one('SELECT COUNT(*) FROM guests WHERE hotel_booked = 1')} of "
              f"{one("SELECT COUNT(*) FROM guests WHERE rsvp_status = 'attending'")} attending")
        print(f"  plus ones     : "
              f"{one('SELECT COUNT(*) FROM guests WHERE plus_one_name IS NOT NULL')} named, "
              f"{one("SELECT COUNT(*) FROM guests WHERE plus_one_allowed = 1 AND plus_one_name IS NULL AND rsvp_status = 'attending'")} invited but unnamed")
        print(f"  rsvp          : "
              f"{one("SELECT COUNT(*) FROM guests WHERE rsvp_status = 'attending'")} attending, "
              f"{one("SELECT COUNT(*) FROM guests WHERE rsvp_status = 'declined'")} declined, "
              f"{one("SELECT COUNT(*) FROM guests WHERE rsvp_status = 'pending'")} pending")
        print(f"  hotels        : {one('SELECT COUNT(*) FROM hotels')}")
        print(f"  shuttle runs  : {one('SELECT COUNT(*) FROM shuttle_runs')}")
        print(f"  wedding_facts : {one('SELECT COUNT(*) FROM wedding_facts')} "
              f"({one('SELECT COUNT(*) FROM wedding_facts WHERE is_public = 0')} private)")
        print(f"  registry      : {one('SELECT COUNT(*) FROM registry')} "
              f"({one('SELECT COUNT(*) FROM registry WHERE claimed_by_guest_id IS NOT NULL')} claimed)")
        open_esc = one("SELECT COUNT(*) FROM escalations WHERE status = 'open'")
        print(f"  escalations   : {one('SELECT COUNT(*) FROM escalations')} "
              f"({open_esc} open)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
