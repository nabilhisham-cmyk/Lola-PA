"""Events tools — validated access to the El Gouna events tables in Supabase.

Design rules enforced here:

- **No arbitrary SQL.** Every tool takes structured arguments and builds its own
  parameterised statement. Column names are checked against a fixed allowlist, so
  a model-supplied string can never become SQL.
- **Writes are limited to the event domain** (venues, events, tasks, suppliers,
  contacts). Reads are the same set.
- **Never trust ``DATABASE_URL``.** The DSN comes from ``SUPABASE_DB_URL``, or is
  assembled from ``SUPABASE_MEMORY_URL`` + ``SUPABASE_DB_PASSWORD``.
- **Every write is read back** before being reported as done, so a claim of
  success is always backed by the row that exists afterwards.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── connection ───────────────────────────────────────────────────────

_PROJECT_REF_RE = re.compile(r"https://([a-z0-9]{20})\.supabase\.co")

# Column allowlists. A string that is not in one of these never reaches SQL.
VENUE_COLS = {
    "name", "zone", "kind", "capacity_seated", "capacity_standing", "address",
    "contact_name", "contact_phone", "contact_email", "curfew_time",
    "power_notes", "rigging_notes", "access_notes", "weather_exposed", "notes",
}
EVENT_COLS = {
    "name", "event_type", "status", "starts_on", "ends_on", "setup_starts_on",
    "teardown_ends_on", "venue_id", "venue_text", "attendance_expected",
    "audience", "ticket_price", "currency", "owner", "description",
    "permits_status", "permit_notes", "sponsors", "budget_estimate",
    "budget_actual", "risk_notes", "source",
}
TASK_COLS = {
    "event_id", "title", "detail", "owner", "due_on", "status", "critical",
    "category",
}
SUPPLIER_COLS = {
    "name", "category", "based_in", "contact_name", "contact_phone",
    "contact_email", "website", "lead_time_days", "payment_terms", "currency",
    "reliable", "performance_notes", "notes",
}
CONTACT_COLS = {"event_id", "name", "role", "organisation", "phone", "email", "notes"}

# Enum guards, mirrored from the schema. Rejecting an unknown value here gives a
# clear error instead of a constraint violation deep in Postgres.
EVENT_STATUS = {"proposed", "confirmed", "in_production", "live", "completed", "cancelled"}
PERMIT_STATUS = {"unknown", "not_started", "applied", "granted", "refused"}
TASK_STATUS = {"open", "blocked", "done", "dropped"}

TABLES = {
    "venues": VENUE_COLS,
    "events": EVENT_COLS,
    "event_tasks": TASK_COLS,
    "suppliers": SUPPLIER_COLS,
    "event_contacts": CONTACT_COLS,
}


def _dsn() -> Optional[str]:
    """Resolve the Postgres DSN. Never falls back to DATABASE_URL."""
    direct = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if direct:
        return direct
    url = (os.environ.get("SUPABASE_MEMORY_URL") or "").strip()
    pw = (os.environ.get("SUPABASE_DB_PASSWORD") or "").strip()
    m = _PROJECT_REF_RE.match(url)
    if m and pw:
        ref = m.group(1)
        return f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
    return None


def _connect():
    import psycopg  # imported lazily so the plugin loads without the driver
    dsn = _dsn()
    if not dsn:
        raise RuntimeError(
            "No Supabase DSN. Set SUPABASE_DB_URL, or SUPABASE_MEMORY_URL plus "
            "SUPABASE_DB_PASSWORD."
        )
    return psycopg.connect(dsn, connect_timeout=15)


def check_events_available() -> bool:
    """Tool gate: are the DSN and the driver both present?

    Deliberately does not open a connection — a gate that dials out on every
    tool listing would be slow and would fail closed during a brief network blip.
    """
    if not _dsn():
        return False
    try:
        import psycopg  # noqa: F401
    except ImportError:
        return False
    return True


# ── helpers ──────────────────────────────────────────────────────────

def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg})


def _reject_unknown(table: str, fields: dict) -> Optional[str]:
    allowed = TABLES[table]
    bad = sorted(k for k in fields if k not in allowed)
    if bad:
        return f"unknown column(s) for {table}: {bad}. Allowed: {sorted(allowed)}"
    return None


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _insert(cur, table: str, fields: dict, returning: str = "*") -> dict:
    bad = _reject_unknown(table, fields)
    if bad:
        raise ValueError(bad)
    if not fields:
        raise ValueError("no fields to write")
    cols = list(fields)
    ph = ", ".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) RETURNING {returning}",
        [fields[c] for c in cols],
    )
    return _rows(cur)[0]


def _update(cur, table: str, pk: str, pkval: str, fields: dict) -> Optional[dict]:
    bad = _reject_unknown(table, fields)
    if bad:
        raise ValueError(bad)
    fields = {k: v for k, v in fields.items() if k != pk}
    if not fields:
        raise ValueError("no fields to update")
    sets = ", ".join(f"{c} = %s" for c in fields)
    cur.execute(
        f"UPDATE {table} SET {sets} WHERE {pk} = %s RETURNING *",
        [fields[c] for c in fields] + [pkval],
    )
    out = _rows(cur)
    return out[0] if out else None


def _validate_enum(value, allowed: set, label: str) -> Optional[str]:
    if value is None:
        return None
    if value not in allowed:
        return f"{label} must be one of {sorted(allowed)}, got {value!r}"
    return None


# ── schemas ──────────────────────────────────────────────────────────

def _fn(name, desc, props, required=()):
    return {
        "name": name,
        "description": desc,
        "parameters": {
            "type": "object",
            "properties": props,
            "required": list(required),
        },
    }


EVENTS_LIST_SCHEMA = _fn(
    "events_list",
    "List events whose full window (setup through teardown) overlaps a date range. "
    "Use this to answer 'what is on', 'what is happening in October', or to check "
    "whether a venue is busy. Dates are YYYY-MM-DD.",
    {
        "from_date": {"type": "string", "description": "Start of range, YYYY-MM-DD. Defaults to today."},
        "to_date": {"type": "string", "description": "End of range, YYYY-MM-DD. Defaults to 30 days from from_date."},
        "venue": {"type": "string", "description": "Optional venue name filter (case-insensitive, partial match)."},
    },
)

EVENTS_UPCOMING_SCHEMA = _fn(
    "events_upcoming",
    "The next N events from today, soonest first.",
    {"limit": {"type": "integer", "description": "How many to return. Default 10."}},
)

EVENTS_GET_SCHEMA = _fn(
    "events_get",
    "One event in full, with its contacts and tasks attached. Identify the event "
    "by id, or by name (partial match, most recent if several).",
    {
        "event_id": {"type": "string", "description": "Event UUID."},
        "name": {"type": "string", "description": "Event name or partial name."},
    },
)

EVENTS_CREATE_SCHEMA = _fn(
    "events_create",
    "Create an event. Always fill setup_starts_on and teardown_ends_on when known: "
    "clash detection depends on the build and get-out windows, not just the "
    "performance dates. Leave venue_id null and use venue_text while a venue is "
    "not confirmed, so it is not treated as booked.",
    {
        "name": {"type": "string", "description": "Event name. Required."},
        "event_type": {"type": "string", "description": "festival | concert | sporting | conference | corporate | activation | private | hotel_programming | other"},
        "status": {"type": "string", "description": "proposed | confirmed | in_production | live | completed | cancelled. Default proposed."},
        "starts_on": {"type": "string", "description": "YYYY-MM-DD."},
        "ends_on": {"type": "string", "description": "YYYY-MM-DD. Equals starts_on for one day."},
        "setup_starts_on": {"type": "string", "description": "YYYY-MM-DD load-in begins."},
        "teardown_ends_on": {"type": "string", "description": "YYYY-MM-DD get-out finishes."},
        "venue_id": {"type": "string", "description": "UUID from venues_list. Only when the venue is CONFIRMED."},
        "venue_text": {"type": "string", "description": "Venue name as free text while unconfirmed."},
        "attendance_expected": {"type": "integer", "description": "Expected attendance."},
        "audience": {"type": "string", "description": "public | invited | ticket-holders | corporate | mixed"},
        "ticket_price": {"type": "number", "description": "Price per ticket."},
        "currency": {"type": "string", "description": "EGP default."},
        "owner": {"type": "string", "description": "Who owns delivery. Default Hisham."},
        "description": {"type": "string", "description": "Free description."},
        "permits_status": {"type": "string", "description": "unknown | not_started | applied | granted | refused"},
        "permit_notes": {"type": "string", "description": "Permit detail."},
        "sponsors": {"type": "string", "description": "Sponsors, free text."},
        "budget_estimate": {"type": "number", "description": "Estimated budget."},
        "risk_notes": {"type": "string", "description": "Known risks."},
    },
    ("name",),
)

EVENTS_UPDATE_SCHEMA = _fn(
    "events_update",
    "Update fields on an existing event. Only the fields you pass are changed. "
    "Returns the updated row so the change can be confirmed.",
    {
        "event_id": {"type": "string", "description": "Event UUID. Required."},
        **{k: {"type": "string", "description": f"New value for {k}."} for k in
           ["name", "event_type", "status", "starts_on", "ends_on", "setup_starts_on",
            "teardown_ends_on", "venue_id", "venue_text", "audience", "currency",
            "owner", "description", "permits_status", "permit_notes", "sponsors",
            "risk_notes"]},
        "attendance_expected": {"type": "integer", "description": "New expected attendance."},
        "budget_estimate": {"type": "number", "description": "New budget estimate."},
        "budget_actual": {"type": "number", "description": "Actual spend."},
    },
    ("event_id",),
)

EVENTS_CLASHES_SCHEMA = _fn(
    "events_clashes",
    "Venue clashes: events sharing a venue whose window overlaps, counting setup "
    "and teardown days. window_days widens the definition of a clash by that many "
    "days on each side, useful for asking 'is this venue free within a week'.",
    {"window_days": {"type": "integer", "description": "Buffer in days. Default 0."}},
)

EVENTS_AT_RISK_SCHEMA = _fn(
    "events_at_risk",
    "Events starting within a horizon that need attention: open critical tasks, "
    "permits not granted, or no confirmed venue.",
    {"horizon_days": {"type": "integer", "description": "Look-ahead in days. Default 30."}},
)

VENUES_LIST_SCHEMA = _fn(
    "venues_list",
    "List venues, optionally filtered by zone or name. Use before creating an event "
    "to find the right venue_id.",
    {
        "zone": {"type": "string", "description": "Filter by zone, e.g. Marina, Downtown, Kafr."},
        "name": {"type": "string", "description": "Partial name match."},
    },
)

VENUES_SAVE_SCHEMA = _fn(
    "venues_save",
    "Create a venue, or update it if the name already exists. Captures the "
    "constraints that decide whether an event can happen there: curfew, power, "
    "rigging, access, weather exposure.",
    {
        **{k: {"type": "string", "description": f"{k}."} for k in
           ["name", "zone", "kind", "address", "contact_name", "contact_phone",
            "contact_email", "curfew_time", "power_notes", "rigging_notes",
            "access_notes", "notes"]},
        "capacity_seated": {"type": "integer", "description": "Seated capacity."},
        "capacity_standing": {"type": "integer", "description": "Standing capacity."},
        "weather_exposed": {"type": "boolean", "description": "Open-air, needs a weather contingency."},
    },
    ("name",),
)

SUPPLIERS_LIST_SCHEMA = _fn(
    "suppliers_list",
    "List suppliers, optionally by category or base town. Shows lead time, payment "
    "terms and the performance note.",
    {
        "category": {"type": "string", "description": "av | staging | lighting | sound | catering | security | medical | talent | transport | accommodation | printing | media | permits | decor | power | other"},
        "based_in": {"type": "string", "description": "El Gouna | Hurghada | Cairo | other"},
        "name": {"type": "string", "description": "Partial name match."},
    },
)

SUPPLIERS_SAVE_SCHEMA = _fn(
    "suppliers_save",
    "Create or update a supplier by name. Record the realistic lead time and how "
    "they actually performed, so future booking decisions are informed.",
    {
        **{k: {"type": "string", "description": f"{k}."} for k in
           ["name", "category", "based_in", "contact_name", "contact_phone",
            "contact_email", "website", "payment_terms", "currency",
            "performance_notes", "notes"]},
        "lead_time_days": {"type": "integer", "description": "Realistic lead time in days."},
        "reliable": {"type": "boolean", "description": "Track record. Omit if untested."},
    },
    ("name",),
)

TASKS_LIST_SCHEMA = _fn(
    "tasks_list",
    "List tasks. Provide event_id for one event, or omit it for all open tasks "
    "across every event. overdue_only returns just the late ones.",
    {
        "event_id": {"type": "string", "description": "Restrict to one event."},
        "status": {"type": "string", "description": "open | blocked | done | dropped. Default all."},
        "overdue_only": {"type": "boolean", "description": "Only tasks past their due date."},
    },
)

TASKS_SAVE_SCHEMA = _fn(
    "tasks_save",
    "Create a task, or update it if task_id is given. Mark critical for anything "
    "whose failure would damage the event.",
    {
        "task_id": {"type": "string", "description": "Provide to update an existing task."},
        "event_id": {"type": "string", "description": "Event the task belongs to."},
        "title": {"type": "string", "description": "Short task title. Required when creating."},
        "detail": {"type": "string", "description": "Detail."},
        "owner": {"type": "string", "description": "Who is doing it."},
        "due_on": {"type": "string", "description": "YYYY-MM-DD."},
        "status": {"type": "string", "description": "open | blocked | done | dropped"},
        "critical": {"type": "boolean", "description": "Would damage the event if it slips."},
        "category": {"type": "string", "description": "permit | venue | supplier | talent | logistics | security | marketing | finance | admin | other"},
    },
)


# ── handlers: reads ──────────────────────────────────────────────────

def _date_or(default_expr: str, value: Optional[str]) -> str:
    """Return a SQL fragment for a date argument, or a SQL default expression."""
    return "%s" if value else default_expr


def handle_events_list(args: dict) -> str:
    from_date = args.get("from_date")
    to_date = args.get("to_date")
    venue = args.get("venue")
    try:
        with _connect() as conn, conn.cursor() as cur:
            sql = """
                SELECT e.id, e.name, e.event_type, e.status,
                       e.starts_on, e.ends_on, e.setup_starts_on, e.teardown_ends_on,
                       COALESCE(v.name, e.venue_text) AS venue, e.venue_id,
                       e.attendance_expected, e.permits_status
                  FROM events e
                  LEFT JOIN venues v ON v.id = e.venue_id
                 WHERE e.status <> 'cancelled'
                   AND COALESCE(e.setup_starts_on, e.starts_on) <= COALESCE(%s, CURRENT_DATE + 30)
                   AND COALESCE(e.teardown_ends_on, e.ends_on, e.starts_on) >= COALESCE(%s, CURRENT_DATE)
            """
            params: list = [to_date, from_date]
            if venue:
                sql += " AND COALESCE(v.name, e.venue_text) ILIKE %s"
                params.append(f"%{venue}%")
            sql += " ORDER BY e.starts_on"
            cur.execute(sql, params)
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("events_list failed: %s", e)
        return _err(str(e))


def handle_events_upcoming(args: dict) -> str:
    limit = int(args.get("limit") or 10)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT e.id, e.name, e.event_type, e.status, e.starts_on, e.ends_on,
                          COALESCE(v.name, e.venue_text) AS venue, e.attendance_expected,
                          e.permits_status
                     FROM events e LEFT JOIN venues v ON v.id = e.venue_id
                    WHERE e.status NOT IN ('completed','cancelled')
                      AND COALESCE(e.ends_on, e.starts_on) >= CURRENT_DATE
                    ORDER BY COALESCE(e.starts_on, e.ends_on)
                    LIMIT %s""",
                (limit,),
            )
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("events_upcoming failed: %s", e)
        return _err(str(e))


