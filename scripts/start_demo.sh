#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

export DEEPSEEK_ENABLED="${DEEPSEEK_ENABLED:-false}"
export QWEN_ENABLED="${QWEN_ENABLED:-false}"
export PYTHONPATH="$ROOT_DIR/backend"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [ -n "${FRONTEND_PID:-}" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

cd "$ROOT_DIR"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID="$!"

cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  npm ci
fi

BACKEND_ORIGIN="http://127.0.0.1:$BACKEND_PORT" npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT" &
FRONTEND_PID="$!"

echo "LifePilot backend:  http://127.0.0.1:$BACKEND_PORT"
echo "LifePilot frontend: http://127.0.0.1:$FRONTEND_PORT"
wait "$BACKEND_PID" "$FRONTEND_PID"
