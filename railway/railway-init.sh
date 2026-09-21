#!/usr/bin/env sh
# railway-init.sh — boot-time materialisation of file-based credentials on Railway.
#
# Railway injects secrets as ENV VARS (read directly by Hermes / the Supabase
# memory plugin via os.environ). A few integrations need real FILES, which we
# write here from base64-encoded Railway variables so no secret is baked into
# the image. Runs once per container start via /etc/cont-init.d/03-railway-init.
set -eu

HOME_DIR="${HERMES_HOME:-/opt/data}"
log() { printf '[railway-init] %s\n' "$1"; }

# --- Git credentials (optional — only if GITHUB_TOKEN is set) --------------
# PA Template doesn't use GitHub by default, but the hook is here in case it's
# enabled later.
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_USER:-}" ]; then
  [ -n "${GIT_AUTHOR_NAME:-}" ]  && git config --global user.name  "$GIT_AUTHOR_NAME"  || true
  [ -n "${GIT_AUTHOR_EMAIL:-}" ] && git config --global user.email "$GIT_AUTHOR_EMAIL" || true
  log "git identity configured"
  if command -v gh >/dev/null 2>&1; then
    _gh_token="$GITHUB_TOKEN"
    unset GH_TOKEN GITHUB_TOKEN
    mkdir -p "$HOME_DIR/.config/gh"
    chown hermes:hermes "$HOME_DIR/.config/gh" 2>/dev/null || true
    if command -v s6-setuidgid >/dev/null 2>&1; then
      printf '%s' "$_gh_token" | env HOME="$HOME_DIR" s6-setuidgid hermes gh auth login --with-token >/dev/null 2>&1 && \
        log "gh CLI authenticated (as hermes)" || log "gh CLI auth failed (non-fatal)"
    else
      printf '%s' "$_gh_token" | gh auth login --with-token >/dev/null 2>&1
      if [ -f /root/.config/gh/hosts.yml ]; then
        cp /root/.config/gh/hosts.yml "$HOME_DIR/.config/gh/hosts.yml"
        chown hermes:hermes "$HOME_DIR/.config/gh/hosts.yml" 2>/dev/null || true
        chmod 600 "$HOME_DIR/.config/gh/hosts.yml"
        log "gh CLI authenticated (copied to hermes home)"
      else
        log "gh CLI auth failed (non-fatal)"
      fi
    fi
    git config --global credential.helper '!gh auth git-credential'
    log "git credential helper set to gh CLI"
  fi
fi

# --- Google Calendar OAuth (Desktop client keys + cached tokens) -----------
# Provide these as base64 in Railway:
#   GCP_OAUTH_KEYS_B64=base64 of gcp-oauth.keys.json
#   GCAL_TOKENS_B64=base64 of ~/.config/google-calendar-mcp/tokens.json
if [ -n "${GCP_OAUTH_KEYS_B64:-}" ]; then
  mkdir -p "$HOME_DIR/secrets"
  printf '%s' "$GCP_OAUTH_KEYS_B64" | base64 -d > "$HOME_DIR/secrets/gcp-oauth.keys.json"
  chmod 600 "$HOME_DIR/secrets/gcp-oauth.keys.json"
  log "gcp-oauth.keys.json written"
fi
if [ -n "${GCAL_TOKENS_B64:-}" ]; then
  mkdir -p "$HOME_DIR/.config/google-calendar-mcp"
  printf '%s' "$GCAL_TOKENS_B64" | base64 -d > "$HOME_DIR/.config/google-calendar-mcp/tokens.json"
  chmod 600 "$HOME_DIR/.config/google-calendar-mcp/tokens.json"
  log "google-calendar tokens written"
fi

# --- Warm the local embedder so first recall isn't slow --------------------
python3 - <<'PY' 2>/dev/null || true
try:
    from fastembed import TextEmbedding
    list(TextEmbedding(model_name="nomic-ai/nomic-embed-text-v1.5").embed(["warmup"]))
except Exception:
    pass
PY

log "init complete"