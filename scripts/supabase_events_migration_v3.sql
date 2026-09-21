-- ─────────────────────────────────────────────────────────────────────
-- Lola PA — resource clash detection (v3)
--
-- Closes the gap left by venue_clashes(): two events can be at DIFFERENT
-- venues and still be impossible, because the same supplier or the same person
-- is needed for both on the same days.
--
-- That is a real El Gouna failure mode. Production, AV, staging and most
-- technical crew come in from Cairo or Hurghada, and the pool is small. In peak
-- season (Oct to Apr) the town runs several events at once, so "we booked the
-- same sound crew for two events" is exactly how a season goes wrong.
--
-- STRUCTURAL PROBLEM FOUND WHILE BUILDING THIS:
-- event_tasks had no column linking a task to a `suppliers` row. The supplier
-- was only ever named in free-text `title`, so there was no dependable way to
-- ask "which events need this supplier". Resource clashes cannot be detected
-- from prose. This migration adds the real foreign keys.
--
-- Safe to re-run.
-- ─────────────────────────────────────────────────────────────────────

-- ── Link tasks to real suppliers ─────────────────────────────────────
ALTER TABLE event_tasks
    ADD COLUMN IF NOT EXISTS supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL;

-- Link tasks to a named person too, so crew clashes are catchable: the same
-- freelancer booked for two events is as damaging as the same company.
ALTER TABLE event_tasks
    ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES event_contacts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_supplier ON event_tasks(supplier_id) WHERE supplier_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_contact  ON event_tasks(contact_id)  WHERE contact_id  IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────
-- Resource clash detection
-- ─────────────────────────────────────────────────────────────────────

-- Suppliers required by two events whose full windows (setup through teardown)
-- overlap. Only counts a supplier on a task that is still live: a done or
-- dropped task is not a claim on the supplier's time.
CREATE OR REPLACE FUNCTION supplier_clashes(
    window_days INT DEFAULT 0
) RETURNS TABLE(
    supplier TEXT, category TEXT,
    event_a TEXT, a_window TEXT, event_b TEXT, b_window TEXT,
    overlap_days INT, task_a TEXT, task_b TEXT
) LANGUAGE sql STABLE AS $$
    SELECT s.name, s.category,
           ea.name,
           to_char(COALESCE(ea.setup_starts_on, ea.starts_on), 'DD Mon') || ' to ' ||
           to_char(COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on), 'DD Mon'),
           eb.name,
           to_char(COALESCE(eb.setup_starts_on, eb.starts_on), 'DD Mon') || ' to ' ||
           to_char(COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on), 'DD Mon'),
           (LEAST(COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on),
                  COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on))
            - GREATEST(COALESCE(ea.setup_starts_on, ea.starts_on),
                       COALESCE(eb.setup_starts_on, eb.starts_on)) + 1)::INT,
           ta.title, tb.title
    FROM event_tasks ta
    JOIN event_tasks tb
      ON tb.supplier_id = ta.supplier_id
     AND tb.id > ta.id
     AND tb.event_id <> ta.event_id
    JOIN suppliers s  ON s.id  = ta.supplier_id
    JOIN events    ea ON ea.id = ta.event_id
    JOIN events    eb ON eb.id = tb.event_id
    WHERE ta.supplier_id IS NOT NULL
      AND ta.status IN ('open', 'blocked')
      AND tb.status IN ('open', 'blocked')
      AND ea.status <> 'cancelled'
      AND eb.status <> 'cancelled'
      AND COALESCE(eb.setup_starts_on, eb.starts_on)
          <= COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on) + window_days
      AND COALESCE(ea.setup_starts_on, ea.starts_on)
          <= COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on) + window_days
    ORDER BY s.name, ea.starts_on;
$$;

-- The same, for a named person (key crew, talent, a specific specialist).
CREATE OR REPLACE FUNCTION contact_clashes(
    window_days INT DEFAULT 0
) RETURNS TABLE(
    person TEXT, role TEXT,
    event_a TEXT, a_window TEXT, event_b TEXT, b_window TEXT, overlap_days INT
) LANGUAGE sql STABLE AS $$
    SELECT c.name, c.role,
           ea.name,
           to_char(COALESCE(ea.setup_starts_on, ea.starts_on), 'DD Mon') || ' to ' ||
           to_char(COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on), 'DD Mon'),
           eb.name,
           to_char(COALESCE(eb.setup_starts_on, eb.starts_on), 'DD Mon') || ' to ' ||
           to_char(COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on), 'DD Mon'),
           (LEAST(COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on),
                  COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on))
            - GREATEST(COALESCE(ea.setup_starts_on, ea.starts_on),
                       COALESCE(eb.setup_starts_on, eb.starts_on)) + 1)::INT
    FROM event_tasks ta
    JOIN event_tasks tb
      ON tb.contact_id = ta.contact_id
     AND tb.id > ta.id
     AND tb.event_id <> ta.event_id
    JOIN event_contacts c ON c.id  = ta.contact_id
    JOIN events         ea ON ea.id = ta.event_id
    JOIN events         eb ON eb.id = tb.event_id
    WHERE ta.contact_id IS NOT NULL
      AND ta.status IN ('open', 'blocked')
      AND tb.status IN ('open', 'blocked')
      AND ea.status <> 'cancelled'
      AND eb.status <> 'cancelled'
      AND COALESCE(eb.setup_starts_on, eb.starts_on)
          <= COALESCE(ea.teardown_ends_on, ea.ends_on, ea.starts_on) + window_days
      AND COALESCE(ea.setup_starts_on, ea.starts_on)
          <= COALESCE(eb.teardown_ends_on, eb.ends_on, eb.starts_on) + window_days
    ORDER BY c.name, ea.starts_on;
$$;

-- Everything that is double-booked, in one call, for the briefing. This is the
-- question Hisham will actually ask: "am I about to promise the same crew to
-- two people?"
CREATE OR REPLACE FUNCTION resource_clashes(
    horizon_days INT DEFAULT 60,
    window_days  INT DEFAULT 0
) RETURNS TABLE(
    kind TEXT, resource TEXT, detail TEXT,
    event_a TEXT, event_b TEXT, overlap_days INT
) LANGUAGE sql STABLE AS $$
    SELECT 'supplier'::TEXT, sc.supplier, sc.category,
           sc.event_a, sc.event_b, sc.overlap_days
      FROM supplier_clashes(window_days) sc
      JOIN events ea ON ea.name = sc.event_a
     WHERE ea.starts_on IS NULL
        OR ea.starts_on BETWEEN CURRENT_DATE AND CURRENT_DATE + horizon_days
    UNION ALL
    SELECT 'person'::TEXT, cc.person, cc.role,
           cc.event_a, cc.event_b, cc.overlap_days
      FROM contact_clashes(window_days) cc
      JOIN events ea ON ea.name = cc.event_a
     WHERE ea.starts_on IS NULL
        OR ea.starts_on BETWEEN CURRENT_DATE AND CURRENT_DATE + horizon_days
    ORDER BY 1, 2;
$$;
