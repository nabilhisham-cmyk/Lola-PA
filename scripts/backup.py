#!/usr/bin/env python3
"""Daily backup of durable Hermes state to Supabase Storage.

Runs as a no-agent cron job. Tars the *valuable, non-regenerable* runtime state
and uploads it to a private Supabase Storage bucket, keeping the last N backups.

Deliberately EXCLUDED (so we never write secrets to storage, and don't bloat the
archive with regenerable data):
  - .env / auth.json     -> secrets, reconstructable from Railway env vars
  - config.yaml/profiles/plugins/skills/scripts -> config-as-code, re-seeded from image
  - .cache / models_dev_cache.json / fastembed -> regenerable caches

Stdlib only (matches heartbeat.py / error-monitor.py). On failure it sends a
Telegram alert to the owner; on success it just prints a status line.
"""
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

HOME = os.environ.get("HERMES_HOME", "/opt/data")
BUCKET = os.environ.get("HERMES_BACKUP_BUCKET", "hermes-backups")
KEEP = int(os.environ.get("HERMES_BACKUP_KEEP", "14"))

# Paths (relative to HERMES_HOME) worth preserving across a volume loss.
INCLUDE = ["cron/jobs.json", "kanban.db", "kanban", "sessions", "state.db", "memories"]


def _parse_env_file(path):
    vals = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return vals


def load_creds():
    url = os.environ.get("SUPABASE_MEMORY_URL", "")
    key = os.environ.get("SUPABASE_MEMORY_KEY", "")
    if not (url and key):  # fall back to the .env on the volume
        env = _parse_env_file(os.path.join(HOME, ".env"))
        url = url or env.get("SUPABASE_MEMORY_URL", "")
        key = key or env.get("SUPABASE_MEMORY_KEY", "")
    return url.rstrip("/"), key


def _req(method, url, key, data=None, headers=None):
    h = {"Authorization": f"Bearer {key}", "apikey": key}
    if headers:
        h.update(headers)
    return urllib.request.urlopen(
        urllib.request.Request(url, data=data, method=method, headers=h), timeout=120
    )


def ensure_bucket(base, key):
    try:
        _req("POST", f"{base}/storage/v1/bucket", key,
             data=json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode(),
             headers={"Content-Type": "application/json"})
    except urllib.error.HTTPError as e:
        if e.code not in (400, 409):  # already exists -> fine
            raise


def make_tar():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in INCLUDE:
            p = os.path.join(HOME, rel)
            if os.path.exists(p):
                tar.add(p, arcname=rel)
    return buf.getvalue()


def upload(base, key, name, blob):
    _req("POST", f"{base}/storage/v1/object/{BUCKET}/{name}", key, data=blob,
         headers={"Content-Type": "application/gzip", "x-upsert": "true"})


def prune(base, key):
    r = _req("POST", f"{base}/storage/v1/object/list/{BUCKET}", key,
             data=json.dumps({"prefix": "", "limit": 1000,
                              "sortBy": {"column": "name", "order": "desc"}}).encode(),
             headers={"Content-Type": "application/json"})
    names = sorted((o["name"] for o in json.loads(r.read())
                    if o.get("name", "").startswith("hermes-")), reverse=True)
    for n in names[KEEP:]:
        try:
            _req("DELETE", f"{base}/storage/v1/object/{BUCKET}/{n}", key)
        except Exception:
            pass


def alert(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    if not (token and chat):
        return
    try:
        data = json.dumps({"chat_id": chat, "text": msg}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}), timeout=10)
    except Exception:
        pass


def main():
    base, key = load_creds()
    if not base or not key:
        print("backup: SUPABASE creds missing; skipping")
        return 0
    try:
        ensure_bucket(base, key)
        name = f"hermes-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
        blob = make_tar()
        upload(base, key, name, blob)
        prune(base, key)
        print(f"backup: uploaded {name} ({len(blob) // 1024} KB) to bucket '{BUCKET}', keep={KEEP}")
        return 0
    except Exception as e:
        detail = e.read().decode()[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
        msg = f"⚠️ Hermes backup FAILED: {detail}"
        print(msg)
        alert(msg)
        return 1


if __name__ == "__main__":
    sys.exit(main())
