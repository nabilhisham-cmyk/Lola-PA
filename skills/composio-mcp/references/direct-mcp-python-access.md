# Direct Composio MCP Access from Python

The Composio MCP server (`connect.composio.dev/mcp`) can be called directly from a Python script — no Hermes MCP session required. This is the pattern for cron jobs, background monitors, and standalone scripts that need Gmail (or other Composio-connected app) access.

## When to use this

- Cron jobs that monitor Gmail for replies (B2B outreach campaigns)
- Background scripts that need to read/send email without a live Hermes session
- Any automation that runs outside the Hermes gateway but needs Composio app access

## The MCP handshake (3 steps)

### Step 1: Initialize session

```python
import json, urllib.request, ssl

MCP_URL = "https://connect.composio.dev/mcp"
SESSION_ID = None

def mcp_call(method, params=None, call_id=1):
    global SESSION_ID
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": call_id
    }).encode()
    headers = {
        "x-consumer-api-key": os.environ.get("MCP_COMPOSIO_API_KEY", ""),
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"  # REQUIRED — server returns SSE
    }
    if SESSION_ID:
        headers["Mcp-Session-Id"] = SESSION_ID  # REQUIRED on all calls after init

    req = urllib.request.Request(MCP_URL, data=payload, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(req, timeout=60, context=ctx)
    raw = resp.read().decode()

    # Capture session ID from response headers (first call only)
    if not SESSION_ID:
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            SESSION_ID = sid

    # Parse SSE format: "event: message\ndata: {json}"
    for line in raw.split("\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])
    # Fallback: plain JSON
    try:
        return json.loads(raw)
    except:
        return {"raw": raw[:500]}
```

### Step 2: Send initialized notification

```python
mcp_call("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "my-script", "version": "1.0"}
}, 1)

mcp_call("notifications/initialized", {}, 2)
```

### Step 3: Execute a tool

```python
result = mcp_call("tools/call", {
    "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
    "arguments": {
        "tools": [
            {
                "tool_slug": "GMAIL_FETCH_EMAILS",  # tool_slug, NOT tool_name
                "input": {
                    "query": "subject:bistro OR subject:catering",
                    "max_results": 15,
                    "ids_only": False,
                    "include_payload": True
                }
            }
        ]
    }
}, 3)
```

## Parsing the response

The response is nested: `result.result.content[0].text` contains a JSON string that itself has `data.results[0].response.data.messages[]`.

```python
def execute_tool(tool_slug, arguments):
    result = mcp_call("tools/call", {
        "name": "COMPOSIO_MULTI_EXECUTE_TOOL",
        "arguments": {"tools": [{"tool_slug": tool_slug, "input": arguments}]}
    })
    content = result.get("result", {}).get("content", [])
    for item in content:
        if isinstance(item, dict) and "text" in item:
            try:
                parsed = json.loads(item["text"])
                results = parsed.get("data", {}).get("results", [])
                if results:
                    return results[0].get("response", {}).get("data", {})
            except:
                pass
    return {}

# Usage
data = execute_tool("GMAIL_FETCH_EMAILS", {
    "query": "subject:catering label:INBOX",
    "max_results": 20,
    "ids_only": False,
    "include_payload": True
})
messages = data.get("messages", [])
for msg in messages:
    print(f"From: {msg.get('sender','')}")
    print(f"Subject: {msg.get('subject','')}")
    print(f"Date: {msg.get('messageTimestamp','')}")
    print(f"Labels: {msg.get('labelIds',[])}")
    print(f"Preview: {msg.get('preview',{}).get('body','')[:200]}")
```

## Key gotchas

| Issue | Fix |
|-------|-----|
| `Validation error: Required at "tools[0].tool_slug"` | Use `tool_slug`, not `tool_name` |
| 401 Unauthorized | Header must be `x-consumer-api-key`, not `x-api-key` |
| SSE response not parsing | Split on newlines, extract lines starting with `data: ` |
| Session ID not captured | Check `resp.headers.get("Mcp-Session-Id")` — case varies by platform |
| `COMPOSIO_GET_TOOL_SCHEMAS` validation error | Parameter is `tool_slugs` (plural, list), not `tool_names` |
| Zero results from GMAIL_FETCH_EMAILS | Check `labelIds` in results — may be returning SENT not INBOX. Add `label:INBOX` to query |

## Gmail monitoring cron job pattern

For a recurring Gmail monitor (e.g. checking for B2B outreach replies every 2 hours):

1. Script at `/opt/data/bistro_gmail_monitor.py` — initializes MCP, searches Gmail, filters for external replies
2. Cron job calls: `source /opt/data/.env && python3 /opt/data/bistro_gmail_monitor.py`
3. Script outputs replies only when found — silent when empty (no "no replies" spam)
4. Filter logic: skip messages with `SENT` label, skip messages from own domain senders

The env var `MCP_COMPOSIO_API_KEY` must be in `/opt/data/.env` (sourced before running the script).