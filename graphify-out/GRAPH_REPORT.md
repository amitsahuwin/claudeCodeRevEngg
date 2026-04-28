# Graph Report - .  (2026-04-28)

## Corpus Check
- Corpus is ~4,771 words - fits in a single context window. You may not need a graph.

## Summary
- 69 nodes · 102 edges · 16 communities detected
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.83)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Log Analyzer UI|Log Analyzer UI]]
- [[_COMMUNITY_SSE Capture Pipeline|SSE Capture Pipeline]]
- [[_COMMUNITY_TLS Interception Layer|TLS Interception Layer]]
- [[_COMMUNITY_Project Overview & Design|Project Overview & Design]]
- [[_COMMUNITY_Binary JS Extraction|Binary JS Extraction]]
- [[_COMMUNITY_Response Processing|Response Processing]]
- [[_COMMUNITY_mitmproxy Addon Core|mitmproxy Addon Core]]
- [[_COMMUNITY_interceptor.py Module|interceptor.py Module]]
- [[_COMMUNITY_Request Capture|Request Capture]]
- [[_COMMUNITY_Log Write Path|Log Write Path]]
- [[_COMMUNITY_Token Usage Tracking|Token Usage Tracking]]
- [[_COMMUNITY_Session Management|Session Management]]
- [[_COMMUNITY_Proxy Launcher|Proxy Launcher]]
- [[_COMMUNITY_Proxyman GUI|Proxyman GUI]]
- [[_COMMUNITY_SSE Streaming Protocol|SSE Streaming Protocol]]
- [[_COMMUNITY_Log Storage|Log Storage]]

