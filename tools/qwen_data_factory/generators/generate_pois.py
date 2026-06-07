from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, "", "generators"}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from qwen_client import QwenClient
    from generators.common import DATA_DIR, assert_no_forbidden_text, ensure_dirs, parse_json_object, progress_bar, sanitize_poi, seed_pois, write_json, write_report
    from generators.prompt_composer import compose_prompt
else:
    from ..qwen_client import QwenClient
    from .common import DATA_DIR, assert_no_forbidden_text, ensure_dirs, parse_json_object, progress_bar, sanitize_poi, seed_pois, write_json, write_report
    from .prompt_composer import compose_prompt


SYSTEM_PROMPT = "你是OpenAI-compatible本地Qwen数据生成API，只生成候选JSON，不写代码，不决定可执行状态。"


def generate_pois(target: int, batch_size: int, output_dir: Path, allow_template_fallback: bool = False) -> dict[str, Any]:
    ensure_dirs()
    accepted: list[dict[str, Any]] = []
    rejected = 0
    request_ids: list[str] = []
    client = QwenClient()
    attempts = 0
    max_attempts = max(4, (target // max(1, batch_size) + 1) * 3)
    last_error: str | None = None

    with progress_bar(total=target, desc="qwen_pois", unit="poi") as pbar:
        while len(accepted) < target and attempts < max_attempts:
            before_count = len(accepted)
            attempts += 1
            prompt = compose_prompt("mock_pois.json", seed=attempts + len(accepted), batch_size=batch_size, start_index=len(accepted) + 1)
            try:
                request_id, text = client.generate_json(task_type="generate_pois", prompt=prompt, system_prompt=SYSTEM_PROMPT)
                request_ids.append(request_id)
                parsed = parse_json_object(text)
                assert_no_forbidden_text(parsed, f"Qwen POI response {request_id}")
                candidates = parsed.get("pois", parsed if isinstance(parsed, list) else [])
                if not isinstance(candidates, list):
                    rejected += 1
                    continue
                for candidate in candidates:
                    if len(accepted) >= target:
                        break
                    if not isinstance(candidate, dict):
                        rejected += 1
                        continue
                    poi = sanitize_poi(candidate, len(accepted) + 1)
                    if poi is None:
                        rejected += 1
                        continue
                    if poi["poi_id"] in {item["poi_id"] for item in accepted}:
                        poi["poi_id"] = f"{poi['poi_id']}_{len(accepted) + 1:03d}"
                    accepted.append(poi)
                pbar.update(len(accepted) - before_count)
                pbar.set_postfix({"attempts": attempts, "rejected": rejected})
            except Exception as exc:
                last_error = str(exc)
                break

        if len(accepted) < target and allow_template_fallback:
            existing_ids = {item["poi_id"] for item in accepted}
            for poi in seed_pois(target * 2):
                if len(accepted) >= target:
                    break
                if poi["poi_id"] not in existing_ids:
                    accepted.append(poi)
                    existing_ids.add(poi["poi_id"])
                    pbar.update(1)

    report = {
        "task": "generate_pois",
        "success": len(accepted) >= target,
        "target": target,
        "batch_size": batch_size,
        "accepted": len(accepted),
        "rejected": rejected,
        "attempts": attempts,
        "request_ids": request_ids,
        "last_error": last_error,
        "used_template_fallback": allow_template_fallback and len(request_ids) == 0,
    }
    write_report("generate_pois_report.json", report)
    if not report["success"]:
        return report

    payload = {"version": "v0.1", "area": "杭州下沙/金沙湖/高教园区", "pois": accepted[:target]}
    assert_no_forbidden_text(payload, "sanitized POIs")
    write_json(output_dir / "mock_pois.json", payload)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LifePilot mock_pois.json with local Qwen candidates.")
    parser.add_argument("--target", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    parser.add_argument("--allow-template-fallback", action="store_true", help="Use deterministic seed data if local Qwen is unavailable.")
    args = parser.parse_args()
    report = generate_pois(args.target, args.batch_size, args.output, args.allow_template_fallback)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
