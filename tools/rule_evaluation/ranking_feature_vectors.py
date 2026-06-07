from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rules.ranking_weights import DEFAULT_RANKING_WEIGHTS  # noqa: E402


def feature_vector(case: Dict[str, Any], feature: Dict[str, Any]) -> Dict[str, float]:
    scenario = str(case.get("scenario") or "")
    role = str(case.get("role") or "")
    intent_tags = set(str(tag) for tag in case.get("intent_tags") or [])
    avoid_tags = set(str(tag) for tag in case.get("avoid_tags") or [])
    markers = intent_tags | set(str(tag) for tag in case.get("explicit_markers") or [])
    tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
    scores = _numeric_map(feature.get("scores"))
    experience = _numeric_map(feature.get("experience_scores"))
    risk = _numeric_map(feature.get("risk_scores"))

    vector = {
        "base.quality": scores.get("quality", 0.0),
        "tag.desired": float(len(tags & intent_tags)),
        "tag.avoid": float(len(tags & avoid_tags)),
        "risk.intent_mismatch": risk.get("intent_mismatch", 0.0),
    }
    if scenario == "friend_group" and "karaoke" in intent_tags and "karaoke" in tags:
        vector["tag.desired"] += 3.0
        vector["risk.intent_mismatch"] = 0.0

    if role == "activity":
        _activity_vector(vector, scenario, markers, tags, scores, experience, risk, avoid_tags)
    elif role == "restaurant":
        _restaurant_vector(vector, scenario, markers, scores, experience, risk)
    else:
        _tail_vector(vector, scenario, scores, experience, risk)
    if role in {"activity", "tail"}:
        vector["risk.weather_exposure"] = risk.get("weather_exposure", 0.0)
    if "low_queue" in markers or "queue" in markers:
        vector["risk.queue_pressure"] = _queue_pressure_for_case(case, feature, risk)
    if markers & {"nearby", "route_simple", "area_jinshahu", "area_xiasha", "area_gaojiao", "light_walk"}:
        vector["context.route_anchor.required"] = scores.get("route_anchor", 0.0)
        vector["risk.route_fragility"] = risk.get("route_fragility", 0.0)
    if "alcohol" not in markers:
        vector["risk.alcohol"] = risk.get("alcohol_risk", 0.0)
    return vector


def score(vector: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
    resolved = weights or DEFAULT_RANKING_WEIGHTS
    return sum(vector.get(key, 0.0) * weight for key, weight in resolved.items())


def _activity_vector(
    vector: Dict[str, float],
    scenario: str,
    markers: set[str],
    tags: set[str],
    scores: Dict[str, float],
    experience: Dict[str, float],
    risk: Dict[str, float],
    avoid_tags: set[str],
) -> None:
    if scenario == "family_parent_child":
        vector["activity.family_fit"] = scores.get("family_fit", 0.0)
        vector["activity.amusement_fit.required"] = scores.get("amusement_fit", 0.0)
        vector["activity.experience_fit"] = experience.get("kid_safety", 0.0)
    elif scenario == "anniversary_emotion":
        vector["activity.date_fit"] = scores.get("date_fit", 0.0)
        vector["activity.experience_fit"] = experience.get("ritual_fit", 0.0)
    elif scenario == "city_light_explore":
        vector["activity.visitor_fit"] = scores.get("visitor_fit", 0.0)
        vector["activity.experience_fit"] = max(experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0))
    elif scenario == "friend_group":
        vector["activity.friend_fit"] = scores.get("friend_fit", 0.0)
        vector["activity.experience_fit"] = max(experience.get("conversation_fit", 0.0), experience.get("stay_duration_fit", 0.0))
    else:
        vector["activity.solo_fit"] = scores.get("solo_fit", 0.0)
        vector["activity.experience_fit"] = max(experience.get("quiet_fit", 0.0), experience.get("walkability", 0.0))
    low_fit_penalty = scores.get("low_fit_penalty", 0.0)
    if scenario == "friend_group" and "karaoke" in markers and "karaoke" in tags:
        low_fit_penalty = 0.0
    vector["activity.low_fit_penalty"] = low_fit_penalty
    if "mall_walk" not in markers:
        vector["activity.mall_dependency_risk"] = risk.get("mall_dependency", 0.0)
    if "light_walk" in markers or avoid_tags & {"movie", "theater", "private_cinema"}:
        vector["activity.movie_dependency_risk"] = risk.get("movie_dependency", 0.0)


