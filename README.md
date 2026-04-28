# CCRE — Claude Code Reverse Engineering Toolkit

A complete system for intercepting, logging, and analyzing every API call that **Claude Code CLI** makes to the Anthropic API — capturing system prompts, tool definitions, tool calls, responses, and token usage in real time.

Also includes a binary extraction pipeline that attempts to pull the embedded JavaScript bundle out of the Claude Code native binary and deobfuscate it with **webcrack**.

---

## Why This Exists

Claude Code is distributed as a compiled native binary (`claude.exe`, 197 MB Mach-O ARM64). There is no readable source. To understand:

- What system prompt Anthropic injects
- What tools are defined and how they are described
- How multi-step tool-call chains work
- How much context is sent per call
- What the full request/response cycle looks like

...you need to intercept the HTTPS traffic at the network layer and reconstruct the SSE streaming responses. That is exactly what this toolkit does.

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Claude Code (claude.exe)       │
│            197 MB native binary          │
└──────────────────┬──────────────────────┘
                   │ HTTPS_PROXY=http://127.0.0.1:8080
                   ▼
┌─────────────────────────────────────────┐
│         mitmproxy  (port 8080)           │
│                                          │
│  interceptor.py addon                    │
│    • filters api.anthropic.com           │
│    • parses JSON request bodies          │
│    • reconstructs SSE streaming          │
│    • extracts tool calls                 │
│    • logs to ./logs/                     │
└──────────────────┬──────────────────────┘
                   │ SSL forwarded
                   ▼
         api.anthropic.com

  Proxyman (GUI) runs in parallel on port 9090
  for real-time visual inspection.
```

---

## Project Structure

```
CCRE/
├── run.sh              # One-command launcher — starts proxy + runs claude
├── interceptor.py      # mitmproxy addon — core capture & logging logic
├── analyze.py          # CLI log analyzer — renders captured flows
├── extract_bundle.sh   # Binary JS extraction + webcrack deobfuscation
├── PLAN.md             # Original design plan with full rationale
├── logs/               # Captured API calls (auto-created)
│   ├── session_YYYYMMDD_HHMMSS.jsonl   # all calls in one session
│   └── call_YYYYMMDD_HHMMSS_ffffff.json # individual call detail
├── bundle-extract/     # Raw extracted JS blob (created by extract_bundle.sh)
└── webcrack-output/    # Deobfuscated JS modules (created by extract_bundle.sh)
```

---

## Prerequisites

| Tool | Install | Purpose |
|------|---------|---------|
| mitmproxy | `brew install mitmproxy` | HTTPS interception proxy |
| webcrack | `npm install -g webcrack` | JS bundle deobfuscation |
| Proxyman | `brew install --cask proxyman` | GUI network inspector |
| Claude Code | already installed | the target being reversed |

All four are already installed on this machine.

---

## Quick Start

### 1. First-time certificate setup (one-time only)

Run any intercepted session — `run.sh` handles cert generation and keychain trust automatically on first launch (will ask for `sudo` once):

```bash
cd /Users/amitsahu/Documents/projects/CCRE
./run.sh
```

This will:
1. Generate the mitmproxy CA certificate at `~/.mitmproxy/mitmproxy-ca-cert.pem`
2. Add it to the macOS System Keychain as a trusted root (so the native binary trusts it)
3. Start `mitmdump` with `interceptor.py` on port 8080
4. Launch `claude` with `HTTPS_PROXY` and `SSL_CERT_FILE` set

### 2. Use Claude Code normally

Once `run.sh` is running, just use `claude` as you normally would. Every API call is intercepted. You will see live summary lines in the terminal:

```
[intercept] Proxy started (PID 12345). Logs → ./logs
[2026-04-28T10:05:01] claude-opus-4-7 → end_turn | in=4821 out=312  tools: Bash, Read
[2026-04-28T10:05:09] claude-opus-4-7 → tool_use | in=5103 out=89   tools: Edit
[2026-04-28T10:05:14] claude-opus-4-7 → end_turn | in=5290 out=41
```

### 3. Analyze the captured logs

```bash
# Interactive session picker
python analyze.py

# Most recent session (full flow, paginated)
python analyze.py --last

# Show only API call #1 in full detail (system prompt, all tools, messages)
python analyze.py --last --call 1

# Show every call with the system prompt expanded on each
python analyze.py --last --verbose

# Aggregate stats across ALL captured sessions
python analyze.py --stats
```

---

## What the Analyzer Shows

For each API call, `analyze.py` renders:

```
══════════ API CALL #1  2026-04-28T10:05:01  claude-opus-4-7  1247ms ══════════
  path: /v1/messages

──────────────────────── SYSTEM PROMPT ────────────────────────────────────────
  <Full system prompt Anthropic injects — role, persona, instructions, codebase
  context, tool usage guidelines, etc. Typically 3,000–8,000 tokens>

──────────────── TOOL DEFINITIONS (18 tools) ───────────────────────────────────
  Bash:       Execute a shell command and return its output…
  Read:       Read a file from the local filesystem…
  Edit:       Perform exact string replacements in files…
  Write:      Write a file to the local filesystem…
  Agent:      Launch a new agent to handle complex multi-step tasks…
  …

──────────────────────────── USER MESSAGE ──────────────────────────────────────
  <Exactly what was sent as the user turn — may include injected context>

──────────────── ASSISTANT RESPONSE (stop=tool_use) ────────────────────────────
  <Assistant text before a tool call>

──────────────── TOOL CALL: Bash (id=toolu_01Xyz) ──────────────────────────────
  {
      "command": "ls -la",
      "description": "List files in current directory"
  }

  tokens: in=4821 out=312  cache_read=4100  cache_write=721
