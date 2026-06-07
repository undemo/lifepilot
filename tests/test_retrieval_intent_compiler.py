import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import CanonicalTagSet, FoodIntent, LatentIntent  # noqa: E402
from app.services.retrieval_intent_compiler import RetrievalIntentCompiler  # noqa: E402


def _latent(tags):
    return LatentIntent.fallback(
        canonical_tag_set=CanonicalTagSet.parse_payload(
            {
                "canonical_tags": tags,
                "source_tags": [],
                "inferred_tags": [],
                "confidence_by_tag": {},
                "evidence_by_tag": {},
            }
        )
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


def _compile(tags, food=None, text=""):
    return RetrievalIntentCompiler().compile(
        raw_user_text=text,
        user_goal={"scenario": "fallback_unknown", "intent_tags": []},
        constraints={},
        latent_intent=_latent(tags),
        food_intent=food or _food(),
    )


def _features(items):
    return {item["feature"] for item in items}


def test_family_child_case_generates_child_queue_distance_and_food_intent():
    food = _food(
        raw_terms=["小龙虾"],
        known_dish_ids=["DISH_CRAYFISH"],
        parent_categories=["CRAYFISH"],
        retrieval_mode="known_dish",
        child_food_required=True,
        non_spicy_required=True,
    )
    machine = _compile(
        [
            "FAMILY_OUTING",
            "WITH_CHILD",
            "CHILD_AGE_PRESCHOOL",
            "AVOID_LONG_QUEUE",
            "NEARBY_REQUIRED",
            "DINNER_REQUIRED",
            "MEAL_REQUIRED",
            "CRAYFISH_REQUIRED",
            "CHILD_FOOD_REQUIRED",
            "NON_SPICY_REQUIRED",
        ],
        food,
        "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾",
    )

    assert machine.global_constraints["with_child"] is True
    assert machine.global_constraints["child_age_group"] == "preschool"
    assert machine.global_constraints["max_single_leg_travel_minutes"] == 30
    assert {"child_friendly_score", "restroom_score", "child_food_score", "low_queue_score", "nearby_score"} <= _features(machine.soft_preferences)
    assert {"high_noise_level", "spicy_only_restaurant", "high_queue_risk", "long_transfer"} <= _features(machine.penalties)
    assert {"verify_queue", "verify_route", "verify_restaurant_capacity"} <= set(machine.verifier_expectations)
    assert machine.retrieval_plan["food_match"]["known_dish_ids"] == ["DISH_CRAYFISH"]
    assert "known_dish_index" in machine.retrieval_plan["indexes"]
    assert any(item.get("slot_type") == "meal" and item.get("preferred_time") == "dinner" for item in machine.slot_requirements)


def test_hotpot_is_supported_not_only_crayfish():
    food = _food(raw_terms=["火锅"], known_dish_ids=["DISH_HOTPOT"], parent_categories=["HOTPOT"], retrieval_mode="known_dish")
    machine = _compile(["HOTPOT_REQUIRED", "MEAL_REQUIRED"], food, "想吃火锅")

    assert machine.retrieval_plan["food_match"]["known_dish_ids"] == ["DISH_HOTPOT"]
    assert "has_hotpot" in _features(machine.hard_filters)
    assert "has_crayfish" not in _features(machine.hard_filters)


def test_charcoal_pineapple_generates_raw_and_attribute_retrieval_plan():
    food = _food(
        raw_terms=["碳烤菠萝"],
        parent_categories=["BBQ"],
        ingredients=["菠萝"],
        cooking_methods=["炭烤", "烧烤"],
        forms=["烤物"],
        retrieval_mode="long_tail_attribute",
    )
    machine = _compile(["BBQ_REQUIRED", "MEAL_REQUIRED", "NEARBY_REQUIRED"], food, "晚上想吃碳烤菠萝，附近顺便逛逛")

    plan = machine.retrieval_plan
    assert plan["food_match"]["raw_terms"] == ["碳烤菠萝"]
    assert "菠萝" in plan["food_match"]["ingredients"]
    assert {"raw_term_index", "ingredient_index", "cooking_method_index", "form_index"} <= set(plan["indexes"])
    assert "DISH_CHARCOAL_GRILLED_PINEAPPLE" not in str(plan)


def test_milk_skin_tanghulu_generates_dessert_snack_attribute_plan():
    food = _food(
        raw_terms=["奶皮子糖葫芦"],
        parent_categories=["DESSERT", "SNACK", "LONG_TAIL_SNACK"],
        ingredients=["奶皮子"],
        flavors=["奶香", "甜"],
        forms=["糖葫芦", "小吃"],
        scenes=["网红小吃"],
        retrieval_mode="long_tail_attribute",
    )
    machine = _compile(["DESSERT_REQUIRED", "SNACK_REQUIRED", "MEAL_REQUIRED"], food, "想吃奶皮子糖葫芦，再找个地方散步")

    match = machine.retrieval_plan["food_match"]
    assert match["raw_terms"] == ["奶皮子糖葫芦"]
    assert {"DESSERT", "SNACK", "LONG_TAIL_SNACK"} <= set(match["parent_categories"])
    assert {"raw_term_index", "ingredient_index", "flavor_index", "form_index", "scene_index"} <= set(machine.retrieval_plan["indexes"])


def test_low_calorie_generates_healthy_weights_and_oiliness_penalty():
    food = _food(
        raw_terms=["清淡的"],
        known_dish_ids=["DISH_LIGHT_MEAL"],
        parent_categories=["LIGHT_MEAL"],
        retrieval_mode="known_dish",
        low_calorie_required=True,
    )
    machine = _compile(["LOW_CALORIE_REQUIRED", "LIGHT_MEAL_REQUIRED", "MEAL_REQUIRED", "RELAXED_PACE"], food)

    assert {"healthy_option_score", "light_meal_match"} <= _features(machine.soft_preferences)
    assert "oiliness_level" in _features(machine.penalties)
    assert machine.global_constraints["pace"] == "relaxed"


def test_hotpot_with_child_non_spicy_generates_child_food_preferences():
    food = _food(
        raw_terms=["火锅"],
        known_dish_ids=["DISH_HOTPOT"],
        parent_categories=["HOTPOT"],
        retrieval_mode="known_dish",
        child_food_required=True,
        non_spicy_required=True,
    )
    machine = _compile(["WITH_CHILD", "CHILD_AGE_PRESCHOOL", "HOTPOT_REQUIRED", "MEAL_REQUIRED", "NON_SPICY_REQUIRED"], food)

    assert {"child_food_score", "non_spicy_option", "family_dining_score"} <= _features(machine.soft_preferences)
    assert "spicy_only_restaurant" in _features(machine.penalties)
    assert "has_hotpot" in _features(machine.hard_filters)


def test_compiler_has_deterministic_empty_fallback_without_llm():
    machine = RetrievalIntentCompiler().compile(
        raw_user_text="安排一下",
        user_goal={"scenario": "fallback_unknown", "intent_tags": []},
        constraints={},
        latent_intent=None,
        food_intent=None,
    )

    assert machine.canonical_tags == []
    assert machine.global_constraints == {}
    assert machine.retrieval_plan == {}
