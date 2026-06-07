import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.plan_generator import PlanGenerator  # noqa: E402


class DummyLogger:
    def log(self, *args, **kwargs):
        return {}


class SpecificActivityNoteLLM:
    def generate_json(self, **kwargs):
        return {
            "activity_note": "亲子拼豆油画，室内安静不赶时间",
            "restaurant_note": "椰子鸡清淡低负担，建议提前取号",
        }


def _route(origin: str, destination: str, minutes: int):
    return {
        "origin_poi_id": origin,
        "destination_poi_id": destination,
        "duration_minutes": minutes,
        "distance_km": 0.4,
        "transport_mode": "walk",
    }


def test_multi_stop_activity_notes_are_poi_specific_when_llm_note_mentions_one_poi():
    craft = {
        "poi_id": "poi_gaode_activity_194_cf1760",
        "name": "小喜·DIY手工坊·拼豆·油画",
        "category": "activity",
        "sub_category": "leisure_play",
        "tags": ["gaode_poi", "leisure", "indoor", "group_ok", "lake"],
    }
    carnival = {
        "poi_id": "poi_gaode_activity_014_0f7faa",
        "name": "爱玩嘉年华(龙湖杭州金沙天街店)",
        "category": "activity",
        "sub_category": "leisure_play",
        "tags": ["gaode_poi", "leisure", "indoor", "group_ok", "mall"],
    }
    restaurant = {
        "poi_id": "poi_gaode_restaurant_coconut",
        "name": "狐狸爱上椰子鸡(龙湖杭州金沙天街店)",
        "category": "restaurant",
        "tags": ["light_meal", "family_friendly"],
    }
    generator = PlanGenerator(DummyLogger(), SpecificActivityNoteLLM())

    drafts = generator.generate(
        "trace_plan_generator_test",
        {
            "scenario": "family_parent_child",
            "goal_summary": "亲子下午，低负担晚饭，别太远。",
            "intent_tags": ["child_friendly", "light_food", "nearby"],
        },
        {
            "target_stop_count": 3,
            "party_size": 3,
            "must_have": [],
            "dining_preference": {},
        },
        {
            "start_time": "2026-05-21T15:00:00+08:00",
            "end_time": "2026-05-21T19:00:00+08:00",
        },
        {
            "selected_pois": {"activity": craft, "tail": carnival, "restaurant": restaurant},
            "itinerary_nodes": [
                {"role": "activity", "poi": craft},
                {"role": "tail", "poi": carnival},
                {"role": "restaurant", "poi": restaurant},
            ],
            "routes": [
                _route(craft["poi_id"], carnival["poi_id"], 4),
                _route(carnival["poi_id"], restaurant["poi_id"], 3),
            ],
            "planning_order": "dinner_last",
        },
    )

    steps = [step for step in drafts[0]["steps"] if step["type"] != "transport"]
    craft_step = next(step for step in steps if step["poi_id"] == craft["poi_id"])
    carnival_step = next(step for step in steps if step["poi_id"] == carnival["poi_id"])

    assert craft_step["description"] != carnival_step["description"]
    assert "手作" in craft_step["description"]
    assert "拼豆" not in carnival_step["description"]
    assert "油画" not in carnival_step["description"]
    assert "商场" in carnival_step["description"] or "游乐" in carnival_step["description"]
