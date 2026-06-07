from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from generators.common import DATA_DIR, build_weather, write_json
else:
    from .common import DATA_DIR, build_weather, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate mock_weather.json.")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    payload = build_weather()
    write_json(args.output / "mock_weather.json", payload)
    print(json.dumps({"success": True, "file": str(args.output / "mock_weather.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
