-- ─────────────────────────────────────────────────────────────────────
-- Lola PA — events schema for El Gouna (Hisham Nabil, Events Manager)
-- Run AFTER supabase_migration.sql (the memory schema) in the Supabase
-- SQL Editor. Safe to re-run: everything is IF NOT EXISTS / OR REPLACE.
-- ─────────────────────────────────────────────────────────────────────

-- ── Venues ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS venues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    zone            TEXT,                 -- Marina, Downtown, Kafr, hotel name, golf, beach
    kind            TEXT,                 -- hotel | marina | outdoor | indoor_hall | beach | club | square | other
    capacity_seated INT,
    capacity_standing INT,
    address         TEXT,
    contact_name    TEXT,
    contact_phone   TEXT,
    contact_email   TEXT,
    -- operational constraints that decide whether an event can happen here
    curfew_time     TIME,                 -- local noise curfew, e.g. 23:00
    power_notes     TEXT,                 -- generator needed? amps available?
    rigging_notes   TEXT,                 -- truss / weight limits / no-rig zones
    access_notes    TEXT,                 -- load-in windows, vehicle access, parking
    weather_exposed BOOLEAN DEFAULT TRUE, -- open-air (wind/rain contingency needed)
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Suppliers (production, AV, catering, talent, security, ...) ──────
CREATE TABLE IF NOT EXISTS suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    category        TEXT,                 -- av | staging | lighting | sound | catering | security |
                                          -- medical | talent | transport | accommodation | printing |
                                          -- media | permits | decor | power | other
    based_in        TEXT,                 -- El Gouna | Hurghada | Cairo | other
    contact_name    TEXT,
    contact_phone   TEXT,
    contact_email   TEXT,
    website         TEXT,
    lead_time_days  INT,                  -- realistic lead time for a booking
    payment_terms   TEXT,                 -- deposit %, account, due on delivery
    currency        TEXT DEFAULT 'EGP',
    reliable        BOOLEAN,              -- track record flag (NULL = untested)
    performance_notes TEXT,               -- how they actually performed on past events
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Events ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    event_type      TEXT,                 -- festival | concert | sporting | conference | corporate |
                                          -- activation | private | hotel_programming | other
    status          TEXT NOT NULL DEFAULT 'proposed',
                                          -- proposed | confirmed | in_production | live | completed | cancelled
    starts_on       DATE,
    ends_on         DATE,                 -- for multi-day; equals starts_on for single day
    setup_starts_on DATE,                 -- load-in / build day(s)
    teardown_ends_on DATE,                -- get-out day(s) — matters for venue clashes
    venue_id        UUID REFERENCES venues(id) ON DELETE SET NULL,
    venue_text      TEXT,                 -- free-text venue while unconfirmed ('probably Marina')
    attendance_expected INT,
    audience        TEXT,                 -- public | invited | ticket-holders | corporate | mixed
    ticket_price    NUMERIC(12,2),
    currency        TEXT DEFAULT 'EGP',
    owner           TEXT DEFAULT 'Hisham',-- who owns delivery
    description     TEXT,
    permits_status  TEXT DEFAULT 'unknown', -- unknown | not_started | applied | granted | refused
    permit_notes    TEXT,
    sponsors        TEXT,
    budget_estimate NUMERIC(14,2),
    budget_actual   NUMERIC(14,2),
    risk_notes      TEXT,
    source          TEXT DEFAULT 'telegram', -- how the record entered the system
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT events_date_order CHECK (
        ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on
    )
);

