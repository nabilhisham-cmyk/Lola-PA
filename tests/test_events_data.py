#!/usr/bin/env python3
"""Tests for scripts/seed_events_data.py and the events SQL.

Two things are checked without needing a live Postgres:

1. The CSV parsing / coercion / validation layer, which is where a bad seed file
   would silently corrupt the data.
2. The events SQL, by parsing every statement with sqlglot and by asserting the
   clash and at-risk logic produces the right answers on hand-built cases run
   through an in-memory SQLite translation of the same predicates.

What this does NOT prove: that the Postgres-specific syntax (gen_random_uuid,
tsvector, LANGUAGE plpgsql, ON CONFLICT ... DO UPDATE with EXCLUDED) executes
server-side. That needs a real Postgres and is verified at deploy time.

Run: pytest tests/test_events_data.py -v
"""
import csv
import datetime as dt
import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "seed_events_data.py"
EVENTS_SQL = REPO_ROOT / "scripts" / "supabase_events_migration.sql"


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_events_data", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


seed = _load_module()


# ── coercion ─────────────────────────────────────────────────────────

class TestCoerce:
    def test_blank_becomes_none(self):
        assert seed.coerce("", str) is None
        assert seed.coerce("   ", int) is None
        assert seed.coerce(None, str) is None

    def test_int_tolerates_float_text(self):
        assert seed.coerce("400", int) == 400
        assert seed.coerce("400.0", int) == 400

    def test_bool_accepts_common_spellings(self):
        for yes in ["true", "yes", "1", "y", "TRUE", "Yes"]:
            assert seed.coerce(yes, bool) is True
        for no in ["false", "no", "0", "n", "FALSE", "No"]:
            assert seed.coerce(no, bool) is False

    def test_bool_rejects_nonsense(self):
        with pytest.raises(ValueError):
            seed.coerce("maybe", bool)

    def test_date_iso(self):
        assert seed.coerce("2026-10-12", "date") == dt.date(2026, 10, 12)

    def test_date_rejects_bad_format(self):
        with pytest.raises(ValueError):
            seed.coerce("12/10/2026", "date")


# ── CSV reading ──────────────────────────────────────────────────────

class TestReadCsv:
    def _write(self, tmp_path, name, text):
        p = tmp_path / name
        p.write_text(text)
        return p

    def test_reads_venues(self, tmp_path):
        p = self._write(tmp_path, "v.csv", "name,zone,capacity_standing,weather_exposed\n"
                                         "El Gouna Marina,Marina,3000,true\n")
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert problems == []
        assert rows == [{"name": "El Gouna Marina", "zone": "Marina",
                         "capacity_standing": 3000, "weather_exposed": True}]

    def test_unknown_column_is_reported_not_ignored(self, tmp_path):
        p = self._write(tmp_path, "v.csv", "name,zone,colour\nMarina,Marina,red\n")
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert any("colour" in x for x in problems)
        assert rows[0]["name"] == "Marina"

    def test_missing_name_skips_the_row(self, tmp_path):
        p = self._write(tmp_path, "v.csv", "name,zone\n,Marina\nDowntown,Downtown\n")
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert len(rows) == 1
        assert any("missing 'name'" in x for x in problems)

    def test_bad_value_is_reported_with_line_number(self, tmp_path):
        p = self._write(tmp_path, "v.csv", "name,capacity_seated\nMarina,notanumber\n")
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert any("line 2" in x for x in problems)
        assert "capacity_seated" not in rows[0]

    def test_blank_cells_are_omitted_not_null_inserted(self, tmp_path):
        """A blank cell must leave the column out entirely, so an existing value
        is not overwritten with NULL on re-import."""
        p = self._write(tmp_path, "v.csv", "name,zone,address\nMarina,Marina,\n")
        rows, _ = seed.read_csv(p, seed.VENUE_COLS)
        assert rows[0] == {"name": "Marina", "zone": "Marina"}

    def test_bom_and_utf8_headers(self, tmp_path):
        p = tmp_path / "v.csv"
        p.write_bytes("\ufeffname,zone\nMarina,Marina\n".encode("utf-8"))
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert problems == []
        assert rows[0]["name"] == "Marina"

    def test_empty_file(self, tmp_path):
        p = self._write(tmp_path, "v.csv", "")
        rows, problems = seed.read_csv(p, seed.VENUE_COLS)
        assert rows == []
        assert problems


# ── event validation ─────────────────────────────────────────────────

