#!/usr/bin/env python3
"""Heartbeat check — verifies the Hermes gateway process is alive.

Designed to run as a cron job INSIDE the Railway container.
If the gateway process is not found, sends a Telegram alert.

Usage:
  python3 scripts/heartbeat.py

Exits 0 if healthy, 1 if not.
"""
import os
import sys
import subprocess
import urllib.request
import json

def check_process():
    """Check if the gateway process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "gateway.*run"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

def send_telegram_alert(message):
    """Send an alert via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    if not token or not chat_id:
        print("Cannot send alert: missing TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USERS")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

if __name__ == "__main__":
    if check_process():
        print("OK: gateway process is running")
        sys.exit(0)
    else:
        print("FAIL: gateway process not found")
        send_telegram_alert(
            "⚠️ *Hermes-PA heartbeat check FAILED*\n"
            f"Gateway process not found at {__import__('datetime').datetime.utcnow().isoformat()}Z\n"
            "The bot may have crashed. Check Railway logs."
        )
        sys.exit(1)