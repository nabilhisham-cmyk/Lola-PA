# Composio MCP — Session Notes

Notes from integration sessions (2026-07-02).

## Setup Sequence That Worked

1. User created Composio account, got API key (ck_...)
2. Initially tried Railway env var `COMPOSIO_API_KEY` — required redeploy, didn't take effect immediately
3. Changed to `.env` file approach: wrote `MCP_COMPOSIO_API_KEY=ck_...` to `/opt/data/.env`
4. Added mcp_servers block to `/opt/data/config.yaml` (appended to end of file)
5. First attempt used `x-api-key` header → 401 Unauthorized
6. Fixed to `x-consumer-api-key` → connected successfully
7. `hermes mcp test composio` confirmed: 7 tools discovered

## Env Var Naming

- Config references `${MCP_COMPOSIO_API_KEY}`
- `.env` stores `MCP_COMPOSIO_API_KEY=ck_...`
- Railway env var was initially `COMPOSIO_API_KEY` (wrong name) then `MCP_COMPOSIO_API_KEY` (correct)
- Key was copied from Railway container env to `.env` to avoid requiring Railway access for future setups

## Verified Connections (as of 2026-07-02)

| Toolkit | Status | Accounts |
|---------|--------|----------|
| Gmail | Active | Sambawy (sambawy@gmail.com, 66k emails), Bistro Cloud (bistrocloud3@gmail.com, 627 emails) |
| Google Sheets | Active | sambawy@gmail.com |
| Google Calendar | Active | 5 calendars: primary, Family, Bistro Kitchen, Egypt Holidays, US Holidays |
| LinkedIn | Active | Hany Sadek |
| GitHub | Active | sambawy01 (28 public, 7 private repos, GitHub Pro) |
| Resend | Active | 2 accounts: resend_longer-adjure (8 API keys), resend_lapped-thorp (send-only restricted key) |
| Browser Tool | Active (no auth needed) | — |
| Composio Search | Active (no auth needed) | — |

## Initiated but Not Completed

X/Twitter, Slack, Notion, Google Drive, WhatsApp, Stripe, Telegram, Outlook, Discord, HubSpot, Calendly, Trello, Linear, Jira, Mailchimp — all show "initiated" on MANAGE_CONNECTIONS but may actually be active (always verify via SEARCH_TOOLS).

## Email Sending Tests

### Gmail via Composio
Successfully sent an email from sambawy@gmail.com to nathaliestefanos@gmail.com via GMAIL_SEND_EMAIL:
- Subject: "🦎 Leave the geckos alone!"
- Returned: id, threadId, display_url
- Email appeared in sent folder immediately
- Used `account: "Sambawy"` to specify which Gmail account to send from

### Resend direct API
Successfully sent a test email from hello@cacti.restaurant to sambawy@gmail.com via Resend API:
- Used curl with RESEND_API_KEY from container env
- Returned: `{"id":"5c85848c-..."}`
- No Cloudflare blocking encountered (contradicts supabase-backend skill note)

## Resend Domain Verification (bistro-cloud.com)

- bistro-cloud.com exists on Resend but status is `not_started` (not verified)
- Domain ID: `38b12b69-aa33-4680-928f-3d357be69ca8`
- Region: eu-west-1
- DNS provider: Google Domains (now Squarespace) — nameservers are `ns-cloud-e*.googledomains.com`
- DNS records needed (retrieved via RESEND_RETRIEVE_DOMAIN):
  1. DKIM TXT: `resend._domainkey` → `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQ...`
  2. SPF MX: `send` → `feedback-smtp.eu-west-1.amazonses.com` (priority 10)
  3. SPF TXT: `send` → `v=spf1 include:amazonses.com ~all`
- Second Resend account (resend_lapped-thorp) has a restricted API key that can only send emails, cannot list domains (returns 401 "restricted_api_key")

## Document Generation

Generated Composio_MCP_Integration_Guide.docx (v3.0, 42KB, 172 paragraphs, 3 tables, 20 headings) via:
- Script: /opt/data/composio-mcp-guide.py
- Python: /tmp/docx-env/bin/python (separate venv with python-docx)
- 10 sections covering human steps + agent instructions + troubleshooting + FAQ
- Guide follows the agent-driven flow: user creates account, connects apps, copies key, attaches doc to agent, agent asks for key, user pastes it

