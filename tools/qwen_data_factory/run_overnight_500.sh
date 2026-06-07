#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

REPORT_DIR="tools/qwen_data_factory/reports"
mkdir -p "$REPORT_DIR"

STAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="$REPORT_DIR/overnight_500_${STAMP}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "== LifePilot Qwen Data Factory overnight run =="
echo "started_at: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "repo: $ROOT_DIR"
echo "log: $LOG_FILE"
echo "target_pois: 500"
echo "batch_size: 5"
echo

export QWEN_TIMEOUT="${QWEN_TIMEOUT:-180}"
export QWEN_RETRY="${QWEN_RETRY:-2}"
export QWEN_BACKOFF="${QWEN_BACKOFF:-2}"
export QWEN_ENABLE_THINKING="${QWEN_ENABLE_THINKING:-false}"

echo "== Step 1/3: generate all mock data =="
python tools/qwen_data_factory/generators/generate_all.py \
  --target-pois 500 \
  --batch-size 5

echo
echo "== Step 2/3: validate mock data =="
python tools/qwen_data_factory/validators/validate_mock_data.py --input backend/data

echo
echo "== Step 3/3: scan contract redlines =="
PYTHONPATH=backend python scripts/contract_scan.py

echo
echo "finished_at: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "success: true"
echo "log: $LOG_FILE"
