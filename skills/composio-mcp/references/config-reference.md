# Composio MCP Config Reference

## The config.yaml block (add to end of file)

```yaml
mcp_servers:
  composio:
    url: https://connect.composio.dev/mcp
    headers:
      x-consumer-api-key: ${MCP_COMPOSIO_API_KEY}
    enabled: true
```

## The .env entry

```
MCP_COMPOSIO_API_KEY=ck_your_key_here
```

## Header names — what works and what doesn't

| Header | Works? | Notes |
|--------|--------|-------|
| `x-consumer-api-key` | ✅ | Required for consumer dashboard keys (ck_ prefix) |
| `x-api-key` | ❌ 401 | Developer platform API only |
| `Authorization: Bearer` | ❌ 401 | Not supported by Composio MCP endpoint |

## Env var names

| Name | Works? | Notes |
|------|---------|-------|
| `MCP_COMPOSIO_API_KEY` | ✅ | Must match the ${...} reference in config.yaml |
| `COMPOSIO_API_KEY` | ❌ | Won't be resolved unless config uses ${COMPOSIO_API_KEY} |

## Verification commands

```bash
# Test MCP connection
hermes mcp test composio

# Check if env var is in running process
cat /proc/$(pgrep -f "hermes gateway" | head -1)/environ | tr '\0' '\n' | grep MCP_COMPOSIO

# Check if mcp Python package is installed
/opt/hermes/.venv/bin/python3 -c "import mcp; print('ok')"

# Restart gateway (s6)
/package/admin/s6-2.13.2.0/command/s6-svc -t /run/service/gateway-default
```

## Config file locations

| Environment | config.yaml path | .env path |
|------------|-----------------|-----------|
| Railway (Hermes) | /opt/data/config.yaml | /opt/data/.env |
| Local (default) | ~/.hermes/config.yaml | ~/.hermes/.env |
| Custom profile | ~/.hermes/profiles/<name>/config.yaml | same .env |

## Common Composio toolkit slugs

| App | Toolkit slug | Notes |
|-----|-------------|-------|
| Gmail | gmail | Supports multiple accounts |
| Google Calendar | google_calendar | |
| Google Sheets | googlesheets | |
| Google Drive | google_drive | |
| X / Twitter | twitter | NOT `x_twitter` — using `x_twitter` returns "Toolkit not found" |
| LinkedIn | linkedin | |
| Slack | slack | |
| Notion | notion | |
| GitHub | github | |
| WhatsApp | whatsapp | |
| Stripe | stripe | |
| Telegram | telegram | |
| Outlook | outlook | |
| Discord | discord | |
| HubSpot | hubspot | |
| Calendly | calendly | |
| Trello | trello | |
| Linear | linear | |
| Jira | jira | |
| Mailchimp | mailchimp | |
| Resend | resend | Supports multiple accounts; restricted keys may only send (not list domains) |

## Resend domain verification via Composio

To verify a new sending domain through Composio's Resend tools:

1. `RESEND_LIST_DOMAINS` → get all domains and their status
2. `RESEND_RETRIEVE_DOMAIN(domain_id)` → get DNS records (type, name, value, status)
3. Add the DNS records to the domain's DNS provider
4. `RESEND_VERIFY_DOMAIN(domain_id)` → trigger verification
5. `RESEND_RETRIEVE_DOMAIN(domain_id)` → confirm status changed to "verified"

DNS records typically include:
- **DKIM**: TXT record at `resend._domainkey` with `p=...` value
- **SPF MX**: MX record at `send` pointing to `feedback-smtp.<region>.amazonses.com`
- **SPF TXT**: TXT record at `send` with `v=spf1 include:amazonses.com ~all`

## DNS provider lookup (when dig/nslookup unavailable)

**Google DNS:**
```bash
curl -s 'https://dns.google/resolve?name=domain.com&type=NS'
```

**Cloudflare DNS-over-HTTPS (returns SOA in Authority when no records exist):**
```bash
curl -s 'https://cloudflare-dns.com/dns-query?name=domain.com&type=MX' -H 'accept: application/dns-json'
```

Both return JSON. Use `type=NS` for nameservers, `type=MX` for mail records.
The Cloudflare endpoint's Authority section is useful for confirming a domain has NO MX records (SOA appears instead of Answer).

Common nameserver patterns:
- `ns-cloud-*.googledomains.com` → Google Domains (now Squarespace)
- `*.cloudflare.com` → Cloudflare
- `*.godaddy.com` → GoDaddy
- `*.nameservers.com` → various registrars