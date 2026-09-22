#!/usr/bin/env python3
"""Diagnose a silent Lola deployment from INSIDE the Railway container.

WHY THIS EXISTS
---------------
"Lola isn't responding" is a symptom with at least six unrelated Railway-level causes,
and Railway reports the service as healthy for every one of them: the container is up,
the healthcheck passes, and no message is ever answered. Reading deploy logs works, but
only if you already know which line matters.

This script checks every cause that can produce a silent bot, and names the one that is
actually firing. It is stdlib-only and read-only by default, so it is safe to run in the
Railway shell against a live deployment:

    railway run python3 /opt/hermes/scripts/lola-doctor.py
    # or, from a shell attached to the container:
    python3 /opt/hermes/scripts/lola-doctor.py

WHAT IT CANNOT SEE
------------------
Whether a SECOND process is holding the bot token. Telegram only reveals that by
answering 409 to a getUpdates call — and issuing that call would steal the polling
session from a HEALTHY gateway and push it toward its own fatal conflict handler.
So that probe is opt-in behind --probe-conflict and must only be run once you already
believe polling is dead. ``pending_updates`` below detects the same condition safely.

EXIT CODE is 1 when any check FAILs, so this can gate a deploy.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

TELEGRAM_API = "https://api.telegram.org"
HERMES_HOME = os.environ.get("HERMES_HOME", "/opt/data")

# Updates queued on Telegram's side with nobody consuming them. A live poller drains the
# queue continuously and sits at 0; anything above this means the consumer is gone.
_PENDING_UPDATES_ALARM = 3

_PASS, _WARN, _FAIL, _INFO = "PASS", "WARN", "FAIL", "INFO"
_MARK = {_PASS: "  ok  ", _WARN: " warn ", _FAIL: " FAIL ", _INFO: " .... "}

_results: list[tuple[str, str, str]] = []


def record(status: str, check: str, detail: str) -> None:
    _results.append((status, check, detail))
    print(f"[{_MARK[status]}] {check}: {detail}", flush=True)


def redact(secret: str) -> str:
    """Enough to recognise a value, never enough to use it."""
    if not secret:
        return "(empty)"
    return f"{secret[:4]}…{secret[-4:]} ({len(secret)} chars)" if len(secret) > 12 else "(set, short)"


class TransportError(Exception):
    """api.telegram.org was unreachable — says nothing about the token or the bot.

    Kept distinct from an API rejection on purpose: "could not connect" and "Telegram
    refused this token" call for opposite fixes, and conflating them sends you rotating a
    perfectly good token while the real problem is egress.
    """


def telegram(token: str, method: str, timeout: float = 20.0) -> tuple[bool, object]:
    """Call a Bot API method. Returns (ok, result-or-api-error); raises TransportError."""
    req = urllib.request.Request(
        f"{TELEGRAM_API}/bot{token}/{method}", headers={"User-Agent": "lola-doctor/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # An HTTP error still came FROM Telegram, so it is an API answer (401, 409, ...).
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return False, f"HTTP {exc.code}"
        return False, payload.get("description") or f"HTTP {exc.code}"
    except Exception as exc:
        raise TransportError(f"{type(exc).__name__}: {exc}") from exc
    if not payload.get("ok"):
        return False, payload.get("description") or "not ok"
    return True, payload.get("result")


# ── checks ────────────────────────────────────────────────────────────────────────────

def check_env() -> str:
    """Railway injects secrets as env vars. A missing one is the cheapest possible cause."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    record(_PASS if token else _FAIL, "TELEGRAM_BOT_TOKEN",
           redact(token) if token else "NOT SET — the Telegram gateway cannot start at all")

    for var, why in (
        ("OLLAMA_API_KEY", "the model provider; without it every turn fails and Lola stays silent"),
        ("SUPABASE_MEMORY_URL", "memory plugin"),
        ("SUPABASE_MEMORY_KEY", "memory plugin"),
        ("SUPABASE_DB_URL", "events tables + boot migrations"),
    ):
        value = (os.environ.get(var) or "").strip()
        status = _PASS if value else (_FAIL if var == "OLLAMA_API_KEY" else _WARN)
        record(status, var, redact(value) if value else f"NOT SET — {why}")
    return token


