#!/usr/bin/env python3
"""
Claude Code API call log analyzer.

Parses JSONL session logs captured by interceptor.py and renders them as
readable conversation flows with statistics.

Usage:
    python analyze.py                  # interactive: list sessions, pick one
    python analyze.py --session <file> # analyze a specific session JSONL
    python analyze.py --stats          # aggregate stats across all sessions
    python analyze.py --last           # analyze the most recent session
    python analyze.py --call 3         # show only call #3 from the most recent session
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Iterator

# Logs live next to this script, inside the CCRE project folder
LOG_DIR = Path(__file__).parent / "logs"

# ── ANSI colours ──────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"


def c(color: str, text: str) -> str:
    return f"{color}{text}{R}"


# ── Log loading ───────────────────────────────────────────────────────────────

def load_session(path: Path) -> list[dict]:
    entries = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def iter_sessions() -> Iterator[Path]:
    return sorted(LOG_DIR.glob("session_*.jsonl"), reverse=True)


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _divider(label: str = "", width: int = 90, ch: str = "─") -> str:
    if label:
        label = f" {label} "
        pad = max(0, width - len(label))
        left = pad // 2
        right = pad - left
        return f"{DIM}{ch * left}{R}{BOLD}{label}{R}{DIM}{ch * right}{R}"
    return f"{DIM}{ch * width}{R}"


def _wrap(text: str, width: int = 88, indent: str = "  ") -> str:
    lines = text.splitlines()
    wrapped = []
    for line in lines:
        if len(line) > width:
            wrapped.extend(
                textwrap.wrap(line, width=width, initial_indent=indent, subsequent_indent=indent)
            )
        else:
            wrapped.append(indent + line)
    return "\n".join(wrapped)


def _render_messages(messages: list[dict]) -> None:
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")

        if role == "user":
            print(c(GREEN, _divider("USER MESSAGE")))
            if isinstance(content, str):
                print(_wrap(content[:4000]))
            elif isinstance(content, list):
                for block in content:
                    btype = block.get("type", "?")
                    if btype == "text":
                        print(_wrap(block.get("text", "")[:4000]))
                    elif btype == "tool_result":
                        tool_id = block.get("tool_use_id", "?")
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            result_text = "\n".join(
                                b.get("text", "") for b in result_content if b.get("type") == "text"
                            )
                        else:
                            result_text = str(result_content)
                        print(c(DIM, f"  [tool_result id={tool_id}]"))
                        print(_wrap(result_text[:2000]))
            print()

        elif role == "assistant":
            print(c(CYAN, _divider("ASSISTANT (prior turn)")))
            if isinstance(content, str):
                print(_wrap(content[:2000]))
            elif isinstance(content, list):
                for block in content:
                    btype = block.get("type", "?")
                    if btype == "text":
                        print(_wrap(block.get("text", "")[:2000]))
                    elif btype == "tool_use":
                        print(c(YELLOW, f"  [tool_use] {block.get('name')} id={block.get('id')}"))
                        try:
                            inp = json.dumps(block.get("input", {}), indent=4)
                        except Exception:
                            inp = str(block.get("input", {}))
                        print(_wrap(inp[:1000]))
            print()


def _render_tools(tools: list[dict]) -> None:
    if not tools:
        return
    print(c(MAGENTA, _divider(f"TOOL DEFINITIONS ({len(tools)} tools)")))
    for t in tools:
        name = t.get("name", "?")
        desc = t.get("description", "")
        short_desc = (desc[:120] + "…") if len(desc) > 120 else desc
        print(f"  {c(BOLD, name)}: {c(DIM, short_desc)}")
    print()


def _render_system(system: str | list) -> None:
    if not system:
        return
    print(c(BLUE, _divider("SYSTEM PROMPT")))
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") == "text":
                print(_wrap(block.get("text", "")[:6000]))
            elif isinstance(block, str):
                print(_wrap(block[:6000]))
    else:
        print(_wrap(str(system)[:6000]))
    print()


def _render_response(resp: dict) -> None:
    assistant_text = resp.get("assistant_text", "")
    tool_calls = resp.get("tool_calls", [])
    stop_reason = resp.get("stop_reason", "?")
    usage = resp.get("usage", {})

    if assistant_text:
        print(c(CYAN, _divider(f"ASSISTANT RESPONSE (stop={stop_reason})")))
        print(_wrap(assistant_text))
        print()

    for tc in tool_calls:
        print(c(YELLOW, _divider(f"TOOL CALL: {tc.get('name')} (id={tc.get('id')})")))
        try:
            inp_str = json.dumps(tc.get("input", {}), indent=4)
        except Exception:
            inp_str = str(tc.get("input", {}))
        print(_wrap(inp_str[:3000]))
        print()

    if usage:
        in_tok = usage.get("input_tokens", "?")
        out_tok = usage.get("output_tokens", "?")
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        print(
            f"  {c(DIM, 'tokens:')} in={c(MAGENTA, str(in_tok))} "
            f"out={c(MAGENTA, str(out_tok))} "
            f"cache_read={c(DIM, str(cache_read))} "
            f"cache_write={c(DIM, str(cache_write))}"
        )
        print()


def render_entry(idx: int, entry: dict, verbose_system: bool = False) -> None:
    req = entry.get("request", {})
    resp = entry.get("response", {})
    body = req.get("body", {})
    ts = entry.get("timestamp", "?")
    elapsed = entry.get("elapsed_ms", "?")
    model = body.get("model", "?")
    path = req.get("path", "?")

    print()
    print(_divider(f"API CALL #{idx + 1}  {ts}  {model}  {elapsed}ms", ch="═"))
    print(f"  {c(DIM, 'path:')} {path}")
    print()

    system = body.get("system", "")
    if system:
        if verbose_system or idx == 0:
            _render_system(system)
        else:
            size = f"{len(system)} chars" if isinstance(system, str) else "(list)"
            print(c(BLUE, f"  [system prompt: {size} — pass --verbose to expand]"))
            print()

    _render_tools(body.get("tools", []))
    _render_messages(body.get("messages", []))
    _render_response(resp)


# ── Session stats ─────────────────────────────────────────────────────────────

def session_stats(entries: list[dict]) -> dict:
    total_in = total_out = 0
    models: dict[str, int] = {}
    tool_freq: dict[str, int] = {}
    stop_reasons: dict[str, int] = {}

    for e in entries:
        body = e.get("request", {}).get("body", {})
        resp = e.get("response", {})
        usage = resp.get("usage", {})
        model = body.get("model", "?")
        stop = resp.get("stop_reason") or "?"

        total_in += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)
        models[model] = models.get(model, 0) + 1
        stop_reasons[stop] = stop_reasons.get(stop, 0) + 1

        for tc in resp.get("tool_calls", []):
            name = tc.get("name", "?")
            tool_freq[name] = tool_freq.get(name, 0) + 1

    return {
        "calls": len(entries),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "models": models,
        "stop_reasons": stop_reasons,
        "tool_calls": tool_freq,
    }


def print_stats(stats: dict, label: str = "") -> None:
    if label:
        print(c(BOLD, f"\n{label}"))
    print(f"  API calls : {c(BOLD, str(stats['calls']))}")
    print(f"  Tokens in : {c(MAGENTA, str(stats['total_input_tokens']))}")
    print(f"  Tokens out: {c(MAGENTA, str(stats['total_output_tokens']))}")
    if stats["models"]:
        print(f"  Models    : {', '.join(f'{m}({n})' for m, n in stats['models'].items())}")
    if stats["stop_reasons"]:
        print(f"  Stop rsns : {', '.join(f'{s}({n})' for s, n in stats['stop_reasons'].items())}")
    if stats["tool_calls"]:
        sorted_tools = sorted(stats["tool_calls"].items(), key=lambda x: -x[1])
        print("  Tool calls:")
        for name, count in sorted_tools:
            bar = "█" * min(count, 40)
            print(f"    {c(YELLOW, name):<30} {count:>4}  {c(DIM, bar)}")
    print()


# ── Interactive session selector ──────────────────────────────────────────────

def pick_session() -> Path | None:
    sessions = list(iter_sessions())
    if not sessions:
        print(c(RED, f"No session logs found in {LOG_DIR}"))
        print("Start an intercepted session with:  ./run.sh")
        return None

    print(c(BOLD, "\nCaptured sessions:\n"))
    for i, path in enumerate(sessions):
        entries = load_session(path)
        stats = session_stats(entries)
        ts = path.stem.replace("session_", "")
        print(
            f"  {c(CYAN, str(i + 1))}.  {ts}  "
            f"{c(DIM, str(stats['calls']) + ' calls')}  "
            f"in={stats['total_input_tokens']} out={stats['total_output_tokens']} tokens"
        )

    print()
    choice = input("Select session number (or Enter for most recent): ").strip()
    if not choice:
        return sessions[0]
    try:
        return sessions[int(choice) - 1]
    except (ValueError, IndexError):
        print(c(RED, "Invalid selection."))
        return None


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Claude Code API intercept logs")
    parser.add_argument("--session", "-s", type=Path, help="Path to a session JSONL file")
    parser.add_argument("--last", "-l", action="store_true", help="Analyze the most recent session")
    parser.add_argument("--stats", action="store_true", help="Aggregate stats across all sessions")
    parser.add_argument("--call", "-c", type=int, default=None, help="Show only call N (1-indexed)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show system prompt on every call")
    args = parser.parse_args()

    if args.stats:
        sessions = list(iter_sessions())
        if not sessions:
            print(c(RED, "No sessions found."))
            sys.exit(1)
        all_entries: list[dict] = []
        for s in sessions:
            all_entries.extend(load_session(s))
        print_stats(session_stats(all_entries), label=f"Aggregate stats ({len(sessions)} sessions)")
        return

    if args.session:
        path = args.session
    elif args.last:
        sessions = list(iter_sessions())
        if not sessions:
            print(c(RED, "No sessions found."))
            sys.exit(1)
        path = sessions[0]
    else:
        path = pick_session()
        if path is None:
            sys.exit(1)

    entries = load_session(path)
    if not entries:
        print(c(RED, f"No entries found in {path}"))
        sys.exit(1)

    print(c(BOLD, f"\nSession: {path.name}  ({len(entries)} API calls)\n"))
    print_stats(session_stats(entries))

    if args.call is not None:
        idx = args.call - 1
        if 0 <= idx < len(entries):
            render_entry(idx, entries[idx], verbose_system=True)
        else:
            print(c(RED, f"Call #{args.call} not found (session has {len(entries)} calls)"))
    else:
        for i, entry in enumerate(entries):
            render_entry(i, entry, verbose_system=args.verbose)
            if i < len(entries) - 1:
                print(c(DIM, "\nPress Enter for next call, q to quit..."), end="", flush=True)
                try:
                    key = input()
                    if key.strip().lower() == "q":
                        break
                except (EOFError, KeyboardInterrupt):
                    break


if __name__ == "__main__":
    main()