def handle_events_get(args: dict) -> str:
    eid, name = args.get("event_id"), args.get("name")
    if not eid and not name:
        return _err("give event_id or name")
    try:
        with _connect() as conn, conn.cursor() as cur:
            if eid:
                cur.execute(
                    """SELECT e.*, v.name AS venue_name FROM events e
                       LEFT JOIN venues v ON v.id = e.venue_id WHERE e.id = %s""",
                    (eid,),
                )
            else:
                cur.execute(
                    """SELECT e.*, v.name AS venue_name FROM events e
                       LEFT JOIN venues v ON v.id = e.venue_id
                       WHERE e.name ILIKE %s
                       ORDER BY e.starts_on DESC NULLS LAST LIMIT 1""",
                    (f"%{name}%",),
                )
            rows = _rows(cur)
            if not rows:
                return _err("no event matched")
            event = rows[0]
            cur.execute("SELECT * FROM event_contacts WHERE event_id = %s ORDER BY name", (event["id"],))
            contacts = _rows(cur)
            cur.execute("SELECT * FROM event_tasks WHERE event_id = %s ORDER BY critical DESC, due_on NULLS LAST", (event["id"],))
            tasks = _rows(cur)
            return _ok({"event": event, "contacts": contacts, "tasks": tasks})
    except Exception as e:
        logger.debug("events_get failed: %s", e)
        return _err(str(e))


