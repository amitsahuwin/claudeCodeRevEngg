#!/usr/bin/env bash
# Claude Code API interceptor launcher.
# Starts mitmproxy with the interceptor addon, then runs `claude` with proxy env vars.
# On first run, installs the mitmproxy CA cert into the macOS system keychain.
#
# Usage:
#   ./run.sh                  # interactive claude session with interception
#   ./run.sh "explain this"   # one-shot prompt with interception
#   ./run.sh --no-proxy       # run claude normally (no interception)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADDON="$SCRIPT_DIR/interceptor.py"
LOG_DIR="$SCRIPT_DIR/logs"
PROXY_PORT=8080
PROXY_HOST="127.0.0.1"
CERT_PATH="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
KEYCHAIN="/Library/Keychains/System.keychain"

# ── Colours ──────────────────────────────────────────────────────────────────
C_RESET="\033[0m"
C_CYAN="\033[36m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_BOLD="\033[1m"

log()  { echo -e "${C_CYAN}[intercept]${C_RESET} $*"; }
ok()   { echo -e "${C_GREEN}[intercept]${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}[intercept]${C_RESET} $*"; }
err()  { echo -e "${C_RED}[intercept]${C_RESET} $*" >&2; }

mkdir -p "$LOG_DIR"

# ── Passthrough mode ──────────────────────────────────────────────────────────
if [[ "${1:-}" == "--no-proxy" ]]; then
    shift
    exec claude "$@"
fi

# ── Dependency check ─────────────────────────────────────────────────────────
if ! command -v mitmdump &>/dev/null; then
    err "mitmdump not found. Install with:  brew install mitmproxy"
    exit 1
fi

if ! command -v claude &>/dev/null; then
    err "claude not found. Install Claude Code first."
    exit 1
fi

# ── Generate mitmproxy CA cert (first run) ────────────────────────────────────
if [[ ! -f "$CERT_PATH" ]]; then
    log "Generating mitmproxy CA certificate (one-time setup)..."
    mitmdump --listen-port "$PROXY_PORT" &
    MITM_INIT_PID=$!
    sleep 2
    kill "$MITM_INIT_PID" 2>/dev/null || true
    wait "$MITM_INIT_PID" 2>/dev/null || true
fi

# ── Trust CA cert in macOS keychain (first run) ───────────────────────────────
CERT_TRUSTED_MARKER="$HOME/.mitmproxy/.trusted_in_keychain"
if [[ ! -f "$CERT_TRUSTED_MARKER" ]]; then
    warn "Trusting mitmproxy CA in system keychain (requires sudo)..."
    if sudo security add-trusted-cert -d -r trustRoot -k "$KEYCHAIN" "$CERT_PATH"; then
        touch "$CERT_TRUSTED_MARKER"
        ok "Certificate trusted. You will NOT be prompted again."
    else
        err "Failed to trust certificate. HTTPS interception may fail."
        err "Run manually:  sudo security add-trusted-cert -d -r trustRoot -k $KEYCHAIN $CERT_PATH"
    fi
fi

# ── Start mitmdump in background ──────────────────────────────────────────────
log "Starting interceptor proxy on ${PROXY_HOST}:${PROXY_PORT}..."
mitmdump \
    --listen-host "$PROXY_HOST" \
    --listen-port "$PROXY_PORT" \
    --scripts "$ADDON" \
    --ssl-insecure \
    --quiet &
MITM_PID=$!

sleep 1

if ! kill -0 "$MITM_PID" 2>/dev/null; then
    err "mitmdump failed to start. Is port $PROXY_PORT already in use?"
    err "Check with:  lsof -i :$PROXY_PORT"
    exit 1
fi

ok "Proxy started (PID $MITM_PID). Logs → $LOG_DIR"
log "Forwarding Claude Code traffic via HTTPS_PROXY=http://${PROXY_HOST}:${PROXY_PORT}"
echo ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
    echo ""
    log "Shutting down proxy (PID $MITM_PID)..."
    kill "$MITM_PID" 2>/dev/null || true
    wait "$MITM_PID" 2>/dev/null || true
    ok "Done. Analyze captured calls with:  python $SCRIPT_DIR/analyze.py --last"
}
trap cleanup EXIT INT TERM

# ── Run Claude Code with proxy env vars ───────────────────────────────────────
export HTTPS_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
export HTTP_PROXY="http://${PROXY_HOST}:${PROXY_PORT}"
export SSL_CERT_FILE="$CERT_PATH"
export NODE_EXTRA_CA_CERTS="$CERT_PATH"

exec claude "$@"
