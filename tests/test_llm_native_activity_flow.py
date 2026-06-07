import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


DEMO_NOW = "2026-05-21T13:30:00+08:00"


@contextmanager
def _client():
    old_env = {key: os.environ.get(key) for key in ("LIFEPILOT_DEMO_NOW", "QWEN_ENABLED", "DEEPSEEK_ENABLED")}
    os.environ["LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    os.environ["QWEN_ENABLED"] = "false"
    os.environ["DEEPSEEK_ENABLED"] = "false"
    with tempfile.TemporaryDirectory(prefix="lifepilot_activity_flow_") as temp_dir:
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


def _post(api, text, key):
    return api.post(
        "/api/v1/plans/create",
        json={
            "input_text": text,
            "use_memory": False,
            "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        },
        headers={"X-Trace-Id": f"trace_activity_{key}", "X-Idempotency-Key": f"idem_activity_{key}"},
    )


def _timeline_titles(plan):
    return " ".join(step["title"] for step in plan.get("timeline") or [] if step.get("type") != "transport")


def _activity_intel(container, text):
    trace_id = "trace_activity_direct"
    user_goal = container.intent_parser.parse(trace_id, text, None)
    extracted = container.constraint_extractor.extract(
        trace_id,
        text,
        user_goal,
        {"use_memory": False, "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319}},
        "user_demo_001",
    )
    constraints = extracted["constraints"]
    latent = container.latent_intent_interpreter.interpret(
        raw_user_text=text,
        user_goal=user_goal,
        constraints=constraints,
        recommendation_profile=constraints.get("recommendation_profile") or {},
        dining_preference=constraints.get("dining_preference") or {},
    )
    canonical_tags = [tag.value for tag in latent.canonical_tag_set.canonical_tags]
    activity = container.activity_semantic_agent.analyze(
        raw_user_text=text,
        constraints=constraints,
        recommendation_profile=constraints.get("recommendation_profile") or {},
        canonical_tags=canonical_tags,
    )
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
        activity_intent=activity,
    )
    return canonical_tags, activity.to_dict(), food.to_dict(), machine.to_dict()


def test_sibling_badminton_uses_activity_intent_and_selects_badminton():
    with _client() as (api, container):
        text = "这周末和姐姐打羽毛球，然后安排一下"
        response = _post(api, text, "badminton")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan_contract"]
        tags, activity, _food, machine = _activity_intel(container, text)

    assert "WITH_SIBLING" in tags
    assert "ACTIVITY_BADMINTON" in activity["activity_type_ids"]
    assert "SPORTS" in activity["parent_categories"]
    assert machine["retrieval_plan"]["activity_match"]["activity_type_ids"] == ["ACTIVITY_BADMINTON"]
    assert "羽毛球" in _timeline_titles(plan)


def test_roommate_esports_selects_esports_without_child_context():
    with _client() as (api, container):
        text = "今晚和室友去打电竞，然后安排一下"
        response = _post(api, text, "esports")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan_contract"]
        _tags, activity, _food, _machine = _activity_intel(container, text)

    assert "ACTIVITY_ESPORTS" in activity["activity_type_ids"]
    assert {"GAME", "SOCIAL_ENTERTAINMENT"} <= set(activity["parent_categories"])
    assert any(word in _timeline_titles(plan) for word in ("电竞", "网咖"))


def test_friend_scenic_walk_selects_walk_spot_not_generic_mall():
    with _client() as (api, container):
        text = "和朋友去景点逛逛，再吃点东西"
        response = _post(api, text, "scenic_walk")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan_contract"]
        _tags, activity, _food, _machine = _activity_intel(container, text)

    assert set(activity["parent_categories"]) & {"SCENIC", "WALK"}
    titles = _timeline_titles(plan)
    assert any(word in titles for word in ("步道", "湖畔", "观景", "公园"))
    assert "普通商场" not in titles


def test_milk_tea_is_food_intent_not_activity_intent():
    with _client() as (api, container):
        text = "今天下午想喝奶茶"
        response = _post(api, text, "milk_tea")
        assert response.status_code == 200, response.text
        plan = response.json()["data"]["plan_contract"]
        _tags, activity, food, _machine = _activity_intel(container, text)

    assert activity["retrieval_mode"] == "unknown"
    assert "DISH_MILK_TEA" in food["known_dish_ids"]
    assert "奶茶" in _timeline_titles(plan) or "茶姬" in _timeline_titles(plan)


def test_child_esports_and_elderly_football_are_safety_demoted():
    with _client() as (api, _container):
        child = _post(api, "孩子5岁，想出去玩，别太远，想打电竞", "child_esports")
        elder = _post(api, "带爷爷去踢足球，再吃个饭", "elder_football")
        assert child.status_code == 200, child.text
        assert elder.status_code == 200, elder.text
        child_titles = _timeline_titles(child.json()["data"]["plan_contract"])
        elder_titles = _timeline_titles(elder.json()["data"]["plan_contract"])

    assert "电竞" not in child_titles and "网咖" not in child_titles
    assert "足球" not in elder_titles
