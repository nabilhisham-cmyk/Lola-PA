# ImprovMX Email Forwarding Setup

Setting up custom-domain email forwarding (e.g. `b2b@bistro-cloud.com` → `sambawy@gmail.com`) without exposing the destination Gmail address to senders.

## When to Use

- User wants emails to a custom domain to forward silently to a Gmail (or other) address
- Resend domain is send-only (receiving disabled) — need a separate inbound solution
- User wants professional-looking email addresses without a full mailbox

## Key Constraint: Free-Tier API Is Read-Only

ImprovMX free-tier API keys can only `GET /v3/domains/` (list domains). All write operations (add domain, create aliases) return 401 "Authentication required." This is a **plan limitation**, not a key problem.

- Auth format: `Basic base64(api:{api_key})`
- Only `GET /domains/` succeeds on free tier
- `POST/PUT /domains/add`, `POST /domains/{domain}/aliases` → all 401

**Conclusion:** On the free tier, the user must set up forwarding through the **ImprovMX dashboard** (improvmx.com), not the API.

## Setup Procedure

### Step 1 — ImprovMX Dashboard

1. Sign up at [improvmx.com](https://improvmx.com) (free, no credit card)
2. Click **Add Domain** → enter the domain (e.g. `bistro-cloud.com`)
3. Add aliases:
   - Specific: `b2b` → `sambawy@gmail.com`
   - Catch-all: `*` (or `@`) → `sambawy@gmail.com`
4. Dashboard will show "Email forwarding needs setup" until MX records propagate

### Step 2 — Add MX Records to DNS Provider

Add two MX records at the **root** (`@`) of the domain in the DNS provider's panel:

```
Name: @
Type: MX
Priority: 10
Value: mx1.improvmx.com
```

```
Name: @
Type: MX
Priority: 20
Value: mx2.improvmx.com
```

### Step 2b — Add SPF TXT Record (REQUIRED)

ImprovMX requires an SPF record at the root to confirm the domain authorizes ImprovMX to forward on its behalf. Without it, the dashboard will keep saying "Email forwarding needs setup" even after MX records propagate. This is the #1 reason setup stalls after MX records are confirmed live.

```
Name: @
Type: TXT
Value: v=spf1 include:spf.improvmx.com ~all
```

**SPF conflict check:** If the root already has an SPF TXT record from another service (e.g. Resend, SendGrid, Google Workspace), you CANNOT have two separate SPF records — RFC 4408 says only the first SPF record is evaluated. You must merge them into one:

```
v=spf1 include:spf.improvmx.com include:amazonses.com ~all
```

In the bistro-cloud.com case, Resend's SPF is on the `send` subdomain (`send.bistro-cloud.com`), NOT the root — so the root SPF for ImprovMX does not conflict.

Verify the TXT record is live:
```bash
curl -s 'https://cloudflare-dns.com/dns-query?name=domain.com&type=TXT' \
  -H 'accept: application/dns-json' | python3 -m json.tool
```

### Step 3 — Verify Propagation

Check MX records via Cloudflare DoH (no dig needed):

```bash
curl -s 'https://cloudflare-dns.com/dns-query?name=domain.com&type=MX' \
  -H 'accept: application/dns-json' | python3 -m json.tool
```

Or Google DNS:
```bash
curl -s 'https://dns.google/resolve?name=domain.com&type=MX'
```

Both should show `mx1.improvmx.com` (priority 10) and `mx2.improvmx.com` (priority 20) in the Answer section.

### Step 4 — Validate Account (REQUIRED before forwarding works)

When you first sign up, ImprovMX sends a "Important: Validate your account" email to the forwarded address with a validation link like:

```
https://app.improvmx.com/validate/<token>
```

**This link MUST be clicked** before forwarding will actually deliver emails, even if the dashboard says forwarding is "active" and all DNS records are verified. The validation email expires in 5 days. If the user hasn't validated, forwarded emails will silently not arrive — no bounce, no error, no spam folder — they just disappear.

Check for this email in the destination Gmail via `GMAIL_FETCH_EMAILS` with `query: "subject:Validate your account from:improvmx"`.

### Step 5 — Confirm in ImprovMX Dashboard

Click "CHECK AGAIN" in the ImprovMX dashboard. May need to wait 2-5 minutes for ImprovMX's DNS cache to update even after public DNS shows the records. If it still says "needs setup" after DNS is confirmed live, check the ImprovMX inspector at `inspector.improvmx.com/<domain>` — it will show which specific records are missing or incorrect (MX, SPF, or both).

**ImprovMX dashboard caching:** The "CHECK AGAIN" button can take 3-5 minutes to reflect changes even after public DNS (Cloudflare/Google) confirms propagation. Don't panic if it shows "needs setup" immediately after DNS is live — wait and retry. Once it goes green, ImprovMX sends a confirmation email ("bistro-cloud.com is forwarding 🚀") to the forwarded address.

**Diagnostic emails from ImprovMX:** During setup, ImprovMX sends several emails to the forwarded address that serve as progress indicators:
1. "Welcome to ImprovMX" — account created
2. "Important: Validate your account" — validation link (MUST click)
3. "Setup bistro-cloud.com for forwarding" — MX records not yet detected (sent while DNS is propagating)
4. "Forwarding active for bistro-cloud.com" — MX records confirmed, forwarding is live

If the test email from a real provider doesn't arrive, check that email #2 was validated and email #4 was received.

### Step 5 — Test Forwarding (IMPORTANT: Use a Real Email Provider)

**Do NOT test with transactional senders (Resend, SendGrid, etc.).** Sending a test email via Resend FROM one domain TO `b2b@bistro-cloud.com` will likely NOT arrive via ImprovMX forwarding. This is because:

1. Transactional senders use their own SMTP infrastructure — the email goes out through Resend's servers, not a standard mail client
2. SPF/DKIM alignment breaks when ImprovMX rewrites the forwarding envelope — the sending domain's SPF doesn't include ImprovMX's servers
3. Gmail may silently drop the forwarded email (not even in spam) due to DMARC/SPF failure

**The reliable test:** Have the user send a plain email from their normal email client (iCloud, Gmail, Outlook) to `b2b@bistro-cloud.com`. This is also the real-world use case — clients replying to a pitch sent from `b2b@bistro-cloud.com` will use their own mail providers.

To verify the forwarded email arrived, use Composio's `GMAIL_FETCH_EMAILS` with `query: "from:sender@domain.com"` or `query: "newer_than:1h"` on the destination Gmail account.

## No Conflict with Resend

Resend's MX records are on the `send` subdomain (e.g. `send.bistro-cloud.com` → `feedback-smtp.eu-west-1.amazonses.com`), not the root. ImprovMX MX records go on the root `@`. They coexist without conflict:

- **Root MX (`@`)** → ImprovMX (inbound forwarding)
- **Subdomain MX (`send`) → Resend (outbound sending)

## End-to-End Flow

```
Sender → b2b@bistro-cloud.com
           ↓ (root MX: mx1.improvmx.com)
       ImprovMX forwarding
           ↓ (silently forwards)
       sambawy@gmail.com
           ↓ (Composio Gmail integration)
       Agent reads it via GMAIL_FETCH_EMAILS
```

The sender never sees `sambawy@gmail.com`. Replies to the email go to the sender's address, not back through ImprovMX (unless the user sets up reply-to handling separately).

## Verified Setup: bistro-cloud.com (2026-07-02)

- Domain: bistro-cloud.com (DNS: Google Domains / Squarespace)
- ImprovMX aliases: `b2b` → sambawy@gmail.com, `catering` → sambawy@gmail.com, catch-all `@` → sambawy@gmail.com
- MX records: `@` MX 10 mx1.improvmx.com, `@` MX 20 mx2.improvmx.com (confirmed live via Cloudflare DoH + Google DNS)
- SPF record: `@` TXT `v=spf1 include:spf.improvmx.com ~all` (confirmed live via Cloudflare DoH)
- Resend sending remains functional (send subdomain MX untouched, no SPF conflict)
- ImprovMX confirmed forwarding active (confirmation email received: "bistro-cloud.com is forwarding 🚀")
- Test emails sent via Resend did NOT arrive via forwarding (SPF/DKIM alignment issue with transactional senders)
- Reliable test: user sends from a normal email client (e.g. iCloud) to b2b@bistro-cloud.com