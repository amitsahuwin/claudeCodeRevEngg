#!/usr/bin/env bash
# Extract embedded JavaScript from the Claude Code native binary, then run webcrack.
#
# Claude Code is a native Mach-O binary. Depending on the build tool
# (Bun, pkg, Node SEA), a JS bundle is embedded at a known offset.
# This script detects the build tool, extracts the blob, and deobfuscates it.
#
# Output:
#   ./bundle-extract/    — raw extracted JS blob + string analysis
#   ./webcrack-output/   — deobfuscated, modularized JS source

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINARY="/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
OUT_DIR="$SCRIPT_DIR/bundle-extract"
WEBCRACK_OUT="$SCRIPT_DIR/webcrack-output"

C_RESET="\033[0m"
C_CYAN="\033[36m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"

log()  { echo -e "${C_CYAN}[extract]${C_RESET} $*"; }
ok()   { echo -e "${C_GREEN}[extract]${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}[extract]${C_RESET} $*"; }
err()  { echo -e "${C_RED}[extract]${C_RESET} $*" >&2; }

mkdir -p "$OUT_DIR" "$WEBCRACK_OUT"

if [[ ! -f "$BINARY" ]]; then
    err "Binary not found: $BINARY"
    exit 1
fi

log "Analyzing binary: $BINARY ($(du -sh "$BINARY" | cut -f1))"

# ── Step 1: Detect build tool ─────────────────────────────────────────────────
log "Detecting build tool from binary strings..."

BUILD_TOOL="unknown"

if strings "$BINARY" 2>/dev/null | grep -q "bun:main\|bun:closure\|BUN_VERSION"; then
    BUILD_TOOL="bun"
    ok "Detected: Bun compiled binary"
elif strings "$BINARY" 2>/dev/null | grep -q "NODE_SEA_BLOB\|__sea_blob"; then
    BUILD_TOOL="node-sea"
    ok "Detected: Node.js Single Executable Application (SEA)"
elif strings "$BINARY" 2>/dev/null | grep -q "PKG_DEFAULT_ENTRYPOINT\|pkg/prelude\|__nexe_require__"; then
    BUILD_TOOL="pkg"
    ok "Detected: pkg/nexe bundled binary"
else
    warn "Build tool not detected — falling back to generic extraction."
    BUILD_TOOL="generic"
fi

log "Build-tool indicator strings from binary:"
strings "$BINARY" 2>/dev/null | grep -E 'bun|pkg|SEA|nexe|node.*version' | head -10 || true

# ── Step 2: Extract based on build tool ───────────────────────────────────────

extract_bun() {
    log "Extracting Bun embedded JS blob..."
    python3 - "$BINARY" "$OUT_DIR/bundle.js" << 'PYEOF'
import sys

binary_path = sys.argv[1]
output_path = sys.argv[2]

with open(binary_path, "rb") as f:
    data = f.read()

patterns = [b'"use strict"', b'var __', b'(function(', b'exports.', b'module.exports']
best_offset = None

for pat in patterns:
    half = len(data) // 2
    idx = data.find(pat, half)
    if idx != -1:
        if best_offset is None or idx < best_offset:
            best_offset = idx
        print(f"  Found {pat!r} at offset {idx} ({idx/len(data)*100:.1f}%)")

if best_offset is not None:
    start = max(0, best_offset - 1000)
    extracted = data[start:]
    with open(output_path, "wb") as f:
        f.write(extracted)
    print(f"Extracted {len(extracted):,} bytes → {output_path}")
else:
    start = int(len(data) * 0.7)
    extracted = data[start:]
    with open(output_path, "wb") as f:
        f.write(extracted)
    print(f"Fallback: extracted last 30% ({len(extracted):,} bytes) → {output_path}")
PYEOF
}

extract_node_sea() {
    log "Extracting Node.js SEA blob..."
    python3 - "$BINARY" "$OUT_DIR/bundle.js" << 'PYEOF'
import sys

binary_path = sys.argv[1]
output_path = sys.argv[2]

with open(binary_path, "rb") as f:
    data = f.read()

sentinel = b"NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2"
idx = data.rfind(sentinel)
if idx != -1:
    print(f"Found SEA fuse at offset {idx}")
    blob = data[idx + len(sentinel):]
    with open(output_path, "wb") as f:
        f.write(blob)
    print(f"Extracted {len(blob):,} bytes → {output_path}")
else:
    start = int(len(data) * 0.65)
    extracted = data[start:]
    with open(output_path, "wb") as f:
        f.write(extracted)
    print(f"Fallback: extracted tail ({len(extracted):,} bytes) → {output_path}")
PYEOF
}

