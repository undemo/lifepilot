from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.services.schema_validator import SchemaValidator  # noqa: E402


CASES_PATH = ROOT / "tests" / "golden_llm_native_cases.json"
DEMO_NOW = "2026-05-21T13:30:00+08:00"


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _client(data_root: Path) -> TestClient:
    os.environ["LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    os.environ["QWEN_ENABLED"] = "false"
    os.environ["DEEPSEEK_ENABLED"] = "false"
    data_dir = data_root / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    return TestClient(create_app(data_dir))


def _request_body(input_text: str) -> dict[str, Any]:
    return {
        "input_text": input_text,
        "use_memory": False,
        "current_time": DEMO_NOW,
        "user_location": {
            "label": "杭州金沙湖地铁站",
            "area": "金沙湖",
            "lat": 30.309,
            "lng": 120.319,
        },
    }


def main() -> int:
    validator = SchemaValidator()
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="lifepilot_phase0_") as temp_dir:
        api = _client(Path(temp_dir))
        for case in _load_cases():
            case_id = case["case_id"]
            response = api.post(
                "/api/v1/plans/create",
                json=_request_body(case["input_text"]),
                headers={
                    "X-Trace-Id": f"trace_phase0_{case_id}",
                    "X-Idempotency-Key": f"idem_phase0_{case_id}",
                },
            )
            if response.status_code != 200:
                print(f"{case_id}: FAIL status={response.status_code} body={response.text}")
                return 1

            payload = response.json()
            if payload.get("success") is not True:
                print(f"{case_id}: FAIL success flag false body={response.text}")
                return 1

            data = payload["data"]
            plan = data["plan_contract"]
            validator.validate_plan_contract(plan)

            serialized = json.dumps(plan, ensure_ascii=False).lower()
            forbidden = ["chain_of_thought", "api_key", "prompt_log"]
            leaked = [field for field in forbidden if field in serialized]
            if leaked:
                print(f"{case_id}: FAIL leaked forbidden fields={leaked}")
                return 1

            results.append(
                {
                    "case_id": case_id,
                    "status": plan["status"],
                    "verifier_status": plan["verifier_result"]["status"],
                    "timeline_steps": len(plan["timeline"]),
                }
            )
            print(f"{case_id}: PASS")

    print(json.dumps({"passed": len(results), "cases": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
