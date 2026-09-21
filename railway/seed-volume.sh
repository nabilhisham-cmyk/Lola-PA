#!/command/with-contenv sh
# seed-volume.sh — populate the Railway persistent volume on first boot.
#
# WHY THIS EXISTS
# ---------------
# HERMES_HOME=/opt/data holds config.yaml, profiles/, plugins/, SOUL.md,
# auth.json and runtime state. The Dockerfile bakes a seed into /opt/data at
# build time — but a Railway *persistent volume* mounted at /opt/data mounts
# EMPTY and SHADOWS that baked content (Railway, unlike Docker named volumes,
# does not copy image data into a fresh volume). With config.yaml hidden,
# Hermes loses model.provider=ollama-cloud and dies with "model provider
# failure" even though OLLAMA_API_KEY is set.
#
# So we keep an immutable seed at /opt/railway-seed (OUTSIDE the mount) and:
#   * first boot (empty volume)   -> copy the whole seed into /opt/data
#   * every boot                  -> re-sync config-as-code (config.yaml,
#                                    SOUL.md) from the image so model/provider
#                                    settings always match the deployed image,
#                                    while preserving mutable runtime state
#                                    (sessions, auth.json, cron, caches, kanban).
#
# Runs as cont-init 00-railway-seed, i.e. BEFORE profile reconciliation,
# railway-init, and the gateway — and AFTER the volume is mounted.
set -eu

SEED=/opt/railway-seed
DATA="${HERMES_HOME:-/opt/data}"
log() { printf '[seed-volume] %s\n' "$1"; }

[ -d "$SEED" ] || { log "no seed dir at $SEED, nothing to do"; exit 0; }
mkdir -p "$DATA"

if [ ! -f "$DATA/config.yaml" ]; then
  # First boot onto an empty (or volume-shadowed) data dir.
  log "no config.yaml in $DATA — seeding full state from image"
  cp -a "$SEED/." "$DATA/"
  chown -R hermes:hermes "$DATA"
  log "full seed complete"
  exit 0
fi

# Subsequent boots: keep runtime state, but force ALL config-as-code to match
# the image. Files AND directories — a volume can end up with config.yaml but
# missing profiles/plugins/scripts (e.g. a volume attached before this script
# existed, which then only got the two top-level files synced). Restoring the
# directories every boot is what keeps the Supabase memory plugin, the
# specialist profiles, and the cron-setup scripts present on the volume.

# Single files: overwrite from image.
for f in config.yaml SOUL.md; do
  if [ -f "$SEED/$f" ]; then
    cp -a "$SEED/$f" "$DATA/$f"
    chown hermes:hermes "$DATA/$f"
    log "re-synced $f from image"
  fi
done

# Repo-managed directories: fully replace from image (declarative — any runtime
# drift here is not meant to persist; real state lives in sessions/, cron/,
# kanban.db, auth.json, state.db, memories/ which we never touch).
for d in profiles plugins scripts; do
  if [ -d "$SEED/$d" ]; then
    rm -rf "$DATA/$d"
    cp -a "$SEED/$d" "$DATA/$d"
    chown -R hermes:hermes "$DATA/$d"
    log "restored $d/ from image"
  fi
done

# skills/: MERGE, not replace — the agent can create skills at runtime, so we
# overlay the repo's skills without deleting volume-only ones.
if [ -d "$SEED/skills" ]; then
  mkdir -p "$DATA/skills"
  cp -a "$SEED/skills/." "$DATA/skills/"
  chown -R hermes:hermes "$DATA/skills"
  log "merged skills/ from image"
fi

log "config-as-code sync complete"
