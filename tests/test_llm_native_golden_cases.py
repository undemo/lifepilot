import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.services.schema_validator import SchemaValidator  # noqa: E402


DEMO_NOW = "2026-05-21T13:30:00+08:00"
FORBIDDEN = ("chain_of_thought", "api_key", "prompt_log", "raw output", "debug payload")


@contextmanager
def _client():
    old_env = {key: os.environ.get(key) for key in ("LIFEPILOT_DEMO_NOW", "QWEN_ENABLED", "DEEPSEEK_ENABLED")}
    os.environ["LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    os.environ["QWEN_ENABLED"] = "false"
    os.environ["DEEPSEEK_ENABLED"] = "false"
    with tempfile.TemporaryDirectory(prefix="lifepilot_phase11_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        shutil.copytree(ROOT / "backend" / "data", data_dir)
        app = create_app(data_dir)
        api = TestClient(app)
        try:
            yield api, app.state.container
        finally:
            api.close()
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _post(api: TestClient, text: str, case_id: str):
    return api.post(
        "/api/v1/plans/create",
        json={
            "input_text": text,
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
            "X-Trace-Id": f"trace_phase11_{case_id}",
            "X-Idempotency-Key": f"idem_phase11_{case_id}",
        },
    )


def _assert_compatible(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    assert payload["success"] is True
    data = payload["data"]
    plan = data["plan_contract"]
    SchemaValidator().validate_plan_contract(plan)
    assert data["plan_id"] == plan["plan_id"]
    projection = data["UserVisiblePlanProjection"]
    assert projection["plan_id"] == plan["plan_id"]
    assert "candidate_plan_ids" in data
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in serialized
    return data, plan, projection


def _intelligence(container: Any, text: str, case_id: str) -> dict[str, Any]:
    trace_id = f"trace_phase11_direct_{case_id}"
    context = {
        "use_memory": False,
        "current_time": DEMO_NOW,
        "user_location": {
            "label": "杭州金沙湖地铁站",
            "area": "金沙湖",
            "lat": 30.309,
            "lng": 120.319,
        },
    }
    user_goal = container.intent_parser.parse(trace_id, text, None)
    extracted = container.constraint_extractor.extract(trace_id, text, user_goal, context, "user_demo_001")
    constraints = extracted["constraints"]
    latent = container.latent_intent_interpreter.interpret(
        raw_user_text=text,
        user_goal=user_goal,
        constraints=constraints,
        recommendation_profile=constraints.get("recommendation_profile") or {},
        dining_preference=constraints.get("dining_preference") or {},
    )
    canonical_tags = [tag.value for tag in latent.canonical_tag_set.canonical_tags]
    food = container.food_semantic_agent.analyze(
        raw_user_text=text,
        constraints=constraints,
        dining_preference=constraints.get("dining_preference") or {},
        recommendation_profile=constraints.get("recommendation_profile") or {},
        canonical_tags=canonical_tags,
    )
    machine = container.retrieval_intent_compiler.compile(
        raw_user_text=text,
        user_goal=user_goal,
        constraints=constraints,
        latent_intent=latent,
        food_intent=food,
    )
    return {
        "user_goal": user_goal,
        "constraints": constraints,
        "latent": latent,
        "canonical_tags": set(canonical_tags),
        "food": food,
        "food_payload": food.to_dict(),
        "machine": machine,
        "machine_payload": machine.to_dict(),
    }


def _run_case(text: str, case_id: str):
    with _client() as (api, container):
        response = _post(api, text, case_id)
        assert response.status_code == 200, response.text
        data, plan, projection = _assert_compatible(response.json())
        intel = _intelligence(container, text, case_id)
        return data, plan, projection, intel


def _projection_text(projection: dict[str, Any]) -> str:
    return json.dumps(projection, ensure_ascii=False)


def _timeline_titles(plan: dict[str, Any]) -> str:
    return " ".join(str(step.get("title") or "") for step in plan.get("timeline") or [])


def test_family_child_crayfish_case_has_child_queue_distance_food_and_addon_explanation():
    text = "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾"
    _data, _plan, projection, intel = _run_case(text, "family_child_crayfish")

    tags = intel["canonical_tags"]
    assert {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "AVOID_LONG_QUEUE", "NEARBY_REQUIRED"} <= tags
    assert tags & {"FOOD_REQUIRED", "MEAL_REQUIRED"}
    food = intel["food_payload"]
    assert "DISH_CRAYFISH" in food["known_dish_ids"]
    assert any("小龙虾" in term for term in food["raw_terms"])

    projection_text = _projection_text(projection)
    assert "不辣" in projection_text
    assert "预约" in projection_text
    assert "湿巾" in projection_text or "饮品" in projection_text


def test_hotpot_child_non_spicy_is_not_crayfish_only():
    _data, _plan, projection, intel = _run_case("想吃火锅，但孩子不能吃辣，别排队", "hotpot_child")

    tags = intel["canonical_tags"]
    assert {"HOTPOT_REQUIRED", "AVOID_LONG_QUEUE"} <= tags
    assert tags & {"WITH_CHILD", "CHILD_FOOD_REQUIRED", "NON_SPICY_REQUIRED"}
    food = intel["food_payload"]
    assert "DISH_HOTPOT" in food["known_dish_ids"]
    assert "DISH_CRAYFISH" not in food["known_dish_ids"]

    projection_text = _projection_text(projection)
    assert "火锅" in projection_text
    assert "不辣" in projection_text or "清汤" in projection_text
    assert "预约" in projection_text


def test_long_tail_charcoal_pineapple_uses_attributes_not_fake_dish_id():
    _data, _plan, projection, intel = _run_case("晚上想吃碳烤菠萝，附近顺便逛逛", "charcoal_pineapple")

    food = intel["food_payload"]
    machine = intel["machine_payload"]
    retrieval_plan = machine["retrieval_plan"]
    assert food["retrieval_mode"] == "long_tail_attribute"
    assert "碳烤菠萝" in food["raw_terms"]
    assert "菠萝" in food["ingredients"]
    assert set(food["cooking_methods"]) & {"炭烤", "烧烤"}
    assert "DISH_CHARCOAL_GRILLED_PINEAPPLE" not in food["known_dish_ids"]
    assert {"raw_term_index", "ingredient_index", "cooking_method_index"} <= set(retrieval_plan.get("indexes") or [])

    projection_text = _projection_text(projection)
    assert "碳烤菠萝" in projection_text
    assert "菠萝" in projection_text
    assert "长尾" in projection_text


def test_long_tail_milk_skin_tanghulu_keeps_raw_terms_and_snack_attributes():
    _data, _plan, projection, intel = _run_case("想吃奶皮子糖葫芦，再找个地方散步", "milk_skin_tanghulu")

    food = intel["food_payload"]
    assert food["retrieval_mode"] == "long_tail_attribute"
    assert "奶皮子糖葫芦" in food["raw_terms"]
    assert set(food["parent_categories"]) & {"DESSERT", "SNACK", "LONG_TAIL_SNACK"}
    assert set(food["ingredients"]) & {"奶皮子", "糖葫芦"}
    assert set(food["forms"]) & {"糖葫芦", "甜品", "小吃"}

    projection_text = _projection_text(projection)
    assert "奶皮子糖葫芦" in projection_text
    assert "长尾" in projection_text


def test_long_tail_rattan_pepper_beef_noodles_keeps_nearby_and_attributes():
    _data, _plan, _projection, intel = _run_case("藤椒牛肉拌面，不想走太远", "rattan_beef_noodles")

    tags = intel["canonical_tags"]
    food = intel["food_payload"]
    assert "NEARBY_REQUIRED" in tags
    assert food["retrieval_mode"] == "long_tail_attribute"
    assert "牛肉" in food["ingredients"]
    assert set(food["flavors"]) & {"藤椒", "麻"}
    assert set(food["forms"]) & {"面", "主食"}


def test_weight_loss_light_walk_prefers_low_calorie_and_relaxed_explanation():
    _data, _plan, projection, intel = _run_case("老婆最近减脂，想吃点清淡的，再安排个轻松的地方走走", "weight_loss_light")

    tags = intel["canonical_tags"]
    food = intel["food_payload"]
    assert {"LOW_CALORIE_REQUIRED", "LIGHT_MEAL_REQUIRED", "RELAXED_PACE"} <= tags
    assert food["low_calorie_required"] is True

    projection_text = _projection_text(projection)
    assert any(term in projection_text for term in ("低脂", "低油", "清淡"))
    assert "轻松" in projection_text or "走走" in projection_text or "散心" in projection_text


def test_stress_relief_case_avoids_high_stimulation_and_explains_low_decision_cost():
    _data, plan, projection, intel = _run_case("我最近学习压力很大，今天下午想出去散散心", "stress_relief")

    assert {"STRESS_RELIEF", "HEALING", "RELAXED_PACE", "AVOID_CROWD"} <= intel["canonical_tags"]
    titles = _timeline_titles(plan)
    assert not any(word in titles for word in ("KTV", "电玩城", "剧本杀"))

    projection_text = _projection_text(projection)
    assert "低刺激" in projection_text
    assert "低决策成本" in projection_text


def test_sports_with_friends_keeps_sports_slot_and_hydration_addon():
    _data, plan, projection, intel = _run_case("这周末和朋友去打个羽毛球，然后你安排", "sports_friends")

    assert {"WITH_FRIENDS", "SPORTS"} <= intel["canonical_tags"]
    machine = intel["machine_payload"]
    assert any(req.get("slot_type") == "activity" and req.get("activity_category") == "sports" for req in machine["slot_requirements"])
    assert "羽毛球" in _timeline_titles(plan)

    projection_text = _projection_text(projection)
    assert "补水" in projection_text or "饮品" in projection_text


def test_conflicting_no_queue_but_hot_shop_records_tradeoff_without_crash():
    _data, _plan, projection, intel = _run_case("不想排队，但想去最火的网红店", "queue_hot_shop_conflict")

    assert "AVOID_LONG_QUEUE" in intel["canonical_tags"]
    projection_text = _projection_text(projection)
    assert "排队" in projection_text
    assert "预约" in projection_text


def test_one_hour_three_places_is_compressed_and_explained():
    _data, plan, projection, intel = _run_case("只有1小时，但想去三个地方", "one_hour_three_places")

    assert "SHORT_DURATION" in intel["canonical_tags"]
    non_transport_steps = [step for step in plan.get("timeline") or [] if step.get("type") != "transport"]
    assert len(non_transport_steps) <= 3

    projection_text = _projection_text(projection)
    assert "短时" in projection_text or "时间窗口较短" in projection_text or "不建议强塞" in projection_text
