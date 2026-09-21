#!/command/with-contenv sh
# apply-migrations.sh — make the database schema match the deployed image.
#
# WHY THIS EXISTS
# ---------------
# Lola's schema lives in Supabase, which is outside the container. Data therefore
# survives a restart, but the SCHEMA definition did not: the migration SQL was
# never shipped in the image and nothing re-applied it. If the Supabase project
# were rebuilt, a second environment stood up, or a table dropped, the running
# container could not reproduce its own database.
#
# This runs at boot as cont-init 04, AFTER the volume is seeded and AFTER
# railway-init has materialised credentials, and BEFORE the gateway starts.
#
# EVERY MIGRATION IS IDEMPOTENT, so re-running is safe and is the whole point:
#   - supabase_migration.sql              CREATE TABLE IF NOT EXISTS
#   - supabase_events_migration.sql       same
#   - supabase_events_migration_v2.sql    IF NOT EXISTS / ADD COLUMN IF NOT EXISTS
#   - supabase_events_migration_v3.sql    same
#   - supabase_meetings_migration.sql     same
#   - supabase_events_seed.sql            guarded WHERE NOT EXISTS
# Each was verified by applying it three times in a row against the live database
# and confirming the row counts did not move.
#
# FAILURE IS NOT FATAL. If Supabase is briefly unreachable at boot, the gateway
# must still start: an assistant that boots with a stale schema is far better than
# one that refuses to boot at all. Failures are logged loudly and the boot
# continues.
set -u

SCRIPTS_DIR="${HERMES_HOME:-/opt/data}/scripts"
DB_URL="${SUPABASE_DB_URL:-}"

log() { printf '[apply-migrations] %s\n' "$1"; }

if [ -z "$DB_URL" ]; then
  log "SUPABASE_DB_URL is not set — skipping. Set it to enable schema sync."
  exit 0
fi

if [ ! -d "$SCRIPTS_DIR" ]; then
  log "no scripts dir at $SCRIPTS_DIR — nothing to apply"
  exit 0
fi

# psycopg is the driver; psql is not installed in this image.
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  log "python3 not found — cannot apply migrations"
  exit 0
fi

MIGRATIONS="
supabase_migration.sql
supabase_events_migration.sql
supabase_events_migration_v2.sql
supabase_events_migration_v3.sql
supabase_meetings_migration.sql
supabase_events_seed.sql
"

for f in $MIGRATIONS; do
  path="$SCRIPTS_DIR/$f"
  if [ ! -f "$path" ]; then
    log "MISSING $f — not shipped in this image, skipped"
    continue
  fi
  # One python process per file so a failure cannot poison the next.
  if "$PY" - "$path" <<'PYEOF'
import os, sys
try:
    import psycopg
except ImportError:
    print("psycopg not installed", file=sys.stderr)
    sys.exit(3)
sql = open(sys.argv[1]).read()
try:
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=25) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
except Exception as e:
    print(f"{type(e).__name__}: {str(e).splitlines()[0]}", file=sys.stderr)
    sys.exit(1)
PYEOF
  then
    log "applied $f"
  else
    log "FAILED $f (non-fatal, boot continues)"
  fi
done

# Inject secrets from the environment into config.yaml. Runs AFTER the volume is
# seeded (00) and AFTER railway-init (03) has materialised credentials, and
# BEFORE the gateway reads the config.
#
# WHY THIS IS HERE AND NOT IN THE MIGRATIONS LIST: the auxiliary lanes (vision,
# web_extract, compression, ...) inherit credentials from model.api_key, and that
# lookup reads config.yaml ONLY with no environment fallback. An env-only key
# therefore leaves every aux lane sending an empty bearer token and getting
#    401 {"error":{"message":"Unauthorized"}}
# The main model is unaffected, because the provider path DOES read
# OLLAMA_API_KEY from the environment, so the breakage is invisible except on the
# aux lanes. Image reading was the visible symptom.
INJECTOR="$SCRIPTS_DIR/inject-config-secrets.py"
if [ -f "$INJECTOR" ]; then
  if "$PY" "$INJECTOR"; then
    log "secrets injected into config.yaml"
  else
    log "FAILED to inject secrets (non-fatal, boot continues)"
  fi
else
  log "no inject-config-secrets.py shipped, skipping secret injection"
fi

log "schema sync complete"
exit 0