## God Nodes (most connected - your core abstractions)
1. `c()` - 9 edges
2. `render_entry()` - 8 edges
3. `main()` - 8 edges
4. `ClaudeInterceptor` - 6 edges
5. `_divider()` - 6 edges
6. `pick_session()` - 6 edges
7. `mitmproxy (HTTPS interception proxy, port 8080)` - 6 edges
8. `_render_messages()` - 5 edges
9. `_render_system()` - 5 edges
10. `_render_response()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `NODE_EXTRA_CA_CERTS env var — additional CA certs for Node.js TLS` --points_to--> `mitmproxy CA certificate — TLS MITM trust anchor`  [INFERRED]
  CLAUDE.md → README.md
- `CCRE — Claude Code Reverse Engineering Toolkit` --implements--> `PLAN.md — API Interception & Reverse Engineering design plan`  [EXTRACTED]
  README.md → PLAN.md
- `run.sh — one-command launcher (proxy + claude)` --sets_env_var--> `SSL_CERT_FILE env var — points to mitmproxy CA cert for TLS trust`  [EXTRACTED]
  README.md → CLAUDE.md
- `run.sh — one-command launcher (proxy + claude)` --sets_env_var--> `NODE_EXTRA_CA_CERTS env var — additional CA certs for Node.js TLS`  [EXTRACTED]
  README.md → CLAUDE.md
- `binwalk — binary analysis tool for JS blob offset detection` --used_by--> `extract_bundle.sh — binary JS extraction and webcrack deobfuscation`  [EXTRACTED]
  PLAN.md → README.md

## Hyperedges (group relationships)
- **TLS interception chain: CA cert + HTTPS_PROXY + SSL_CERT_FILE enable transparent HTTPS interception** — readme_mitmproxy_ca_cert, readme_https_proxy_env, claude_md_ssl_cert_file [EXTRACTED 1.00]
- **SSE processing pipeline: _parse_sse + _extract_tool_calls + _extract_usage reconstruct complete API call semantics** — claude_md_parse_sse, claude_md_extract_tool_calls, claude_md_extract_usage [EXTRACTED 1.00]
- **Binary JS extraction pipeline: extract_bundle.sh + binwalk + webcrack perform static deobfuscation** — readme_extract_bundle_sh, plan_binwalk, readme_webcrack [EXTRACTED 1.00]

## Communities

### Community 0 - "Log Analyzer UI"
Cohesion: 0.41
Nodes (14): c(), _divider(), iter_sessions(), load_session(), main(), pick_session(), print_stats(), render_entry() (+6 more)

### Community 1 - "SSE Capture Pipeline"
Cohesion: 0.2
Nodes (11): ClaudeInterceptor.request() — captures full JSON request body into _pending dict, ClaudeInterceptor.response() — reconstructs SSE, extracts tool calls, usage, writes logs, _extract_tool_calls() — assembles streamed tool input JSON fragments, _extract_usage() — pulls token usage from SSE events, LOG_DIR — resolved relative to script path, not CWD, _parse_sse() — SSE stream event reconstruction method, _redact_headers() — redacts API keys before disk write, analyze.py — CLI log analyzer (+3 more)

### Community 2 - "TLS Interception Layer"
Cohesion: 0.48
Nodes (7): NODE_EXTRA_CA_CERTS env var — additional CA certs for Node.js TLS, SSL_CERT_FILE env var — points to mitmproxy CA cert for TLS trust, api.anthropic.com — Anthropic API endpoint, mitmproxy (HTTPS interception proxy, port 8080), mitmproxy CA certificate — TLS MITM trust anchor, Proxyman — GUI network inspector (port 9090), run.sh — one-command launcher (proxy + claude)

### Community 3 - "Project Overview & Design"
Cohesion: 0.33
Nodes (6): PLAN.md — API Interception & Reverse Engineering design plan, Rationale: HTTPS_PROXY is the key interception vector because claude.exe respects it, CCRE — Claude Code Reverse Engineering Toolkit, Claude Code native binary (claude.exe, 197 MB Mach-O ARM64), HTTPS_PROXY environment variable — traffic routing mechanism, Rationale: closed binary requires network-layer interception to inspect system prompts, tools, and API flow

### Community 4 - "Binary JS Extraction"
Cohesion: 0.33
Nodes (6): binwalk — binary analysis tool for JS blob offset detection, Rationale: webcrack provides static deobfuscated source revealing prompt construction and tool definitions, bundle-extract/ — raw extracted JS blob from binary, extract_bundle.sh — binary JS extraction and webcrack deobfuscation, webcrack — JS bundle deobfuscator (by @j4k0xb), webcrack-output/ — deobfuscated JS modules

### Community 5 - "Response Processing"
Cohesion: 0.5
Nodes (3): _extract_usage(), _print_summary(), Pull token usage stats from message_start / message_delta events.

### Community 6 - "mitmproxy Addon Core"
Cohesion: 0.5
Nodes (2): ClaudeInterceptor, mitmproxy addon that captures all Claude Code → Anthropic API traffic.

### Community 7 - "interceptor.py Module"
Cohesion: 0.5
Nodes (3): _extract_tool_calls(), mitmproxy addon — Claude Code API interceptor.  Captures every request/response, Extract tool_use blocks from SSE events, assembling streamed input JSON.

### Community 8 - "Request Capture"
Cohesion: 0.67
Nodes (2): Remove API key from logged headers., _redact_headers()

### Community 9 - "Log Write Path"
Cohesion: 1.0
Nodes (2): Write individual call JSON and append to session JSONL., _write_log()

### Community 10 - "Token Usage Tracking"
Cohesion: 1.0
Nodes (2): _parse_sse(), Parse a Server-Sent Events response body into structured events and     reconstr

### Community 11 - "Session Management"
Cohesion: 1.0
Nodes (1): render_entry() — top-level log rendering pipeline in analyze.py

### Community 12 - "Proxy Launcher"
Cohesion: 1.0
Nodes (1): ClaudeInterceptor — mitmproxy addon class with request() and response() hooks

### Community 13 - "Proxyman GUI"
Cohesion: 1.0
Nodes (1): session_<ts>.jsonl — append-only per-session API call log

### Community 14 - "SSE Streaming Protocol"
Cohesion: 1.0
Nodes (1): call_<ts>.json — individual API call detail log

### Community 15 - "Log Storage"
Cohesion: 1.0
Nodes (1): CLAUDE.md — project guidance for CCRE repository

## Knowledge Gaps
- **23 isolated node(s):** `mitmproxy addon — Claude Code API interceptor.  Captures every request/response`, `Remove API key from logged headers.`, `Parse a Server-Sent Events response body into structured events and     reconstr`, `Extract tool_use blocks from SSE events, assembling streamed input JSON.`, `Pull token usage stats from message_start / message_delta events.` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Log Write Path`** (2 nodes): `Write individual call JSON and append to session JSONL.`, `_write_log()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Token Usage Tracking`** (2 nodes): `_parse_sse()`, `Parse a Server-Sent Events response body into structured events and     reconstr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Session Management`** (1 nodes): `render_entry() — top-level log rendering pipeline in analyze.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Proxy Launcher`** (1 nodes): `ClaudeInterceptor — mitmproxy addon class with request() and response() hooks`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Proxyman GUI`** (1 nodes): `session_<ts>.jsonl — append-only per-session API call log`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SSE Streaming Protocol`** (1 nodes): `call_<ts>.json — individual API call detail log`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Log Storage`** (1 nodes): `CLAUDE.md — project guidance for CCRE repository`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `mitmproxy (HTTPS interception proxy, port 8080)` connect `TLS Interception Layer` to `SSE Capture Pipeline`, `Project Overview & Design`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `SSE (Server-Sent Events) streaming — response format from Anthropic API` connect `SSE Capture Pipeline` to `TLS Interception Layer`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `interceptor.py — mitmproxy addon for capture and logging` connect `SSE Capture Pipeline` to `TLS Interception Layer`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **What connects `mitmproxy addon — Claude Code API interceptor.  Captures every request/response`, `Remove API key from logged headers.`, `Parse a Server-Sent Events response body into structured events and     reconstr` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._