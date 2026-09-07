#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
WEB_PORT="${WEB_PORT:-5173}"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"
INSTALL_OLLAMA_MODEL="${INSTALL_OLLAMA_MODEL:-1}"
OLLAMA_MODEL="${LOCAL_MODEL_NAME:-qwen2.5:3b-instruct}"

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

info "TrustGuard AI setup"
info "Project: $ROOT_DIR"
info "Required components: Python, Node.js/npm, gateway, web dashboard, and RCHAT.apk"

command -v "$PYTHON_BIN" >/dev/null || fail "Python 3 is missing. Install Python 3.12 or newer."
command -v node >/dev/null || fail "Node.js is missing. Install Node.js 20 or newer."
command -v npm >/dev/null || fail "npm is missing. Install it with Node.js."
command -v curl >/dev/null || fail "curl is missing; it is required for health checks."

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
NODE_VERSION="$(node --version)"
info "Found Python $PYTHON_VERSION, Node.js $NODE_VERSION, npm $(npm --version)"

[[ -f .env.example ]] || fail "Missing .env.example."
[[ -f artifacts/RCHAT.apk ]] || fail "Missing artifacts/RCHAT.apk."

if [[ ! -f .env ]]; then
  cp .env.example .env
  sed -i 's#^DATABASE_URL=.*#DATABASE_URL=sqlite+aiosqlite:///data/trustguard.db#' .env
  sed -i '/^REDIS_URL=/d' .env
  info "Created .env with local SQLite storage and empty cloud keys."
else
  info "Using existing .env; existing settings and API keys were not changed."
fi

if grep -qE '^(GROQ_API_KEY|GEMINI_API_KEY|OPENROUTER_API_KEY|ALIBABA_API_KEY)=[^[:space:]]+' .env; then
  info "At least one cloud API key is configured. Cloud Tier-2 scoring is available."
else
  warn "No cloud API keys are configured. Local classifier and deterministic scoring work; cloud Tier-2 requires keys in .env."
  warn "API keys are optional. Add GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, or ALIBABA_API_KEY to enable cloud providers."
fi

if [[ ! -x .venv/bin/python ]]; then
  info "Creating Python virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

info "Installing Python dependencies from requirements.txt..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

info "Installing locked web dependencies with npm ci..."
(
  cd apps/web/dashboard
  npm ci
)

if command -v ollama >/dev/null; then
  info "Ollama is installed."
  if ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
    info "Local Ollama model is already installed: $OLLAMA_MODEL"
  elif [[ "$INSTALL_OLLAMA_MODEL" == "1" ]]; then
    info "Downloading local Ollama model: $OLLAMA_MODEL"
    ollama pull "$OLLAMA_MODEL"
  else
    warn "Ollama model $OLLAMA_MODEL is not installed. Set INSTALL_OLLAMA_MODEL=1 to download it."
  fi
else
  warn "Ollama is not installed. Local Tier-2 AI will be unavailable until Ollama is installed."
  warn "Install Ollama, then run: ollama pull $OLLAMA_MODEL"
fi

info "Whisper voice model note: faster-whisper downloads its STT model on first voice use; text/paste analysis does not require it."

cleanup() {
  [[ -n "${GATEWAY_PID:-}" ]] && kill "$GATEWAY_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

info "Starting gateway on http://localhost:${GATEWAY_PORT}..."
PYTHONPATH="services:services/realtime-gateway" \
  STT_MODEL="${STT_MODEL:-tiny}" \
  .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "$GATEWAY_PORT" \
  > gateway.log 2>&1 &
GATEWAY_PID=$!

info "Starting web dashboard on http://localhost:${WEB_PORT}..."
(
  cd apps/web/dashboard
  npm run dev -- --host 0.0.0.0 --port "$WEB_PORT"
) > web.log 2>&1 &
WEB_PID=$!

gateway_ready=0
web_ready=0
for attempt in {1..60}; do
  curl -fsS "http://localhost:${GATEWAY_PORT}/health" >/dev/null 2>&1 && gateway_ready=1 || true
  curl -fsS "http://localhost:${WEB_PORT}/" >/dev/null 2>&1 && web_ready=1 || true
  [[ "$gateway_ready" == 1 && "$web_ready" == 1 ]] && break
  sleep 1
done

[[ "$gateway_ready" == 1 ]] || fail "Gateway did not become healthy. Read gateway.log."
[[ "$web_ready" == 1 ]] || fail "Web dashboard did not become ready. Read web.log."
info "Gateway health check passed."
info "Web dashboard health check passed."

if command -v adb >/dev/null; then
  if adb get-state >/dev/null 2>&1; then
    adb install -r artifacts/RCHAT.apk
    info "Installed artifacts/RCHAT.apk on the connected Android device."
  else
    warn "adb is installed, but no Android device/emulator is connected. RCHAT.apk is ready to install."
  fi
else
  warn "adb is not installed. Install Android Platform Tools to install RCHAT.apk automatically."
fi

printf '\nTrustGuard AI is ready.\n'
printf '  Web dashboard: http://localhost:%s\n' "$WEB_PORT"
printf '  Gateway health: http://localhost:%s/health\n' "$GATEWAY_PORT"
printf '  APK:            %s\n' "$ROOT_DIR/artifacts/RCHAT.apk"
printf '  Logs:           %s/gateway.log and %s/web.log\n' "$ROOT_DIR" "$ROOT_DIR"
printf 'Press Ctrl+C to stop both services.\n'
wait "$GATEWAY_PID" "$WEB_PID"
