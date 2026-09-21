---
name: events-ops
description: Capture, query and maintain El Gouna event data in Supabase for Lola PA — event intake from plain-language Telegram messages, venue and supplier records, run-sheets, clash detection, and the daily briefing. Load before writing ANY event data.
---

# Events Ops

The operating procedure for Hisham's event data. **Read this before writing event
data** — the schema and the intake rules are here, and guessing at either creates
records nobody can trust.

## The rule that matters most

**Structured event data goes in Postgres tables. Memory is for everything else.**

Never record an event's dates only as a memory. If it has a date and a venue, it
is a row in `events`. Memory holds the things that are not rows: how Hisham likes
his briefing, a venue manager who is difficult, a supplier who quietly doubles a
quote on the second booking.

## Connection

Supabase Postgres. From the deploy environment, connection details come from the
environment (`SUPABASE_MEMORY_URL` / `SUPABASE_MEMORY_KEY` for the memory plugin;
the same project holds the events tables). From a local shell, use `psycopg` —
`psql` is not installed. **Never trust a shell `$DATABASE_URL`** — read the real
value from the environment or config, and confirm the project ref before writing.

Always verify a write by reading the row back. A successful query call is not
proof the data landed.

## Schema

| Table | What goes in it |
|---|---|
| `venues` | Every place an event happens. Zone, kind, capacities, curfew, power, rigging, access, weather exposure. |
| `suppliers` | Vendors by category: AV, staging, catering, security, talent, transport, permits and so on. Includes lead time, payment terms and a performance note. |
| `events` | The event itself: name, type, status, dates (including setup and teardown), venue, expected attendance, permits, budget. |
| `event_contacts` | People attached to one event in a role: sponsor, talent, venue contact, authority, hotel GM. |
| `event_tasks` | Follow-through. Title, owner, due date, status, `critical` flag, category. |

### Status vocabulary — do not invent new values

`events.status`: `proposed` → `confirmed` → `in_production` → `live` → `completed`,
plus `cancelled`.

`permits_status`: `unknown` | `not_started` | `applied` | `granted` | `refused`.

`event_tasks.status`: `open` | `blocked` | `done` | `dropped`.

### Dates

**Always fill `setup_starts_on` and `teardown_ends_on` whenever you know them.**
They are what make clash detection real — a concert at the Marina and a festival on
the same stretch of waterfront can clash purely on build and get-out days even when
the performance dates do not overlap. If you do not know them, say so rather than
assuming they equal the event dates.

### Venue confidence

While a venue is not confirmed, leave `venue_id` NULL and put the best guess in
`venue_text`. **Never** set `venue_id` on a maybe — a linked venue is a claim that
the venue said yes, and it will silently pass clash checks as if it were solid.

## Intake: plain-language message to record

Hisham will message something like:

> "New event: Sunset Sessions on Thursday 12 October at the Marina, around 400
> people, DJ from Cairo, need to sort the sound"

Do this:

1. **Extract** name, date(s), venue, attendance, type, and anything about
   suppliers, permits, talent or budget.
2. **Resolve the venue** — match against `venues` by name and zone. If it is not
   there, either create it (if you know enough) or leave `venue_text` and flag
   that the venue needs adding.
3. **Resolve the date to a full date with weekday and year.** "Thursday 12 October"
   is ambiguous across years — take the next occurrence, and if the year is
   genuinely unclear, ask. Call `get-current-time` first; never compute relative
   dates from memory.
4. **Check for clashes before saving.** Run `venue_clashes()` and look at the new
   event's window against existing events sharing that venue. If there is a clash,
   **report it in the same reply as the confirmation** — do not save silently and
   mention it later.
5. **Insert the event**, then read it back.
6. **Confirm in plain language** with the key fields, the weekday, and anything
   still missing. Do not dump the raw row.

Example confirmation:

> Saved: **Sunset Sessions**, Thursday 12 October 2026, El Gouna Marina, ~400
> standing, type: concert, status: proposed.
> Missing: setup/teardown dates, permit status, supplier.
> No venue clash, but there is a **catering setup at the Marina on 10 October**
> whose get-out runs to the 11th — 1 day of overlap with your build.

## The daily briefing

Every morning, build the briefing in this order:

1. **Today** — events live today, plus setup or teardown on site today.
2. **This week** — what is coming in the next 7 days.
3. **At risk** — from `at_risk()`: open critical tasks, overdue items, permits not
   granted, events with no confirmed venue.
4. **Silence** — suppliers or contacts who were expected to reply and have not.

Keep it scannable. If a section is empty, one line saying so, then move on. Never
pad. If there is nothing at all, say "nothing on today" and stop — a briefing that
fabricates urgency trains Hisham to ignore it.

## Run-sheet generation

A run-sheet for an event is assembled from the tables, not invented:

- **Header**: name, type, date with weekday, venue with zone, expected attendance.
- **Venue constraints**: curfew, power, rigging, access notes, weather exposure.
- **Contacts**: from `event_contacts`, grouped by role.
- **Suppliers**: from `suppliers` joined through the event's tasks and contacts,
  each with lead time and payment terms.
- **Timeline**: setup window through teardown, with tasks by category.
- **Open items**: tasks not `done`, critical ones first.

If a section has no data, say the data is missing. **Do not fill a run-sheet with
plausible-sounding detail** — a run-sheet with an invented load-in time is worse
than one that says the load-in time is unknown.

## Pitfalls

- **Do not put an event in memory instead of the table.** It cannot be queried and
  it will not appear in clash checks or the briefing.
- **Do not treat `venue_text` as a booked venue.** It is a note, not a booking.
- **Do not skip teardown dates.** Most real clashes in an events town are overlap
  in the build and get-out windows.
- **Do not compute dates mentally.** Call `get-current-time`, then compute.
- **Do not write to any table without reading the row back** and confirming.
- **Never state a price or budget figure that is not in the database or given by
  Hisham.** If it is unknown, it is unknown.
- Existing rows may legitimately have NULL setup/teardown dates. Handle NULL with
  `COALESCE` (the provided functions already do) rather than treating it as an error.
