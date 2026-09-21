-- ─────────────────────────────────────────────────────────────────────
-- Lola PA — events schema, v2 additions
--
-- Run AFTER supabase_events_migration.sql. Safe to re-run (IF NOT EXISTS).
--
-- Three gaps this closes, each found by looking at how real event systems
-- model the same problems:
--
-- 1. RECURRING SERIES. The original schema could only express one-off
--    events, so the Marina Street Festival (weekly), Cook's Club pool
--    parties (daily) and Casa Cook BBQ nights (weekly) would have been
--    re-entered every single week. That is both wasted effort and a
--    correctness risk: re-entered rows drift, and a series that drifts
--    cannot be reasoned about. Modelled as a parent series row plus
--    occurrences, which is how openSUSE/osem splits a conference from its
--    scheduled events, and how resource schedulers separate a booking rule
--    from a booking instance.
--
-- 2. WEATHER DEPENDENCY. El Gouna's largest recurring event class is
--    wind-driven watersports. The original schema had no way to say "this
--    event is cancelled without wind" or "this event is ruined by rain",
--    so nothing could ever warn about it. Now a first-class column.
--
-- 3. APPROVAL STEPS. permits_status was a single field. Real town-wide
--    events (GFF, Boat Show) need several separate sign-offs from different
--    bodies, each tracked independently, and "which approval is outstanding"
--    is the question that actually gets asked. Modelled as rows, not a
--    single status.
-- ─────────────────────────────────────────────────────────────────────