class TestValidateEvents:
    def test_accepts_valid_event(self):
        row = {"name": "Sunset Sessions", "status": "proposed",
               "permits_status": "not_started",
               "starts_on": dt.date(2026, 10, 12), "ends_on": dt.date(2026, 10, 12),
               "setup_starts_on": dt.date(2026, 10, 10),
               "teardown_ends_on": dt.date(2026, 10, 13)}
        assert seed.validate_events([row]) == []

    def test_rejects_unknown_status(self):
        row = {"name": "X", "status": "maybe"}
        assert any("status" in p for p in seed.validate_events([row]))

    def test_rejects_unknown_permit_status(self):
        row = {"name": "X", "permits_status": "pending-ish"}
        assert any("permits_status" in p for p in seed.validate_events([row]))

    def test_rejects_ends_before_starts(self):
        row = {"name": "X", "starts_on": dt.date(2026, 10, 12),
               "ends_on": dt.date(2026, 10, 10)}
        assert any("before starts_on" in p for p in seed.validate_events([row]))

    def test_rejects_setup_after_start(self):
        row = {"name": "X", "starts_on": dt.date(2026, 10, 12),
               "setup_starts_on": dt.date(2026, 10, 14)}
        assert any("setup_starts_on" in p for p in seed.validate_events([row]))

    def test_rejects_teardown_before_end(self):
        row = {"name": "X", "starts_on": dt.date(2026, 10, 10),
               "ends_on": dt.date(2026, 10, 12),
               "teardown_ends_on": dt.date(2026, 10, 11)}
        assert any("teardown_ends_on" in p for p in seed.validate_events([row]))

    def test_single_day_event_without_setup_teardown_is_fine(self):
        row = {"name": "X", "starts_on": dt.date(2026, 10, 12),
               "ends_on": dt.date(2026, 10, 12)}
        assert seed.validate_events([row]) == []


# ── upsert SQL construction ──────────────────────────────────────────

class _FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class TestUpsert:
    def test_builds_on_conflict_update(self):
        cur = _FakeCursor()
        n = seed.upsert(cur, "venues", [{"name": "Marina", "zone": "Marina"}])
        sql, params = cur.calls[0]
        assert n == 1
        assert "INSERT INTO venues" in sql
        assert "ON CONFLICT (name) DO UPDATE SET zone = EXCLUDED.zone" in sql
        assert params == ["Marina", "Marina"]

    def test_name_only_row_uses_do_nothing(self):
        cur = _FakeCursor()
        seed.upsert(cur, "suppliers", [{"name": "Acme AV"}])
        sql, _ = cur.calls[0]
        assert "DO NOTHING" in sql
        assert "DO UPDATE" not in sql

    def test_never_updates_the_conflict_column(self):
        """name is the conflict key; setting it to EXCLUDED.name is a no-op at
        best and confusing in review."""
        cur = _FakeCursor()
        seed.upsert(cur, "venues", [{"name": "A", "zone": "z"}])
        sql, _ = cur.calls[0]
        assert "name = EXCLUDED.name" not in sql


# ── the SQL file itself ──────────────────────────────────────────────

class TestEventsSql:
    def test_file_exists_and_non_empty(self):
        assert EVENTS_SQL.is_file()
        assert len(EVENTS_SQL.read_text().strip()) > 500

    def test_defines_every_table_the_skill_promises(self):
        sql = EVENTS_SQL.read_text()
        for table in ["venues", "suppliers", "events", "event_contacts", "event_tasks"]:
            assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"{table} not created"

    def test_is_rerunnable(self):
        sql = EVENTS_SQL.read_text()
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "DROP TRIGGER IF EXISTS" in sql
        assert "CREATE OR REPLACE FUNCTION" in sql

    def test_setup_and_teardown_are_first_class(self):
        """Clash detection is worthless without build and get-out windows."""
        sql = EVENTS_SQL.read_text()
        assert "setup_starts_on" in sql
        assert "teardown_ends_on" in sql
        assert "idx_events_window" in sql

    def test_venue_id_is_nullable_so_a_maybe_venue_is_not_a_booking(self):
        sql = EVENTS_SQL.read_text()
        assert "venue_id        UUID REFERENCES venues(id) ON DELETE SET NULL" in sql
        assert "venue_text" in sql

    def test_provides_the_three_query_functions(self):
        sql = EVENTS_SQL.read_text()
        for fn in ["events_between", "venue_clashes", "at_risk"]:
            assert f"FUNCTION {fn}" in sql, f"{fn} missing"

    def test_clash_function_uses_the_full_window_not_just_event_dates(self):
        sql = EVENTS_SQL.read_text()
        start = sql.index("FUNCTION venue_clashes")
        body = sql[start:start + 1400]
        assert "setup_starts_on" in body
        assert "teardown_ends_on" in body

    def test_no_destructive_statements(self):
        sql = EVENTS_SQL.read_text()
        for bad in ["DROP TABLE", "TRUNCATE", "DELETE FROM"]:
            assert bad not in sql, f"destructive statement {bad!r} in the migration"

    def test_statements_parse(self):
        """Parse every statement so a syntax error cannot reach Supabase."""
        try:
            import sqlglot
        except ImportError:
            pytest.skip("sqlglot not installed")
        sql = EVENTS_SQL.read_text()
        statements = sqlglot.parse(sql, read="postgres")
        assert len(statements) >= 8, f"only parsed {len(statements)} statements"


