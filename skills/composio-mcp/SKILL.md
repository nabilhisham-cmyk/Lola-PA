---
name: composio-mcp
description: "Connect Hermes Agent to 1000+ apps (Gmail, Google Calendar, Sheets, X/Twitter, LinkedIn, Slack, Notion, GitHub, WhatsApp, Stripe, and more) via Composio's MCP server. Covers initial setup, app connection, tool discovery, and the agent-driven integration workflow where users paste an API key in Telegram."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [composio, mcp, integration, email, calendar, sheets, social-media, api]
    related_skills: [hermes-agent, google-workspace]
---

# Composio MCP Integration

Composio connects your AI agent to 1000+ apps through a single MCP server. Instead of writing per-app integrations, you connect once to Composio's MCP server and gain access to Gmail, Google Calendar, Google Sheets, X/Twitter, LinkedIn, Slack, Notion, GitHub, WhatsApp, Stripe, and hundreds more — all through 7 meta-tools that discover and execute app actions on demand.

## When to Use

- User wants to connect their agent to email, calendar, sheets, or social media
- User mentions Composio, composio.dev, or "connect my apps"
- User wants to integrate Gmail/Calendar/Sheets without per-app OAuth setup
- User is onboarding a new client and needs a simple integration flow
- User asks to "check my connected accounts" or "what apps can I use"

## Architecture

```
User → Hermes Agent (Telegram) → Composio MCP Server (connect.composio.dev/mcp)
                                        ↓
                              1000+ app toolkits
                              (Gmail, Calendar, Sheets, X, LinkedIn, ...)
```

The MCP server provides 7 meta-tools (not per-app tools). The agent uses these meta-tools to search for app-specific tools, get their schemas, check connections, and execute actions — all dynamically.

## Setup — Two Approaches

### Approach 1: Agent-Driven (Recommended for clients/users)

The user creates a Composio account, connects apps on the dashboard, copies their API key, and pastes it to their agent in Telegram. The agent handles all technical setup.

**User steps:**
1. Create account at composio.dev
2. Connect desired apps on the Composio dashboard (Gmail, Calendar, etc.)
3. Copy API key from the dashboard home page (starts with `ck_`)
4. Attach the integration guide doc to their agent in Telegram
5. Paste the API key when the agent asks for it

**Agent steps (when user pastes the key):**
1. Write key to `.env` file: `MCP_COMPOSIO_API_KEY=ck_...`
2. Add MCP server block to config.yaml (see below)
3. Restart the gateway
4. Run `hermes mcp test composio` to verify
5. Confirm to user and list available capabilities

### Approach 2: Admin-Driven (For infrastructure owners)

Set the env var on Railway (or hosting platform) and add the config block manually.

## The config.yaml Block

```yaml
mcp_servers:
  composio:
    url: https://connect.composio.dev/mcp
    headers:
      x-consumer-api-key: ${MCP_COMPOSIO_API_KEY}
    enabled: true
```

**This is added to the end of `config.yaml`** (typically `/opt/data/config.yaml` on Railway, `~/.hermes/config.yaml` locally).

## Critical Gotchas

### 1. Header name: `x-consumer-api-key` (NOT `x-api-key`)

This is the #1 integration error. Composio's consumer dashboard API keys (the `ck_` keys) require the header `x-consumer-api-key`. Using `x-api-key` or `Authorization: Bearer` results in 401 Unauthorized.

- `x-consumer-api-key` → ✅ works (for consumer/For You dashboard keys starting with `ck_`)
- `x-api-key` → ❌ 401 (this is for the developer platform API, not MCP)
- `Authorization: Bearer` → ❌ 401

### 2. Env var name must match config reference

The config uses `${MCP_COMPOSIO_API_KEY}` — Hermes resolves this from the environment. The env var must be named exactly `MCP_COMPOSIO_API_KEY` (not `COMPOSIO_API_KEY`).

If the key is in the `.env` file, Hermes reads it at startup. If it's on Railway, the container must redeploy for the env var to take effect.

### 3. `hermes mcp add` interactive flow can't handle Composio

The interactive `hermes mcp add` flow only supports `Authorization: Bearer` headers. Composio requires `x-consumer-api-key`, so you must write the config block directly into `config.yaml` — the CLI flow will save a config with the wrong header.

### 4. `.env` file is preferred over Railway env vars for client setups

Clients typically can't access Railway. Put the key in `/opt/data/.env` on the persistent volume. Hermes reads this file at startup and resolves the `${MCP_COMPOSIO_API_KEY}` reference automatically. No Railway access, no redeploy needed — just restart the gateway.

### 5. The `mcp` Python package must be installed

Check: `/opt/hermes/.venv/bin/python3 -c "import mcp"` — if it fails, install with `uv pip install mcp` (using the Hermes venv, not system Python).

