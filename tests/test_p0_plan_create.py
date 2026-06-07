import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.rules.recommendation_taxonomy import get_tag_keywords  # noqa: E402


TRACE_ID = "trace_test_20260521_p0"


def tag_keywords(*tags):
    result = []
    for tag in tags:
        for keyword in get_tag_keywords(tag):
            if keyword not in result:
                result.append(keyword)
    return tuple(result)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-21T13:30:00+08:00")
    monkeypatch.setenv("QWEN_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_ENABLED", "false")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    app = create_app(data_dir)
    return TestClient(app)


def headers(key="idem_p0_001"):
    result = {"X-Trace-Id": TRACE_ID}
    if key:
        result["X-Idempotency-Key"] = key
    return result


def create_plan(client, input_text, key, scenario_hint=None):
    body = {"input_text": input_text, "use_memory": False}
    if scenario_hint:
        body["scenario_hint"] = scenario_hint
    response = client.post("/api/v1/plans/create", json=body, headers=headers(key))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    plan = payload["data"]["plan_contract"]
    assert plan["plan_id"].startswith("plan_")
    assert plan["trace_id"] == TRACE_ID
    assert plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
    assert plan["executable_window"]["expire_at"]
    return payload["data"], plan


def test_p0_family_plan_create(client):
    _, plan = create_plan(client, "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。", "idem_p0_family")
    assert plan["user_goal"]["scenario"] == "family_parent_child"
    assert plan["constraints"]["party_size"] == 3
    assert plan["constraints"]["child_friendly_required"] is True
    assert {"low_calorie", "light_food"} & set(plan["constraints"]["dietary_preference"])
    assert plan["backup_plans"]


def test_p0_friend_plan_create_candidates(client):
    data, plan = create_plan(client, "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。", "idem_p0_friend")
    assert plan["user_goal"]["scenario"] == "friend_group"
    assert plan["constraints"]["party_size"] == 4
    assert plan["constraints"]["budget_max_per_person"] == 100.0
    assert len(data["candidate_plan_ids"]) >= 3
    for plan_id in data["candidate_plan_ids"]:
        response = client.get(f"/api/v1/plans/{plan_id}", headers=headers(None))
        assert response.status_code == 200


def test_friend_game_and_cheap_meal_respects_explicit_activity_and_budget(client):
    _, plan = create_plan(client, "周末想和朋友找个地方打游戏,然后吃人均不超过 50 的饭", "idem_friend_game_cheap_meal")

    assert plan["user_goal"]["scenario"] == "friend_group"
    assert "esports" in set(plan["user_goal"]["intent_tags"])
    assert "esports" in set(plan["constraints"]["must_have"])
    assert plan["constraints"]["budget_max_per_person"] == 50.0
    assert plan["constraints"]["budget_is_strict"] is True
    assert plan["budget"]["price_per_person"] <= 50.0

    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert [step["type"] for step in poi_steps] == ["activity", "restaurant"]
    assert any(word in poi_steps[0]["title"] for word in ("电竞", "网咖", "游戏", "电玩"))
    assert not any(word in " ".join(step["title"] for step in poi_steps) for word in ("金沙湖湖畔慢行环线", "日落观景台", "火锅"))
    assert all(int(step.get("duration_minutes") or 0) <= 20 for step in plan["timeline"] if step["type"] == "transport")


