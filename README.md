# Lola PA

Lola is the personal events assistant for **Hisham Nabil, Events Manager at
El Gouna** (Orascom's resort town on the Red Sea).

One **concierge** front door routes to four specialists, with persistent semantic
memory, Google Calendar, a Supabase events database, and a Telegram gateway.
Forked from [Hermes Agent](https://hermes-agent.nousresearch.com) and built on the
Hermes-PA template kit.

## Architecture

```
Telegram
    |
  LOLA (concierge front door)  -- classifies, routes, replies as ONE assistant
    |- pa       Hisham's calendar, reminders, briefings, travel
    |- events   the event lifecycle: events, venues, run-sheets, suppliers
    |- ops      tasks, follow-ups, risk across events
    |- admin    budgets, contracts, invoices, vendor records
         |
  Supabase Postgres (event data + semantic memory)
```

- **Model:** Ollama Cloud (Hisham's key), with an OpenAI fallback so the bot does
  not go silent when Ollama is down or rate-limited. Provider and models are single
  config values in `config.yaml`, swappable without a rebuild.
- **Memory:** custom Supabase plugin (`plugins/memory/supabase/`) with hybrid
  keyword + vector recall, persona-scoped, local `fastembed` embeddings
  (`nomic-embed-text-v1.5`, 768-dim).
- **Event data:** real Postgres tables (`venues`, `events`, `event_contacts`,
  `suppliers`, `event_tasks`) with clash-detection and at-risk functions. See
  `scripts/supabase_events_migration.sql`.
- **Timezone:** Africa/Cairo (EET).
- **Language:** English by default, Arabic when Hisham writes Arabic.

## Layout

| Path | What |
|---|---|
| `config.yaml`, `SOUL.md` | concierge config + routing soul |
| `profiles/<name>/` | the four specialists (config + soul) |
| `plugins/memory/supabase/` | custom Supabase memory provider |
| `skills/events-ops/` | **the events operating procedure** (schema, intake, run-sheets) |
| `scripts/supabase_migration.sql` | memory schema (tables, pgvector, search fns) |
| `scripts/supabase_events_migration.sql` | **events schema** (venues, events, tasks, suppliers, clash fns) |
| `railway/railway-init.sh` | boot-time materialisation of git/Google creds from env |
| `scripts/railway-push.sh` | set Railway vars + deploy |

## Setup

1. Run `scripts/supabase_migration.sql`, then `scripts/supabase_events_migration.sql`
   in the Supabase SQL Editor.
2. `cp .env.example ~/.hermes/.env` and fill in real values.
3. Install Hermes; copy `config.yaml`, `SOUL.md`, `profiles/`, `plugins/`,
   `skills/` into `~/.hermes/`.
4. `pip install fastembed` into the Hermes venv.
5. Local: `hermes`. Cloud: deploy with `Dockerfile.railway` on Railway.

## Seed data still needed

The events tables start empty. Before Lola is useful, Hisham needs to seed:
his **venues** (name, zone, capacity, curfew), his **suppliers** (category, based
in, lead time), and a first real **event**.