def check_allowlist() -> None:
    """The single most common silent-drop: an allowlist that does not contain Hisham.

    ``TELEGRAM_ALLOWED_USERS`` holds NUMERIC Telegram user IDs. An @username or a phone
    number there never matches, so every inbound message is dropped before it reaches the
    agent — the bot receives it, logs a WARNING, and says nothing. That is indistinguishable
    from a dead bot unless you read the logs.
    """
    raw = (os.environ.get("TELEGRAM_ALLOWED_USERS") or "").strip()
    allow_all = (os.environ.get("GATEWAY_ALLOW_ALL_USERS") or "").strip().lower() in {"1", "true", "yes"}

    if not raw:
        record(_WARN if allow_all else _FAIL, "TELEGRAM_ALLOWED_USERS",
               "empty — " + ("GATEWAY_ALLOW_ALL_USERS is on, so everyone is allowed"
                             if allow_all else
                             "with no allowlist and no GATEWAY_ALLOW_ALL_USERS, unknown senders "
                             "are dropped or sent a pairing code instead of an answer"))
        return

    ids = [part.strip() for part in raw.split(",") if part.strip()]
    bad = [i for i in ids if not i.lstrip("-").isdigit()]
    if bad:
        record(_FAIL, "TELEGRAM_ALLOWED_USERS",
               f"{bad} are not numeric Telegram user IDs. Telegram matches on the numeric ID "
               f"only — an @username or phone number here drops EVERY message silently. "
               f"Get the real ID by messaging @userinfobot from Hisham's account.")
    else:
        record(_PASS, "TELEGRAM_ALLOWED_USERS", f"{len(ids)} numeric ID(s): {', '.join(ids)}")
    if allow_all:
        record(_WARN, "GATEWAY_ALLOW_ALL_USERS",
               "true — the allowlist is bypassed and ANY Telegram user can talk to Lola")


def check_bot_identity(token: str) -> None:
    ok, result = telegram(token, "getMe")
    if not ok:
        record(_FAIL, "bot token", f"Telegram rejected it: {result}. "
                                   "Re-copy the token from @BotFather into the Railway variable.")
        return
    username = (result or {}).get("username", "?")
    record(_PASS, "bot token", f"valid — @{username} (id {(result or {}).get('id')})")
    if username.lower() != "lola_pa_1_bot":
        record(_WARN, "bot identity",
               f"Railway is holding the token for @{username}, but Hisham is messaging "
               f"@Lola_PA_1_bot. Messages to a bot whose token nobody is polling go nowhere.")


def check_delivery_path(token: str) -> None:
    """getWebhookInfo answers, without disturbing anything, whether updates are being consumed.

    Two decisive signals live here:
      * ``url`` set  -> Telegram is pushing to a webhook, so the gateway's long-polling
                        getUpdates gets 409 forever. Lola never sees a message.
      * ``pending_update_count`` high with no webhook -> nobody is draining the queue, i.e.
                        the poller is dead. In this codebase that is usually the Telegram
                        adapter having exhausted its 5 conflict retries and latched a
                        NON-RETRYABLE fatal error: the container stays up and healthy while
                        the bot is permanently deaf until it is restarted.
    """
    ok, info = telegram(token, "getWebhookInfo")
    if not ok:
        record(_FAIL, "delivery path", f"getWebhookInfo failed: {info}")
        return
    info = info or {}
    url = (info.get("url") or "").strip()
    pending = int(info.get("pending_update_count") or 0)

    if url:
        record(_FAIL, "delivery path",
               f"a WEBHOOK is registered ({url}). Lola polls with getUpdates, and Telegram "
               f"refuses polling while a webhook is set. Clear it: "
               f"curl -X POST '{TELEGRAM_API}/bot<TOKEN>/deleteWebhook'")
    else:
        record(_PASS, "delivery path", "no webhook registered — long polling is the right mode")

    if pending >= _PENDING_UPDATES_ALARM and not url:
        record(_FAIL, "pending_updates",
               f"{pending} updates are queued on Telegram with nobody consuming them. The "
               f"poller is NOT running. Check the deploy log for "
               f"'Telegram polling could not recover' (fatal conflict — another process holds "
               f"this token) and restart the service once the duplicate is gone.")
    elif pending:
        record(_WARN, "pending_updates", f"{pending} queued — normal only if Lola just restarted")
    else:
        record(_PASS, "pending_updates", "0 — updates are being consumed")

    if last_error := info.get("last_error_message"):
        record(_WARN, "telegram last_error", str(last_error))