-- ── 1. Recurring series ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS event_series (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,     -- e.g. 'Marina Street Festival'
    event_type      TEXT,
    venue_id        UUID REFERENCES venues(id) ON DELETE SET NULL,
    venue_text      TEXT,
    -- 'daily' | 'weekly' | 'fortnightly' | 'monthly' | 'seasonal' | 'custom'
    recurrence      TEXT NOT NULL DEFAULT 'weekly',
    -- 1=Monday .. 7=Sunday, for weekly recurrences. Postgres DOW is 0=Sunday.
    weekday         INT CHECK (weekday IS NULL OR weekday BETWEEN 1 AND 7),
    starts_on       DATE,                     -- season start
    ends_on         DATE,                     -- season end (NULL = open-ended)
    attendance_typical INT,
    audience        TEXT,
    permits_status  TEXT DEFAULT 'unknown',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Link one-off events to the series they belong to. NULL for standalone events.
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS series_id UUID REFERENCES event_series(id) ON DELETE SET NULL;

-- ── 2. Weather dependency ────────────────────────────────────────────

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS weather_dependency TEXT NOT NULL DEFAULT 'none';
-- 'none'        indoor or weather-immune
-- 'rain_risk'   outdoor, degraded by rain
-- 'rain_fatal'  outdoor, cancelled by rain
-- 'wind_required' watersports: useless without wind
-- 'wind_fatal'  cancelled in high wind (rigging, staging, balloons)

ALTER TABLE event_series
    ADD COLUMN IF NOT EXISTS weather_dependency TEXT NOT NULL DEFAULT 'none';

-- Minimum and ideal wind speed in knots, for watersports events. Nullable
-- everywhere else; a kitesurf competition has a real operating window and a
-- generic 'windy' note does not capture it.
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS wind_min_knots INT,
    ADD COLUMN IF NOT EXISTS wind_max_knots INT;

-- ── 3. Approval steps ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS event_approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID REFERENCES events(id) ON DELETE CASCADE,
    -- who: 'orascom' | 'venue' | 'authority' | 'police' | 'civil_defence' |
    --      'tourism' | 'maritime' | 'other'
    authority       TEXT NOT NULL,
    authority_name  TEXT,                     -- the specific body or person
    -- 'not_started' | 'applied' | 'in_review' | 'granted' | 'refused' | 'expired'
    status          TEXT NOT NULL DEFAULT 'not_started',
    applied_on      DATE,
    decided_on      DATE,
    expires_on      DATE,
    reference       TEXT,                     -- their reference number
    conditions      TEXT,                     -- conditions attached to a grant
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_series_active   ON event_series(active) WHERE active;
CREATE INDEX IF NOT EXISTS idx_events_series   ON events(series_id);
CREATE INDEX IF NOT EXISTS idx_approvals_event ON event_approvals(event_id);
CREATE INDEX IF NOT EXISTS idx_approvals_state ON event_approvals(status);

-- ─────────────────────────────────────────────────────────────────────
-- Functions
-- ─────────────────────────────────────────────────────────────────────

-- Which recurring series should be running on a given date, and is there a
-- one-off event already covering it? Answers "what is on this Saturday"
-- including the recurring programming that never appears as a new event.
CREATE OR REPLACE FUNCTION series_on(
    on_date DATE
) RETURNS TABLE(
    series TEXT, recurrence TEXT, venue TEXT, attendance_typical INT,
    weather_dependency TEXT, covered_by_event TEXT
) LANGUAGE sql STABLE AS $$
    SELECT s.name, s.recurrence, COALESCE(v.name, s.venue_text),
           s.attendance_typical, s.weather_dependency,
           (SELECT e.name FROM events e
             WHERE e.series_id = s.id
               AND COALESCE(e.setup_starts_on, e.starts_on) <= on_date
               AND COALESCE(e.teardown_ends_on, e.ends_on, e.starts_on) >= on_date
               AND e.status <> 'cancelled'
             LIMIT 1) AS covered_by_event
    FROM event_series s
    LEFT JOIN venues v ON v.id = s.venue_id
    WHERE s.active
      AND (s.starts_on IS NULL OR s.starts_on <= on_date)
      AND (s.ends_on IS NULL OR s.ends_on >= on_date)
      AND (
            (s.recurrence = 'daily')
         OR (s.recurrence = 'weekly' AND EXTRACT(ISODOW FROM on_date)::INT = s.weekday)
         OR (s.recurrence = 'fortnightly' AND s.starts_on IS NOT NULL
             AND EXTRACT(ISODOW FROM on_date)::INT = s.weekday
             AND ((on_date - s.starts_on) / 7) % 2 = 0)
         OR (s.recurrence = 'monthly' AND s.starts_on IS NOT NULL
             AND EXTRACT(DAY FROM on_date) = EXTRACT(DAY FROM s.starts_on))
         OR (s.recurrence NOT IN ('daily','weekly','fortnightly','monthly'))
      )
    ORDER BY s.name;
$$;

-- Approvals still outstanding on events that are near. This is the question
-- that actually gets asked: not "what is the permit status" but "which
-- sign-off is missing and how long have we got".
CREATE OR REPLACE FUNCTION approvals_outstanding(
    horizon_days INT DEFAULT 60
) RETURNS TABLE(
    event TEXT, starts_on DATE, days_away INT,
    authority TEXT, authority_name TEXT, status TEXT, applied_on DATE
) LANGUAGE sql STABLE AS $$
    SELECT e.name, e.starts_on, (e.starts_on - CURRENT_DATE)::INT,
           a.authority, a.authority_name, a.status, a.applied_on
    FROM events e
    JOIN event_approvals a ON a.event_id = e.id
    WHERE e.status NOT IN ('completed', 'cancelled')
      AND e.starts_on IS NOT NULL
      AND e.starts_on BETWEEN CURRENT_DATE AND CURRENT_DATE + horizon_days
      AND a.status NOT IN ('granted', 'refused')
    ORDER BY e.starts_on, a.authority;
$$;

-- Events whose weather dependency makes them vulnerable, for the briefing
-- and for a wind check on watersports days.
CREATE OR REPLACE FUNCTION weather_sensitive_events(
    horizon_days INT DEFAULT 14
) RETURNS TABLE(
    event TEXT, starts_on DATE, days_away INT, weather_dependency TEXT,
    wind_min_knots INT, wind_max_knots INT, venue TEXT
) LANGUAGE sql STABLE AS $$
    SELECT e.name, e.starts_on, (e.starts_on - CURRENT_DATE)::INT,
           e.weather_dependency, e.wind_min_knots, e.wind_max_knots,
           COALESCE(v.name, e.venue_text)
    FROM events e
    LEFT JOIN venues v ON v.id = e.venue_id
    WHERE e.status NOT IN ('completed', 'cancelled')
      AND e.starts_on IS NOT NULL
      AND e.starts_on BETWEEN CURRENT_DATE AND CURRENT_DATE + horizon_days
      AND e.weather_dependency <> 'none'
    ORDER BY e.starts_on;
$$;

-- ── updated_at triggers for the new tables ───────────────────────────
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['event_series','event_approvals'] LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s;
             CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION touch_updated_at();', t);
    END LOOP;
END $$;