extract_generic() {
    log "Generic extraction: searching for JS patterns in binary..."

    if command -v binwalk &>/dev/null; then
        log "Running binwalk analysis..."
        binwalk "$BINARY" 2>/dev/null | head -40 || true
        warn "For deep extraction run:  binwalk -e '$BINARY' --directory '$OUT_DIR/binwalk-extract'"
    fi

    log "Extracting JS-like strings..."
    strings -n 20 "$BINARY" 2>/dev/null \
        | grep -E '^(var |const |let |function |class |module\.|exports\.|require\()' \
        | head -200 > "$OUT_DIR/js_strings.txt" || true
    ok "JS strings → $OUT_DIR/js_strings.txt  ($(wc -l < "$OUT_DIR/js_strings.txt") lines)"

    log "Extracting prompt-like strings..."
    strings -n 40 "$BINARY" 2>/dev/null \
        | grep -E 'system prompt|You are|assistant|tool_use|tool_result|<[a-zA-Z_]+>' \
        | head -300 > "$OUT_DIR/prompt_strings.txt" || true
    ok "Prompt strings → $OUT_DIR/prompt_strings.txt  ($(wc -l < "$OUT_DIR/prompt_strings.txt") lines)"

    warn "Full blob extraction requires knowing the build tool."
}

case "$BUILD_TOOL" in
    bun)      extract_bun ;;
    node-sea) extract_node_sea ;;
    pkg)
        warn "pkg/nexe: install pkg-fetch for proper extraction (npm install -g pkg-fetch)"
        extract_generic
        ;;
    *)        extract_generic ;;
esac

# ── Step 3: Run webcrack ──────────────────────────────────────────────────────
BUNDLE_FILE="$OUT_DIR/bundle.js"

if [[ -f "$BUNDLE_FILE" ]] && [[ -s "$BUNDLE_FILE" ]]; then
    log "Bundle: $BUNDLE_FILE ($(du -sh "$BUNDLE_FILE" | cut -f1))"

    if command -v webcrack &>/dev/null; then
        log "Running webcrack deobfuscation..."
        webcrack "$BUNDLE_FILE" --output "$WEBCRACK_OUT" 2>&1 || {
            warn "webcrack failed on raw blob (may have binary prefix). Trying cleaned JS..."

            python3 - "$BUNDLE_FILE" "$OUT_DIR/bundle_clean.js" << 'PYEOF'
import sys

with open(sys.argv[1], "rb") as f:
    raw = f.read()

for pat in [b'"use strict"', b'(function', b'var ', b'const ', b'!function']:
    idx = raw.find(pat)
    if idx != -1 and idx < len(raw) * 0.5:
        js_content = raw[idx:].decode("utf-8", errors="ignore")
        with open(sys.argv[2], "w") as f:
            f.write(js_content)
        print(f"Extracted {len(js_content):,} chars of JS")
        break
PYEOF

            if [[ -f "$OUT_DIR/bundle_clean.js" ]]; then
                webcrack "$OUT_DIR/bundle_clean.js" --output "$WEBCRACK_OUT" 2>&1 \
                    || warn "webcrack failed — binary may not contain a extractable JS bundle."
            fi
        }

        if [[ -d "$WEBCRACK_OUT" ]] && [[ "$(ls -A "$WEBCRACK_OUT" 2>/dev/null)" ]]; then
            ok "webcrack output → $WEBCRACK_OUT"
            ls -la "$WEBCRACK_OUT" | head -20
        fi
    else
        warn "webcrack not installed. Run:  npm install -g webcrack"
        warn "Then:  webcrack '$BUNDLE_FILE' --output '$WEBCRACK_OUT'"
    fi
else
    warn "No bundle file extracted. Manual analysis required."
fi

echo ""
log "Extraction complete."
log "Outputs in $SCRIPT_DIR:"
log "  bundle-extract/   — raw blob + string analysis files"
log "  webcrack-output/  — deobfuscated JS modules (if extraction succeeded)"
echo ""
log "Next steps if extraction failed:"
log "  1. binwalk -e '$BINARY'  for deep binary analysis"
log "  2. Ghidra/Hopper for ARM64 disassembly"
log "  3. The HTTPS proxy logs (./logs/) capture all runtime behaviour without needing source"
