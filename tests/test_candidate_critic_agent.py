import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import FoodIntent, MachineIntent  # noqa: E402
from app.services.candidate_critic_agent import CandidateCriticAgent  # noqa: E402
from app.services.candidate_retriever import CandidateRetriever  # noqa: E402


def _agent(llm_client=None, top_n=10):
    return CandidateCriticAgent(llm_client=llm_client, top_n=top_n)


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


def _report_by_id(reports, poi_id):
    for report in reports:
        if report.poi_id == poi_id:
            return report
    raise AssertionError(f"missing report for {poi_id}")


def test_child_with_noisy_spicy_restaurant_is_demoted():
    item = {
        "poi_id": "spicy_barbecue",
        "name": "高噪声重辣烤吧",
        "category": "restaurant",
        "menu_features": {
            "spicy_level": 0.9,
            "has_non_spicy": False,
            "has_child_friendly_food": False,
        },
        "family_features": {
            "child_food_score": 0.2,
            "noise_level": 0.86,
        },
    }

    reports = _agent().review(
        user_goal={"intent_tags": []},
        constraints={},
        machine_intent=_machine(["WITH_CHILD", "CHILD_AGE_PRESCHOOL", "CHILD_FOOD_REQUIRED"]),
        top_candidates=[item],
    )
    report = _report_by_id(reports, "spicy_barbecue")

    assert report.decision in {"demote", "backup_only"}
    assert report.score_delta < 0
    assert {"CHILD_FOOD_MISSING", "SPICY_CHILD_RISK", "CHILD_NOISE_RISK"} & set(report.reason_codes)


def test_avoid_queue_demotes_high_queue_candidate():
    item = {
        "poi_id": "viral_shop",
        "name": "高排队网红店",
        "category": "restaurant",
        "queue_features": {
            "queue_risk": 0.88,
            "avg_wait_minutes_peak": 38,
            "reservation_supported": False,
        },
    }

    report = _agent().review(
        user_goal={"intent_tags": []},
        constraints={"queue_tolerance": "low"},
        machine_intent=_machine(["AVOID_LONG_QUEUE"]),
        top_candidates=[item],
    )[0]

    assert report.decision in {"demote", "backup_only"}
    assert report.score_delta <= -20
    assert "HIGH_QUEUE_RISK" in report.reason_codes


def test_weight_loss_demotes_high_oil_heavy_food():
    item = {
        "poi_id": "heavy_crayfish",
        "name": "重油小龙虾",
        "category": "restaurant",
        "menu_features": {
            "oiliness_level": 0.86,
            "healthy_option_score": 0.25,
            "spicy_level": 0.78,
        },
    }

    report = _agent().review(
        user_goal={"intent_tags": []},
        constraints={},
        machine_intent=_machine(["LOW_CALORIE_REQUIRED"]),
        top_candidates=[item],
    )[0]

    assert report.score_delta < 0
    assert "LOW_CALORIE_MISMATCH" in report.reason_codes


def test_long_tail_charcoal_pineapple_keeps_matching_bbq_and_demotes_hotpot():
    food = _food(
        raw_terms=["碳烤菠萝"],
        parent_categories=["BBQ", "LONG_TAIL_SNACK"],
        ingredients=["菠萝"],
        cooking_methods=["炭烤", "烧烤"],
        forms=["烤物"],
        retrieval_mode="long_tail_attribute",
    )
    creative_bbq = {
        "poi_id": "creative_bbq",
        "name": "创意烧烤",
        "category": "restaurant",
        "menu_features": {
            "raw_food_terms": ["碳烤菠萝"],
            "parent_categories": ["BBQ", "LONG_TAIL_SNACK"],
            "ingredients": ["菠萝"],
            "cooking_methods": ["炭烤"],
            "forms": ["烤物"],
        },
    }
    plain_hotpot = {
        "poi_id": "plain_hotpot",
        "name": "普通火锅",
        "category": "restaurant",
        "menu_features": {
            "dish_ids": ["DISH_HOTPOT"],
            "parent_categories": ["HOTPOT"],
        },
    }

    reports = _agent().review(
        user_goal={"intent_tags": []},
        constraints={},
        food_intent=food,
        top_candidates=[creative_bbq, plain_hotpot],
    )

    assert _report_by_id(reports, "creative_bbq").decision == "keep"
    assert _report_by_id(reports, "plain_hotpot").decision in {"demote", "backup_only"}
    assert "FOOD_INTENT_MISMATCH" in _report_by_id(reports, "plain_hotpot").reason_codes


