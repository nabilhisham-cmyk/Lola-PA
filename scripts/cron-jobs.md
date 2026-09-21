# Cron Jobs — create these on Railway after deploy
#
# Run these commands from a Telegram session with the bot, or via
# `hermes cron create` in the Railway container shell.

# 1. Morning Briefing (daily 7am [your city] time)
#    Schedule: 0 7 * * *
#    Prompt: "Good morning. Give me a concise daily briefing:
#             (1) Check today's calendar events using get-current-time then list-events.
#             (2) Flag anything that needs a decision or prep.
#             (3) Note any open GitHub PRs or failing CI on my repos.
#             (4) One line on weather in [your city].
#             Keep it scannable — no filler. UK English."
#
#    To create via Telegram:
#    /cron create 0 7 * * * Good morning. Give me a concise daily briefing: (1) Check today's calendar events using get-current-time then list-events. (2) Flag anything that needs a decision or prep. (3) Note any open GitHub PRs or failing CI on my repos. (4) One line on weather in [your city]. Keep it scannable. UK English.

# 2. Heartbeat (every 15 minutes)
#    Script-only job (no LLM needed). Runs scripts/heartbeat.py inside the
#    container. If the gateway process is dead, sends a Telegram alert.
#    Created via Hermes cron with no_agent=True:
#
#    hermes cron create "*/15 * * * *" --no-agent --script scripts/heartbeat.py
#
#    Or via the cronjob tool:
#    schedule: "*/15 * * * *"
#    script: scripts/heartbeat.py
#    no_agent: true