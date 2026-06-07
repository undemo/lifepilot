import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.services.schema_validator import SchemaValidator  # noqa: E402


CASES_PATH = ROOT / "tests" / "golden_llm_native_cases.json"
DEMO_NOW = "2026-05-21T13:30:00+08:00"


def load_cases():
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", DEMO_NOW)
    monkeypatch.setenv("QWEN_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    return TestClient(create_app(data_dir))


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["case_id"])
def test_phase0_golden_case_create_plan_contract_compatible(client, case):
    response = client.post(
        "/api/v1/plans/create",
        json={
            "input_text": case["input_text"],
            "use_memory": False,
            "current_time": DEMO_NOW,
            "user_location": {
                "label": "杭州金沙湖地铁站",
                "area": "金沙湖",
                "lat": 30.309,
                "lng": 120.319,
            },
        },
        headers={
            "X-Trace-Id": f"trace_phase0_{case['case_id']}",
            "X-Idempotency-Key": f"idem_phase0_{case['case_id']}",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    plan = data["plan_contract"]

    SchemaValidator().validate_plan_contract(plan)
    assert plan["plan_id"].startswith("plan_")
    assert plan["trace_id"].startswith("trace_")
    assert plan["timeline"]
    assert plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
    assert "candidate_plan_ids" in data

    serialized = json.dumps(plan, ensure_ascii=False).lower()
    assert "chain_of_thought" not in serialized
    assert "api_key" not in serialized
    assert "prompt_log" not in serialized