## The 7 Meta-Tools

Once connected, the agent gains these tools. These are NOT per-app tools — they are gateway tools that discover and execute app-specific tools dynamically.

| Tool | What It Does |
|------|-------------|
| `COMPOSIO_SEARCH_TOOLS` | Search across 500+ app toolkits. Pass a use_case description, get back tool slugs + schemas + connection status. |
| `COMPOSIO_GET_TOOL_SCHEMAS` | Get full input schema for specific tool slugs. Always call before executing a tool. |
| `COMPOSIO_MANAGE_CONNECTIONS` | List, create, rename, or remove app connections. Generates OAuth links for connecting new apps. |
| `COMPOSIO_WAIT_FOR_CONNECTIONS` | Poll until user completes OAuth authentication. Call after generating an auth link. |
| `COMPOSIO_MULTI_EXECUTE_TOOL` | Execute one or more Composio tools in parallel. The main workhorse. |
| `COMPOSIO_REMOTE_BASH_TOOL` | Run bash in Composio's remote sandbox. For processing large tool responses. |
| `COMPOSIO_REMOTE_WORKBENCH` | Process remote files or script bulk tool executions in a Python sandbox. |

## Tool Execution Workflow

When the user asks for an action (e.g. "send an email"):

1. **Search**: `COMPOSIO_SEARCH_TOOLS` with a use_case description → get tool slug + connection status
2. **Schema**: `COMPOSIO_GET_TOOL_SCHEMAS` with the tool slug → get required parameters
3. **Connection check**: `COMPOSIO_MANAGE_CONNECTIONS` to verify the app is connected
4. **OAuth if needed**: If not connected, generate OAuth link → user clicks → `COMPOSIO_WAIT_FOR_CONNECTIONS`
5. **Execute**: `COMPOSIO_MULTI_EXECUTE_TOOL` with the tool slug + arguments
6. **Report**: Return the result to the user

**Key rules:**
- Always search first — never guess tool slugs
- Always check schema — never invent parameter names
- Only batch independent tools (never chain dependent calls in one batch)
- Confirm with user before external actions (sending emails, posting to social)
- Never echo the API key back to the user

## Checking Connected Accounts

To see what apps a user has connected:

```
COMPOSIO_MANAGE_CONNECTIONS(toolkits=[{"name": "gmail", "action": "list"}, {"name": "google_calendar", "action": "list"}, ...])
```

Or use `COMPOSIO_SEARCH_TOOLS` with a use_case — it returns `toolkit_connection_statuses` showing which apps are active, initiated, or not connected.

Statuses:
- **active** — app is connected and ready to use
- **initiated** — OAuth was started but not completed (user needs to finish sign-in on Composio dashboard)
- **not connected** — no connection attempt made

## Config file locations

| Environment | config.yaml path | .env path |
|------------|-----------------|-----------|
| Railway (Hermes) | /opt/data/config.yaml | /opt/data/.env |
| Local (default) | ~/.hermes/config.yaml | ~/.hermes/.env |
| Custom profile | ~/.hermes/profiles/<name>/config.yaml | same .env |

See `references/config-reference.md` for the full config block, header names, env var names, verification commands, and common toolkit slugs.
See `references/improvmx-email-forwarding.md` for the ImprovMX email forwarding setup procedure (custom domain → Gmail, free-tier dashboard workflow, MX record configuration, Resend coexistence).
See `references/direct-mcp-python-access.md` for calling the Composio MCP server directly from Python scripts (cron jobs, background monitors) without a live Hermes session — includes the MCP handshake, SSE parsing, and `tool_slug` parameter naming.

## Client Onboarding Guide

A pre-written `.docx` integration guide is available at `/opt/data/Composio_MCP_Integration_Guide.docx` (generated via `/opt/data/composio-mcp-guide.py`). This guide is branded for Farasa.AI and written for the agent-driven flow:

- Section 1-6: Human-facing steps (create account, connect apps, copy key, attach guide, paste key)
- Section 7: Agent instructions (exact setup steps, config block, security rules, tool workflow)
- Section 8-11: What you can do, troubleshooting, FAQ

The guide can be regenerated with: `/tmp/docx-env/bin/python /opt/data/composio-mcp-guide.py`

## Security Rules

- Never echo the API key back to the user
- Never log the key in plain text
- Never commit `.env` or `config.yaml` with the key to git
- If user pastes a new key, replace the old one — don't add duplicates
- After writing key to `.env`, don't repeat it in conversation
- The key can be rotated instantly from the Composio dashboard

## Pitfalls

1. **401 Unauthorized** — almost always the header name. Must be `x-consumer-api-key`, not `x-api-key`.

