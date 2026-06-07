import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import FoodIntent, MachineIntent, RecommendationExplanation  # noqa: E402
from app.services.explanation_agent import ExplanationAgent  # noqa: E402
from app.services.response_assembler import ResponseAssembler  # noqa: E402


def _machine(tags=None, food_match=None):
    return MachineIntent.parse_payload(
        {
            "canonical_tags": tags or [],
            "global_constraints": {},
            "slot_requirements": [],
            "hard_filters": [],
            "soft_preferences": [],
            "penalties": [],
            "retrieval_plan": {"food_match": food_match} if food_match else {},
            "verifier_expectations": [],
            "explanation_hints": [],
        }
    )


def _food(**kwargs):
    payload = {
        "raw_terms": [],
        "known_dish_ids": [],
        "parent_categories": [],
        "ingredients": [],
        "cooking_methods": [],
        "flavors": [],
        "forms": [],
        "scenes": [],
        "specific_tags_from_existing_taxonomy": [],
        "fallback_query_text": "",
        "retrieval_mode": "unknown",
        "child_food_required": False,
        "non_spicy_required": False,
        "low_calorie_required": False,
    }
    payload.update(kwargs)
    return FoodIntent.parse_payload(payload)


def _plan(*steps, status="executable", verifier_status="pass"):
    return {
        "plan_id": "plan_test",
        "trace_id": "trace_test",
        "status": status,
        "user_goal": {"scenario": "fallback_unknown", "goal_summary": "测试计划"},
        "timeline": list(steps) or [
            {
                "step_id": "step_0001",
                "order": 1,
                "type": "restaurant",
                "title": "测试餐厅",
                "poi_id": "poi_restaurant",
                "start_time": "2026-05-27T18:00:00+08:00",
                "end_time": "2026-05-27T19:00:00+08:00",
                "duration_minutes": 60,
                "display_tags": [],
                "user_visible_notes": "",
            }
        ],
        "budget": {"currency": "CNY", "estimated_total": 100, "items": []},
        "executable_window": {"expire_at": "2026-05-27T18:20:00+08:00", "reasons": ["mock_api state"]},
        "risks": [],
        "messages": {},
        "verifier_result": {"status": verifier_status, "score": 0.9, "failed_checks": [], "warnings": []},
    }


def _step(step_type="restaurant", title="测试餐厅", poi_id="poi_restaurant"):
    return {
        "step_id": "step_0001",
        "order": 1,
        "type": step_type,
        "title": title,
        "poi_id": poi_id,
        "start_time": "2026-05-27T18:00:00+08:00",
        "end_time": "2026-05-27T19:00:00+08:00",
        "duration_minutes": 60,
        "display_tags": [],
        "user_visible_notes": "",
    }


def _text(explanation):
    payload = explanation.to_dict() if hasattr(explanation, "to_dict") else explanation
    return str(payload)


def test_family_child_crayfish_explanation_mentions_reservation_non_spicy_and_addons():
    food = _food(
        raw_terms=["小龙虾"],
        known_dish_ids=["DISH_CRAYFISH"],
        parent_categories=["CRAYFISH"],
        retrieval_mode="known_dish",
        child_food_required=True,
        non_spicy_required=True,
    )
    restaurant = {
        "poi_id": "poi_crayfish",
        "name": "小龙虾餐厅",
        "category": "restaurant",
        "menu_features": {"dish_ids": ["DISH_CRAYFISH"], "raw_food_terms": ["小龙虾"], "parent_categories": ["CRAYFISH"], "has_child_friendly_food": True, "has_non_spicy": True},
        "family_features": {"child_food_score": 0.8},
        "queue_features": {"queue_risk": 0.3},
    }

    explanation = ExplanationAgent().explain(
        final_plan_contract=_plan(_step("restaurant", "小龙虾餐厅", "poi_crayfish")),
        user_goal={},
        constraints={},
        food_intent=food,
        machine_intent=_machine(["WITH_CHILD", "CHILD_AGE_PRESCHOOL", "AVOID_LONG_QUEUE", "NEARBY_REQUIRED"]),
        selected_candidates={"selected_pois": {"restaurant": restaurant}},
    )
    text = _text(explanation)

    assert "预约" in text
    assert "不辣" in text
    assert "湿巾" in text
    assert "饮品" in text


def test_hotpot_child_non_spicy_explanation_mentions_clear_soup_and_reservation():
    food = _food(
        raw_terms=["火锅"],
        known_dish_ids=["DISH_HOTPOT"],
        parent_categories=["HOTPOT"],
        retrieval_mode="known_dish",
        child_food_required=True,
        non_spicy_required=True,
    )
    explanation = ExplanationAgent().explain(
        final_plan_contract=_plan(_step("restaurant", "清汤火锅", "poi_hotpot")),
        user_goal={},
        constraints={},
        food_intent=food,
        machine_intent=_machine(["WITH_CHILD", "NON_SPICY_REQUIRED", "AVOID_LONG_QUEUE"]),
        selected_candidates={
            "selected_pois": {
                "restaurant": {
                    "poi_id": "poi_hotpot",
                    "name": "清汤火锅",
                    "category": "restaurant",
                    "menu_features": {"dish_ids": ["DISH_HOTPOT"], "has_non_spicy": True, "has_child_friendly_food": True},
                    "family_features": {"child_food_score": 0.8},
                    "queue_features": {"queue_risk": 0.4},
                }
            }
        },
    )
    text = _text(explanation)

    assert "清汤" in text
    assert "不辣" in text
    assert "预约" in text


