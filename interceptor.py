"""
mitmproxy addon — Claude Code API interceptor.

Captures every request/response between Claude Code and api.anthropic.com.
Handles SSE streaming, reconstructs full assistant turns and tool calls.

Usage:
    mitmdump -s interceptor.py --listen-port 8080
"""

from __future__ import annotations

import json
import time
import datetime
from pathlib import Path

from mitmproxy import http

TARGET_HOST = "api.anthropic.com"

# Logs are stored next to this script (inside the CCRE project folder)
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# One session JSONL per mitmproxy process run
_session_ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
_session_log = LOG_DIR / f"session_{_session_ts}.jsonl"

# ANSI colours for terminal summary
_RESET = "\033[0m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"
_BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove API key from logged headers."""
    return {
        k: "***REDACTED***" if k.lower() in ("x-api-key", "authorization") else v
        for k, v in headers.items()
    }


def _parse_sse(raw: bytes) -> tuple[list[dict], str]:
    """
    Parse a Server-Sent Events response body into structured events and
    reconstruct the full assistant text.

    Returns (events_list, full_assistant_text).
    """
    events: list[dict] = []
    text_parts: list[str] = []

    try:
        lines = raw.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return [], ""

    for line in lines:
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue

        events.append(obj)

        if obj.get("type") == "content_block_delta":
            delta = obj.get("delta", {})
            if delta.get("type") == "text_delta":
                text_parts.append(delta.get("text", ""))

    return events, "".join(text_parts)


def _extract_tool_calls(events: list[dict]) -> list[dict]:
    """Extract tool_use blocks from SSE events, assembling streamed input JSON."""
    tool_calls: list[dict] = []
    current_tool: dict | None = None
    input_json_parts: list[str] = []

    for ev in events:
        t = ev.get("type", "")

        if t == "content_block_start":
            block = ev.get("content_block", {})
            if block.get("type") == "tool_use":
                current_tool = {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": {},
                }
                input_json_parts = []

        elif t == "content_block_delta" and current_tool is not None:
            delta = ev.get("delta", {})
            if delta.get("type") == "input_json_delta":
                input_json_parts.append(delta.get("partial_json", ""))

        elif t == "content_block_stop" and current_tool is not None:
            raw_input = "".join(input_json_parts)
            try:
                current_tool["input"] = json.loads(raw_input)
            except json.JSONDecodeError:
                current_tool["input"] = {"_raw": raw_input}
            tool_calls.append(current_tool)
            current_tool = None
            input_json_parts = []

    return tool_calls


def _extract_usage(events: list[dict]) -> dict:
    """Pull token usage stats from message_start / message_delta events."""
    usage: dict = {}
    for ev in events:
        if ev.get("type") == "message_start":
            usage.update(ev.get("message", {}).get("usage", {}))
        elif ev.get("type") == "message_delta":
            usage.update(ev.get("usage", {}))
    return usage


def _print_summary(entry: dict) -> None:
    req = entry["request"]
    resp = entry["response"]
    model = req.get("body", {}).get("model", "?")
    stop = resp.get("stop_reason", "?")
    usage = resp.get("usage", {})
    in_tok = usage.get("input_tokens", "?")
    out_tok = usage.get("output_tokens", "?")
    tools = resp.get("tool_calls", [])
    ts = entry["timestamp"]

    tool_str = ""
    if tools:
        names = [t["name"] for t in tools]
        tool_str = f"  {_YELLOW}tools: {', '.join(names)}{_RESET}"

    print(
        f"{_CYAN}[{ts}]{_RESET} "
        f"{_BOLD}{model}{_RESET} → "
        f"{_GREEN}{stop}{_RESET} | "
        f"in={_MAGENTA}{in_tok}{_RESET} "
        f"out={_MAGENTA}{out_tok}{_RESET}"
        f"{tool_str}"
    )


def _write_log(entry: dict) -> None:
    """Write individual call JSON and append to session JSONL."""
    ts = entry["timestamp"].replace(":", "-").replace(".", "-")
    call_file = LOG_DIR / f"call_{ts}.json"
    call_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))

    with _session_log.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# mitmproxy addon class
# ---------------------------------------------------------------------------

class ClaudeInterceptor:
    """mitmproxy addon that captures all Claude Code → Anthropic API traffic."""

    def __init__(self) -> None:
        self._pending: dict[int, dict] = {}  # flow id → partial entry

    def request(self, flow: http.HTTPFlow) -> None:
        if TARGET_HOST not in flow.request.pretty_host:
            return

        try:
            body = json.loads(flow.request.content or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"_raw": flow.request.content.decode("utf-8", errors="replace")}

        self._pending[id(flow)] = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "request": {
                "method": flow.request.method,
                "path": flow.request.path,
                "headers": _redact_headers(dict(flow.request.headers)),
                "body": body,
            },
            "_start_ns": time.monotonic_ns(),
        }

    def response(self, flow: http.HTTPFlow) -> None:
        if TARGET_HOST not in flow.request.pretty_host:
            return

        partial = self._pending.pop(id(flow), None)
        if partial is None:
            return

        elapsed_ms = (time.monotonic_ns() - partial.pop("_start_ns")) / 1_000_000

        content = flow.response.content or b""
        events, assistant_text = _parse_sse(content)
        tool_calls = _extract_tool_calls(events)
        usage = _extract_usage(events)

        stop_reason = None
        for ev in events:
            if ev.get("type") == "message_delta":
                stop_reason = ev.get("delta", {}).get("stop_reason")
                break

        entry = {
            **partial,
            "elapsed_ms": round(elapsed_ms, 1),
            "response": {
                "status": flow.response.status_code,
                "stop_reason": stop_reason,
                "assistant_text": assistant_text,
                "tool_calls": tool_calls,
                "usage": usage,
                "sse_event_count": len(events),
                "sse_events": events,
            },
        }

        _write_log(entry)
        _print_summary(entry)

    def error(self, flow: http.HTTPFlow) -> None:
        self._pending.pop(id(flow), None)


addons = [ClaudeInterceptor()]