def handle_events_clashes(args: dict) -> str:
    window = int(args.get("window_days") or 0)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM venue_clashes(%s)", (window,))
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("events_clashes failed: %s", e)
        return _err(str(e))


def handle_events_at_risk(args: dict) -> str:
    horizon = int(args.get("horizon_days") or 30)
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM at_risk(%s)", (horizon,))
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("events_at_risk failed: %s", e)
        return _err(str(e))


def handle_venues_list(args: dict) -> str:
    try:
        with _connect() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM venues WHERE TRUE"
            params: list = []
            if args.get("zone"):
                sql += " AND zone ILIKE %s"
                params.append(f"%{args['zone']}%")
            if args.get("name"):
                sql += " AND name ILIKE %s"
                params.append(f"%{args['name']}%")
            sql += " ORDER BY zone NULLS LAST, name"
            cur.execute(sql, params)
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("venues_list failed: %s", e)
        return _err(str(e))


def handle_suppliers_list(args: dict) -> str:
    try:
        with _connect() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM suppliers WHERE TRUE"
            params: list = []
            for key in ("category", "based_in"):
                if args.get(key):
                    sql += f" AND {key} ILIKE %s"
                    params.append(f"%{args[key]}%")
            if args.get("name"):
                sql += " AND name ILIKE %s"
                params.append(f"%{args['name']}%")
            sql += " ORDER BY category NULLS LAST, name"
            cur.execute(sql, params)
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("suppliers_list failed: %s", e)
        return _err(str(e))


