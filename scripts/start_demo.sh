#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://127.0.0.1:$BACKEND_PORT}"

export DEEPSEEK_ENABLED="${DEEPSEEK_ENABLED:-false}"
export QWEN_ENABLED="${QWEN_ENABLED:-false}"
export PYTHONPATH="$ROOT_DIR/backend"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "${FRONTEND_PID:-}" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
python3 -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID="$!"

cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  npm ci
fi

BACKEND_ORIGIN="$BACKEND_ORIGIN" npm run dev -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
FRONTEND_PID="$!"

echo "LifePilot backend bind:  http://$BACKEND_HOST:$BACKEND_PORT"
echo "LifePilot frontend bind: http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "Open from another machine: http://<server-ip>:$FRONTEND_PORT"
wait "$BACKEND_PID" "$FRONTEND_PID"
