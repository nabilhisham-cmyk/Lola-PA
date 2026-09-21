"""Tests for the events plugin (plugins/events_data).

Focus on the two things that fail *dangerously* if wrong:

1. Column-name handling. The tools build SQL from dict keys, so a key that is not
   in the allowlist must be rejected before it reaches a statement. If this
   regresses, a crafted field name becomes arbitrary SQL.
2. DSN resolution. If the plugin ever falls back to ``DATABASE_URL`` it could
   write into an unrelated client's database, which has actually happened on this
   host.

Also covers enum guards, argument validation, and the read-back behaviour that
makes "created" a proven claim rather than an assumption.

Run: pytest tests/test_events_plugin.py -v
"""
import importlib.util
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "plugins" / "events_data" / "tools.py"
INIT = REPO_ROOT / "plugins" / "events_data" / "__init__.py"


def _load():
    spec = importlib.util.spec_from_file_location("events_tools", TOOLS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


t = _load()


# ── the plugin module itself ─────────────────────────────────────────

class TestPluginModule:
    def test_init_registers_every_documented_tool(self):
        src = INIT.read_text()
        for name in ["events_list", "events_upcoming", "events_get", "events_create",
                     "events_update", "events_clashes", "events_at_risk", "venues_list",
                     "venues_save", "suppliers_list", "suppliers_save", "tasks_list",
                     "tasks_save"]:
            assert name in src, f"{name} not registered"

    def test_uses_the_events_toolset(self):
        assert 'toolset="events"' in INIT.read_text()

    def test_every_registered_handler_exists(self):
        """A typo in the tuple would only surface at runtime otherwise."""
        import re
        src = INIT.read_text()
        handlers = re.findall(r"_t\.(handle_[a-z_]+)", src)
        assert handlers, "no handlers referenced"
        for h in handlers:
            assert hasattr(t, h), f"{h} referenced in __init__ but missing from tools"

    def test_every_registered_schema_exists(self):
        import re
        src = INIT.read_text()
        for s in re.findall(r"_t\.([A-Z_]+_SCHEMA)", src):
            assert hasattr(t, s), f"{s} missing from tools"

    def test_has_a_check_fn(self):
        assert "check_fn=" in INIT.read_text()
        assert callable(t.check_events_available)


# ── column allowlist: the injection guard ────────────────────────────

class TestColumnAllowlist:
    def test_every_table_has_an_allowlist(self):
        for table in ["venues", "events", "event_tasks", "suppliers", "event_contacts"]:
            assert table in t.TABLES
            assert t.TABLES[table], f"{table} allowlist is empty"

    def test_unknown_column_is_rejected(self):
        err = t._reject_unknown("events", {"name": "X", "evil": "1"})
        assert err and "evil" in err

    def test_known_columns_pass(self):
        assert t._reject_unknown("events", {"name": "X", "starts_on": "2026-10-12"}) is None

    def test_sql_metacharacters_in_a_key_are_rejected(self):
        """The dangerous case: a key that tries to become SQL."""
        for evil in ["name; DROP TABLE events--", "name) VALUES (1)--", "*", "id, name"]:
            assert t._reject_unknown("events", {evil: "x"}) is not None, f"{evil!r} was allowed"

    def test_insert_refuses_unknown_column_before_building_sql(self):
        class C:
            executed = []
            def execute(self, sql, params=None):
                C.executed.append(sql)
        with pytest.raises(ValueError):
            t._insert(C(), "events", {"name": "X", "evil": 1})
        assert C.executed == [], "SQL was built despite an invalid column"

    def test_update_refuses_unknown_column(self):
        class C:
            executed = []
            def execute(self, sql, params=None):
                C.executed.append(sql)
        with pytest.raises(ValueError):
            t._update(C(), "events", "id", "abc", {"evil": 1})
        assert C.executed == []

    def test_update_cannot_touch_the_primary_key(self):
        """`id` is not in the allowlist at all, so it is rejected before any SQL
        is built. That is stricter than merely skipping it in the SET clause."""
        class C:
            executed = []
            def execute(self, sql, params=None):
                C.executed.append((sql, params))
                self.description = [("id",), ("name",)]
            def fetchall(self):
                return [("id1", "X")]
        with pytest.raises(ValueError):
            t._update(C(), "events", "id", "id1", {"id": "hacked", "name": "Y"})
        assert C.executed == [], "no SQL should be built for a rejected update"

    def test_update_without_the_pk_succeeds_normally(self):
        class C:
            executed = []
            def execute(self, sql, params=None):
                C.executed.append((sql, params))
                self.description = [("id",), ("status",)]
            def fetchall(self):
                return [("id1", "confirmed")]
        row = t._update(C(), "events", "id", "id1", {"status": "confirmed"})
        sql, params = C.executed[0]
        assert "SET status = %s" in sql
        assert row == {"id": "id1", "status": "confirmed"}

    def test_insert_uses_parameterised_values(self):
        """Values must never be interpolated into the statement text."""
        class C:
            executed = []
            def execute(self, sql, params=None):
                C.executed.append((sql, params))
                self.description = [("id",)]
            def fetchall(self):
                return [("id1",)]
        t._insert(C(), "events", {"name": "Robert'); DROP TABLE events;--"})
        sql, params = C.executed[0]
        assert "DROP TABLE" not in sql, "value was interpolated into SQL"
        assert params == ["Robert'); DROP TABLE events;--"], "value must be a bound parameter"


# ── DSN resolution ───────────────────────────────────────────────────

class TestDsn:
    def test_uses_supabase_db_url_when_present(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres")
        monkeypatch.setenv("DATABASE_URL", "postgresql://evil@neondb.example.com:5432/neondb")
        dsn = t._dsn()
        assert dsn and "supabase.co" in dsn
        assert "neondb" not in dsn

    def test_never_falls_back_to_database_url(self, monkeypatch):
        """DATABASE_URL on this host pointed at an unrelated client's database."""
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.delenv("SUPABASE_MEMORY_URL", raising=False)
        monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://evil@neondb:5432/neondb")
        assert t._dsn() is None, "must NOT fall back to DATABASE_URL"

    def test_assembles_from_memory_url_and_password(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.setenv("SUPABASE_MEMORY_URL", "https://abcdefghijklmnopqrst.supabase.co")
        monkeypatch.setenv("SUPABASE_DB_PASSWORD", "sekret")
        dsn = t._dsn()
        assert dsn and "db.abcdefghijklmnopqrst.supabase.co" in dsn
        assert "sekret" in dsn

    def test_partial_config_yields_nothing_rather_than_a_bad_dsn(self, monkeypatch):
        """URL present but no password must not produce a connection string."""
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.setenv("SUPABASE_MEMORY_URL", "https://abcdefghijklmnopqrst.supabase.co")
        monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
        assert t._dsn() is None

    def test_unrecognised_url_shape_is_refused(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.setenv("SUPABASE_MEMORY_URL", "https://not-a-supabase-host.example.com")
        monkeypatch.setenv("SUPABASE_DB_PASSWORD", "sekret")
        assert t._dsn() is None

    def test_check_fn_false_without_dsn(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.delenv("SUPABASE_MEMORY_URL", raising=False)
        monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
        assert t.check_events_available() is False

    def test_check_fn_true_with_dsn_and_driver(self, monkeypatch):
        pytest.importorskip("psycopg")
        monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres")
        assert t.check_events_available() is True


# ── value presentation ───────────────────────────────────────────────

class TestCurfewFormatting:
    """Postgres TIME serialises as '23:00:00'. A curfew is spoken as '23:00'."""

    def _cur(self, value):
        class C:
            description = [("curfew_time",), ("name",)]
            def fetchall(self):
                return [(value, "Marina")]
        return t._rows(C())

    def test_trims_seconds_from_a_datetime_time(self):
        """This is the real case: psycopg hands back datetime.time, not a string."""
        import datetime as _dt
        assert self._cur(_dt.time(23, 0))[0]["curfew_time"] == "23:00"

    def test_keeps_a_real_number_of_seconds(self):
        import datetime as _dt
        assert self._cur(_dt.time(23, 30, 15))[0]["curfew_time"] == "23:30:15"

    def test_also_handles_the_string_form(self):
        assert self._cur("23:00:00")[0]["curfew_time"] == "23:00"

    def test_handles_null(self):
        assert self._cur(None)[0]["curfew_time"] is None

    def test_leaves_other_columns_alone(self):
        assert self._cur("23:00:00")[0]["name"] == "Marina"


# ── enum guards ──────────────────────────────────────────────────────

class TestEnumGuards:
    def test_event_status_matches_the_schema(self):
        sql = (REPO_ROOT / "scripts" / "supabase_events_migration.sql").read_text()
        for value in t.EVENT_STATUS:
            assert value in sql, f"{value} not in the schema"
        assert "DEFAULT 'proposed'" in sql, "events.status must default to proposed"

    def test_permit_status_matches_the_schema(self):
        sql = (REPO_ROOT / "scripts" / "supabase_events_migration.sql").read_text()
        for value in t.PERMIT_STATUS:
            assert value in sql

    def test_rejects_bad_status_on_create(self):
        out = json.loads(t.handle_events_create({"name": "X", "status": "maybe"}))
        assert out["ok"] is False and "status" in out["error"]

    def test_rejects_bad_permit_status(self):
        out = json.loads(t.handle_events_create({"name": "X", "permits_status": "sortof"}))
        assert out["ok"] is False

    def test_validates_enum_helper(self):
        assert t._validate_enum(None, {"a"}, "x") is None
        assert t._validate_enum("a", {"a"}, "x") is None
        assert t._validate_enum("b", {"a"}, "x") is not None


# ── argument validation (no database needed) ─────────────────────────

class TestArgumentValidation:
    def test_events_get_needs_an_identifier(self):
        out = json.loads(t.handle_events_get({}))
        assert out["ok"] is False and "event_id or name" in out["error"]

    def test_events_update_needs_event_id(self):
        out = json.loads(t.handle_events_update({"status": "confirmed"}))
        assert out["ok"] is False and "event_id" in out["error"]

    def test_tasks_save_needs_title_when_creating(self):
        out = json.loads(t.handle_tasks_save({"event_id": "e1"}))
        assert out["ok"] is False and "title" in out["error"]

    def test_tasks_save_needs_event_when_creating(self):
        out = json.loads(t.handle_tasks_save({"title": "Book AV"}))
        assert out["ok"] is False and "event_id" in out["error"]

    def test_tasks_save_rejects_bad_status_before_connecting(self):
        out = json.loads(t.handle_tasks_save({"title": "x", "event_id": "e", "status": "nope"}))
        assert out["ok"] is False and "status" in out["error"]

    def test_venues_save_needs_a_name(self):
        out = json.loads(t.handle_venues_save({"zone": "Marina"}))
        assert out["ok"] is False

    def test_upsert_by_name_requires_name(self):
        class C:
            def execute(self, sql, params=None):
                pass
        with pytest.raises(ValueError):
            t._upsert_by_name(C(), "venues", {"zone": "Marina"})

    def test_errors_are_valid_json_with_ok_false(self):
        out = json.loads(t.handle_events_get({}))
        assert out == {"ok": False, "error": out["error"]}


# ── status vocabulary is the same everywhere ─────────────────────────

class TestVocabularyConsistency:
    def test_skill_documents_the_same_status_values(self):
        skill = (REPO_ROOT / "skills" / "events-ops" / "SKILL.md").read_text()
        for value in t.EVENT_STATUS:
            assert value in skill, f"{value} missing from the skill's status list"
        for value in t.PERMIT_STATUS:
            assert value in skill
        for value in t.TASK_STATUS:
            assert value in skill

    def test_soul_and_skill_agree_on_the_tables(self):
        soul = (REPO_ROOT / "SOUL.md").read_text()
        for table in t.TABLES:
            assert table in soul, f"{table} not named in the concierge SOUL"