2. **MCP server not discovered after config change** — restart the gateway. Config changes don't hot-reload; they require a fresh session/gateway restart.

3. **`hermes mcp add` saves wrong header** — the interactive flow uses `Authorization: Bearer`. You must edit config.yaml directly to use `x-consumer-api-key`.

4. **Env var not in running process** — if set on Railway, requires redeploy. If set in `.env`, requires gateway restart. Check with `cat /proc/$(pgrep -f "hermes gateway" | head -1)/environ | tr '\0' '\n' | grep MCP_COMPOSIO`.

5. **Apps show "initiated" not "active"** — user started OAuth but didn't finish. They need to complete the sign-in flow on the Composio dashboard. No agent action needed — the user must click through the OAuth flow in their browser.

6. **Multiple Gmail accounts** — Composio supports multiple accounts per toolkit. Specify which account to use via the `account` parameter (alias or ID) when executing tools.

7. **`COMPOSIO_MANAGE_CONNECTIONS` list shows stale status** — calling `COMPOSIO_MANAGE_CONNECTIONS` with `action: "list"` frequently shows toolkits as "initiated" even when they are actually active and working. **Do not trust this for verification.** The reliable way to check connection status is `COMPOSIO_SEARCH_TOOLS` — its `toolkit_connection_statuses` array reflects the real connection state at query time, including account details and user info.

8. **Gmail contacts (People API) returns 403** — `GMAIL_SEARCH_PEOPLE` and `GMAIL_GET_CONTACTS` require Google People API scopes that Composio's default Gmail OAuth does not grant. You'll get `403 PERMISSION_DENIED` with `ACCESS_TOKEN_SCOPE_INSUFFICIENT`. **Workaround:** search emails with `GMAIL_FETCH_EMAILS` using `query: "person's name"` and extract the email from the sender/to fields.

9. **X/Twitter toolkit slug is `twitter`, not `x_twitter`** — when searching for X/Twitter tools or managing connections, use the slug `twitter`. Using `x_twitter` returns "Toolkit not found".

10. **Twitter/X cannot be agent-connected** — `COMPOSIO_MANAGE_CONNECTIONS` with `action: "add"` for the `twitter` toolkit fails with "Composio does not manage auth for toolkit twitter." The user must connect X/Twitter through the Composio dashboard directly.

11. **Resend API works from Hermes container** — despite earlier notes in other skills, Resend's API (api.resend.com) is NOT blocked from the Hermes Railway container. Emails can be sent directly via `curl` with the `RESEND_API_KEY` env var. Verified domains: cacti.restaurant, justmanalized.com, orders.justmanalized.com, sekhmetwellness.com.

12. **Resend is also available via Composio** — the `resend` toolkit is connected on Composio with multiple accounts. Use `RESEND_LIST_DOMAINS` to list verified domains, `RESEND_RETRIEVE_DOMAIN` to get DNS records for unverified domains, `RESEND_SEND_EMAIL` to send. When using Composio's Resend tools, specify the account ID (e.g. `resend_longer-adjure`) since multiple accounts may be connected.

13. **Resend domain verification via Composio** — to add a new sending domain: `RESEND_CREATE_DOMAIN` creates it (returns DNS records), add the DNS records to the domain's DNS provider, then `RESEND_VERIFY_DOMAIN` to verify. `RESEND_RETRIEVE_DOMAIN` returns the full DNS record set (type, name, value, status) for a domain ID.

14. **DNS provider lookup without dig/nslookup** — when `dig` and `nslookup` are not installed, use Google's public DNS API: `curl -s 'https://dns.google/resolve?name=domain.com&type=NS'` returns nameserver records as JSON. This reveals the DNS provider (e.g. googledomains.com → Squarespace, cloudflare.com → Cloudflare, godaddy.com → GoDaddy).

15. **Gmail multi-account sending** — when sending via `GMAIL_SEND_EMAIL` with multiple Gmail accounts connected, specify the account alias (e.g. `account: "Sambawy"`) in `COMPOSIO_MULTI_EXECUTE_TOOL`. Without it, the default account (first one connected) is used.

16. **Sending emails from custom domains** — Composio's Gmail tools send from the authenticated Gmail address only. To send from custom domains (e.g. hello@cacti.restaurant, hello@bistro-cloud.com), use Resend instead — either via the Resend API directly (`curl` with `RESEND_API_KEY`) or via Composio's `RESEND_SEND_EMAIL` tool. The domain must be verified on Resend first.

17. **Resend send-only vs receive-capable domains** — `RESEND_RETRIEVE_DOMAIN` returns a `capabilities` object: `{sending: "enabled", receiving: "disabled"}`. Most Resend domains are send-only. This means emails sent TO the domain (e.g. b2b@bistro-cloud.com) have nowhere to arrive — there's no root MX record. Resend's MX record is on the `send` subdomain (e.g. `send.bistro-cloud.com`), not the root (`@`). To receive emails at a custom domain, you need a separate forwarding service (ImprovMX, Cloudflare Email Routing, etc.) with MX records at the root — these do NOT conflict with Resend's subdomain MX.

