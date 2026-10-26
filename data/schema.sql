-- Bells — wedding guest concierge for destination weddings.
-- SQLite schema. Timestamps are ISO-8601 strings in the wedding's local timezone
-- unless the column name says otherwise.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS usage_log;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS escalations;
DROP TABLE IF EXISTS registry;
DROP TABLE IF EXISTS seating_constraints;
DROP TABLE IF EXISTS guests;
DROP TABLE IF EXISTS tables;
DROP TABLE IF EXISTS shuttle_runs;
DROP TABLE IF EXISTS hotels;
DROP TABLE IF EXISTS wedding_facts;
DROP TABLE IF EXISTS weddings;

CREATE TABLE weddings (
    id           INTEGER PRIMARY KEY,
    couple_names TEXT NOT NULL,
    date         TEXT NOT NULL,          -- YYYY-MM-DD
    city         TEXT NOT NULL,
    country      TEXT NOT NULL,
    timezone     TEXT NOT NULL,          -- IANA tz, e.g. Europe/Rome
    currency     TEXT NOT NULL           -- ISO 4217, e.g. EUR
);

-- The single source of truth for the concierge agent.
-- The agent answers ONLY from rows in this table, and only where is_public = 1.
CREATE TABLE wedding_facts (
    id               INTEGER PRIMARY KEY,
    wedding_id       INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    topic            TEXT NOT NULL,      -- short slug, e.g. 'dress_code'
    question_pattern TEXT NOT NULL,      -- the guest-phrased questions this answers
    answer           TEXT NOT NULL,
    source           TEXT,               -- where the host got it ('bride', 'hotel email', ...)
    is_public        INTEGER NOT NULL DEFAULT 1 CHECK (is_public IN (0, 1)),
    updated_at       TEXT NOT NULL
);

CREATE INDEX idx_facts_wedding_public ON wedding_facts(wedding_id, is_public);
CREATE INDEX idx_facts_topic ON wedding_facts(topic);

CREATE TABLE hotels (
    id            INTEGER PRIMARY KEY,
    wedding_id    INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    address       TEXT,
    block_code    TEXT,                  -- room-block code guests quote when booking
    nightly_rate  REAL,                  -- in the wedding's currency
    book_by_date  TEXT,                  -- YYYY-MM-DD, block released after this
    url           TEXT,
    distance_km   REAL                   -- to the venue
);

CREATE TABLE shuttle_runs (
    id          INTEGER PRIMARY KEY,
    wedding_id  INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    direction   TEXT NOT NULL CHECK (direction IN ('arrival', 'departure')),
    depart_at   TEXT NOT NULL,
    from_loc    TEXT NOT NULL,
    to_loc      TEXT NOT NULL,
    capacity    INTEGER NOT NULL,
    seats_taken INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_shuttle_wedding ON shuttle_runs(wedding_id, direction, depart_at);

CREATE TABLE tables (
    id         INTEGER PRIMARY KEY,
    wedding_id INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    capacity   INTEGER NOT NULL,
    shape      TEXT NOT NULL DEFAULT 'round'
               CHECK (shape IN ('round', 'long', 'square'))
);

CREATE INDEX idx_tables_wedding ON tables(wedding_id);

CREATE TABLE guests (
    id              INTEGER PRIMARY KEY,
    wedding_id      INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    email           TEXT,
    language        TEXT NOT NULL DEFAULT 'en',   -- 'en','fr','es','it',...
    party_size      INTEGER NOT NULL DEFAULT 1,
    rsvp_status     TEXT NOT NULL DEFAULT 'pending'
                    CHECK (rsvp_status IN ('pending', 'attending', 'declined')),
    rsvp_at         TEXT,
    dietary         TEXT,
    -- party_size is derived: 1 + 1 if a plus one has been named.
    plus_one_allowed  INTEGER NOT NULL DEFAULT 0 CHECK (plus_one_allowed IN (0, 1)),
    plus_one_name     TEXT,
    plus_one_dietary  TEXT,
    phone           TEXT,
    arrival_flight  TEXT,
    arrival_at      TEXT,
    departure_at    TEXT,
    hotel_id        INTEGER REFERENCES hotels(id) ON DELETE SET NULL,
    hotel_booked    INTEGER NOT NULL DEFAULT 0 CHECK (hotel_booked IN (0, 1)),
    table_id        INTEGER REFERENCES tables(id) ON DELETE SET NULL,
    seating_group   TEXT,              -- 'bride family', 'university friends', ...
    shuttle_run_id  INTEGER REFERENCES shuttle_runs(id) ON DELETE SET NULL,
    notes           TEXT
);

CREATE INDEX idx_guests_wedding ON guests(wedding_id);
CREATE INDEX idx_guests_email ON guests(email);
CREATE INDEX idx_guests_rsvp ON guests(wedding_id, rsvp_status);

CREATE TABLE registry (
    id                INTEGER PRIMARY KEY,
    wedding_id        INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    item              TEXT NOT NULL,
    url               TEXT,
    image_url         TEXT,               -- optional photo; falls back to a drawn thumbnail
    price             REAL,
    claimed_by_guest_id INTEGER REFERENCES guests(id) ON DELETE SET NULL,
    claimed_at        TEXT
);

CREATE INDEX idx_registry_wedding ON registry(wedding_id);

-- Who must sit together, and who must not. The solver treats both as hard:
-- it will report a constraint it cannot satisfy rather than quietly break it.
CREATE TABLE seating_constraints (
    id         INTEGER PRIMARY KEY,
    wedding_id INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    guest_a    INTEGER NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    guest_b    INTEGER NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('together', 'apart')),
    reason     TEXT,
    CHECK (guest_a <> guest_b)
);

CREATE INDEX idx_constraints_wedding ON seating_constraints(wedding_id, kind);

-- Questions the agent could not answer from wedding_facts, handed to the host.
CREATE TABLE escalations (
    id           INTEGER PRIMARY KEY,
    wedding_id   INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    guest_id     INTEGER REFERENCES guests(id) ON DELETE SET NULL,
    question     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'answered', 'dismissed')),
    draft_answer TEXT,                   -- agent's suggestion, host edits it
    host_answer  TEXT,
    created_at   TEXT NOT NULL,
    resolved_at  TEXT
);

CREATE INDEX idx_escalations_status ON escalations(wedding_id, status);

CREATE TABLE messages (
    id         INTEGER PRIMARY KEY,
    wedding_id INTEGER NOT NULL REFERENCES weddings(id) ON DELETE CASCADE,
    guest_id   INTEGER REFERENCES guests(id) ON DELETE SET NULL,
    role       TEXT NOT NULL,            -- 'user' | 'assistant' | 'system'
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_messages_guest ON messages(guest_id, created_at);

-- Tokenomics evidence: one row per model call.
CREATE TABLE usage_log (
    id                 INTEGER PRIMARY KEY,
    wedding_id         INTEGER REFERENCES weddings(id) ON DELETE CASCADE,
    guest_id           INTEGER REFERENCES guests(id) ON DELETE SET NULL,
    agent              TEXT NOT NULL,    -- which agent made the call
    model              TEXT NOT NULL,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    cached_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);

CREATE INDEX idx_usage_wedding ON usage_log(wedding_id, created_at);
