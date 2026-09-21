#!/usr/bin/env python3
"""Create cron jobs on the Hermes instance.

Run this inside the Railway container (or locally) to ensure the
morning briefing and heartbeat cron jobs exist.

Usage:
  python3 scripts/setup-cron-jobs.py

This is idempotent — it checks for existing jobs by name and only
creates missing ones.
"""
import json
import os
import subprocess
import sys

JOBS = [
    {
        "name": "morning-briefing",
        "schedule": "0 7 * * *",
        "prompt": (
            "Good morning. Give me a concise daily briefing: "
            "(1) Check today's calendar events using get-current-time then list-events. "
            "(2) Flag anything that needs a decision or prep. "
            "(3) Note any open GitHub PRs or failing CI on my repos. "
            "(4) One line on weather in Cairo. "
            "Keep it scannable — no filler. UK English."
        ),
        "deliver": "origin",
    },
    {
        "name": "heartbeat",
        "schedule": "*/15 * * * *",
        "script": "heartbeat.py",
        "no_agent": True,
    },
    {
        "name": "error-monitor",
        "schedule": "*/30 * * * *",
        "script": "error-monitor.py",
        "no_agent": True,
    },
    {
        "name": "daily-backup",
        "schedule": "0 3 * * *",  # 03:00 Africa/Cairo
        "script": "backup.py",
        "no_agent": True,
    },
]

def run_cron_list():
    """Return existing cron jobs (list of {name, id, ...}).

    Reads the authoritative store at $HERMES_HOME/cron/jobs.json. NOTE: there is
    no 'hermes cron list --json' flag — relying on it silently returned [], so
    every run recreated all jobs and duplicates piled up. Reading the file is
    what actually makes this script idempotent.
    """
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    path = os.path.join(home, "cron", "jobs.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        return jobs if isinstance(jobs, list) else []
    except Exception:
        return []

def cron_job_exists(jobs, name):
    """Check if a job with the given name exists."""
    for job in jobs:
        if job.get("name") == name:
            return True
    return False

def create_cron_job(job):
    """Create a single cron job via hermes CLI."""
    cmd = ["hermes", "cron", "create", job["schedule"]]

    if job.get("no_agent"):
        cmd.append("--no-agent")

    if job.get("script"):
        cmd.extend(["--script", job["script"]])

    if job.get("prompt"):
        cmd.append(job["prompt"])  # prompt is a positional arg, not --prompt

    cmd.extend(["--name", job["name"]])

    if job.get("deliver"):
        cmd.extend(["--deliver", job["deliver"]])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"  Created: {job['name']}")
            return True
        else:
            print(f"  Failed to create {job['name']}: {result.stderr}")
            return False
    except Exception as e:
        print(f"  Error creating {job['name']}: {e}")
        return False

def main():
    print("Checking existing cron jobs...")
    existing_names = {j.get("name", "") for j in run_cron_list()}
    if existing_names:
        print(f"  Found {len(existing_names)} existing jobs: {existing_names}")

    created = 0
    skipped = 0
    for job in JOBS:
        if job["name"] in existing_names:
            print(f"  Skipped (exists): {job['name']}")
            skipped += 1
            continue
        if create_cron_job(job):
            created += 1

    print(f"\nDone: {created} created, {skipped} skipped")

if __name__ == "__main__":
    main()