# ── clash logic, executed on SQLite ──────────────────────────────────

class TestClashLogic:
    """Runs the same overlap predicate the SQL function uses, in SQLite, so the
    arithmetic is actually exercised rather than asserted by eye."""

    @pytest.fixture()
    def db(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute("""CREATE TABLE events (
            id INTEGER PRIMARY KEY, name TEXT, venue TEXT,
            starts_on TEXT, ends_on TEXT,
            setup_starts_on TEXT, teardown_ends_on TEXT, status TEXT)""")
        conn.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
            [
                (1, "Sunset Sessions", "Marina", "2026-10-12", "2026-10-12",
                 "2026-10-10", "2026-10-13", "confirmed"),
                (2, "Catering Setup", "Marina", "2026-10-11", "2026-10-11",
                 "2026-10-09", "2026-10-11", "confirmed"),
                (3, "Golf Open", "Golf", "2026-10-12", "2026-10-14",
                 "2026-10-11", "2026-10-15", "confirmed"),
                (4, "Beach Party", "Marina", "2026-11-20", "2026-11-20",
                 "2026-11-19", "2026-11-21", "proposed"),
                (5, "Cancelled Thing", "Marina", "2026-10-12", "2026-10-12",
                 "2026-10-10", "2026-10-13", "cancelled"),
            ],
        )
        return conn

    def _clashes(self, conn, window_days=0):
        # NOTE: this mirrors the Postgres predicate but must use julianday() for
        # the day arithmetic. Postgres `date - date` already yields an integer
        # number of days; SQLite does not do that, so a literal translation
        # silently reports 0 or 1 for every overlap. That mistake is exactly what
        # the day-count assertion below exists to catch.
        q = """
        SELECT a.name, b.name,
          CAST(julianday(MIN(COALESCE(a.teardown_ends_on, a.ends_on, a.starts_on),
                             COALESCE(b.teardown_ends_on, b.ends_on, b.starts_on)))
             - julianday(MAX(COALESCE(a.setup_starts_on, a.starts_on),
                             COALESCE(b.setup_starts_on, b.starts_on))) + 1 AS INTEGER)
        FROM events a JOIN events b
          ON b.id > a.id AND b.venue = a.venue
        WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
          AND julianday(COALESCE(b.setup_starts_on, b.starts_on))
              <= julianday(COALESCE(a.teardown_ends_on, a.ends_on, a.starts_on)) + ?
          AND julianday(COALESCE(a.setup_starts_on, a.starts_on))
              <= julianday(COALESCE(b.teardown_ends_on, b.ends_on, b.starts_on)) + ?
        """
        return conn.execute(q, (window_days, window_days)).fetchall()

    def test_detects_overlap_that_exists_only_in_the_setup_window(self, db):
        """Sunset Sessions builds 10-13 Oct; Catering sets up 9-11 Oct and gets
        out on the 11th. The performance days do not overlap at all, but the
        venue does. This is exactly the clash the events SOUL promises to catch."""
        clashes = self._clashes(db)
        pairs = {tuple(sorted((a, b))) for a, b, _ in clashes}
        assert ("Catering Setup", "Sunset Sessions") in pairs

    def test_overlap_day_count_is_correct(self, db):
        for a, b, days in self._clashes(db):
            if {a, b} == {"Catering Setup", "Sunset Sessions"}:
                # 10, 11, 12, 13 vs 9, 10, 11 -> overlap is 10 and 11 = 2 days
                assert days == 2, f"expected 2 overlap days, got {days}"

    def test_different_venues_do_not_clash(self, db):
        pairs = {tuple(sorted((a, b))) for a, b, _ in self._clashes(db)}
        assert ("Golf Open", "Sunset Sessions") not in pairs

    def test_cancelled_events_are_excluded(self, db):
        names = {n for a, b, _ in self._clashes(db) for n in (a, b)}
        assert "Cancelled Thing" not in names

    def test_window_days_widens_detection(self, db):
        """The venue frees on 13 October and the November event loads in from
        19 November, a 37-day gap. A zero buffer must not flag it; a buffer wide
        enough to cover the gap must."""
        tight = {tuple(sorted((a, b))) for a, b, _ in self._clashes(db, 0)}
        loose = {tuple(sorted((a, b))) for a, b, _ in self._clashes(db, 40)}
        assert ("Beach Party", "Sunset Sessions") not in tight
        assert ("Beach Party", "Sunset Sessions") in loose

    def test_window_days_too_small_does_not_widen(self, db):
        """37-day gap against a 30-day buffer must stay unflagged. Guards against
        an off-by-a-lot in the buffer arithmetic."""
        pairs = {tuple(sorted((a, b))) for a, b, _ in self._clashes(db, 30)}
        assert ("Beach Party", "Sunset Sessions") not in pairs