def test_milk_skin_tanghulu_demotes_unrelated_restaurant():
    food = _food(
        raw_terms=["奶皮子糖葫芦"],
        parent_categories=["DESSERT", "SNACK", "LONG_TAIL_SNACK"],
        ingredients=["奶皮子"],
        flavors=["奶香", "甜"],
        forms=["糖葫芦", "小吃"],
        scenes=["网红小吃"],
        retrieval_mode="long_tail_attribute",
    )
    dessert = {
        "poi_id": "dessert",
        "name": "网红甜品小吃",
        "category": "restaurant",
        "menu_features": {
            "raw_food_terms": ["奶皮子糖葫芦"],
            "ingredients": ["奶皮子", "糖葫芦"],
            "flavors": ["奶香", "甜"],
            "forms": ["糖葫芦", "小吃"],
            "scenes": ["网红小吃"],
        },
    }
    rice = {
        "poi_id": "rice",
        "name": "普通盖饭",
        "category": "restaurant",
        "menu_features": {
            "dish_ids": ["DISH_RICE"],
            "parent_categories": ["RICE"],
        },
    }

    reports = _agent().review(
        user_goal={"intent_tags": []},
        constraints={},
        food_intent=food,
        top_candidates=[dessert, rice],
    )

    assert _report_by_id(reports, "dessert").decision == "keep"
    assert _report_by_id(reports, "rice").score_delta < 0


class InvalidJSONLLM:
    def generate_json(self, **kwargs):
        return {"reports": [{"poi_id": "spicy", "decision": "not_allowed", "score_delta": "bad"}]}


def test_llm_invalid_json_falls_back_to_deterministic_reports():
    item = {
        "poi_id": "spicy",
        "name": "重辣餐厅",
        "category": "restaurant",
        "menu_features": {"spicy_level": 0.9, "has_non_spicy": False, "has_child_friendly_food": False},
        "family_features": {"child_food_score": 0.2},
    }

    reports = _agent(InvalidJSONLLM()).review(
        user_goal={"intent_tags": []},
        constraints={},
        machine_intent=_machine(["WITH_CHILD", "CHILD_AGE_PRESCHOOL"]),
        top_candidates=[item],
    )

    assert len(reports) == 1
    assert reports[0].score_delta < 0
    assert "CHILD_FOOD_MISSING" in reports[0].reason_codes


def test_top_n_limit_is_respected():
    items = [
        {
            "poi_id": f"poi_{index}",
            "name": f"候选{index}",
            "category": "restaurant",
            "queue_features": {"queue_risk": 0.9, "avg_wait_minutes_peak": 35},
        }
        for index in range(12)
    ]

    reports = _agent(top_n=5).review(
        user_goal={"intent_tags": []},
        constraints={},
        machine_intent=_machine(["AVOID_LONG_QUEUE"]),
        top_candidates=items,
        top_n=5,
    )

    assert len(reports) == 5
    assert [report.poi_id for report in reports] == [f"poi_{index}" for index in range(5)]


def test_apply_critic_reports_adjusts_backup_scores_without_deleting_candidates():
    candidate_set = {
        "selected_pois": {
            "restaurant": {"poi_id": "selected", "name": "当前餐厅", "category": "restaurant"},
        },
        "extra_pois": [],
        "backup_candidates": [
            {"role": "restaurant", "poi": {"poi_id": "backup_a"}, "score": 100},
            {"role": "restaurant", "poi": {"poi_id": "backup_b"}, "score": 90},
        ],
    }
    report = {
        "poi_id": "backup_a",
        "decision": "demote",
        "score_delta": -30,
        "reason_codes": ["HIGH_QUEUE_RISK"],
        "user_facing_reason": "排队风险高",
        "risk_notes": ["排队风险高"],
    }

    updated = CandidateRetriever(None, None).apply_critic_reports(candidate_set, [report])

    assert len(updated["backup_candidates"]) == 2
    assert updated["backup_candidates"][0]["poi"]["poi_id"] == "backup_b"
    assert updated["backup_candidates"][1]["_critic_score_delta"] == -30
