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

# ── Voice transcription: make the STT model present and usable ────────────────
#
# Two problems this solves, both of which hit the FIRST voice note:
#
# 1. The model is not in the image (1.62 GB of weights would be paid for on every
#    build), so it downloads on first use. On a cold container that download runs
#    while Hisham waits, and it can exceed the transcription timeout.
#
# 2. The cache directory must exist and be owned by the runtime user BEFORE
#    whisper writes to it, or the write fails with a permission error. This has
#    already been observed once on this deployment as
#       [Errno 13] Permission denied: '/opt/data/.cache/fastembed/...'
#    which is the same class of ownership drift 015-supervise-perms guards
#    against for supervise trees.
STT_MODEL_DIR="${HERMES_HOME:-/opt/data}/.cache/whisper"

if mkdir -p "$STT_MODEL_DIR" 2>/dev/null; then
  # Match the ownership the runtime user needs. hermes is UID 10000 in this image.
  chown -R hermes:hermes "$STT_MODEL_DIR" 2>/dev/null || \
    log "could not chown $STT_MODEL_DIR (continuing)"
  log "STT cache ready at $STT_MODEL_DIR"
else
  log "could not create $STT_MODEL_DIR (continuing)"
fi

# Pre-fetch the model in the BACKGROUND so the first voice note is instant.
# Deliberately not awaited: a 1.62 GB download must never delay the gateway, and
# must never be able to block boot. If it fails, transcription still works and
# simply downloads on demand instead.
if [ "$(ls -A "$STT_MODEL_DIR" 2>/dev/null | wc -l)" -eq 0 ]; then
  log "STT model absent, prefetching in background (1.62 GB)"
  (
    "$PY" - <<'PYEOF' >>/var/log/stt-prefetch.log 2>&1
import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
try:
    from faster_whisper import WhisperModel
    root = os.path.join(os.environ.get("HERMES_HOME", "/opt/data"), ".cache", "whisper")
    # Instantiating the model downloads it if missing. Small footprint here on
    # purpose: we only want the weights on disk, not a resident model.
    WhisperModel("turbo", download_root=root, device="cpu", compute_type="int8")
    print("prefetch complete")
except Exception as exc:
    print(f"prefetch failed: {type(exc).__name__}: {exc}")
PYEOF
  ) &
  log "prefetch started"
else
  log "STT model already cached, skipping prefetch"
fi

log "schema sync complete"
exit 0