def _restaurant_vector(
    vector: Dict[str, float],
    scenario: str,
    markers: set[str],
    scores: Dict[str, float],
    experience: Dict[str, float],
    risk: Dict[str, float],
) -> None:
    vector["restaurant.proper_dining"] = scores.get("proper_dining", 0.0)
    vector["restaurant.casual_penalty"] = scores.get("casual_penalty", 0.0)
    vector["restaurant.experience_fit"] = max(experience.get("dining_substance", 0.0), experience.get("ritual_fit", 0.0))
    vector["restaurant.snack_substitution_risk"] = max(risk.get("snack_substitution", 0.0), risk.get("dinner_substitution", 0.0))
    if scenario == "family_parent_child":
        vector["restaurant.family_fit"] = scores.get("family_fit", 0.0)
        vector["restaurant.experience_fit"] += experience.get("kid_safety", 0.0)
    elif scenario == "anniversary_emotion":
        vector["restaurant.date_fit"] = scores.get("date_fit", 0.0)
        vector["restaurant.experience_fit"] += experience.get("ritual_fit", 0.0)
    elif scenario == "city_light_explore":
        vector["restaurant.visitor_fit"] = scores.get("visitor_fit", 0.0)
        vector["restaurant.experience_fit"] += experience.get("conversation_fit", 0.0)
    elif scenario == "friend_group":
        vector["restaurant.friend_fit"] = scores.get("friend_fit", 0.0)
    if "buffet" in markers:
        vector["restaurant.buffet_fit.required"] = scores.get("buffet_fit", 0.0)
    if markers & {"light_meal", "light_food", "healthy_light"}:
        vector["restaurant.light_meal_fit.required"] = scores.get("light_meal_fit", 0.0)
        vector["restaurant.heavy_meal_risk"] = risk.get("heavy_meal", 0.0)
    if markers & {"beautiful_dining", "quality_dining", "ambience_dining"}:
        vector["restaurant.quality.required"] = scores.get("quality", 0.0)
        vector["restaurant.proper_dining.required"] = scores.get("proper_dining", 0.0)


def _tail_vector(
    vector: Dict[str, float],
    scenario: str,
    scores: Dict[str, float],
    experience: Dict[str, float],
    risk: Dict[str, float],
) -> None:
    if scenario == "family_parent_child":
        vector["tail.family_fit"] = scores.get("family_fit", 0.0)
        vector["tail.experience_fit"] = experience.get("kid_safety", 0.0)
    elif scenario == "anniversary_emotion":
        vector["tail.date_fit"] = scores.get("date_fit", 0.0)
        vector["tail.experience_fit"] = experience.get("ritual_fit", 0.0)
    elif scenario == "city_light_explore":
        vector["tail.visitor_fit"] = scores.get("visitor_fit", 0.0)
        vector["tail.experience_fit"] = max(experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0))
    else:
        vector["tail.solo_fit"] = scores.get("solo_fit", 0.0)
        vector["tail.experience_fit"] = max(experience.get("quiet_fit", 0.0), experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0))
    vector["tail.route_anchor"] = scores.get("route_anchor", 0.0)
    vector["tail.low_fit_penalty"] = scores.get("low_fit_penalty", 0.0)
    vector["risk.intent_mismatch"] = max(vector.get("risk.intent_mismatch", 0.0), risk.get("low_fit_activity", 0.0) * 0.5)


def _numeric_map(value: Any) -> Dict[str, float]:
    return {
        str(key): float(raw)
        for key, raw in (value or {}).items()
        if isinstance(raw, (int, float))
    }


def _queue_pressure_for_case(case: Dict[str, Any], feature: Dict[str, Any], risk: Dict[str, float]) -> float:
    status_signals = feature.get("status_signals") if isinstance(feature, dict) else {}
    profile = (status_signals or {}).get("queue_profile") if isinstance(status_signals, dict) else {}
    segment = str(case.get("queue_segment") or _segment_for_time(case.get("rejected_start_time") or case.get("start_time")) or "")
    if segment and isinstance(profile, dict) and isinstance(profile.get(segment), dict):
        value = profile[segment].get("queue_pressure")
        if isinstance(value, (int, float)):
            return float(value)
    if isinstance(status_signals, dict) and isinstance(status_signals.get("queue_pressure"), (int, float)):
        return float(status_signals.get("queue_pressure") or 0.0)
    return risk.get("queue_pressure", 0.0)


def _segment_for_time(value: Any) -> str:
    if not value:
        return ""
    try:
        hour = datetime.fromisoformat(str(value)).hour
    except (TypeError, ValueError):
        return ""
    if hour < 16:
        return "afternoon"
    if hour < 19:
        return "dinner"
    return "evening"