def handle_tasks_list(args: dict) -> str:
    try:
        with _connect() as conn, conn.cursor() as cur:
            sql = """SELECT t.*, e.name AS event_name, e.starts_on AS event_starts_on
                       FROM event_tasks t LEFT JOIN events e ON e.id = t.event_id
                      WHERE TRUE"""
            params: list = []
            if args.get("event_id"):
                sql += " AND t.event_id = %s"
                params.append(args["event_id"])
            if args.get("status"):
                err = _validate_enum(args["status"], TASK_STATUS, "status")
                if err:
                    return _err(err)
                sql += " AND t.status = %s"
                params.append(args["status"])
            else:
                sql += " AND t.status IN ('open','blocked')"
            if args.get("overdue_only"):
                sql += " AND t.due_on < CURRENT_DATE AND t.status = 'open'"
            sql += " ORDER BY t.critical DESC, t.due_on NULLS LAST"
            cur.execute(sql, params)
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("tasks_list failed: %s", e)
        return _err(str(e))


# ── handlers: writes (every one reads back before claiming success) ──

def _write_event(cur, fields: dict) -> dict:
    return _insert(cur, "events", fields)


def handle_events_create(args: dict) -> str:
    err = _validate_enum(args.get("status"), EVENT_STATUS, "status")
    if err:
        return _err(err)
    err = _validate_enum(args.get("permits_status"), PERMIT_STATUS, "permits_status")
    if err:
        return _err(err)
    fields = {k: v for k, v in args.items() if v is not None and k in EVENT_COLS}
    if "status" not in fields:
        fields["status"] = "proposed"
    # Refuse a venue_id that does not exist, rather than failing on the FK with a
    # less useful message.
    try:
        with _connect() as conn, conn.cursor() as cur:
            if fields.get("venue_id"):
                cur.execute("SELECT name FROM venues WHERE id = %s", (fields["venue_id"],))
                if not cur.fetchone():
                    return _err(f"venue_id {fields['venue_id']} does not exist. Use venues_list first, "
                                "or put the name in venue_text while it is unconfirmed.")
            row = _write_event(cur, fields)
            # Read the row back on the same connection and in its own statement,
            # so "created" is proven rather than assumed.
            cur.execute("SELECT e.*, v.name AS venue_name FROM events e "
                        "LEFT JOIN venues v ON v.id = e.venue_id WHERE e.id = %s", (row["id"],))
            readback = _rows(cur)[0]
            # Warn about clashes immediately, in the same answer.
            try:
                cur.execute("SELECT * FROM venue_clashes(0)")
                clashes = [c for c in _rows(cur)
                           if readback["name"] in (c.get("event_a"), c.get("event_b"))]
            except Exception:
                clashes = []
            conn.commit()
        out = {"event": readback}
        if clashes:
            out["venue_clashes"] = clashes
        return _ok(out)
    except Exception as e:
        logger.debug("events_create failed: %s", e)
        return _err(str(e))


