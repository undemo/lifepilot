from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.rules.recommendation_taxonomy import get_tag_keywords  # noqa: E402


SAMPLES = {
    "test_p0_family_plan_create": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
    "test_p0_friend_plan_create_candidates": "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。",
    "test_p0_anniversary_plan_create": "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。",
    "test_p0_solo_mood_relief_plan_create": "我想下午一个人找个地方散散心。",
    "test_recommendation_date_handcraft_beautiful_meal": "我周末想和女朋友去做手工,顺便安排一顿漂亮饭",
    "test_recommendation_sister_visiting_xiasha": "这周末我姐要来下沙找我玩,帮我安排一下行程",
    "test_recommendation_family_light_dinner": "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。",
    "test_recommendation_date_hotpot": "周末想和女朋友出去放松一下,下午活动你来安排,但晚上我们想去吃火锅",
    "test_recommendation_date_bbq": "周末想和女朋友出去放松一下,下午活动你来安排,但晚上我们想去吃烤肉",
    "test_recommendation_date_lamb_chop": "这周末想和女朋友吃烤羊排",
    "test_recommendation_date_western": "这周末想和女朋友吃西餐",
    "test_recommendation_date_diet": "这周末女朋友想减脂,帮我安排晚饭",
    "test_recommendation_date_light_meal": "这周末想和女朋友吃点清淡的",
    "test_recommendation_date_japanese": "周末想和女朋友出去放松一下,晚上想吃日料",
}


def tag_keywords(*tags: str) -> tuple[str, ...]:
    result: list[str] = []
    for tag in tags:
        for keyword in get_tag_keywords(tag):
            if keyword not in result:
                result.append(keyword)
    return tuple(result)


def client() -> TestClient:
    os.environ.setdefault("LIFEPILOT_DEMO_NOW", "2026-05-21T13:30:00+08:00")
    os.environ.setdefault("DEEPSEEK_ENABLED", "false")
    os.environ.setdefault("QWEN_ENABLED", "false")
    data_dir = Path(tempfile.mkdtemp(prefix="lifepilot_p0_")) / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    return TestClient(create_app(data_dir))


def headers(key: str | None = None) -> dict[str, str]:
    result = {"X-Trace-Id": "trace_test_20260521_p0_runner"}
    if key:
        result["X-Idempotency-Key"] = key
    return result


def create_plan(api: TestClient, name: str, input_text: str) -> dict:
    response = api.post("/api/v1/plans/create", json={"input_text": input_text, "use_memory": False}, headers=headers(f"idem_{name}"))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    plan = data["plan_contract"]
    assert plan["plan_id"].startswith("plan_")
    assert plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
    assert plan["executable_window"]["expire_at"]
    return data