def test_long_tail_charcoal_pineapple_explains_attribute_match():
    food = _food(
        raw_terms=["碳烤菠萝"],
        parent_categories=["BBQ", "LONG_TAIL_SNACK"],
        ingredients=["菠萝"],
        cooking_methods=["炭烤", "烧烤"],
        forms=["烤物"],
        retrieval_mode="long_tail_attribute",
    )

    explanation = ExplanationAgent().explain(
        final_plan_contract=_plan(_step("restaurant", "创意烧烤", "poi_bbq")),
        user_goal={},
        constraints={},
        food_intent=food,
        selected_candidates={"selected_pois": {"restaurant": {"poi_id": "poi_bbq", "name": "创意烧烤", "category": "restaurant", "menu_features": {"raw_food_terms": ["碳烤菠萝"], "ingredients": ["菠萝"], "cooking_methods": ["炭烤"], "forms": ["烤物"]}}}},
    )
    text = _text(explanation)

    assert "碳烤菠萝" in text
    assert "菠萝" in text
    assert "炭烤" in text or "烧烤" in text
    assert "长尾" in text


def test_milk_skin_tanghulu_explains_dessert_snack_attributes():
    food = _food(
        raw_terms=["奶皮子糖葫芦"],
        parent_categories=["DESSERT", "SNACK", "LONG_TAIL_SNACK"],
        ingredients=["奶皮子", "糖葫芦"],
        flavors=["奶香", "甜"],
        forms=["糖葫芦", "小吃"],
        scenes=["网红小吃"],
        retrieval_mode="long_tail_attribute",
    )

    explanation = ExplanationAgent().explain(
        final_plan_contract=_plan(_step("restaurant", "甜品小吃", "poi_dessert")),
        user_goal={},
        constraints={},
        food_intent=food,
        selected_candidates={"selected_pois": {"restaurant": {"poi_id": "poi_dessert", "name": "甜品小吃", "category": "restaurant", "menu_features": {"raw_food_terms": ["奶皮子糖葫芦"], "ingredients": ["奶皮子", "糖葫芦"], "forms": ["糖葫芦", "小吃"], "scenes": ["网红小吃"]}}}},
    )
    text = _text(explanation)

    assert "奶皮子糖葫芦" in text
    assert "奶香" in text or "甜" in text
    assert "小吃" in text


def test_stress_relief_explanation_mentions_low_stimulation():
    explanation = ExplanationAgent().explain(
        final_plan_contract=_plan(_step("walk", "金沙湖散步", "poi_walk")),
        user_goal={},
        constraints={},
        machine_intent=_machine(["STRESS_RELIEF", "HEALING", "AVOID_CROWD", "RELAXED_PACE"]),
        selected_candidates={"selected_pois": {"walk": {"poi_id": "poi_walk", "name": "金沙湖散步", "category": "walk_spot", "experience_features": {"relaxation_score": 0.9}}}},
    )
    text = _text(explanation)

    assert "低刺激" in text
    assert "低人流" in text or "低决策成本" in text


class FailingLLM:
    def snapshot(self):
        return {"enabled": True}

    def generate_json(self, **kwargs):
        raise RuntimeError("llm failed")


def test_llm_failure_uses_fallback_explanation():
    explanation = ExplanationAgent(llm_client=FailingLLM()).explain(
        final_plan_contract=_plan(),
        user_goal={},
        constraints={},
        machine_intent=_machine(["AVOID_LONG_QUEUE"]),
    )

    assert explanation.why_this_plan
    assert "排队" in _text(explanation)


class _Logger:
    def log(self, *args, **kwargs):
        return None


def test_response_assembler_adds_optional_projection_and_sanitizes_debug_terms():
    explanation = RecommendationExplanation.fallback(
        why_this_plan=["不要暴露 prompt raw output chain-of-thought API Key debug payload"],
        why_selected=[{"poi_id": "poi_1", "title": "节点", "reason": "基于 mock_api 状态"}],
        addon_suggestions=[{"type": "reservation", "label": "提前预约", "reason": "少排队"}],
    )

    data = ResponseAssembler(_Logger()).assemble("trace_test", _plan(), [], explanation=explanation)
    projection = data["UserVisiblePlanProjection"]
    text = str(projection)

    assert "explanation" in projection
    assert "reason_cards" in projection
    assert "addon_suggestions" in projection
    assert "prompt" not in text
    assert "raw output" not in text
    assert "chain-of-thought" not in text
    assert "API Key" not in text
    assert "debug payload" not in text


def test_response_assembler_uses_taxonomy_display_labels_for_tags():
    step = _step("activity", "亲子手作乐园", "poi_family")
    step["display_tags"] = ["child_friendly", "kid_safe", "mock_api", "unknown_machine", "室内"]

    data = ResponseAssembler(_Logger()).assemble("trace_test", _plan(step), [], explanation=None)
    labels = data["UserVisiblePlanProjection"]["timeline"][0]["display_tags"]

    assert "亲子友好" in labels
    assert "适合孩子" in labels
    assert "室内" in labels
    assert "mock_api" not in labels
    assert "unknown_machine" not in labels
