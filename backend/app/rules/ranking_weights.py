from __future__ import annotations

from typing import Any, Dict


SCHEMA_VERSION = "recommendation_ranker_weights.v1"
GENERATED_AT = "2026-05-24T00:00:00+08:00"

DEFAULT_RANKING_WEIGHTS: Dict[str, float] = {
    "base.quality": 18.0,
    "tag.desired": 7.0,
    "tag.avoid": -22.0,
    "activity.family_fit": 84.0,
    "activity.amusement_fit.default": 22.0,
    "activity.amusement_fit.required": 140.0,
    "activity.date_fit": 72.0,
    "activity.visitor_fit": 76.0,
    "activity.friend_fit": 58.0,
    "activity.solo_fit": 70.0,
    "activity.experience_fit": 24.0,
    "activity.mall_dependency_risk": -18.0,
    "activity.movie_dependency_risk": -18.0,
    "activity.low_fit_penalty": -190.0,
    "restaurant.proper_dining": 46.0,
    "restaurant.casual_penalty": -92.0,
    "restaurant.family_fit": 42.0,
    "restaurant.date_fit": 52.0,
    "restaurant.visitor_fit": 48.0,
    "restaurant.friend_fit": 42.0,
    "restaurant.experience_fit": 34.0,
    "restaurant.snack_substitution_risk": -86.0,
    "restaurant.heavy_meal_risk": -48.0,
    "restaurant.buffet_fit.required": 180.0,
    "restaurant.light_meal_fit.required": 104.0,
    "restaurant.quality.required": 44.0,
    "restaurant.proper_dining.required": 44.0,
    "tail.family_fit": 34.0,
    "tail.date_fit": 30.0,
    "tail.visitor_fit": 34.0,
    "tail.solo_fit": 30.0,
    "tail.experience_fit": 20.0,
    "tail.route_anchor": 22.0,
    "tail.low_fit_penalty": -90.0,
    "context.route_anchor.required": 18.0,
    "risk.intent_mismatch": -36.0,
    "risk.route_fragility": -16.0,
    "risk.queue_pressure": -28.0,
    "risk.weather_exposure": -42.0,
    "risk.alcohol": -20.0,
}


def default_ranker_weight_document() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "source": "default_runtime_constants",
        "weights": dict(DEFAULT_RANKING_WEIGHTS),
        "training_summary": {
            "preference_case_count": 0,
            "pair_accuracy": None,
            "note": "Default weights mirror the checked runtime behavior.",
        },
    }


def normalize_ranker_weights(document: Dict[str, Any]) -> Dict[str, float]:
    weights = dict(DEFAULT_RANKING_WEIGHTS)
    raw_weights = document.get("weights") if isinstance(document, dict) else None
    if not isinstance(raw_weights, dict):
        return weights
    for key, value in raw_weights.items():
        if key not in DEFAULT_RANKING_WEIGHTS:
            continue
        try:
            weights[key] = float(value)
        except (TypeError, ValueError):
            continue
    return weights