def main() -> int:
    api = client()
    results: list[dict] = []
    plans: dict[str, dict] = {}
    try:
        family = create_plan(api, "family", SAMPLES["test_p0_family_plan_create"])["plan_contract"]
        assert family["user_goal"]["scenario"] == "family_parent_child"
        assert family["constraints"]["party_size"] == 3
        assert family["constraints"]["child_friendly_required"] is True
        results.append({"name": "test_p0_family_plan_create", "passed": True})

        friend_data = create_plan(api, "friend", SAMPLES["test_p0_friend_plan_create_candidates"])
        friend = friend_data["plan_contract"]
        assert friend["user_goal"]["scenario"] == "friend_group"
        assert friend["constraints"]["party_size"] == 4
        assert len(friend_data["candidate_plan_ids"]) >= 3
        results.append({"name": "test_p0_friend_plan_create_candidates", "passed": True})

        anniversary = create_plan(api, "anniversary", SAMPLES["test_p0_anniversary_plan_create"])["plan_contract"]
        assert anniversary["user_goal"]["scenario"] == "anniversary_emotion"
        assert anniversary["constraints"]["emotion_intensity"] == "light"
        results.append({"name": "test_p0_anniversary_plan_create", "passed": True})

        solo = create_plan(api, "solo", SAMPLES["test_p0_solo_mood_relief_plan_create"])["plan_contract"]
        assert solo["user_goal"]["scenario"] == "fallback_unknown"
        assert solo["constraints"]["party_size"] == 1
        assert {"alone", "mood_relief", "quiet", "nearby", "low_pressure", "light_walk"}.issubset(set(solo["user_goal"]["intent_tags"]))
        results.append({"name": "test_p0_solo_mood_relief_plan_create", "passed": True})

        drink_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": "我今天有点不开心,想找个地方喝点酒,晚上十点之前到家",
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
                "preferred_start_time": "2026-05-21T18:00:00+08:00",
                "preferred_end_time": "2026-05-21T22:00:00+08:00",
            },
            headers=headers("idem_recommendation_drink_runner"),
        )
        assert drink_data.status_code == 200, drink_data.text
        drink = drink_data.json()["data"]["plan_contract"]
        first_poi = next(step for step in drink["timeline"] if step["type"] != "transport")
        assert "alcohol" in set(first_poi.get("display_tags") or []) or "酒" in first_poi["title"]
        assert "棋牌" not in first_poi["title"] and "咖啡" not in first_poi["title"]
        results.append({"name": "test_recommendation_solo_unhappy_drink", "passed": True})

        date_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_handcraft_beautiful_meal"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
                "preferred_start_time": "2026-05-24T14:00:00+08:00",
                "preferred_end_time": "2026-05-24T21:30:00+08:00",
            },
            headers=headers("idem_recommendation_date_runner"),
        )
        assert date_data.status_code == 200, date_data.text
        date_plan = date_data.json()["data"]["plan_contract"]
        assert date_plan["user_goal"]["scenario"] == "anniversary_emotion"
        date_titles = " ".join(step["title"] for step in date_plan["timeline"] if step["type"] != "transport")
        assert any(word in date_titles for word in tag_keywords("hands_on"))
        assert not any(word in date_titles for word in ("萨莉亚", "米村", "麦当劳", "肯德基", "德克士", "老乡鸡", "古茗", "蜜雪"))
        results.append({"name": "test_recommendation_date_handcraft_beautiful_meal", "passed": True})

        sister_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_sister_visiting_xiasha"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
                "preferred_start_time": "2026-05-24T13:30:00+08:00",
                "preferred_end_time": "2026-05-24T21:00:00+08:00",
            },
            headers=headers("idem_recommendation_sister_runner"),
        )
        assert sister_data.status_code == 200, sister_data.text
        sister = sister_data.json()["data"]["plan_contract"]
        assert sister["user_goal"]["scenario"] == "city_light_explore"
        assert sister["constraints"]["party_size"] == 2
        assert any(step["type"] == "restaurant" for step in sister["timeline"])
        sister_titles = " ".join(step["title"] for step in sister["timeline"] if step["type"] != "transport")
        assert not any(word in sister_titles for word in ("棋牌", "KTV", "电竞", "健身", "麦当劳", "肯德基", "德克士", "萨莉亚", "蜜雪", "古茗"))
        results.append({"name": "test_recommendation_sister_visiting_xiasha", "passed": True})

        family_light_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_family_light_dinner"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_family_light_runner"),
        )
        assert family_light_data.status_code == 200, family_light_data.text
        family_light = family_light_data.json()["data"]["plan_contract"]
        family_light_steps = [step for step in family_light["timeline"] if step["type"] != "transport"]
        family_light_titles = " ".join(step["title"] for step in family_light_steps)
        assert family_light["user_goal"]["scenario"] == "family_parent_child"
        assert {"light_meal", "low_queue", "child_friendly"}.issubset(set(family_light["user_goal"]["intent_tags"]))
        assert family_light_steps[-1]["type"] == "restaurant"
        assert "T17:" in family_light_steps[-1]["start_time"] or "T18:" in family_light_steps[-1]["start_time"]
        assert any(word in family_light_titles for word in tag_keywords("child_friendly", "kid_safe", "family_time", "hands_on", "amusement"))
        assert not any(word in family_light_titles for word in tag_keywords("low_fit_activity", "alcohol", "spicy_heavy"))
        results.append({"name": "test_recommendation_family_light_dinner", "passed": True})

        hotpot_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_hotpot"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_hotpot_runner"),
        )
        assert hotpot_data.status_code == 200, hotpot_data.text
        hotpot = hotpot_data.json()["data"]["plan_contract"]
        hotpot_steps = [step for step in hotpot["timeline"] if step["type"] != "transport"]
        hotpot_titles = " ".join(step["title"] for step in hotpot_steps)
        assert hotpot["user_goal"]["scenario"] == "anniversary_emotion"
        assert {"hotpot", "dinner", "date_friendly"}.issubset(set(hotpot["user_goal"]["intent_tags"]))
        assert hotpot_steps[-1]["type"] == "restaurant"
        assert any(word in hotpot_steps[-1]["title"] for word in tag_keywords("hotpot")) or "hotpot" in set(hotpot_steps[-1].get("display_tags") or [])
        assert "T17:" in hotpot_steps[-1]["start_time"] or "T18:" in hotpot_steps[-1]["start_time"]
        assert not any(word in hotpot_titles for word in (*tag_keywords("low_fit_activity"), "篮球馆"))
        results.append({"name": "test_recommendation_date_hotpot", "passed": True})

        bbq_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_bbq"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_bbq_runner"),
        )
        assert bbq_data.status_code == 200, bbq_data.text
        bbq = bbq_data.json()["data"]["plan_contract"]
        bbq_steps = [step for step in bbq["timeline"] if step["type"] != "transport"]
        bbq_titles = " ".join(step["title"] for step in bbq_steps)
        bbq_restaurant_text = bbq_steps[-1]["title"] + " " + " ".join(bbq_steps[-1].get("display_tags") or [])
        assert bbq["user_goal"]["scenario"] == "anniversary_emotion"
        assert {"bbq", "grill", "dinner", "date_friendly"}.issubset(set(bbq["user_goal"]["intent_tags"]))
        assert bbq_steps[-1]["type"] == "restaurant"
        assert any(word in bbq_restaurant_text for word in (*tag_keywords("bbq", "grill"), "bbq", "grill"))
        assert "T17:" in bbq_steps[-1]["start_time"] or "T18:" in bbq_steps[-1]["start_time"]
        assert not any(word in bbq_titles for word in (*tag_keywords("low_fit_activity"), "篮球馆"))
        results.append({"name": "test_recommendation_date_bbq", "passed": True})

        lamb_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_lamb_chop"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_lamb_runner"),
        )
        assert lamb_data.status_code == 200, lamb_data.text
        lamb = lamb_data.json()["data"]["plan_contract"]
        lamb_steps = [step for step in lamb["timeline"] if step["type"] != "transport"]
        lamb_restaurant_text = lamb_steps[-1]["title"] + " " + " ".join(lamb_steps[-1].get("display_tags") or [])
        assert {"lamb", "bbq", "grill", "dinner", "date_friendly"}.issubset(set(lamb["user_goal"]["intent_tags"]))
        assert any(word in lamb_restaurant_text for word in (*tag_keywords("lamb", "bbq", "grill"), "lamb", "bbq", "grill"))
        assert not any(word in lamb_restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
        assert "蕉个朋友DIY手工" not in " ".join(step["title"] for step in lamb_steps[:-1])
        results.append({"name": "test_recommendation_date_lamb_chop", "passed": True})

        western_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_western"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_western_runner"),
        )
        assert western_data.status_code == 200, western_data.text
        western = western_data.json()["data"]["plan_contract"]
        western_restaurant_text = [step for step in western["timeline"] if step["type"] != "transport"][-1]["title"] + " " + " ".join([step for step in western["timeline"] if step["type"] != "transport"][-1].get("display_tags") or [])
        assert {"western_cuisine", "dinner", "date_friendly"}.issubset(set(western["user_goal"]["intent_tags"]))
        assert any(word in western_restaurant_text for word in (*tag_keywords("western_cuisine", "steak"), "western_cuisine", "steak"))
        assert not any(word in western_restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
        results.append({"name": "test_recommendation_date_western", "passed": True})

        diet_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_diet"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_diet_runner"),
        )
        assert diet_data.status_code == 200, diet_data.text
        diet = diet_data.json()["data"]["plan_contract"]
        diet_restaurant_text = [step for step in diet["timeline"] if step["type"] != "transport"][-1]["title"] + " " + " ".join([step for step in diet["timeline"] if step["type"] != "transport"][-1].get("display_tags") or [])
        assert {"light_meal", "light_food", "healthy_light", "dinner"}.issubset(set(diet["user_goal"]["intent_tags"]))
        assert any(word in diet_restaurant_text for word in (*tag_keywords("light_meal", "light_food", "healthy_light"), "light_meal", "light_food", "healthy_light"))
        assert not any(word in diet_restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪", *tag_keywords("spicy_heavy")))
        results.append({"name": "test_recommendation_date_diet", "passed": True})

        light_meal_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_light_meal"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_recommendation_light_meal_runner"),
        )
        assert light_meal_data.status_code == 200, light_meal_data.text
        light_meal = light_meal_data.json()["data"]["plan_contract"]
        light_meal_steps = [step for step in light_meal["timeline"] if step["type"] != "transport"]
        light_meal_restaurant_text = light_meal_steps[-1]["title"] + " " + " ".join(light_meal_steps[-1].get("display_tags") or [])
        assert {"light_meal", "light_food", "dinner", "date_friendly"}.issubset(set(light_meal["user_goal"]["intent_tags"]))
        assert "T17:" in light_meal_steps[-1]["start_time"] or "T18:" in light_meal_steps[-1]["start_time"]
        assert any(word in light_meal_restaurant_text for word in (*tag_keywords("light_meal", "light_food"), "light_meal", "light_food"))
        assert not any(word in light_meal_restaurant_text for word in tag_keywords("spicy_heavy"))
        results.append({"name": "test_recommendation_date_light_meal", "passed": True})

        japanese_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": SAMPLES["test_recommendation_date_japanese"],
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
                "preferred_start_time": "2026-05-24T14:00:00+08:00",
                "preferred_end_time": "2026-05-24T21:30:00+08:00",
            },
            headers=headers("idem_recommendation_japanese_runner"),
        )
        assert japanese_data.status_code == 200, japanese_data.text
        japanese = japanese_data.json()["data"]["plan_contract"]
        japanese_steps = [step for step in japanese["timeline"] if step["type"] != "transport"]
        japanese_restaurant_text = japanese_steps[-1]["title"] + " " + " ".join(japanese_steps[-1].get("display_tags") or [])
        assert japanese["user_goal"]["scenario"] == "anniversary_emotion"
        assert {"cuisine_japanese", "dinner", "date_friendly"}.issubset(set(japanese["user_goal"]["intent_tags"]))
        assert japanese_steps[-1]["type"] == "restaurant"
        assert any(word in japanese_restaurant_text for word in (*tag_keywords("cuisine_japanese", "sushi", "izakaya"), "cuisine_japanese", "sushi", "izakaya"))
        assert not any(word in japanese_restaurant_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
        results.append({"name": "test_recommendation_date_japanese", "passed": True})
        assert not any(
            check["name"] == "weather_risk" and check["status"] == "fail"
            for check in japanese["verifier_result"]["checks"]
        )
        results.append({"name": "test_recommendation_date_japanese_avoids_weather_failed_walk", "passed": True})

        recovery_relation = api.post(
            f"/api/v1/plans/{japanese['plan_id']}/recover",
            json={
                "trigger": "NO_TABLE_AVAILABLE",
                "failed_step_id": japanese_steps[-1]["step_id"],
                "recovery_strategy": "replace_restaurant_same_area",
                "auto_verify": True,
            },
            headers=headers("idem_recovery_relation_runner"),
        )
        assert recovery_relation.status_code == 200, recovery_relation.text
        recovery_relation_data = recovery_relation.json()["data"]
        recovery_relation_result = recovery_relation_data["recovery_result"]
        assert recovery_relation_result["replacement"]["source"] == "poi_relation_edge"
        assert recovery_relation_result["replacement"]["relation"] == "substitute"
        assert recovery_relation_data["updated_plan_contract"] is not None
        updated_japanese_steps = [step for step in recovery_relation_data["updated_plan_contract"]["timeline"] if step["type"] != "transport"]
        updated_japanese_text = updated_japanese_steps[-1]["title"] + " " + " ".join(updated_japanese_steps[-1].get("display_tags") or [])
        assert updated_japanese_steps[-1]["poi_id"] != japanese_steps[-1]["poi_id"]
        assert any(word in updated_japanese_text for word in (*tag_keywords("cuisine_japanese", "sushi", "izakaya"), "cuisine_japanese", "sushi", "izakaya"))
        assert not any(word in updated_japanese_text for word in ("茶空间", "咖啡", "M Stand", "瑞幸", "库迪"))
        assert any(
            check["name"] == "restaurant_capacity" and check["related_poi_id"] == updated_japanese_steps[-1]["poi_id"] and check["status"] == "pass"
            for check in recovery_relation_data["updated_plan_contract"]["verifier_result"]["checks"]
        )
        results.append({"name": "test_recovery_relation_replacement", "passed": True})

        buffet_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": "这周末想和老婆孩子去游乐园,然后吃一顿自助餐",
                "use_memory": False,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
                "preferred_start_time": "2026-05-24T14:00:00+08:00",
                "preferred_end_time": "2026-05-24T21:30:00+08:00",
            },
            headers=headers("idem_recovery_buffet_plan_runner"),
        )
        assert buffet_data.status_code == 200, buffet_data.text
        buffet = buffet_data.json()["data"]["plan_contract"]
        assert "buffet" in set(buffet["constraints"]["must_have"])
        buffet_steps = [step for step in buffet["timeline"] if step["type"] != "transport"]
        buffet_recovery = api.post(
            f"/api/v1/plans/{buffet['plan_id']}/recover",
            json={
                "trigger": "NO_TABLE_AVAILABLE",
                "failed_step_id": buffet_steps[-1]["step_id"],
                "recovery_strategy": "replace_restaurant_same_area",
                "auto_verify": True,
            },
            headers=headers("idem_recovery_buffet_runner"),
        )
        assert buffet_recovery.status_code == 200, buffet_recovery.text
        buffet_replacement = buffet_recovery.json()["data"]["recovery_result"]["replacement"]
        wrong_food_terms = ("肯德基", "包子", "面馆", "馄饨", "饺子", "茶空间", "咖啡", "甜品", "CHAGEE", "瑞幸", "M Stand")
        if buffet_replacement.get("available") is False:
            assert "poi_name" not in buffet_replacement
            assert buffet_replacement["failure_reason_code"] in {
                "no_same_semantic_restaurant_available",
                "same_semantic_restaurant_capacity_or_queue_failed",
                "same_semantic_restaurant_no_capacity",
                "same_semantic_restaurant_queue_exceeded",
            }
            assert buffet_replacement["failure_reasons"][0]["message"]
            assert buffet_recovery.json()["data"]["recovery_result"]["diff"]["recovery_diagnostics"]["candidate_summary"]["required_semantic_tags"] == ["buffet"]
        else:
            buffet_replacement_text = str(buffet_replacement.get("poi_name") or "")
            assert any(word in buffet_replacement_text for word in (*tag_keywords("buffet"), "自助"))
            assert not any(word in buffet_replacement_text for word in wrong_food_terms)
        results.append({"name": "test_recovery_does_not_replace_buffet_with_fast_food", "passed": True})

        assert "T14:00:00" in solo["time_window"]["start_time"]
        assert "T18:00:00" in solo["time_window"]["end_time"]
        results.append({"name": "test_afternoon_time_window_stable", "passed": True})

        long_date_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。安排4-5个活动。下午一点出发，晚上十点钟回来",
                "use_memory": False,
                "current_time": "2026-05-23T09:00:00+08:00",
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_anniversary_long_multi_stop_runner"),
        )
        assert long_date_data.status_code == 200, long_date_data.text
        long_date = long_date_data.json()["data"]["plan_contract"]
        assert long_date["time_window"]["start_time"].startswith("2026-05-23T13:00:00")
        assert long_date["time_window"]["end_time"].startswith("2026-05-23T22:00:00")
        assert long_date["constraints"]["target_stop_count_range"] == [4, 5]
        long_date_pois = [step for step in long_date["timeline"] if step["type"] != "transport"]
        assert 4 <= len(long_date_pois) <= 5
        assert max(step["end_time"] for step in long_date["timeline"]) <= long_date["time_window"]["end_time"]
        assert long_date["budget"]["price_per_person"] <= long_date["constraints"]["budget_max_per_person"]
        assert long_date["verifier_result"]["status"] == "pass"
        results.append({"name": "test_anniversary_long_multi_stop_window", "passed": True})

        five_activity_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。要安排五个活动",
                "use_memory": False,
                "current_time": "2026-05-23T09:00:00+08:00",
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_anniversary_exact_five_evening_runner"),
        )
        assert five_activity_data.status_code == 200, five_activity_data.text
        five_activity = five_activity_data.json()["data"]["plan_contract"]
        assert five_activity["time_window"]["start_time"].startswith("2026-05-23T17:00:00")
        assert five_activity["time_window"]["end_time"].startswith("2026-05-23T22:00:00")
        assert five_activity["constraints"]["target_stop_count"] == 5
        assert five_activity["constraints"]["target_stop_count_range"] == [5, 5]
        five_activity_pois = [step for step in five_activity["timeline"] if step["type"] != "transport"]
        assert len(five_activity_pois) == 5
        assert five_activity["verifier_result"]["status"] == "pass"
        results.append({"name": "test_anniversary_exact_five_without_exact_clock", "passed": True})

        current_anchor_data = api.post(
            "/api/v1/plans/create",
            json={
                "input_text": "周末下午我想去一个人散散心，顺便喝杯酒。",
                "use_memory": False,
                "current_time": "2026-05-23T18:00:00+08:00",
                "preferred_duration_hours": 4,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=headers("idem_current_anchor_weekend_afternoon_runner"),
        )
        assert current_anchor_data.status_code == 200, current_anchor_data.text
        current_anchor = current_anchor_data.json()["data"]["plan_contract"]
        assert current_anchor["time_window"]["start_time"].startswith("2026-05-24T15:00:00")
        assert current_anchor["time_window"]["end_time"].startswith("2026-05-24T19:00:00")
        results.append({"name": "test_current_time_anchor_weekend_afternoon", "passed": True})

        no_key = api.post(f"/api/v1/plans/{family['plan_id']}/execute", json={"confirmed": True}, headers=headers(None))
        assert no_key.status_code == 400
        assert no_key.json()["error"]["code"] == "BAD_REQUEST"
        results.append({"name": "test_execute_requires_idempotency_key", "passed": True})

        api.app.state.container.schema_validator.validate_plan_contract(friend)
        results.append({"name": "test_plan_contract_schema_pass", "passed": True})

        recovery = api.post(
            f"/api/v1/plans/{family['plan_id']}/recover",
            json={"trigger": "PLAN_EXECUTABLE_WINDOW_EXPIRED", "recovery_strategy": "refresh_window", "auto_verify": True},
            headers=headers("idem_recovery_runner"),
        )
        assert recovery.status_code == 200, recovery.text
        recovery_data = recovery.json()["data"]
        assert recovery_data["updated_plan_id"] != family["plan_id"]
        results.append({"name": "test_recovery_versioned", "passed": True})
    except Exception as exc:
        results.append({"name": "backend_p0_runner", "passed": False, "error": repr(exc)})
    finally:
        out = ROOT / "reports" / "backend_p0_tests.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [item for item in results if not item.get("passed")]
    for item in results:
        print(f"{item['name']}: {'PASS' if item.get('passed') else 'FAIL'}")
        if item.get("error"):
            print(item["error"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
