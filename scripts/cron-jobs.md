# Cron Jobs — created after deploy

Lola's scheduled work. Run `python3 scripts/setup-cron-jobs.py` inside the Railway
container (or via `hermes cron create` in a Telegram session) to create them. The
script is idempotent: it matches jobs by name and only creates what is missing.

---

## 1. events-briefing — the daily events briefing

**Schedule:** `0 7 * * *` (07:00 Africa/Cairo)
**Delivery:** `origin` (Hisham's own Telegram chat)
**Type:** agent job

This is the backbone of Lola. It is what Hisham sees every morning, and it is what
forces the event data in Supabase to stay accurate: an empty briefing is a visible
failure, so the data gets maintained.

It reports five sections in order:

1. **Today** — events live today, plus setup or teardown on site today.
2. **This week** — the next 7 days, day-of-week included.
3. **At risk** — from `at_risk()`: overdue or open critical tasks, permits not
   granted, events with no confirmed venue. States the consequence, not just the fact.
4. **Clashes** — from `venue_clashes(0)`, including build and get-out overlap.
5. **Chase list** — suppliers or contacts expected to have replied and who have not.

An empty day produces one line, not padding. Manufactured urgency makes the real
warnings worthless.

**Note:** `0 7 * * *` is interpreted in the container's timezone, which is set to
`Africa/Cairo` in `config.yaml`. That is Hisham's local time.

---

## 2. heartbeat — is the box alive

**Schedule:** `*/15 * * * *`
**Type:** script only (`no_agent: true`), runs `scripts/heartbeat.py`

Runs inside the container and sends a Telegram alert if the gateway process is
dead. No LLM involved, so it still fires when the model provider is down. That
matters: the failure it guards against is exactly the kind that would also stop an
agent-based watchdog from reporting.

**Cost note:** GitHub Actions bills a whole minute per job, so schedules like this
belong in Hermes cron on Railway, not in Actions. Keep Actions for CI only.

---

## 3. error-monitor

**Schedule:** `*/30 * * * *`
**Type:** script only, runs `scripts/error-monitor.py`

Scans logs for error markers and reports. Silent when clean.

---

## 4. daily-backup

**Schedule:** `0 3 * * *` (03:00 Africa/Cairo)
**Type:** script only, runs `scripts/backup.py`

Backs up runtime state to Supabase Storage. Keeps `HERMES_BACKUP_KEEP` copies
(default 14).

---

## Delivery rule

Status, briefing and escalation output go to **Hisham's own chat only**
(`deliver: origin` resolves to the chat that created the job). Never route a
briefing or a status report into a group, and never use `deliver: all`.

## Adding a briefing at a second time

If Hisham wants an evening look-ahead as well, create a second job with the same
prompt and a different schedule (for example `0 18 * * *`), and change the prompt's
first line to "Build Hisham's end-of-day look-ahead" so the two are not confused in
the job list.