def handle_events_update(args: dict) -> str:
    eid = args.get("event_id")
    if not eid:
        return _err("event_id is required")
    err = _validate_enum(args.get("status"), EVENT_STATUS, "status")
    if err:
        return _err(err)
    err = _validate_enum(args.get("permits_status"), PERMIT_STATUS, "permits_status")
    if err:
        return _err(err)
    fields = {k: v for k, v in args.items() if v is not None and k != "event_id"}
    try:
        with _connect() as conn, conn.cursor() as cur:
            row = _update(cur, "events", "id", eid, fields)
            if not row:
                return _err(f"no event with id {eid}")
            conn.commit()
            cur.execute("SELECT e.*, v.name AS venue_name FROM events e "
                        "LEFT JOIN venues v ON v.id = e.venue_id WHERE e.id = %s", (eid,))
            readback = _rows(cur)[0]
            try:
                cur.execute("SELECT * FROM venue_clashes(0)")
                clashes = [c for c in _rows(cur)
                           if readback["name"] in (c.get("event_a"), c.get("event_b"))]
            except Exception:
                clashes = []
        out = {"event": readback}
        if clashes:
            out["venue_clashes"] = clashes
        return _ok(out)
    except Exception as e:
        logger.debug("events_update failed: %s", e)
        return _err(str(e))


