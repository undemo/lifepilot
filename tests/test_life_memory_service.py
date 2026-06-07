from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-21T13:30:00+08:00")
    monkeypatch.setenv("QWEN_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    return TestClient(create_app(data_dir))


def headers(trace_id: str, idem: str | None = None):
    result = {"X-Trace-Id": trace_id, "X-Demo-User-Id": "user_demo_001"}
    if idem:
        result["X-Idempotency-Key"] = idem
    return result


def create_friend_plan(client: TestClient, trace_id: str, idem: str, *, use_memory: bool = True):
    response = client.post(
        "/api/v1/plans/create",
        json={
            "input_text": "周末和朋友在下沙附近聚一下，预算人均100，轻松一点。",
            "scenario_hint": "friend_group",
            "use_memory": use_memory,
            "current_time": "2026-05-21T13:30:00+08:00",
        },
        headers=headers(trace_id, idem),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["plan_contract"]


def test_feedback_candidate_confirmed_memory_is_used_by_next_plan(client):
    first_plan = create_friend_plan(client, "trace_mem_001", "idem_mem_first", use_memory=False)

    feedback = client.post(
        "/api/v1/feedback",
        json={
            "plan_id": first_plan["plan_id"],
            "rating": "okay",
            "selected_options": [],
            "free_text": "下次我更喜欢安静咖啡聊天，少走路。",
        },
        headers=headers("trace_mem_feedback", "idem_feedback"),
    )
    assert feedback.status_code == 200, feedback.text
    candidates = feedback.json()["data"]["memory_candidates"]
    coffee_candidate = next(item for item in candidates if "咖啡" in item["content"])
    assert coffee_candidate["status"] == "pending_confirmation"
    assert coffee_candidate["sensitivity"] == "low"

    confirm = client.post(
        f"/api/v1/memory/candidates/{coffee_candidate['candidate_id']}/confirm",
        json={"confirmed": True},
        headers=headers("trace_mem_confirm", "idem_confirm"),
    )
    assert confirm.status_code == 200, confirm.text
    memory = confirm.json()["data"]["memory"]
    assert memory["status"] == "enabled"
    assert "coffee" in memory["hints"]["tags"]

    memory_page = client.get("/api/v1/memory", headers=headers("trace_mem_list"))
    assert memory_page.status_code == 200, memory_page.text
    assert memory_page.json()["data"]["profile_summary"]["enabled_count"] == 1

    next_plan = create_friend_plan(client, "trace_mem_next", "idem_mem_next", use_memory=True)
    assert next_plan["memory_usage"]
    profile_tags = set(next_plan["constraints"]["recommendation_profile"]["normalized_tags"])
    assert {"coffee", "conversation", "quiet"} & profile_tags
    assert next_plan["messages"]["memory_profile_summary"]["used_long_term_count"] >= 1

    disabled = client.patch(
        f"/api/v1/memory/{memory['memory_id']}",
        json={"enabled": False},
        headers=headers("trace_mem_disable_one", "idem_mem_disable_one"),
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"

    deleted = client.delete(
        f"/api/v1/memory/{memory['memory_id']}",
        headers=headers("trace_mem_delete_one", "idem_mem_delete_one"),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["status"] == "deleted"


def test_use_memory_false_does_not_read_confirmed_memory(client):
    first_plan = create_friend_plan(client, "trace_mem_false_001", "idem_mem_false_first", use_memory=False)
    feedback = client.post(
        "/api/v1/feedback",
        json={"plan_id": first_plan["plan_id"], "free_text": "以后朋友聚会我更喜欢安静咖啡聊天。"},
        headers=headers("trace_mem_false_feedback", "idem_mem_false_feedback"),
    )
    assert feedback.status_code == 200, feedback.text
    candidate = next(item for item in feedback.json()["data"]["memory_candidates"] if "咖啡" in item["content"])
    confirm = client.post(
        f"/api/v1/memory/candidates/{candidate['candidate_id']}/confirm",
        json={"confirmed": True},
        headers=headers("trace_mem_false_confirm", "idem_mem_false_confirm"),
    )
    assert confirm.status_code == 200, confirm.text

    plan = create_friend_plan(client, "trace_mem_false_next", "idem_mem_false_next", use_memory=False)
    assert plan["memory_usage"] == []
    profile_tags = set(plan["constraints"]["recommendation_profile"]["normalized_tags"])
    assert "coffee" not in profile_tags


def test_personalization_disable_blocks_read_and_write(client):
    first_plan = create_friend_plan(client, "trace_mem_disable_001", "idem_mem_disable_first", use_memory=False)
    disabled = client.post("/api/v1/memory/personalization/disable", json={}, headers=headers("trace_mem_disable"))
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["personalization_enabled"] is False

    feedback = client.post(
        "/api/v1/feedback",
        json={"plan_id": first_plan["plan_id"], "free_text": "以后朋友聚会我更喜欢安静咖啡聊天。"},
        headers=headers("trace_mem_disable_feedback", "idem_mem_disable_feedback"),
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["data"]["memory_candidates"] == []

    plan = create_friend_plan(client, "trace_mem_disable_next", "idem_mem_disable_next", use_memory=True)
    assert plan["memory_usage"] == []


def test_high_sensitivity_feedback_is_not_saved_as_candidate(client):
    plan = create_friend_plan(client, "trace_mem_privacy_001", "idem_mem_privacy_first", use_memory=False)
    feedback = client.post(
        "/api/v1/feedback",
        json={"plan_id": plan["plan_id"], "free_text": "我月薪三万，住在金沙湖某小区3栋2单元。"},
        headers=headers("trace_mem_privacy_feedback", "idem_mem_privacy_feedback"),
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["data"]["memory_candidates"] == []

    candidates = client.get("/api/v1/memory/candidates", headers=headers("trace_mem_privacy_list"))
    assert candidates.status_code == 200, candidates.text
    assert candidates.json()["data"]["items"] == []