def test_friend_game_without_meal_is_afternoon_activity_only(client):
    body = {
        "input_text": "这周末想和朋友去打游戏",
        "use_memory": False,
        "current_time": "2026-06-03T08:00:00+08:00",
        "preferred_duration_hours": 2.5,
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_friend_game_activity_only"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]

    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert [step["type"] for step in poi_steps] == ["activity"]
    assert poi_steps[0]["start_time"].startswith("2026-06-06T14:00:00")
    assert any(word in poi_steps[0]["title"] for word in ("电竞", "网咖", "游戏", "电玩"))
    assert {"esports", "group_ok", "indoor"} & set(poi_steps[0].get("display_tags") or [])
    assert not {"child_friendly", "kid_safe", "family_time"} & set(poi_steps[0].get("display_tags") or [])
    assert plan["budget"]["price_per_person"] < 80


def test_p0_anniversary_plan_create(client):
    _, plan = create_plan(client, "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。", "idem_p0_anniversary")
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert plan["constraints"]["emotion_intensity"] == "light"
    assert plan["messages"].get("partner_note")


def test_anniversary_concrete_backup_and_service_delivery_link(client):
    _, plan = create_plan(client, "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。", "idem_p0_anniversary_agent_realism")
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = next(step for step in poi_steps if step["type"] == "restaurant")
    assert not any(word in restaurant["title"] for word in ("茶姬", "奶茶", "咖啡", "瑞幸", "库迪", "甜品", "蛋糕"))

    restaurant_backup = next((backup for backup in plan["backup_plans"] if backup.get("trigger") == "restaurant_capacity"), None)
    assert restaurant_backup is not None
    assert restaurant_backup["replace_step_id"] == restaurant["step_id"]
    assert restaurant_backup["original_poi_id"] == restaurant["poi_id"]
    assert restaurant_backup["new_poi_id"]
    assert restaurant_backup["expected_diff"]["replacement_poi_name"]
    assert restaurant_backup["expected_diff"]["replacement_poi_name"] in restaurant_backup["description"]

    order_actions = [action for action in plan["tool_actions"] if action["type"] == "order_item"]
    assert order_actions
    service_action = order_actions[0]
    service_step = next(step for step in plan["timeline"] if step["step_id"] == service_action["step_id"])
    delivery_target = service_action["payload"]["delivery_target"]
    assert service_step["order"] < restaurant["order"]
    assert not any(
        step["type"] == "transport" and step.get("to_poi_id") == service_step["poi_id"]
        for step in plan["timeline"]
    )
    assert delivery_target["poi_id"] == restaurant["poi_id"]
    assert delivery_target["step_id"] == restaurant["step_id"]
    assert delivery_target["label"] == restaurant["title"]
    assert delivery_target["deliver_at"] == restaurant["start_time"]


def test_anniversary_default_does_not_overselect_hands_on(client):
    _, plan = create_plan(client, "今晚想给纪念日安排一段轻松一点的约会，不夸张，路线别太折腾。", "idem_anniversary_no_default_craft")
    assert not {"hands_on", "craft"} & set(plan["user_goal"]["intent_tags"])
    primary_titles = " ".join(step["title"] for step in plan["timeline"] if step["type"] in {"activity", "walk"})
    assert not any(word in primary_titles for word in tag_keywords("hands_on"))


def test_p0_solo_mood_relief_plan_create(client):
    _, plan = create_plan(client, "我想下午一个人找个地方散散心。", "idem_p0_solo")
    assert plan["user_goal"]["scenario"] == "fallback_unknown"
    assert plan["constraints"]["party_size"] == 1
    assert {"alone", "mood_relief", "quiet", "nearby", "low_pressure", "light_walk"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert plan["constraints"]["emotion_goal"] == "放松/散心/低压力"
    text = " ".join(step.get("description", "") for step in plan["timeline"])
    assert "低压力" in text or "散心" in text


def test_afternoon_time_window_stable(client):
    _, plan = create_plan(client, "我想下午一个人找个地方散散心。", "idem_p0_time")
    assert "T14:00:00" in plan["time_window"]["start_time"]
    assert "T18:00:00" in plan["time_window"]["end_time"]


def test_current_time_anchor_does_not_force_weekend_afternoon_start(client):
    body = {
        "input_text": "周末下午我想去一个人散散心，顺便喝杯酒。",
        "use_memory": False,
        "current_time": "2026-05-23T18:00:00+08:00",
        "preferred_duration_hours": 4,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_current_anchor_weekend_afternoon"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["time_window"]["start_time"].startswith("2026-05-24T15:00:00")
    assert plan["time_window"]["end_time"].startswith("2026-05-24T19:00:00")
    assert plan["constraints"]["planning_anchor_time"].startswith("2026-05-23T18:00:00")
    assert plan["constraints"]["time_intent"] == "afternoon_window"


def test_mood_relief_jinshahu_stays_near_requested_area(client):
    _, plan = create_plan(client, "我最近很难受，想去金沙湖附近转转。", "idem_p0_jinshahu_mood")
    assert plan["user_goal"]["scenario"] == "fallback_unknown"
    assert {"mood_relief", "nearby", "light_walk"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert "area_jinshahu" in plan["constraints"]["must_have"]
    titles = " ".join(step["title"] for step in plan["timeline"] if step["type"] != "transport")
    assert "高教园区" not in titles


def test_deadline_before_7pm_caps_timeline(client, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-21T17:30:00+08:00")
    _, plan = create_plan(client, "我出去溜一圈，晚上七点之前回来。", "idem_p0_deadline")
    assert plan["time_window"]["end_time"].endswith("T19:00:00+08:00")
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]


def test_solo_breakup_drink_music_deadline_keeps_user_constraints(client):
    _, plan = create_plan(client, "我最近失恋了,想去喝杯酒,然后再去逛一些有音乐的地方.在十点钟准时回家", "idem_p0_breakup_drink_music")
    assert plan["user_goal"]["scenario"] == "fallback_unknown"
    assert plan["constraints"]["party_size"] == 1
    assert plan["time_window"]["end_time"].endswith("T22:00:00+08:00")
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]
    assert {"alcohol", "music", "mood_relief"}.issubset(set(plan["user_goal"]["intent_tags"]))
    first_poi = next(step for step in plan["timeline"] if step["type"] != "transport")
    assert first_poi["type"] == "restaurant"
    visible = " ".join(
        item
        for step in plan["timeline"]
        for item in [step.get("title", ""), " ".join(step.get("display_tags") or [])]
    )
    assert "清吧" in visible or "alcohol" in visible
    assert "音乐" in visible or "music" in visible


def test_benchmark_solo_unhappy_drink_recommends_bar_not_chess_or_coffee_first(client):
    body = {
        "input_text": "我今天有点不开心,想找个地方喝点酒,晚上十点之前到家",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-21T18:00:00+08:00",
        "preferred_end_time": "2026-05-21T22:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_benchmark_solo_drink"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert poi_steps
    first = poi_steps[0]
    assert "alcohol" in set(first.get("display_tags") or []) or "酒" in first["title"]
    first_text = first["title"] + " " + " ".join(first.get("display_tags") or [])
    assert "棋牌" not in first_text
    assert "咖啡" not in first_text
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]


def test_benchmark_anniversary_avoids_fast_food_and_repeated_square(client):
    body = {
        "input_text": "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-21T18:00:00+08:00",
        "preferred_end_time": "2026-05-21T22:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_benchmark_anniversary"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    titles = [step["title"] for step in plan["timeline"] if step["type"] != "transport"]
    visible = " ".join(titles)
    assert len(titles) == len(set(titles))
    assert "米村" not in visible
    assert "福雷德广场" not in visible
    assert not any(word in visible for word in ("棋牌", "麦当劳", "肯德基", "德克士", "老乡鸡"))
    assert plan["budget"]["estimated_total"] <= 430


def test_anniversary_explicit_long_window_generates_multi_stop_itinerary(client, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-23T09:00:00+08:00")
    body = {
        "input_text": "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。安排4-5个活动。下午一点出发，晚上十点钟回来",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "current_time": "2026-05-23T09:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_anniversary_long_multi_stop"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert plan["time_window"]["start_time"].startswith("2026-05-23T13:00:00")
    assert plan["time_window"]["end_time"].startswith("2026-05-23T22:00:00")
    assert plan["constraints"]["target_stop_count_range"] == [4, 5]
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert 4 <= len(poi_steps) <= 5
    assert poi_steps[0]["start_time"].startswith("2026-05-23T13:00:00")
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]
    assert len({step["poi_id"] for step in poi_steps}) == len(poi_steps)
    restaurant = next(step for step in poi_steps if step["type"] == "restaurant")
    service = next((step for step in poi_steps if step["type"] == "service"), None)
    assert restaurant["start_time"] >= "2026-05-23T17:30:00+08:00"
    if service:
        assert service["order"] < restaurant["order"]
        assert not any(
            step["type"] == "transport" and step.get("to_poi_id") == service["poi_id"]
            for step in plan["timeline"]
        )
    assert plan["budget"]["price_per_person"] <= plan["constraints"]["budget_max_per_person"]
    assert plan["verifier_result"]["status"] == "pass"


def test_anniversary_explicit_five_activities_without_exact_clock_keeps_count(client, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-23T09:00:00+08:00")
    body = {
        "input_text": "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。要安排五个活动",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "current_time": "2026-05-23T09:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_anniversary_exact_five_evening"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["time_window"]["start_time"].startswith("2026-05-23T17:00:00")
    assert plan["time_window"]["end_time"].startswith("2026-05-23T22:00:00")
    assert plan["time_window"]["time_intent"] == "evening_window"
    assert plan["constraints"]["target_stop_count"] == 5
    assert plan["constraints"]["target_stop_count_range"] == [5, 5]
    assert plan["constraints"]["target_stop_count_source"] == "explicit"
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert len(poi_steps) == 5
    handcraft_count = sum(
        1
        for step in poi_steps
        if step["type"] == "activity" and any(word in step["title"] for word in tag_keywords("hands_on"))
    )
    assert handcraft_count <= 1
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]
    assert plan["verifier_result"]["status"] == "pass"


def test_recommendation_date_handcraft_beautiful_meal(client):
    body = {
        "input_text": "我周末想和女朋友去做手工,顺便安排一顿漂亮饭",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T14:00:00+08:00",
        "preferred_end_time": "2026-05-24T21:30:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_handcraft"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert {"hands_on", "craft", "beautiful_dining"} & set(plan["user_goal"]["intent_tags"])
    titles = " ".join(step["title"] for step in plan["timeline"] if step["type"] != "transport")
    assert any(word in titles for word in tag_keywords("hands_on"))
    assert not any(word in titles for word in ("萨莉亚", "米村", "麦当劳", "肯德基", "德克士", "老乡鸡", "古茗", "蜜雪"))
    restaurant = next(step for step in plan["timeline"] if step["type"] == "restaurant")
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in ("餐厅", "料理", "湖畔", "茶空间", "quality_dining", "ambience_dining", "proper_dining"))


def test_recommendation_sister_visiting_xiasha_is_host_guest_plan(client):
    body = {
        "input_text": "这周末我姐要来下沙找我玩,帮我安排一下行程",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T13:30:00+08:00",
        "preferred_end_time": "2026-05-24T21:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_sister_visit"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "city_light_explore"
    assert plan["constraints"]["party_size"] == 2
    assert plan["constraints"]["preferred_area"] == "下沙"
    assert {"host_guest", "visitor_friendly", "showcase_local"} & set(plan["user_goal"]["intent_tags"])
    assert any(step["type"] == "restaurant" for step in plan["timeline"])
    titles = " ".join(step["title"] for step in plan["timeline"] if step["type"] != "transport")
    assert not any(word in titles for word in ("棋牌", "KTV", "电竞", "健身", "麦当劳", "肯德基", "德克士", "萨莉亚", "蜜雪", "古茗"))
    assert max(step["end_time"] for step in plan["timeline"]) <= plan["time_window"]["end_time"]


def test_recommendation_family_light_dinner_avoids_esports_and_puts_dinner_last(client):
    body = {
        "input_text": "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。",
        "scenario_hint": "family_parent_child",
        "generate_candidates": False,
        "use_memory": True,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "current_time": "2026-05-25T08:00:00+08:00",
        "preferred_duration_hours": 4,
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_family_light_dinner"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "family_parent_child"
    assert "亲子" in plan["user_goal"]["goal_summary"]
    assert "用餐计划" not in plan["user_goal"]["goal_summary"]
    assert {"light_meal", "low_queue", "child_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"light_food", "light_meal"} & set(plan["constraints"]["dietary_preference"])
    assert plan["constraints"]["target_stop_count"] >= 3
    assert plan["constraints"]["target_stop_count_source"] == "time_inferred"
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert len(poi_steps) >= 2
    assert poi_steps[-1]["type"] == "restaurant"
    assert poi_steps[-1]["start_time"] >= "2026-05-21T17:00:00+08:00"
    titles = " ".join(step["title"] for step in poi_steps)
    assert any(word in titles for word in tag_keywords("child_friendly", "kid_safe", "family_time", "hands_on", "amusement"))
    assert not any(word in titles for word in tag_keywords("low_fit_activity", "alcohol", "spicy_heavy"))
    dinner_text = poi_steps[-1]["title"] + " " + " ".join(poi_steps[-1].get("display_tags") or [])
    assert "light_meal" in dinner_text or "light_food" in dinner_text or any(word in dinner_text for word in tag_keywords("light_meal", "light_food"))


def test_family_child_burger_request_does_not_turn_restaurants_into_service_chain(client):
    body = {
        "input_text": "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。孩子想吃汉堡.",
        "scenario_hint": "family_parent_child",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "current_time": "2026-05-25T08:00:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_family_burger"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]

    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    assert poi_steps[0]["type"] == "activity"
    assert poi_steps[-1]["type"] == "restaurant"
    assert [step["type"] for step in poi_steps].count("restaurant") == 1
    assert not any(step["type"] == "service" for step in poi_steps)
    assert not any(action["type"] == "order_item" for action in plan["tool_actions"])

    dining_preference = plan["constraints"]["dining_preference"]
    assert dining_preference["raw_match_available"] is True
    assert "汉堡" in dining_preference["raw_terms"]
    restaurant_text = poi_steps[-1]["title"] + " " + " ".join(poi_steps[-1].get("display_tags") or [])
    assert any(word in restaurant_text for word in ("汉堡", "麦当劳", "肯德基", "德克士", "塔斯汀"))
    assert "提前" not in " ".join(step["description"] for step in poi_steps)


def test_recommendation_date_relax_hotpot_keeps_hotpot_as_dinner(client):
    body = {
        "input_text": "周末想和女朋友出去放松一下,下午活动你来安排,但晚上我们想去吃火锅",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_hotpot"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert {"hotpot", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"hotpot", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = poi_steps[-1]
    assert restaurant["type"] == "restaurant"
    assert restaurant["start_time"] >= "2026-05-21T17:00:00+08:00"
    assert any(word in restaurant["title"] for word in tag_keywords("hotpot")) or "hotpot" in set(restaurant.get("display_tags") or [])
    titles = " ".join(step["title"] for step in poi_steps)
    assert not any(word in titles for word in (*tag_keywords("low_fit_activity"), "篮球馆"))


def test_recommendation_date_relax_bbq_keeps_grill_as_dinner(client):
    body = {
        "input_text": "周末想和女朋友出去放松一下,下午活动你来安排,但晚上我们想去吃烤肉",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_bbq"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert {"bbq", "grill", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"bbq", "grill", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = poi_steps[-1]
    assert restaurant["type"] == "restaurant"
    assert restaurant["start_time"] >= "2026-05-21T17:00:00+08:00"
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in (*tag_keywords("bbq", "grill"), "bbq", "grill"))
    titles = " ".join(step["title"] for step in poi_steps)
    assert not any(word in titles for word in (*tag_keywords("low_fit_activity"), "篮球馆"))


def test_recommendation_open_dining_lamb_chop_does_not_fall_back_to_generic_date_plan(client):
    body = {
        "input_text": "这周末想和女朋友吃烤羊排",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_lamb_chop"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert {"lamb", "bbq", "grill", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"lamb", "bbq", "grill", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    assert plan["constraints"]["dining_preference"]["explicit"] is True
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = poi_steps[-1]
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert restaurant["type"] == "restaurant"
    assert restaurant["start_time"] >= "2026-05-21T17:00:00+08:00"
    assert any(word in restaurant_text for word in (*tag_keywords("lamb", "bbq", "grill"), "lamb", "bbq", "grill"))
    assert not any(word in restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
    activity_titles = " ".join(step["title"] for step in poi_steps[:-1])
    assert "蕉个朋友DIY手工" not in activity_titles


def test_recommendation_open_dining_western_cuisine_aligns_to_restaurant(client):
    body = {
        "input_text": "这周末想和女朋友吃西餐",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_western"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert {"western_cuisine", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"western_cuisine", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    restaurant = [step for step in plan["timeline"] if step["type"] != "transport"][-1]
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in (*tag_keywords("western_cuisine", "steak"), "western_cuisine", "steak"))
    assert not any(word in restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))


def test_recommendation_date_diet_prefers_light_restaurant_not_cafe(client):
    body = {
        "input_text": "这周末女朋友想减脂,帮我安排晚饭",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_diet"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert {"light_meal", "light_food", "healthy_light", "dinner"}.issubset(set(plan["user_goal"]["intent_tags"]))
    restaurant = [step for step in plan["timeline"] if step["type"] != "transport"][-1]
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in (*tag_keywords("light_meal", "light_food", "healthy_light"), "light_meal", "light_food", "healthy_light"))
    assert not any(word in restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪", *tag_keywords("spicy_heavy")))


def test_recommendation_date_light_meal_defaults_to_dinner_window(client):
    body = {
        "input_text": "这周末想和女朋友吃点清淡的",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_light_meal"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert {"light_meal", "light_food", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = poi_steps[-1]
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert restaurant["type"] == "restaurant"
    assert restaurant["start_time"] >= "2026-05-21T17:00:00+08:00"
    assert any(word in restaurant_text for word in (*tag_keywords("light_meal", "light_food"), "light_meal", "light_food"))
    assert not any(word in restaurant_text for word in tag_keywords("spicy_heavy"))


def test_recommendation_date_japanese_cuisine_aligns_to_poi_semantics(client):
    body = {
        "input_text": "周末想和女朋友出去放松一下,晚上想吃日料",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T14:00:00+08:00",
        "preferred_end_time": "2026-05-24T21:30:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recommendation_date_japanese"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert plan["user_goal"]["scenario"] == "anniversary_emotion"
    assert {"cuisine_japanese", "dinner", "date_friendly"}.issubset(set(plan["user_goal"]["intent_tags"]))
    assert {"cuisine_japanese", "dinner"}.issubset(set(plan["constraints"]["must_have"]))
    poi_steps = [step for step in plan["timeline"] if step["type"] != "transport"]
    restaurant = poi_steps[-1]
    assert restaurant["type"] == "restaurant"
    assert restaurant["start_time"] >= "2026-05-24T17:00:00+08:00"
    restaurant_text = restaurant["title"] + " " + " ".join(restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in (*tag_keywords("cuisine_japanese", "sushi", "izakaya"), "cuisine_japanese", "sushi", "izakaya"))
    assert not any(word in restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
    assert not any(
        check["name"] == "weather_risk" and check["status"] == "fail"
        for check in plan["verifier_result"]["checks"]
    )


def test_recovery_uses_relation_edges_for_restaurant_replacement(client):
    body = {
        "input_text": "周末想和女朋友出去放松一下,晚上想吃日料",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T14:00:00+08:00",
        "preferred_end_time": "2026-05-24T21:30:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recovery_relation_plan"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    restaurant = [step for step in plan["timeline"] if step["type"] != "transport"][-1]
    recovery = client.post(
        f"/api/v1/plans/{plan['plan_id']}/recover",
        json={"trigger": "NO_TABLE_AVAILABLE", "failed_step_id": restaurant["step_id"], "recovery_strategy": "replace_restaurant_same_area", "auto_verify": True},
        headers=headers("idem_recovery_relation"),
    )
    assert recovery.status_code == 200, recovery.text
    data = recovery.json()["data"]
    recovery_result = data["recovery_result"]
    assert recovery_result["replacement"]["source"] == "poi_relation_edge"
    assert recovery_result["replacement"]["relation"] == "substitute"
    assert data["updated_plan_contract"] is not None
    updated_restaurant = [step for step in data["updated_plan_contract"]["timeline"] if step["type"] != "transport"][-1]
    assert updated_restaurant["poi_id"] != restaurant["poi_id"]
    restaurant_text = updated_restaurant["title"] + " " + " ".join(updated_restaurant.get("display_tags") or [])
    assert any(word in restaurant_text for word in (*tag_keywords("cuisine_japanese", "sushi", "izakaya"), "cuisine_japanese", "sushi", "izakaya"))
    assert not any(word in restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
    assert any(
        check["name"] == "restaurant_capacity" and check["related_poi_id"] == updated_restaurant["poi_id"] and check["status"] == "pass"
        for check in data["updated_plan_contract"]["verifier_result"]["checks"]
    )


def test_recovery_does_not_replace_buffet_with_fast_food(client):
    body = {
        "input_text": "这周末想和老婆孩子去游乐园,然后吃一顿自助餐",
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T14:00:00+08:00",
        "preferred_end_time": "2026-05-24T21:30:00+08:00",
    }
    response = client.post("/api/v1/plans/create", json=body, headers=headers("idem_recovery_buffet_plan"))
    assert response.status_code == 200, response.text
    plan = response.json()["data"]["plan_contract"]
    assert "buffet" in set(plan["constraints"]["must_have"])
    restaurant = [step for step in plan["timeline"] if step["type"] != "transport"][-1]
    recovery = client.post(
        f"/api/v1/plans/{plan['plan_id']}/recover",
        json={"trigger": "NO_TABLE_AVAILABLE", "failed_step_id": restaurant["step_id"], "recovery_strategy": "replace_restaurant_same_area", "auto_verify": True},
        headers=headers("idem_recovery_buffet"),
    )
    assert recovery.status_code == 200, recovery.text
    recovery_result = recovery.json()["data"]["recovery_result"]
    replacement = recovery_result["replacement"]
    wrong_food_terms = ("肯德基", "包子", "面馆", "馄饨", "饺子", "茶空间", "咖啡", "甜品", "CHAGEE", "瑞幸", "M Stand")
    if replacement.get("available") is False:
        assert "poi_name" not in replacement
        assert replacement["failure_reason_code"] in {
            "no_same_semantic_restaurant_available",
            "same_semantic_restaurant_capacity_or_queue_failed",
            "same_semantic_restaurant_no_capacity",
            "same_semantic_restaurant_queue_exceeded",
        }
        assert replacement["failure_reasons"][0]["message"]
        assert recovery_result["diff"]["recovery_diagnostics"]["candidate_summary"]["required_semantic_tags"] == ["buffet"]
    else:
        replacement_text = str(replacement.get("poi_name") or "")
        assert any(word in replacement_text for word in (*tag_keywords("buffet"), "自助"))
        assert not any(word in replacement_text for word in wrong_food_terms)


def test_execute_requires_idempotency_key(client):
    _, plan = create_plan(client, "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。", "idem_p0_exec_plan")
    response = client.post(f"/api/v1/plans/{plan['plan_id']}/execute", json={"confirmed": True}, headers=headers(None))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_plan_contract_schema_pass(client):
    _, plan = create_plan(client, "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。", "idem_p0_schema")
    client.app.state.container.schema_validator.validate_plan_contract(plan)


def test_recovery_versioned(client):
    _, plan = create_plan(client, "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。", "idem_p0_recovery_plan")
    response = client.post(
        f"/api/v1/plans/{plan['plan_id']}/recover",
        json={"trigger": "PLAN_EXECUTABLE_WINDOW_EXPIRED", "recovery_strategy": "refresh_window", "auto_verify": True},
        headers=headers("idem_p0_recovery"),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["updated_plan_id"] != plan["plan_id"]
    assert data["updated_plan_contract"]["plan_id"] == data["updated_plan_id"]


def test_llm_settings_masks_credentials(client):
    response = client.get("/api/v1/settings/llm", headers=headers(None))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "deepseek"
    assert "api_key" not in data
    assert data["credential_configured"] is False
    assert data["credential_mask"] == ""

    updated = client.patch(
        "/api/v1/settings/llm",
        json={"provider": "qwen", "base_url": "http://127.0.0.1:8000/v1", "model": "qwen-local", "credential": "local-secret"},
        headers=headers("idem_llm_settings"),
    )
    assert updated.status_code == 200
    payload = updated.json()["data"]
    assert payload["provider"] == "qwen"
    assert payload["credential_mask"] == "loc***cret"
    assert "local-secret" not in str(payload)
