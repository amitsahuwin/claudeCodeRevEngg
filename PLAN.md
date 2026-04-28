# Plan: Claude Code Complete API Interception & Reverse Engineering System

## Context

Claude Code is a 197 MB native Mach-O (ARM64) binary distributed via npm. It communicates with `api.anthropic.com` over HTTPS using streaming (SSE). The binary **does** respect standard `HTTPS_PROXY` / `HTTP_PROXY` environment variables, which is the key interception vector. There are no JavaScript bundles to deobfuscate directly — but the binary may embed a compiled JS blob (Bun/pkg/Node SEA), which webcrack can process if extracted.

**Goal:** Build a system that captures every API call Claude Code makes — full system prompts, user messages, tool definitions, tool calls, responses, and token counts — so the complete internal flow is visible and auditable.

---

## Architecture

```
Claude Code binary
      │
      ▼  HTTPS_PROXY=http://localhost:8080
mitmproxy (port 8080)
      │
      ├─► interceptor.py addon
      │       └─► ~/.claude/intercept/logs/
      │           ├── session_<ts>.jsonl   ← all calls in a session
      │           └── call_<ts>.json       ← individual call detail
      │
      ▼  SSL forwarded
api.anthropic.com

Proxyman (GUI, port 9090) runs in parallel for visual real-time inspection.
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `~/.claude/intercept/interceptor.py` | mitmproxy addon — core capture logic |
| `~/.claude/intercept/run.sh` | One-command launcher: starts proxy + runs `claude` |
| `~/.claude/intercept/analyze.py` | CLI log analyzer: renders captured flows as readable conversations |
| `~/.claude/intercept/extract_bundle.sh` | Attempt to extract embedded JS blob from binary for webcrack |
| `~/.claude/intercept/logs/` | Output directory (auto-created) |

---

## Step-by-Step Implementation

### Step 1 — Install tools

```bash
brew install --cask proxyman
pip install mitmproxy
npm install -g webcrack
brew install binwalk  # binary analysis for JS extraction
```

### Step 2 — `interceptor.py` (mitmproxy addon)

Full-featured addon that:
- Filters requests by `api.anthropic.com` host
- On `request()`: captures method, path, headers (redacting API key), full JSON body
  - Extracts: `model`, `system`, `messages[]`, `tools[]`, `max_tokens`, `stream`
- On `response()`: captures status, reconstructs SSE stream event-by-event
  - Assembles `content_block_delta` events into full assistant text
  - Captures tool_use blocks, input_json, stop_reason, usage (input/output tokens)
- Writes one `call_<timestamp>.json` per API call
- Appends to `session_<ts>.jsonl` for the current session
- Prints a compact summary line to stdout per call: `[model] → [stop_reason] | in=N out=M tokens`

### Step 3 — `run.sh` (launcher)

```bash
#!/usr/bin/env bash
# First-run: generate mitmproxy CA cert and trust it in macOS keychain
# Start mitmdump with interceptor.py in background
# Export HTTPS_PROXY=http://127.0.0.1:8080 SSL_CERT_FILE=~/.mitmproxy/mitmproxy-ca-cert.pem
# exec claude "$@"
# Trap EXIT to kill proxy cleanly
```

Certificate trust command (runs once):
```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain ~/.mitmproxy/mitmproxy-ca-cert.pem
```

### Step 4 — `analyze.py` (log analyzer)

Interactive CLI tool that:
- Lists captured sessions with call counts and token totals
- For a selected session, renders full conversation flow:
  - `[SYSTEM]` block
  - `[USER]` messages
  - `[TOOL DEFS]` — all tools available (names + descriptions)
  - `[ASSISTANT]` text
  - `[TOOL USE]` — tool name + input params
  - `[TOOL RESULT]` — tool output (from next API call's messages)
- Shows statistics: models used, total tokens, call timing, tool call frequency

### Step 5 — Proxyman Setup (parallel GUI monitoring)

Configure in addition to mitmproxy for visual real-time view:
1. Launch Proxyman → **Certificate** → **Install Certificate** → trust in Keychain
2. **Tools → SSL Proxying** → add `api.anthropic.com` with port `443`
3. Proxyman auto-sets macOS system proxy
4. Run `claude` normally — all traffic appears in Proxyman's request list

### Step 6 — `extract_bundle.sh` + webcrack (source code analysis)

Attempt to extract embedded JavaScript from the binary:
```bash
# Detect build tool from binary strings
strings /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe \
  | grep -E 'bun|pkg|SEA_BLOB|BLOB_SENTINEL|__nexe' | head -20

# If Bun: extract the embedded JS blob
# Bun executables have a known trailer structure starting at file end
# binwalk can identify the offset of the embedded JS blob
binwalk -e /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe

# Run webcrack on any extracted .js
webcrack extracted_bundle.js -o ./webcrack-output/
```

webcrack output gives: deobfuscated, modularized JS with readable variable names, revealing prompt construction logic, API call patterns, and tool definitions statically.

---

## Critical Files (no existing code to reuse — all new)

- `~/.claude/intercept/interceptor.py` — new mitmproxy addon
- `~/.claude/intercept/run.sh` — new launcher script
- `~/.claude/intercept/analyze.py` — new CLI analyzer
- `~/.claude/intercept/extract_bundle.sh` — new extraction helper

---

## Verification

1. Run `~/.claude/intercept/run.sh` — should print `[intercept] proxy started on :8080`
2. Type any prompt to claude (e.g. `claude "list files here"`)
3. In terminal: summary line should appear: `[claude-opus-4-7] → end_turn | in=1240 out=87 tokens`
4. Check `~/.claude/intercept/logs/` — new `call_*.json` should exist
5. Run `python ~/.claude/intercept/analyze.py` — select the session → full flow renders
6. In Proxyman: `api.anthropic.com/v1/messages` entry visible with full request/response
7. Run `extract_bundle.sh` — if extraction succeeds, `webcrack-output/` has readable source

---

## What You Will See

After setup, for every prompt you give Claude Code, you will have:
- The **full system prompt** Anthropic injects (context about your codebase, tools, etc.)
- Every **tool definition** sent (Bash, Read, Edit, Write, Agent, etc.)
- The **exact user message** as Claude Code reformats it
- Every **tool call** with its input params
- Every **tool result** Claude sees
- The **assistant's reasoning** and responses
- **Token counts** per call and cumulative totals
- A **static deobfuscated source** (if binary extraction succeeds) showing how prompts are constructed
