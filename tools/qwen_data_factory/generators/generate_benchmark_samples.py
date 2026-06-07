from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from generators.common import DATA_DIR, build_benchmarks, write_json
else:
    from .common import DATA_DIR, build_benchmarks, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate benchmark_samples.json.")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    payload = build_benchmarks()
    write_json(args.output / "benchmark_samples.json", payload)
    print(json.dumps({"success": True, "file": str(args.output / "benchmark_samples.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