## bistro-cloud.com Email Forwarding Setup (2026-07-02, continued)

Goal: `b2b@bistro-cloud.com` should forward silently to `sambawy@gmail.com` without exposing the Gmail address to senders.

### What we found via Composio/Resend
- `RESEND_RETRIEVE_DOMAIN` for bistro-cloud.com (id `38b12b69-aa33-4680-928f-3d357be69ca8`): status `verified`, `capabilities: {sending: "enabled", receiving: "disabled"}`
- Resend's MX record is on the `send` subdomain (`send.bistro-cloud.com` → `feedback-smtp.eu-west-1.amazonses.com`), NOT on the root `@`
- No root MX records exist on bistro-cloud.com → emails sent TO `b2b@bistro-cloud.com` have nowhere to go
- This is why the reply_to trick didn't work — the reply went to an address with no MX

### ImprovMX API attempts
- User provided ImprovMX API key `sk_5a...` (free tier)
- Auth: `Basic base64(api:{api_key})` — only `GET /v3/domains/` succeeded (returned empty domain list)
- All write attempts failed: `POST /domains/add` → 405, `PUT /domains/add` → 404, `POST /domains/` → 401, `PUT /domains/{domain}/` → 401, `POST /domains/{domain}/aliases` → 401
- Conclusion: free-tier ImprovMX API is read-only. User must use dashboard to add domain + alias.

### DNS lookup without dig
- `dig` and `nslookup` not installed on the container
- Used Cloudflare DoH: `https://cloudflare-dns.com/dns-query?name=bistro-cloud.com&type=MX` with `accept: application/dns-json` header
- NS records revealed Google Domains nameservers (`ns-cloud-e*.googledomains.com`) → now Squarespace
- MX query returned only SOA in Authority section → confirmed no root MX records exist

### Resolution — COMPLETED ✅
1. User added bistro-cloud.com in ImprovMX dashboard with 3 aliases:
   - `b2b` → sambawy@gmail.com
   - `catering` → sambawy@gmail.com
   - `@` (catch-all) → sambawy@gmail.com
2. User added two MX records in Google Domains/Squarespace DNS at root `@`:
   - `mx1.improvmx.com` priority 10
   - `mx2.improvmx.com` priority 20
3. Verified via Cloudflare DoH and Google DNS — both MX records live and propagated
4. ImprovMX dashboard still showed "needs setup" initially (DNS cache lag) — user needs to click CHECK AGAIN after a few minutes
5. See `references/improvmx-email-forwarding.md` for the reusable setup procedure

### Security note
User shared ImprovMX API key in plain text in Telegram. Warned them (again). This is a recurring pattern — see memory rule about sharing secrets.

## Key Errors Encountered

1. `x-api-key` header → 401 (fixed by using `x-consumer-api-key`)
2. `COMPOSIO_MANAGE_CONNECTIONS` showing "initiated" for active connections (worked around by using `COMPOSIO_SEARCH_TOOLS`)
3. `GMAIL_SEARCH_PEOPLE` → 403 PERMISSION_DENIED (insufficient scopes; worked around by searching emails with GMAIL_FETCH_EMAILS)
4. Twitter toolkit slug `x_twitter` → "Toolkit not found" (correct slug is `twitter`)
5. Twitter `COMPOSIO_MANAGE_CONNECTIONS` add → "Composio does not manage auth" (must use dashboard)
6. docx `makeelement` with `qn('w:val')` → ValueError (fixed by using `.set()` method on the element instead of passing attributes dict to makeelement)
7. `mcp_servers` block wiped by `sed` line-number operations (re-appended with `cat >>`)
8. Vision API (`vision_analyze`) returning 401 Unauthorized — could not view user screenshots throughout the session
9. ImprovMX free-tier API key returns 401 on all write operations — read-only (GET /domains/ only). Must use dashboard for domain/alias creation.
10. Resend domain "verified" does not mean it can receive email — check `capabilities.receiving`. Send-only domains have MX on `send` subdomain, not root.