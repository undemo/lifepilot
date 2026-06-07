#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

failures=()

add_if_exists() {
  local path="$1"
  if [ -e "$path" ]; then
    failures+=("$path")
  fi
}

add_if_nonempty_files() {
  local path="$1"
  if [ -d "$path" ] && find "$path" -type f | grep -q .; then
    failures+=("$path")
  fi
}

add_if_exists "frontend/node_modules"
add_if_exists "frontend/.next"
add_if_exists "frontend/test-results"
add_if_exists "frontend/tsconfig.tsbuildinfo"
add_if_exists "backend/.venv"
add_if_exists ".pytest_cache"
add_if_exists "backend/data/runtime"
add_if_exists "rebuild"
add_if_exists "lifepilot-dev"
add_if_exists "重构前.tar.gz"
add_if_nonempty_files "reports"
add_if_nonempty_files "debug"

while IFS= read -r generated_file; do
  failures+=("$generated_file")
done < <(find . -type f \( -name ".DS_Store" -o -name "*.pyc" -o -name "*.corrupt.*" -o -name "*.tmp" -o -name "*.log" \) -print)

if [ "${#failures[@]}" -gt 0 ]; then
  echo "Submission clean check failed. Remove these local artifacts before upload:"
  printf ' - %s\n' "${failures[@]}"
  exit 1
fi

echo "Submission clean check passed."
