#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/backend"
export DEEPSEEK_ENABLED="${DEEPSEEK_ENABLED:-false}"
export QWEN_ENABLED="${QWEN_ENABLED:-false}"

python3 scripts/contract_scan.py
python3 scripts/validate_mock_data.py
python3 scripts/run_backend_p0_tests.py

cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  npm ci
fi

npm run verify
npm audit
