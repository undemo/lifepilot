import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.rules.recommendation_taxonomy import extract_budget_max_per_person, extract_dining_preference  # noqa: E402
from tools.rule_evaluation.plan_quality import auto_quality_review  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-21T13:30:00+08:00")
    monkeypatch.setenv("QWEN_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    app = create_app(data_dir)
    return TestClient(app)


def test_buffet_specific_tags_do_not_inherit_family_light_meal_defaults():
    profile = extract_dining_preference("这周末想和老婆孩子去游乐园，然后吃一顿自助餐", ["light_food", "family_parent_child"])

    assert profile["explicit"] is True
    assert profile["mode"] == "format"
    assert "buffet" in profile["specific_tags"]
    assert "light_food" not in profile["specific_tags"]
    assert "自助餐" in profile["positive_terms"]


def test_budget_extractor_ignores_explicit_stop_count_ranges():
    text = "预算适中，路线别太折腾。安排4-5个活动。下午一点出发，晚上十点钟回来"

    assert extract_budget_max_per_person(text) is None


def test_rule_eval_dataset_has_200_contract_cases():
    dataset_path = ROOT / "tools" / "rule_evaluation" / "rule_eval_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert dataset["schema_version"] == "rule_eval.v1"
    assert dataset["case_count"] == 200
    assert len(dataset["cases"]) == 200
    assert len({case["case_id"] for case in dataset["cases"]}) == 200
    assert dataset["groups"]["family_parent_child"] >= 40
    assert dataset["groups"]["date_dining_anchor"] >= 40
    assert all(case["request_body"]["input_text"] for case in dataset["cases"])


def test_family_amusement_buffet_plan_uses_buffet_not_buns(client):
    response = client.post(
        "/api/v1/plans/create",
        json={
            "input_text": "这周末想和老婆孩子去游乐园，然后吃一顿自助餐",
            "use_memory": False,
            "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        },
        headers={"X-Trace-Id": "trace_rule_buffet", "X-Idempotency-Key": "idem_rule_buffet"},
    )
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]

    assert plan["user_goal"]["scenario"] == "family_parent_child"
    assert {"amusement", "buffet", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert poi_steps[0]["type"] == "activity"
    assert "amusement" in set(poi_steps[0].get("display_tags") or []) or any(
        token in poi_steps[0]["title"] for token in ("游乐园", "嘉年华", "儿童乐园")
    )
    restaurant = poi_steps[-1]
    assert restaurant["type"] == "restaurant"
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert "buffet" in restaurant_text or any(token in restaurant_text for token in ("自助餐", "自助烤肉", "自助火锅", "放题"))
    assert not any(token in restaurant_text for token in ("包子", "牛肉汤"))


def test_auto_quality_review_blocks_buffet_replaced_by_snack():
    review = auto_quality_review(
        {
            "scenario": "family_parent_child",
            "intent_tags": ["family_parent_child", "amusement", "buffet", "dinner"],
            "constraints": {"must_have": ["amusement", "buffet", "dinner"]},
            "expected": {
                "scenario": "family_parent_child",
                "must_have_tags": ["amusement", "buffet", "dinner"],
                "activity_should_match_any": ["amusement"],
                "restaurant_should_match_any": ["buffet"],
                "timeline_order": "dinner_last",
                "should_exclude_terms": ["包子", "牛肉汤"],
            },
            "timeline": [
                {
                    "type": "activity",
                    "title": "爱玩嘉年华",
                    "display_tags": ["amusement", "child_friendly"],
                    "semantic_tags": ["amusement", "child_friendly", "kid_safe"],
                },
                {
                    "type": "restaurant",
                    "title": "马走日·露馅包子·大骨牛肉汤",
                    "display_tags": ["snack_meal"],
                    "semantic_tags": ["restaurant", "snack_meal", "casual_chain"],
                },
            ],
            "route_summary": {"total_duration_minutes": 18, "total_distance_km": 1.2},
        }
    )

    assert review["decision"] == "fail"
    assert review["critical_issue_count"] >= 1
    assert {
        "restaurant_slot_miss",
        "buffet_replaced_by_snack",
        "excluded_term_present",
    } & {issue["code"] for issue in review["issues"]}


def test_auto_quality_review_passes_clean_buffet_plan_with_route_warning():
    review = auto_quality_review(
        {
            "scenario": "family_parent_child",
            "intent_tags": ["family_parent_child", "amusement", "buffet", "dinner"],
            "constraints": {"must_have": ["amusement", "buffet", "dinner", "route_simple"]},
            "expected": {
                "scenario": "family_parent_child",
                "must_have_tags": ["amusement", "buffet", "dinner"],
                "activity_should_match_any": ["amusement"],
                "restaurant_should_match_any": ["buffet"],
                "timeline_order": "dinner_last",
                "should_exclude_terms": ["包子", "牛肉汤"],
            },
            "timeline": [
                {
                    "type": "activity",
                    "title": "爱玩嘉年华",
                    "display_tags": ["amusement", "child_friendly"],
                    "semantic_tags": ["amusement", "child_friendly", "kid_safe"],
                },
                {
                    "type": "restaurant",
                    "title": "举高高自助小火锅",
                    "display_tags": ["buffet", "family_friendly"],
                    "semantic_tags": ["restaurant", "buffet", "proper_dining", "family_friendly"],
                },
            ],
            "route_summary": {"total_duration_minutes": 42, "total_distance_km": 2.8},
        }
    )

    assert review["decision"] == "pass"
    assert review["critical_issue_count"] == 0
    assert review["score"] >= 70
    assert "route_simple_not_compact" in {issue["code"] for issue in review["issues"]}
