import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import (  # noqa: E402
    CanonicalTagSet,
    FoodIntent,
    InternalIntelligenceValidationError,
    PlanCriticReport,
    RecommendationExplanation,
)


def test_unknown_canonical_tag_is_rejected():
    with pytest.raises(InternalIntelligenceValidationError):
        CanonicalTagSet.parse_payload(
            {
                "canonical_tags": ["WITH_CHILD", "NOT_A_REAL_TAG"],
                "source_tags": ["child"],
            }
        )


def test_food_intent_long_tail_can_omit_known_dish_ids():
    intent = FoodIntent.parse_payload(
        {
            "raw_terms": ["碳烤菠萝"],
            "known_dish_ids": [],
            "parent_categories": ["SNACK"],
            "ingredients": ["菠萝"],
            "cooking_methods": ["炭烤", "烧烤"],
            "flavors": ["酸甜"],
            "forms": ["小吃"],
            "scenes": ["夜市"],
            "fallback_query_text": "碳烤菠萝 菠萝 炭烤 烧烤 小吃",
            "retrieval_mode": "long_tail_attribute",
            "child_food_required": False,
            "non_spicy_required": False,
            "low_calorie_required": False,
        }
    )

    assert intent.retrieval_mode == "long_tail_attribute"
    assert intent.known_dish_ids == []
    assert "碳烤菠萝" in intent.raw_terms
    assert "菠萝" in intent.ingredients
    assert {"炭烤", "烧烤"} & set(intent.cooking_methods)


def test_food_intent_rejects_unknown_known_dish_id():
    with pytest.raises(InternalIntelligenceValidationError):
        FoodIntent.parse_payload(
            {
                "raw_terms": ["碳烤菠萝"],
                "known_dish_ids": ["DISH_CHARCOAL_GRILLED_PINEAPPLE"],
                "retrieval_mode": "known_dish",
            }
        )


def test_plan_critic_report_accepts_pass_alias():
    report = PlanCriticReport.parse_payload(
        {
            "pass": False,
            "issues": [{"code": "queue_risk", "message": "排队风险过高"}],
            "repair_instructions": [{"action": "replace_restaurant"}],
            "severity": "medium",
            "verifier_related_notes": ["verify_queue"],
        }
    )

    assert report.pass_ is False
    assert report.to_dict()["pass"] is False
    assert report.to_dict()["severity"] == "medium"


def test_parse_payload_can_return_fallback_without_crashing():
    fallback = CanonicalTagSet.parse_payload(
        {"canonical_tags": ["UNKNOWN_TAG"], "source_tags": ["legacy_tag"]},
        fallback_on_error=True,
        source_tags=["legacy_tag"],
    )

    assert fallback.canonical_tags == []
    assert fallback.source_tags == ["legacy_tag"]


def test_fallback_filters_invalid_food_enum_values():
    fallback = FoodIntent.fallback(
        raw_terms=["奶皮子糖葫芦"],
        known_dish_ids=["DISH_FAKE"],
        parent_categories=["DESSERT", "NOT_A_CATEGORY"],
        retrieval_mode="not_valid",
    )

    assert fallback.raw_terms == ["奶皮子糖葫芦"]
    assert fallback.known_dish_ids == []
    assert fallback.parent_categories == ["DESSERT"]
    assert fallback.retrieval_mode == "unknown"


def test_to_dict_serializes_enums_and_aliases():
    tag_set = CanonicalTagSet.parse_payload(
        {
            "canonical_tags": ["WITH_CHILD", "AVOID_LONG_QUEUE"],
            "inferred_tags": ["RESTROOM_REQUIRED"],
            "confidence_by_tag": {"WITH_CHILD": 0.9},
            "evidence_by_tag": {"WITH_CHILD": "用户提到孩子"},
        }
    )
    explanation = RecommendationExplanation.fallback(
        why_this_plan=["亲子场景优先低排队和低强度"],
        addon_suggestions=[{"type": "wet_tissue", "label": "湿巾"}],
    )

    tag_payload = tag_set.to_dict()
    explanation_payload = explanation.to_dict()

    assert tag_payload["canonical_tags"] == ["WITH_CHILD", "AVOID_LONG_QUEUE"]
    assert tag_payload["inferred_tags"] == ["RESTROOM_REQUIRED"]
    assert explanation_payload["why_this_plan"] == ["亲子场景优先低排队和低强度"]
    assert explanation_payload["addon_suggestions"][0]["type"] == "wet_tissue"
