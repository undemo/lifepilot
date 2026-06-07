import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import ActivityIntent, CanonicalTagSet, FoodIntent, LatentIntent  # noqa: E402
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


def _food():
    return FoodIntent.fallback()


def _activity(**kwargs):
    payload = {
        "raw_terms": [],
        "activity_type_ids": [],
        "parent_categories": [],
        "facility_types": [],
        "genres": [],
        "styles": [],
        "scenes": [],
        "fallback_query_text": "",
        "retrieval_mode": "unknown",
        "intensity": "unknown",
        "indoor_preferred": False,
        "outdoor_acceptable": True,
        "booking_required": False,
        "child_suitable_required": False,
        "elderly_suitable_required": False,
        "quiet_required": False,
        "social_mode": "unknown",
    }
    payload.update(kwargs)
    return ActivityIntent.parse_payload(payload)


def _compile(tags, activity, text=""):
    return RetrievalIntentCompiler().compile(
        raw_user_text=text,
        user_goal={"scenario": "fallback_unknown", "intent_tags": []},
        constraints={},
        latent_intent=_latent(tags),
        food_intent=_food(),
        activity_intent=activity,
    )


def _features(items):
    return {item["feature"] for item in items}


def test_badminton_compiles_activity_match_and_sports_addons():
    machine = _compile(
        ["WITH_SIBLING", "SPORTS"],
        _activity(
            raw_terms=["羽毛球"],
            activity_type_ids=["ACTIVITY_BADMINTON"],
            parent_categories=["SPORTS"],
            facility_types=["羽毛球馆"],
            genres=["球类"],
            retrieval_mode="known_activity",
            intensity="medium",
            booking_required=True,
            social_mode="sibling",
        ),
        "和姐姐打羽毛球",
    )

    match = machine.retrieval_plan["activity_match"]
    assert match["activity_type_ids"] == ["ACTIVITY_BADMINTON"]
    assert "raw_activity_term_index" in machine.retrieval_plan["indexes"]
    assert "activity_type_index" in machine.retrieval_plan["indexes"]
    assert {"exact_raw_activity_match", "known_activity_match", "activity_attribute_match"} <= _features(machine.soft_preferences)
    assert any(req.get("slot_type") == "addon" and req.get("tag") == "DRINK_SUGGESTED" for req in machine.slot_requirements)


def test_esports_with_child_adds_child_incompatible_penalty():
    machine = _compile(
        ["WITH_CHILD", "CHILD_AGE_PRESCHOOL"],
        _activity(
            raw_terms=["电竞"],
            activity_type_ids=["ACTIVITY_ESPORTS"],
            parent_categories=["GAME", "SOCIAL_ENTERTAINMENT"],
            facility_types=["电竞馆"],
            retrieval_mode="known_activity",
            child_suitable_required=True,
            social_mode="family",
        ),
        "带5岁孩子去打电竞",
    )

    assert "child_activity_score" in _features(machine.soft_preferences)
    assert "child_incompatible_activity" in _features(machine.penalties)


def test_elderly_football_adds_elderly_and_intensity_penalties():
    machine = _compile(
        ["WITH_ELDERLY"],
        _activity(
            raw_terms=["足球"],
            activity_type_ids=["ACTIVITY_FOOTBALL"],
            parent_categories=["SPORTS"],
            facility_types=["足球场"],
            retrieval_mode="known_activity",
            intensity="high",
            elderly_suitable_required=True,
            social_mode="elderly",
        ),
        "带爷爷去踢足球",
    )

    assert "elderly_incompatible_activity" in _features(machine.penalties)
    assert "high_physical_intensity" in _features(machine.penalties)
