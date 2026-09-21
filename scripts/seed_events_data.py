#!/usr/bin/env python3
"""Seed Lola's El Gouna data: venues, suppliers, and optionally events.

The events tables start empty, and Lola is useless until they are populated. This
imports a CSV so a season's worth of venues, suppliers and events can be loaded in
one go instead of one Telegram message at a time. Hisham can then maintain the data
by talking to Lola.

Usage:
    python scripts/seed_events_data.py --venues venues.csv
    python scripts/seed_events_data.py --suppliers suppliers.csv
    python scripts/seed_events_data.py --events events.csv
    python scripts/seed_events_data.py --venues venues.csv --suppliers suppliers.csv
    python scripts/seed_events_data.py --venues venues.csv --dry-run

Connection:
    Reads SUPABASE_DB_URL from the environment (or .env). Uses psycopg, because
    psql is not installed in the container. NEVER trust a shell DATABASE_URL -
    confirm the Supabase project ref before writing.

Columns (header row required, order does not matter, blanks allowed):

  venues.csv
      name, zone, kind, capacity_seated, capacity_standing, address,
      contact_name, contact_phone, contact_email, curfew_time,
      power_notes, rigging_notes, access_notes, weather_exposed, notes

  suppliers.csv
      name, category, based_in, contact_name, contact_phone, contact_email,
      website, lead_time_days, payment_terms, currency, reliable,
      performance_notes, notes

  events.csv
      name, event_type, status, starts_on, ends_on, setup_starts_on,
      teardown_ends_on, venue, attendance_expected, audience, ticket_price,
      currency, owner, description, permits_status, permit_notes, sponsors,
      budget_estimate, risk_notes

Dates are ISO (YYYY-MM-DD). Booleans accept true/false/yes/no/1/0.

Rows are upserted on `name`, so re-running with corrected data updates in place
rather than creating duplicates. `--dry-run` parses and reports without writing.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import pathlib
import sys

# Per-table column definitions: csv header -> (db column, type)
VENUE_COLS = {
    "name": ("name", str),
    "zone": ("zone", str),
    "kind": ("kind", str),
    "capacity_seated": ("capacity_seated", int),
    "capacity_standing": ("capacity_standing", int),
    "address": ("address", str),
    "contact_name": ("contact_name", str),
    "contact_phone": ("contact_phone", str),
    "contact_email": ("contact_email", str),
    "curfew_time": ("curfew_time", str),
    "power_notes": ("power_notes", str),
    "rigging_notes": ("rigging_notes", str),
    "access_notes": ("access_notes", str),
    "weather_exposed": ("weather_exposed", bool),
    "notes": ("notes", str),
}

SUPPLIER_COLS = {
    "name": ("name", str),
    "category": ("category", str),
    "based_in": ("based_in", str),
    "contact_name": ("contact_name", str),
    "contact_phone": ("contact_phone", str),
    "contact_email": ("contact_email", str),
    "website": ("website", str),
    "lead_time_days": ("lead_time_days", int),
    "payment_terms": ("payment_terms", str),
    "currency": ("currency", str),
    "reliable": ("reliable", bool),
    "performance_notes": ("performance_notes", str),
    "notes": ("notes", str),
}

EVENT_COLS = {
    "name": ("name", str),
    "event_type": ("event_type", str),
    "status": ("status", str),
    "starts_on": ("starts_on", "date"),
    "ends_on": ("ends_on", "date"),
    "setup_starts_on": ("setup_starts_on", "date"),
    "teardown_ends_on": ("teardown_ends_on", "date"),
    "venue": ("_venue_name", str),  # resolved to venue_id at insert time
    "attendance_expected": ("attendance_expected", int),
    "audience": ("audience", str),
    "ticket_price": ("ticket_price", float),
    "currency": ("currency", str),
    "owner": ("owner", str),
    "description": ("description", str),
    "permits_status": ("permits_status", str),
    "permit_notes": ("permit_notes", str),
    "sponsors": ("sponsors", str),
    "budget_estimate": ("budget_estimate", float),
    "risk_notes": ("risk_notes", str),
}

VALID_EVENT_STATUS = {"proposed", "confirmed", "in_production", "live", "completed", "cancelled"}
VALID_PERMIT_STATUS = {"unknown", "not_started", "applied", "granted", "refused"}


def load_dotenv(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def coerce(value: str, typ):
    """Convert a CSV string to its database type. Blank becomes None."""
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    if typ is str:
        return value
    if typ is int:
        return int(float(value))  # tolerate "400.0"
    if typ is float:
        return float(value)
    if typ == "date":
        return dt.date.fromisoformat(value)
    if typ is bool:
        low = value.lower()
        if low in {"true", "yes", "1", "y"}:
            return True
        if low in {"false", "no", "0", "n"}:
            return False
        raise ValueError(f"not a boolean: {value!r}")
    raise TypeError(typ)


def read_csv(path: pathlib.Path, colmap: dict) -> tuple[list[dict], list[str]]:
    """Return (rows, problems). Unknown headers are reported, not silently dropped."""
    rows: list[dict] = []
    problems: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return [], [f"{path.name}: no header row"]
        unknown = [h for h in reader.fieldnames if h and h.strip() not in colmap]
        for h in unknown:
            problems.append(f"{path.name}: column {h!r} is not in the schema and was ignored")
        for n, raw in enumerate(reader, start=2):  # line 1 is the header
            row = {}
            for csvname, (dbcol, typ) in colmap.items():
                if csvname not in (reader.fieldnames or []):
                    continue
                try:
                    val = coerce(raw.get(csvname), typ)
                except Exception as exc:
                    problems.append(f"{path.name} line {n}: {csvname}={raw.get(csvname)!r} invalid ({exc})")
                    val = None
                if val is not None:
                    row[dbcol] = val
            if not row.get("name"):
                problems.append(f"{path.name} line {n}: missing 'name', row skipped")
                continue
            rows.append(row)
    return rows, problems


def upsert(cur, table: str, rows: list[dict], conflict: str = "name") -> int:
    """INSERT ... ON CONFLICT (conflict) DO UPDATE. Returns rows written."""
    written = 0
    for row in rows:
        cols = list(row)
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != conflict)
        if updates:
            sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                   f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}")
        else:
            sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                   f"ON CONFLICT ({conflict}) DO NOTHING")
        cur.execute(sql, [row[c] for c in cols])
        written += 1
    return written


def validate_events(rows: list[dict]) -> list[str]:
    """Catch the mistakes that would silently corrupt clash detection."""
    problems = []
    for row in rows:
        name = row.get("name")
        st = row.get("status")
        if st and st not in VALID_EVENT_STATUS:
            problems.append(f"event {name!r}: status {st!r} not in {sorted(VALID_EVENT_STATUS)}")
        ps = row.get("permits_status")
        if ps and ps not in VALID_PERMIT_STATUS:
            problems.append(f"event {name!r}: permits_status {ps!r} not in {sorted(VALID_PERMIT_STATUS)}")
        s, e = row.get("starts_on"), row.get("ends_on")
        if s and e and e < s:
            problems.append(f"event {name!r}: ends_on {e} is before starts_on {s}")
        setup = row.get("setup_starts_on")
        if setup and s and setup > s:
            problems.append(f"event {name!r}: setup_starts_on {setup} is after starts_on {s}")
        td, te = row.get("teardown_ends_on"), e or s
        if td and te and td < te:
            problems.append(f"event {name!r}: teardown_ends_on {td} is before the event ends {te}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed Lola's El Gouna event data from CSV.")
    ap.add_argument("--venues", type=pathlib.Path)
    ap.add_argument("--suppliers", type=pathlib.Path)
    ap.add_argument("--events", type=pathlib.Path)
    ap.add_argument("--env-file", type=pathlib.Path, default=pathlib.Path(".env"))
    ap.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    args = ap.parse_args()

    if not any([args.venues, args.suppliers, args.events]):
        ap.error("give at least one of --venues / --suppliers / --events")

    load_dotenv(args.env_file)

    plan: dict[str, list[dict]] = {}
    problems: list[str] = []

    if args.venues:
        rows, p = read_csv(args.venues, VENUE_COLS)
        plan["venues"] = rows
        problems += p
    if args.suppliers:
        rows, p = read_csv(args.suppliers, SUPPLIER_COLS)
        plan["suppliers"] = rows
        problems += p
    if args.events:
        rows, p = read_csv(args.events, EVENT_COLS)
        plan["events"] = rows
        problems += p + validate_events(rows)

    for table, rows in plan.items():
        print(f"{table}: {len(rows)} row(s) parsed")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)

    if args.dry_run:
        print("\nDry run: nothing written.")
        return 1 if problems else 0

    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        print("\nSUPABASE_DB_URL is not set (checked the environment and "
              f"{args.env_file}). Nothing written.", file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("\npsycopg is not installed. Install it with: pip install 'psycopg[binary]'",
              file=sys.stderr)
        return 2

    # Refuse to run if the target is not the expected Supabase project.
    expected_ref = os.environ.get("SUPABASE_PROJECT_REF")
    if expected_ref and expected_ref not in dsn:
        print(f"\nRefusing to write: SUPABASE_PROJECT_REF={expected_ref} is not in "
              "SUPABASE_DB_URL. Check you are pointed at the right project.",
              file=sys.stderr)
        return 2

    written = {}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            if "venues" in plan:
                written["venues"] = upsert(cur, "venues", plan["venues"])
            if "suppliers" in plan:
                written["suppliers"] = upsert(cur, "suppliers", plan["suppliers"])
            if "events" in plan:
                # Resolve venue names to ids. An unknown venue leaves venue_id NULL
                # and keeps the name in venue_text, so nothing is silently invented.
                resolved = []
                unknown_venues = set()
                for row in plan["events"]:
                    vname = row.pop("_venue_name", None)
                    if vname:
                        cur.execute("SELECT id FROM venues WHERE lower(name) = lower(%s)", (vname,))
                        hit = cur.fetchone()
                        if hit:
                            row["venue_id"] = hit[0]
                        else:
                            row["venue_text"] = vname
                            unknown_venues.add(vname)
                    resolved.append(row)
                if unknown_venues:
                    print("\nWARNING: these venue names are not in the venues table, so the "
                          "events were saved with venue_text only (no clash checking against "
                          "them until the venue exists):")
                    for v in sorted(unknown_venues):
                        print("  -", v)
                written["events"] = upsert(cur, "events", resolved)
        conn.commit()

    print("\nWritten:")
    for table, n in written.items():
        print(f"  {table}: {n}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
