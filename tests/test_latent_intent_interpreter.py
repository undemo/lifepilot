import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.latent_intent_interpreter import LatentIntentInterpreter  # noqa: E402


def _minimal_goal(tags=None, scenario="fallback_unknown"):
    return {
        "raw_text": "",
        "scenario": scenario,
        "goal_summary": "test",
        "intent_tags": tags or [],
    }


def _minimal_constraints(**overrides):
    constraints = {
        "must_have": [],
        "recommendation_profile": {"normalized_tags": []},
        "dining_preference": {"normalized_tags": [], "specific_tags": [], "raw_terms": []},
    }
    constraints.update(overrides)
    return constraints


def _tag_values(latent_intent):
    return set(latent_intent.canonical_tag_set.to_dict()["canonical_tags"])


def test_family_child_crayfish_case_maps_required_tags():
    text = "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾"
    interpreter = LatentIntentInterpreter()

    latent = interpreter.interpret(
        raw_user_text=text,
        user_goal=_minimal_goal(scenario="family_parent_child"),
        constraints=_minimal_constraints(),
    )

    tags = _tag_values(latent)
    assert {
        "FAMILY_OUTING",
        "WITH_CHILD",
        "CHILD_AGE_PRESCHOOL",
        "SHORT_DURATION",
        "AFTERNOON",
        "NEARBY_REQUIRED",
        "AVOID_LONG_QUEUE",
        "DINNER_REQUIRED",
        "CRAYFISH_REQUIRED",
        "CHILD_FOOD_REQUIRED",
        "NON_SPICY_REQUIRED",
        "RESERVATION_SUGGESTED",
        "RESTROOM_REQUIRED",
        "REST_AREA_REQUIRED",
    }.issubset(tags)
    assert latent.hidden_constraints
    assert latent.failure_cases


def test_anniversary_weight_loss_maps_ceremony_and_low_calorie():
    text = "这周末我和我老婆小孩去过纪念日，老婆在减脂，想带老婆去游乐园，晚上吃小龙虾"
    latent = LatentIntentInterpreter().interpret(
        raw_user_text=text,
        user_goal=_minimal_goal(scenario="anniversary_emotion"),
        constraints=_minimal_constraints(),
    )

    tags = _tag_values(latent)
    assert {"ANNIVERSARY", "CEREMONIAL", "FLOWER_SUGGESTED", "PHOTO_SPOT_REQUIRED"}.issubset(tags)
    assert {"LOW_CALORIE_REQUIRED", "LIGHT_MEAL_REQUIRED", "WITH_CHILD", "WITH_COUPLE"}.issubset(tags)
    assert "周末" not in latent.canonical_tag_set.source_tags


def test_stress_relief_maps_healing_and_relaxed_pace():
    latent = LatentIntentInterpreter().interpret(
        raw_user_text="我最近学习压力很大，今天下午想出去散散心",
        user_goal=_minimal_goal(),
        constraints=_minimal_constraints(),
    )

    tags = _tag_values(latent)
    assert {"STRESS_RELIEF", "HEALING", "RELAXED_PACE", "AVOID_CROWD", "AFTERNOON", "TODAY"}.issubset(tags)
    assert any("低刺激" in item or "低决策" in item for item in latent.latent_goals + latent.hidden_constraints)


def test_friends_badminton_maps_sports_and_addon_drink():
    latent = LatentIntentInterpreter().interpret(
        raw_user_text="这周末和朋友去打个羽毛球，然后你安排",
        user_goal=_minimal_goal(scenario="friend_group"),
        constraints=_minimal_constraints(),
    )

    tags = _tag_values(latent)
    assert {"WITH_FRIENDS", "SPORTS", "WEEKEND", "DRINK_SUGGESTED"}.issubset(tags)


class DisabledLLM:
    def generate_json(self, **kwargs):
        raise RuntimeError("llm disabled")


def test_llm_disabled_keeps_deterministic_fallback():
    latent = LatentIntentInterpreter(DisabledLLM()).interpret(
        raw_user_text="安排一下",
        user_goal=_minimal_goal(),
        constraints=_minimal_constraints(),
    )

    assert _tag_values(latent) == set()
    assert latent.clarification_policy["ask_only_if_blocking"] is True


class InvalidTagLLM:
    def generate_json(self, **kwargs):
        return {
            "latent_goals": ["需要低决策成本"],
            "hidden_constraints": ["避免太折腾"],
            "success_definition": ["顺利完成"],
            "failure_cases": ["安排不合适"],
            "inferred_tags": ["NOT_A_REAL_TAG"],
            "confidence_by_tag": {"NOT_A_REAL_TAG": 0.9},
            "evidence_by_tag": {"NOT_A_REAL_TAG": "bad"},
        }


def test_llm_invalid_tag_is_rejected_and_fallback_survives():
    latent = LatentIntentInterpreter(InvalidTagLLM()).interpret(
        raw_user_text="安排一下",
        user_goal=_minimal_goal(),
        constraints=_minimal_constraints(),
    )

    assert _tag_values(latent) == set()
    assert latent.latent_goals == []
    assert latent.failure_cases == []
