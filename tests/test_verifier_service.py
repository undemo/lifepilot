import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.data_paths import DATA_DIR, PLANS_STORE_PATH, TRACES_STORE_PATH  # noqa: E402
from app.main import create_app  # noqa: E402


TRACE_ID = "trace_test_20260521_verifier"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    app = create_app(data_dir)
    return TestClient(app)


def headers(key=None):
    result = {"X-Trace-Id": TRACE_ID}
    if key:
        result["X-Idempotency-Key"] = key
    return result


def _data_path(client, configured_path):
    return client.app.state.data_dir / Path(configured_path).relative_to(DATA_DIR)


def create_plan(client):
    response = client.post(
        "/api/v1/plans/create",
        json={"input_text": "今天下午想和朋友去打羽毛球，别太远。", "scenario_hint": "friend_group"},
        headers=headers("idem_verifier_plan_001"),
    )
    assert response.status_code == 200
    return response.json()["data"]["plan_contract"]


def test_verifier_outputs_required_contracts_and_logs(client):
    plan = create_plan(client)

    assert plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
    assert {"expire_at", "window_minutes", "confidence", "reasons"}.issubset(plan["executable_window"])
    check_names = {check["name"] for check in plan["verifier_result"]["checks"]}
    assert {
        "time_feasibility",
        "budget_constraint",
        "activity_ticket",
        "tool_action_integrity",
        "executable_window",
    }.issubset(check_names)

    traces = json.loads(_data_path(client, TRACES_STORE_PATH).read_text(encoding="utf-8"))
    assert any(log["event_type"] == "verifier_log" and log["module"] == "VerifierService" for log in traces["logs"])


def test_verifier_fails_overlapping_timeline_and_blocks_executor(client):
    plan = create_plan(client)
    plans_path = _data_path(client, PLANS_STORE_PATH)
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    stored = plans["plans"][plan["plan_id"]]
    duplicate = dict(stored["timeline"][0])
    duplicate["step_id"] = "step_0002"
    duplicate["order"] = 2
    stored["timeline"].append(duplicate)
    plans_path.write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")

    verify = client.post(f"/api/v1/plans/{plan['plan_id']}/verify", json={"reason": "test_overlap"}, headers=headers())
    assert verify.status_code == 200
    data = verify.json()["data"]
    assert data["verifier_result"]["status"] == "fail"
    assert "time_feasibility" in data["verifier_result"]["failed_checks"]

    execute = client.post(
        f"/api/v1/plans/{plan['plan_id']}/execute",
        json={"confirmed": True},
        headers=headers("idem_verifier_execute_blocked"),
    )
    assert execute.status_code == 400
    assert execute.json()["error"]["code"] == "BAD_REQUEST"