```

---

## Log Format

### `logs/session_*.jsonl`
One JSON object per line, one line per API call. Append-only. Safe to `tail -f`.

### `logs/call_*.json`
Full detail for one API call:

```json
{
  "timestamp": "2026-04-28T10:05:01.123456",
  "elapsed_ms": 1247.3,
  "request": {
    "method": "POST",
    "path": "/v1/messages",
    "headers": { "x-api-key": "***REDACTED***", "content-type": "application/json" },
    "body": {
      "model": "claude-opus-4-7-20251101",
      "system": "<full system prompt>",
      "messages": [ ... ],
      "tools": [ ... ],
      "max_tokens": 32000,
      "stream": true
    }
  },
  "response": {
    "status": 200,
    "stop_reason": "tool_use",
    "assistant_text": "<assistant prose before tool call>",
    "tool_calls": [
      { "id": "toolu_01Xyz", "name": "Bash", "input": { "command": "ls -la" } }
    ],
    "usage": {
      "input_tokens": 4821,
      "output_tokens": 312,
      "cache_read_input_tokens": 4100,
      "cache_creation_input_tokens": 721
    },
    "sse_event_count": 87,
    "sse_events": [ ... ]
  }
}
```

---

## Proxyman (GUI Inspection)

Proxyman gives a live GUI view of all traffic — useful for clicking through individual calls and inspecting raw JSON without writing any code.

1. Open `/Applications/Proxyman.app`
2. **Certificate → Install Certificate** → trust in Keychain when prompted
3. **Tools → SSL Proxying** → add rule: host = `api.anthropic.com`, port = `443`
4. Proxyman auto-configures the macOS system proxy
5. Run `./run.sh` — all `api.anthropic.com` calls appear in Proxyman's sidebar with full request/response JSON

> **Note:** Proxyman and mitmproxy can run simultaneously. Proxyman uses a different port (9090 by default) and configures the system proxy independently; mitmproxy is set via `HTTPS_PROXY` env var in `run.sh`.

---

## Binary JS Extraction + webcrack

Claude Code's native binary may embed a JavaScript bundle (if built with Bun, Node.js SEA, or pkg). `extract_bundle.sh` tries to extract and deobfuscate it:

```bash
./extract_bundle.sh
```

**What it does:**
1. Detects build tool from binary string signatures (Bun / Node SEA / pkg)
2. Extracts the embedded JS blob using build-tool-specific byte-offset logic
3. Runs `webcrack` on the extracted JS, producing modular, readable output in `./webcrack-output/`
4. Falls back to string extraction (JS patterns, prompt templates) if blob extraction fails

**webcrack** (by [@j4k0xb](https://github.com/j4k0xb/webcrack)) reverses:
- Webpack/rollup module bundling → separate files
- Variable renaming obfuscation → readable names
- Dead code and control-flow obfuscation → clean logic

If extraction succeeds, `./webcrack-output/` will contain the de-bundled source modules showing exactly how prompts are constructed, how tools are defined, how the conversation loop works, etc.

---

## Troubleshooting

### Port 8080 already in use
```bash
lsof -i :8080          # find what's using it
# or change PROXY_PORT in run.sh to 8081 and update interceptor.py accordingly
```

### Certificate not trusted / SSL errors
```bash
# Re-trust manually
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem

# Reset the marker so run.sh retries on next launch
rm ~/.mitmproxy/.trusted_in_keychain
```

### No logs appearing
- Confirm `mitmdump` is running: `ps aux | grep mitmdump`
- Confirm `HTTPS_PROXY` is set: `echo $HTTPS_PROXY` (should be `http://127.0.0.1:8080`)
- Check `mitmdump` output for errors (remove `--quiet` from `run.sh` temporarily)

### mitmproxy not capturing claude traffic
The native binary may use a bundled TLS stack that ignores `HTTPS_PROXY`. If so:
```bash
# Set as system-wide proxy instead (Proxyman does this automatically)
networksetup -setsecurewebproxy Wi-Fi 127.0.0.1 8080
networksetup -setsecurewebproxystate Wi-Fi on
# Remember to turn off when done:
networksetup -setsecurewebproxystate Wi-Fi off
```

---

## Key Findings from Initial Analysis

| Property | Value |
|----------|-------|
| Binary location | `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe` |
| Binary size | 197 MB |
| Binary format | Mach-O 64-bit ARM64 (native, not JS) |
| Proxy support | Respects `HTTPS_PROXY` / `HTTP_PROXY` env vars |
| API endpoint | `https://api.anthropic.com/v1/messages` |
| Response format | Server-Sent Events (SSE) streaming |
| JS bundles | None in package dir; may be embedded in binary |
| Type definitions | `sdk-tools.d.ts` (2,744 lines) available in package |

---

## Files Reference

| File | Description |
|------|-------------|
| `run.sh` | Main entrypoint. Handles cert setup, starts proxy, passes args to `claude`. |
| `interceptor.py` | mitmproxy addon. `request()` captures JSON body. `response()` parses SSE, extracts tool calls, writes logs. |
| `analyze.py` | Log viewer. Renders system prompt, tool defs, messages, tool calls, token stats. |
| `extract_bundle.sh` | Binary analysis. Detects build tool, extracts JS blob, runs webcrack. |
| `PLAN.md` | Design document with architecture rationale and verification steps. |
| `logs/` | Captured sessions. Each session = one JSONL + individual JSON per call. |
| `bundle-extract/` | Raw extracted binary data and string dumps (created on first extraction run). |
| `webcrack-output/` | De-bundled JS source modules (created if extraction succeeds). |