18. **ImprovMX free-tier API is read-only** — the free ImprovMX plan allows GET /domains/ (listing) but all write operations (add domain, create aliases) return 401 "Authentication required." This is a plan limitation, not a key problem. To set up ImprovMX forwarding on the free tier, the user must use the ImprovMX dashboard (improvmx.com), not the API. Auth format: `Basic base64(api:{api_key})` — only GET /domains/ succeeds; POST/PUT to /domains/add or /domains/{domain}/aliases all return 401.

19. **Cloudflare DNS-over-HTTPS as dig alternative** — when `dig` and `nslookup` are unavailable, Cloudflare's DoH endpoint works alongside the Google DNS endpoint already documented: `curl -s 'https://cloudflare-dns.com/dns-query?name=domain.com&type=MX' -H 'accept: application/dns-json'` returns JSON with Answer/Authority sections. Use `type=NS` for nameservers, `type=MX` for mail records, `type=TXT` for SPF/verification records. The Authority section (SOA) appears when no records of that type exist — useful for confirming a domain has no MX records set up.

20. **ImprovMX requires SPF TXT record, not just MX** — ImprovMX forwarding will NOT activate with MX records alone. The dashboard keeps showing "Email forwarding needs setup" until you add `v=spf1 include:spf.improvmx.com ~all` as a TXT record at the root (`@`). The ImprovMX inspector at `inspector.improvmx.com/<domain>` shows which records are missing. If the root already has an SPF record from another service, merge them into one TXT record (RFC 4408: only the first SPF record is evaluated).

21. **Don't test ImprovMX forwarding with transactional senders** — sending a test email via Resend FROM a domain TO `b2b@bistro-cloud.com` will likely NOT arrive via ImprovMX forwarding. SPF/DKIM alignment breaks when ImprovMX rewrites the forwarding envelope, and Gmail may silently drop the email (not even in spam). Test with a normal email client (iCloud, Gmail, Outlook) — have the user send a plain email to the custom-domain address.

22. **ImprovMX account validation required before forwarding works** — ImprovMX sends a "Important: Validate your account" email with a validation link (`https://app.improvmx.com/validate/<token>`) to the forwarded address. This link MUST be clicked before forwarded emails will actually arrive, even if the dashboard says forwarding is "active" and all DNS records are verified. If the user hasn't validated, forwarded emails silently disappear — no bounce, no spam, no error. The validation email expires in 5 days. Check for it with `GMAIL_FETCH_EMAILS` query `"subject:Validate your account from:improvmx"`. This is the #1 reason forwarding appears set up but test emails don't arrive.

23. **Direct MCP Python access (outside Hermes MCP session)** — the Composio MCP server can be called directly from a Python script via HTTP POST to `connect.composio.dev/mcp`. This is useful for cron jobs and background scripts that need Gmail access without a live Hermes session. See `references/direct-mcp-python-access.md` for the full pattern: session initialization, SSE response parsing, and `GMAIL_FETCH_EMAILS` execution.

24. **`tool_slug` NOT `tool_name` in COMPOSIO_MULTI_EXECUTE_TOOL** — when calling `COMPOSIO_MULTI_EXECUTE_TOOL` via the MCP server, the parameter is `tool_slug` (not `tool_name`). Using `tool_name` returns: `"Validation error: Required at \"tools[0].tool_slug\""`. This only matters for direct MCP calls — when using the Hermes MCP tool integration, the parameter mapping is handled automatically.

25. **MCP session initialization flow** — direct MCP calls require a three-step handshake: (1) `initialize` with protocolVersion `2024-11-05` → capture `Mcp-Session-Id` from response headers, (2) `notifications/initialized` (no response expected), (3) `tools/call` for actual execution. The session ID must be passed as `Mcp-Session-Id` header on all subsequent calls.

26. **MCP responses use SSE format** — the MCP server returns Server-Sent Events format (`event: message\ndata: {json}`). Parse by splitting on newlines and extracting lines starting with `data: `. Plain `json.loads(raw)` fails on the SSE wrapper.

27. **GMAIL_FETCH_EMAILS parameters** — key parameters: `query` (Gmail search query syntax, same as Gmail search bar), `max_results` (capped at 500/call), `ids_only` (bool — true returns just message/thread IDs), `include_payload` (bool — true returns full body but can truncate on large responses). Recommended pattern: `ids_only=false, include_payload=true` for monitoring scripts; paginate with `nextPageToken` from the response.