def check_conflict(token: str) -> None:
    """Opt-in: prove whether a second process holds the token. See the module docstring."""
    ok, result = telegram(token, "getUpdates?offset=-1&limit=1&timeout=0")
    if ok:
        record(_PASS, "token exclusivity",
               f"getUpdates succeeded — no other process was polling at this instant "
               f"({len(result or [])} update(s) waiting). NOTE: this call just took the polling "
               f"session; restart the service so the gateway reclaims it.")
        return
    if "conflict" in str(result).lower() or "terminated by other" in str(result).lower():
        record(_FAIL, "token exclusivity",
               "409 Conflict — ANOTHER process is polling this bot token right now. On Railway "
               "this is almost always the previous deployment still running, or replicas > 1. "
               "Set the service to 1 replica, remove/stop any other deployment or environment "
               "sharing this token, then redeploy.")
    else:
        record(_WARN, "token exclusivity", f"inconclusive: {result}")


def check_disk() -> None:
    """A full volume makes SQLite writes fail, which takes the gateway down mid-turn."""
    try:
        usage = shutil.disk_usage(HERMES_HOME)
    except Exception as exc:
        record(_WARN, "volume", f"cannot stat {HERMES_HOME}: {exc}")
        return
    pct = usage.used / usage.total * 100 if usage.total else 0
    free_gb, total_gb = usage.free / 1e9, usage.total / 1e9
    detail = f"{HERMES_HOME}: {pct:.0f}% used, {free_gb:.2f} GB free of {total_gb:.2f} GB"
    if pct >= 95 or free_gb < 0.15:
        record(_FAIL, "volume", detail + " — writes are failing or about to; grow the Railway volume")
    elif pct >= 85:
        record(_WARN, "volume", detail + " — tight; the Whisper model alone is 1.62 GB")
    else:
        record(_PASS, "volume", detail)


def check_injected_api_key() -> None:
    """model.api_key must be present in the volume's config.yaml, not just in the env.

    The auxiliary lanes read ``model.api_key`` from config.yaml with NO environment fallback.
    ``scripts/inject-config-secrets.py`` writes it at boot from OLLAMA_API_KEY; if that hook
    did not run, the main model still answers but all 13 aux lanes 401.
    """
    config_path = os.path.join(HERMES_HOME, "config.yaml")
    if not os.path.isfile(config_path):
        record(_FAIL, "config.yaml", f"missing at {config_path} — the volume was never seeded")
        return
    try:
        with open(config_path, encoding="utf-8") as handle:
            import yaml  # deferred: only needed when the file exists
            cfg = yaml.safe_load(handle) or {}
    except Exception as exc:
        record(_WARN, "config.yaml", f"unreadable ({type(exc).__name__}: {exc})")
        return
    model = cfg.get("model") or {}
    key = (model.get("api_key") or "").strip()
    record(_PASS if key else _FAIL, "config.yaml model.api_key",
           redact(key) if key else
           "EMPTY — inject-config-secrets.py did not run, so every auxiliary lane "
           "(vision, extraction, compression) will 401. Check the boot log for "
           "'[inject-config-secrets]'.")
    record(_INFO, "config.yaml model",
           f"{model.get('default')} via {model.get('provider')} ({model.get('base_url')})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe-conflict", action="store_true",
                        help="ask Telegram whether another process holds the token. This STEALS "
                             "the polling session from a healthy gateway — only run it when you "
                             "already believe polling is dead, and restart the service afterwards.")
    args = parser.parse_args()

    print(f"lola-doctor — HERMES_HOME={HERMES_HOME}\n")
    token = check_env()
    check_allowlist()
    check_disk()
    check_injected_api_key()
    if token:
        try:
            check_bot_identity(token)
            check_delivery_path(token)
            if args.probe_conflict:
                check_conflict(token)
        except TransportError as exc:
            record(_FAIL, "telegram reachability",
                   f"cannot reach {TELEGRAM_API} ({exc}). Nothing below this point could be "
                   f"checked, and the token is NOT implicated. If this is the Railway container, "
                   f"the gateway cannot reach Telegram either — that alone makes Lola silent.")
    else:
        record(_INFO, "telegram checks", "skipped — no token to test with")

    failures = [r for r in _results if r[0] == _FAIL]
    warnings = [r for r in _results if r[0] == _WARN]
    print("\n" + "─" * 72)
    if failures:
        print(f"{len(failures)} FAIL, {len(warnings)} warn. Fix these, most likely cause first:")
        for _, check, detail in failures:
            print(f"  • {check}: {detail}")
    else:
        print(f"No failures ({len(warnings)} warn). If Lola is still silent, the cause is not "
              f"visible from inside the container — read the deploy log for the gateway's own "
              f"errors, and re-run with --probe-conflict to rule out a duplicate poller.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
