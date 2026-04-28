# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

CCRE (Claude Code Reverse Engineering) intercepts every HTTPS call that the Claude Code native binary (`claude.exe`, 197 MB Mach-O ARM64) makes to `api.anthropic.com`. It captures system prompts, tool definitions, tool calls, assistant responses, and token usage by routing traffic through a local mitmproxy instance.

It also includes a binary extraction pipeline that attempts to pull the embedded JavaScript bundle out of the binary and deobfuscate it with `webcrack`.

## Commands

### Run an intercepted Claude session
```bash
./run.sh                  # interactive session with full interception
./run.sh "one-shot prompt" # single prompt
./run.sh --no-proxy       # passthrough (no interception)
```

### Analyze captured logs
```bash
python analyze.py                    # interactive session picker
python analyze.py --last             # most recent session, paginated
python analyze.py --last --call 1    # full detail for call #1 (system prompt, tools, messages)
python analyze.py --last --verbose   # expand system prompt on every call
python analyze.py --stats            # aggregate stats across all sessions
python analyze.py --session logs/session_YYYYMMDD_HHMMSS.jsonl
```

### Extract + deobfuscate JS from binary
```bash
./extract_bundle.sh    # outputs to ./bundle-extract/ and ./webcrack-output/
```

### Syntax validation (used in CI/settings)
```bash
python3 -c "import ast; ast.parse(open('interceptor.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('analyze.py').read()); print('OK')"
bash -n run.sh
bash -n extract_bundle.sh
```

## Architecture

```
claude.exe  ──HTTPS_PROXY──►  mitmproxy :8080  ──►  api.anthropic.com
                                    │
                              interceptor.py
                                    │
                              logs/session_*.jsonl   (one JSONL per run)
                              logs/call_*.json        (one JSON per API call)
                                    │
                              analyze.py  (renders flows + stats)
```

`run.sh` handles first-run certificate generation and macOS keychain trust automatically (needs `sudo` once). After that, it starts `mitmdump` in the background, sets `HTTPS_PROXY`, `SSL_CERT_FILE`, and `NODE_EXTRA_CA_CERTS`, then `exec`s into `claude`.

## Key Design Details

**`interceptor.py` — mitmproxy addon**
- `ClaudeInterceptor.request()` captures full JSON request body, stores in `_pending` dict keyed by `id(flow)`.
- `ClaudeInterceptor.response()` retrieves the pending entry, reconstructs SSE streaming events via `_parse_sse()`, assembles streamed tool input JSON fragments via `_extract_tool_calls()`, pulls token usage from `message_start`/`message_delta` events via `_extract_usage()`, then writes logs and prints a colored summary line.
- API keys are redacted via `_redact_headers()` before any disk write.

**`analyze.py` — log renderer**
- `LOG_DIR` is resolved relative to the script, not CWD.
- System prompt is shown in full only on the first call per session (or when `--verbose` / `--call N` is used) to reduce noise.
- `render_entry()` → `_render_system()`, `_render_tools()`, `_render_messages()`, `_render_response()` pipeline.
- Session JSONL files are sorted descending by filename (timestamp-named), so `sessions[0]` is always the most recent.

**Log format**
- `logs/session_*.jsonl`: one JSON object per line, one line per API call; append-only.
- `logs/call_*.json`: full individual call with `request.body` (model, system, messages, tools), `response` (stop_reason, assistant_text, tool_calls, usage, sse_events).

## Prerequisites

| Tool | Install |
|------|---------|
| mitmproxy | `brew install mitmproxy` |
| webcrack | `npm install -g webcrack` |
| Proxyman (optional GUI) | `brew install --cask proxyman` |

The target binary is at `/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`.

## Troubleshooting

- **Port 8080 in use**: `lsof -i :8080`, or change `PROXY_PORT` in `run.sh`.
- **SSL errors / cert not trusted**: `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/.mitmproxy/mitmproxy-ca-cert.pem` then `touch ~/.mitmproxy/.trusted_in_keychain`.
- **No traffic captured**: if the binary ignores `HTTPS_PROXY`, set the macOS system proxy: `networksetup -setsecurewebproxy Wi-Fi 127.0.0.1 8080` (Proxyman does this automatically).
