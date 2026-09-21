#!/usr/bin/env python3
"""Error monitor — scans Hermes gateway logs for errors and alerts via Telegram.

Designed to run as a cron job INSIDE the Railway container.
Checks the gateway log file for ERROR/CRITICAL/Traceback entries since
the last check. Sends a Telegram alert with the error summary.

Usage:
  python3 scripts/error-monitor.py

State: tracks last scan timestamp in /opt/data/.cache/error-monitor.state
"""
import os
import re
import sys
import json
import time
import subprocess
import urllib.request
from datetime import datetime, timezone

LOG_FILE = os.path.expanduser("~/.hermes/logs/gateway.log")
STATE_FILE = os.path.expanduser("~/.hermes/.cache/error-monitor.state")
ERROR_PATTERNS = [
    r"ERROR",
    r"CRITICAL",
    r"Traceback",
    r"Exception",
    r"FAILED",
    r"FATAL",
]
# Ignore these (they're warnings, not real errors)
IGNORE_PATTERNS = [
    r"npm notice",
    r"PTBUserWarning",
    r"tool_executor.*returned error",  # tool errors are handled by the agent
    r"old_string and new_string are identical",  # patch no-op
    r"not_found.*No process with ID",  # stale process ref
    r"BLOCKED.*user.*NOT consented",  # approval timeout
]

def load_state():
    """Load last scan timestamp."""
    try:
        with open(STATE_FILE) as f:
            return json.loads(f.read()).get("last_scan", 0)
    except Exception:
        return 0

def save_state(ts):
    """Save last scan timestamp."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"last_scan": ts}, f)

def scan_logs(since_ts):
    """Scan log file for errors since the given timestamp."""
    if not os.path.isfile(LOG_FILE):
        return []

    errors = []
    with open(LOG_FILE, errors="replace") as f:
        for line in f:
            # Check if line matches any error pattern
            is_error = any(re.search(p, line, re.IGNORECASE) for p in ERROR_PATTERNS)
            if not is_error:
                continue

            # Check if line should be ignored
            is_ignored = any(re.search(p, line, re.IGNORECASE) for p in IGNORE_PATTERNS)
            if is_ignored:
                continue

            errors.append(line.strip())

    return errors[-20:]  # Last 20 errors max

def send_telegram_alert(errors):
    """Send error alert via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    if not token or not chat_id:
        print("Cannot send alert: missing TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USERS")
        return

    # Deduplicate errors
    unique_errors = list(dict.fromkeys(errors))
    count = len(unique_errors)

    # Truncate to fit Telegram message limit
    error_text = "\n".join(unique_errors[:5])
    if len(error_text) > 3000:
        error_text = error_text[:3000] + "\n... (truncated)"

    message = (
        f"⚠️ *Hermes-PA Error Monitor*\n"
        f"Found {count} error(s) in gateway logs.\n\n"
        f"```\n{error_text}\n```"
    )

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        print(f"Alert sent: {count} errors reported")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

if __name__ == "__main__":
    now = time.time()
    last_scan = load_state()

    print(f"Scanning logs since {datetime.fromtimestamp(last_scan, tz=timezone.utc).isoformat() if last_scan > 0 else 'beginning'}...")

    errors = scan_logs(last_scan)

    if errors:
        print(f"Found {len(errors)} error(s)")
        send_telegram_alert(errors)
    else:
        print("No errors found")

    save_state(now)
    sys.exit(0)