def _upsert_by_name(cur, table: str, fields: dict) -> dict:
    """Insert, or update the existing row with the same name. Reads back after."""
    bad = _reject_unknown(table, fields)
    if bad:
        raise ValueError(bad)
    if not fields.get("name"):
        raise ValueError("name is required")
    cols = list(fields)
    ph = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "name")
    if updates:
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
               f"ON CONFLICT (name) DO UPDATE SET {updates} RETURNING *")
    else:
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) "
               f"ON CONFLICT (name) DO NOTHING RETURNING *")
    cur.execute(sql, [fields[c] for c in cols])
    got = _rows(cur)
    if not got:
        # DO NOTHING path: the row already existed unchanged. Read it.
        cur.execute(f"SELECT * FROM {table} WHERE name = %s", (fields["name"],))
        got = _rows(cur)
    return got[0]


def handle_venues_save(args: dict) -> str:
    fields = {k: v for k, v in args.items() if v is not None and k in VENUE_COLS}
    try:
        with _connect() as conn, conn.cursor() as cur:
            row = _upsert_by_name(cur, "venues", fields)
            conn.commit()
        return _ok({"venue": row})
    except Exception as e:
        logger.debug("venues_save failed: %s", e)
        return _err(str(e))


def handle_suppliers_save(args: dict) -> str:
    fields = {k: v for k, v in args.items() if v is not None and k in SUPPLIER_COLS}
    try:
        with _connect() as conn, conn.cursor() as cur:
            row = _upsert_by_name(cur, "suppliers", fields)
            conn.commit()
        return _ok({"supplier": row})
    except Exception as e:
        logger.debug("suppliers_save failed: %s", e)
        return _err(str(e))


def handle_tasks_save(args: dict) -> str:
    err = _validate_enum(args.get("status"), TASK_STATUS, "status")
    if err:
        return _err(err)
    task_id = args.get("task_id")
    fields = {k: v for k, v in args.items() if v is not None and k in TASK_COLS}
    if not task_id and not fields.get("title"):
        return _err("title is required when creating a task")
    if not task_id and not fields.get("event_id"):
        return _err("event_id is required when creating a task")
    try:
        with _connect() as conn, conn.cursor() as cur:
            if task_id:
                row = _update(cur, "event_tasks", "id", task_id, fields)
                if not row:
                    return _err(f"no task with id {task_id}")
            else:
                row = _insert(cur, "event_tasks", fields)
            conn.commit()
            cur.execute("SELECT * FROM event_tasks WHERE id = %s", (row["id"],))
            readback = _rows(cur)[0]
        return _ok({"task": readback})
    except Exception as e:
        logger.debug("tasks_save failed: %s", e)
        return _err(str(e))
