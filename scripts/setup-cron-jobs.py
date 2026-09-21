#!/usr/bin/env python3
"""Create Lola's cron jobs on the Hermes instance.

Run this inside the Railway container (or locally) to ensure the events
briefing, heartbeat, error monitor and backup jobs exist.

Usage:
  python3 scripts/setup-cron-jobs.py

This is idempotent: it checks for existing jobs by name and only creates the
missing ones.
"""
import json
import os
import subprocess

# The events briefing is the whole point of Lola: it is what Hisham sees every
# morning, and it is what forces the event data to stay real. Everything else
# here keeps the box alive.
BRIEFING_PROMPT = (
    "Build Hisham's daily events briefing for El Gouna. Call get-current-time "
    "first, then query the Supabase events tables (load the events-ops skill for "
    "the schema and the briefing order).\n\n"
    "Report in this order, and skip a section with one line if it is empty:\n"
    "1. TODAY: events live today, plus any event on site for setup or teardown today.\n"
    "2. THIS WEEK: what is coming in the next 7 days, as 'Day DD Month - name - venue'.\n"
    "3. AT RISK: from at_risk() - overdue or open critical tasks, permits not granted, "
    "events with no confirmed venue. State the consequence, not just the fact.\n"
    "4. CLASHES: run venue_clashes(0) and report any venue with overlapping windows, "
    "including setup and teardown overlap.\n"
    "5. CHASE LIST: suppliers or contacts expected to have replied and who have not.\n\n"
    "If nothing is on today and nothing is at risk, say so in one line and stop. "
    "Do not invent urgency. Dates always carry the weekday. "
    "No em dashes. English."
)

JOBS = [
    {
        "name": "events-briefing",
        "schedule": "0 7 * * *",  # 07:00 Africa/Cairo
        "prompt": BRIEFING_PROMPT,
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
    """Return existing cron jobs as a list of dicts.

    Reads the authoritative store at $HERMES_HOME/cron/jobs.json. NOTE: there is
    no 'hermes cron list --json' flag; relying on it silently returned [], so
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


def create_cron_job(job):
    """Create a single cron job via the hermes CLI."""
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