-- ── Event contacts (who is attached to which event, in what role) ────
CREATE TABLE IF NOT EXISTS event_contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID REFERENCES events(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    role            TEXT,                 -- sponsor | talent | venue_contact | supplier_contact |
                                          -- authority | hotel_gm | partner | staff | guest
    organisation    TEXT,
    phone           TEXT,
    email           TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Event tasks (operations follow-through) ──────────────────────────
CREATE TABLE IF NOT EXISTS event_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID REFERENCES events(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    detail          TEXT,
    owner           TEXT,
    due_on          DATE,
    status          TEXT NOT NULL DEFAULT 'open',   -- open | blocked | done | dropped
    critical        BOOLEAN DEFAULT FALSE,
    category        TEXT,                 -- permit | venue | supplier | talent | logistics |
                                          -- security | marketing | finance | admin | other
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_events_starts      ON events(starts_on);
CREATE INDEX IF NOT EXISTS idx_events_status      ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_venue       ON events(venue_id);
CREATE INDEX IF NOT EXISTS idx_events_dates       ON events(starts_on, ends_on);
CREATE INDEX IF NOT EXISTS idx_events_window      ON events(setup_starts_on, teardown_ends_on);
CREATE INDEX IF NOT EXISTS idx_tasks_event        ON event_tasks(event_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due   ON event_tasks(status, due_on);
CREATE INDEX IF NOT EXISTS idx_tasks_critical     ON event_tasks(critical) WHERE critical;
CREATE INDEX IF NOT EXISTS idx_contacts_event     ON event_contacts(event_id);
CREATE INDEX IF NOT EXISTS idx_suppliers_category ON suppliers(category);

-- ─────────────────────────────────────────────────────────────────────
-- Queries the assistant relies on
-- ─────────────────────────────────────────────────────────────────────

-- Events overlapping a given date window (any phase: setup, live, teardown)
CREATE OR REPLACE FUNCTION events_between(
    from_date DATE, to_date DATE
) RETURNS TABLE(
    id UUID, name TEXT, event_type TEXT, status TEXT,
    starts_on DATE, ends_on DATE, venue TEXT, attendance_expected INT,
    permits_status TEXT
) LANGUAGE sql STABLE AS $$
    SELECT e.id, e.name, e.event_type, e.status,
           e.starts_on, e.ends_on, COALESCE(v.name, e.venue_text) AS venue,
           e.attendance_expected, e.permits_status
    FROM events e
    LEFT JOIN venues v ON v.id = e.venue_id
    WHERE e.status <> 'cancelled'
      AND COALESCE(e.setup_starts_on, e.starts_on) <= to_date
      AND COALESCE(e.teardown_ends_on, e.ends_on, e.starts_on) >= from_date
    ORDER BY e.starts_on;
$$;

-- Clash detection: events sharing a venue whose full windows overlap
CREATE OR REPLACE FUNCTION venue_clashes(
    window_days INT DEFAULT 0
) RETURNS TABLE(
    venue TEXT, event_a TEXT, a_starts DATE, a_ends DATE,
    event_b TEXT, b_starts DATE, b_ends DATE, overlap_days INT
) LANGUAGE sql STABLE AS $$
    SELECT COALESCE(v.name, a.venue_text) AS venue,
           a.name, COALESCE(a.setup_starts_on, a.starts_on), COALESCE(a.teardown_ends_on, a.ends_on),
           b.name, COALESCE(b.setup_starts_on, b.starts_on), COALESCE(b.teardown_ends_on, b.ends_on),
           (LEAST(COALESCE(a.teardown_ends_on, a.ends_on, a.starts_on),
                  COALESCE(b.teardown_ends_on, b.ends_on, b.starts_on))
            - GREATEST(COALESCE(a.setup_starts_on, a.starts_on),
                       COALESCE(b.setup_starts_on, b.starts_on)) + 1)::INT
    FROM events a
    JOIN events b
      ON b.id > a.id
     AND b.venue_id IS NOT NULL
     AND b.venue_id = a.venue_id
    LEFT JOIN venues v ON v.id = a.venue_id
    WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
      AND COALESCE(b.setup_starts_on, b.starts_on) <= COALESCE(a.teardown_ends_on, a.ends_on, a.starts_on) + window_days
      AND COALESCE(a.setup_starts_on, a.starts_on) <= COALESCE(b.teardown_ends_on, b.ends_on, b.starts_on) + window_days
    ORDER BY 2;
$$;

-- What is at risk: open critical items on events that are near
CREATE OR REPLACE FUNCTION at_risk(
    horizon_days INT DEFAULT 30
) RETURNS TABLE(
    event TEXT, starts_on DATE, days_away INT, permits_status TEXT,
    open_tasks BIGINT, overdue_tasks BIGINT, venue TEXT
) LANGUAGE sql STABLE AS $$
    SELECT e.name, e.starts_on,
           (e.starts_on - CURRENT_DATE)::INT,
           e.permits_status,
           COUNT(t.id) FILTER (WHERE t.status = 'open'),
           COUNT(t.id) FILTER (WHERE t.status = 'open' AND t.due_on < CURRENT_DATE),
           COALESCE(v.name, e.venue_text)
    FROM events e
    LEFT JOIN venues v ON v.id = e.venue_id
    LEFT JOIN event_tasks t ON t.event_id = e.id
    WHERE e.status NOT IN ('completed', 'cancelled')
      AND e.starts_on IS NOT NULL
      AND e.starts_on BETWEEN CURRENT_DATE AND CURRENT_DATE + horizon_days
    GROUP BY e.id, e.name, e.starts_on, e.permits_status, v.name, e.venue_text
    HAVING COUNT(t.id) FILTER (WHERE t.status = 'open' AND t.critical) > 0
        OR e.permits_status IN ('unknown', 'not_started')
        OR e.venue_id IS NULL
    ORDER BY e.starts_on;
$$;

-- ── updated_at maintenance ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['venues','suppliers','events','event_tasks'] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s;
             CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION touch_updated_at();', t);
    END LOOP;
END $$;
