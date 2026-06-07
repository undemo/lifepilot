from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


PRODUCT_REVIEW_SCHEMA_VERSION = "auto_plan_quality.v1"


CRITICAL_PENALTY = 44
MAJOR_PENALTY = 18
WARNING_PENALTY = 8
MINOR_PENALTY = 4


def auto_quality_review(review_case: Dict[str, Any]) -> Dict[str, Any]:
    """Score a generated plan as a product recommendation, not just a tag hit.

    This is intentionally deterministic and conservative. It does not replace
    human review; it catches obvious plan-level failures before reviewers spend
    time on cases that should never pass a product-quality gate.
    """

    expected = review_case.get("expected") or {}
    timeline = review_case.get("timeline") or []
    constraints = review_case.get("constraints") or {}
    intent_tags = set(str(tag) for tag in review_case.get("intent_tags") or [])
    must_have = set(str(tag) for tag in constraints.get("must_have") or [])
    activity = _first_step(timeline, "activity")
    restaurant = _first_step(timeline, "restaurant")
    poi_steps = [step for step in timeline if step.get("type") != "transport"]
    issues: list[Dict[str, Any]] = []
    slot_checks: Dict[str, Any] = {}

    def add_issue(code: str, severity: str, penalty: int, message: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        issues.append(
            {
                "code": code,
                "severity": severity,
                "penalty": penalty,
                "message": message,
                "evidence": evidence or {},
            }
        )

    expected_scenario = expected.get("scenario")
    slot_checks["scenario_match"] = not expected_scenario or review_case.get("scenario") == expected_scenario
    if not slot_checks["scenario_match"]:
        add_issue(
            "scenario_mismatch",
            "critical",
            CRITICAL_PENALTY,
            "场景识别和评测期望不一致。",
            {"expected": expected_scenario, "actual": review_case.get("scenario")},
        )

    expected_tags = set(str(tag) for tag in expected.get("must_have_tags") or [])
    visible_tags = intent_tags | must_have
    missing_tags = sorted(expected_tags - visible_tags)
    slot_checks["must_have_tags_match"] = not missing_tags
    if missing_tags:
        add_issue(
            "missing_intent_tags",
            "critical",
            CRITICAL_PENALTY,
            "用户明说或评测要求的核心意图没有进入约束层。",
            {"missing": missing_tags},
        )

    activity_expected = [str(tag) for tag in expected.get("activity_should_match_any") or []]
    if activity_expected:
        if not activity:
            slot_checks["activity_slot_match"] = False
            add_issue("missing_activity", "major", MAJOR_PENALTY, "方案缺少活动槽。")
        else:
            slot_checks["activity_slot_match"] = _matches_any(activity, activity_expected)
            if not slot_checks["activity_slot_match"]:
                add_issue(
                    "activity_slot_miss",
                    "critical",
                    CRITICAL_PENALTY,
                    "活动槽没有命中用户真正要的活动类型。",
                    _slot_evidence(activity, activity_expected),
                )
    else:
        slot_checks["activity_slot_match"] = True

    restaurant_expected = [str(tag) for tag in expected.get("restaurant_should_match_any") or []]
    if restaurant_expected:
        if not restaurant:
            slot_checks["restaurant_slot_match"] = False
            add_issue("missing_restaurant", "critical", CRITICAL_PENALTY, "方案缺少餐饮槽。")
        else:
            slot_checks["restaurant_slot_match"] = _matches_any(restaurant, restaurant_expected)
            if not slot_checks["restaurant_slot_match"]:
                add_issue(
                    "restaurant_slot_miss",
                    "critical",
                    CRITICAL_PENALTY + 6,
                    "餐饮槽没有命中用户明说的餐型、菜系或菜品。",
                    _slot_evidence(restaurant, restaurant_expected),
                )
            _check_restaurant_substitution(restaurant, restaurant_expected, add_issue)
    else:
        slot_checks["restaurant_slot_match"] = True

    excluded_terms = [str(term) for term in expected.get("should_exclude_terms") or []]
    title_blob = " ".join(str(step.get("title") or "") for step in poi_steps)
    hit_exclusions = sorted(term for term in excluded_terms if term and term in title_blob)
    slot_checks["exclusions_absent"] = not hit_exclusions
    if hit_exclusions:
        add_issue(
            "excluded_term_present",
            "critical",
            CRITICAL_PENALTY,
            "方案包含了用户场景下应排除的明显不合适地点。",
            {"terms": hit_exclusions},
        )

    expected_order = expected.get("timeline_order")
    slot_checks["timeline_order_match"] = _timeline_order_matches(poi_steps, expected_order)
    if not slot_checks["timeline_order_match"]:
        add_issue(
            "timeline_order_miss",
            "major",
            MAJOR_PENALTY,
            "方案顺序没有符合餐饮/活动的时间意图。",
            {"expected": expected_order, "actual": [step.get("type") for step in poi_steps]},
        )

    scenario = str(review_case.get("scenario") or "")
    if activity:
        activity_tags = _step_tags(activity)
        if scenario in {"family_parent_child", "anniversary_emotion", "city_light_explore"} and "low_fit_activity" in activity_tags:
            add_issue(
                "low_fit_activity",
                "major",
                MAJOR_PENALTY + 6,
                "活动槽属于当前关系/场景下的低适配活动。",
                _slot_evidence(activity, []),
            )

    _check_solo_mood_arc(review_case, constraints, activity, restaurant, poi_steps, add_issue)
    _check_restaurant_first_request_order(constraints, poi_steps, add_issue)
    _check_post_meal_conversation_order(review_case, constraints, poi_steps, add_issue)
    _check_route_quality(review_case, constraints, add_issue)
    _check_experience_arc(poi_steps, scenario, add_issue)

    score = max(0, 100 - sum(int(issue["penalty"]) for issue in issues))
    critical_count = sum(1 for issue in issues if issue["severity"] == "critical")
    major_count = sum(1 for issue in issues if issue["severity"] == "major")
    decision = "pass" if score >= 70 and critical_count == 0 else "fail"
    return {
        "schema_version": PRODUCT_REVIEW_SCHEMA_VERSION,
        "score": score,
        "grade": _grade(score, critical_count),
        "decision": decision,
        "critical_issue_count": critical_count,
        "major_issue_count": major_count,
        "slot_checks": slot_checks,
        "issues": issues,
    }


def summarize_auto_quality(cases: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    reviews = [
        case.get("auto_quality_review") or auto_quality_review(case)
        for case in cases
        if isinstance(case, dict)
    ]
    scores = [int(review.get("score") or 0) for review in reviews]
    issue_counts: Dict[str, int] = {}
    for review in reviews:
        for issue in review.get("issues") or []:
            code = str(issue.get("code") or "unknown")
            issue_counts[code] = issue_counts.get(code, 0) + 1
    return {
        "schema_version": PRODUCT_REVIEW_SCHEMA_VERSION,
        "case_count": len(reviews),
        "passed": sum(1 for review in reviews if review.get("decision") == "pass"),
        "failed": sum(1 for review in reviews if review.get("decision") != "pass"),
        "min_score": min(scores) if scores else None,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "critical_issue_count": sum(int(review.get("critical_issue_count") or 0) for review in reviews),
        "major_issue_count": sum(int(review.get("major_issue_count") or 0) for review in reviews),
        "issue_counts": dict(sorted(issue_counts.items())),
    }


def _first_step(timeline: list[Dict[str, Any]], step_type: str) -> Optional[Dict[str, Any]]:
    return next((step for step in timeline if step.get("type") == step_type), None)


def _matches_any(step: Dict[str, Any], expected: Iterable[str]) -> bool:
    tags = _step_tags(step)
    text = _step_text(step)
    for value in expected:
        token = str(value)
        if token in tags or token in text:
            return True
    return False


def _step_tags(step: Dict[str, Any]) -> set[str]:
    tags = set(str(tag) for tag in step.get("display_tags") or [])
    tags.update(str(tag) for tag in step.get("semantic_tags") or [])
    return tags


def _step_text(step: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(step.get("title") or ""),
            str(step.get("user_visible_notes") or ""),
            " ".join(str(tag) for tag in step.get("display_tags") or []),
            " ".join(str(tag) for tag in step.get("semantic_tags") or []),
        ]
    )


def _slot_evidence(step: Dict[str, Any], expected: Iterable[str]) -> Dict[str, Any]:
    return {
        "title": step.get("title"),
        "expected_any": list(expected),
        "display_tags": step.get("display_tags") or [],
        "semantic_tags": step.get("semantic_tags") or [],
    }


def _timeline_order_matches(poi_steps: list[Dict[str, Any]], expected_order: Any) -> bool:
    if not expected_order or not poi_steps:
        return True
    types = [str(step.get("type") or "") for step in poi_steps]
    if expected_order == "dinner_last":
        return types[-1] == "restaurant"
    if expected_order == "restaurant_first":
        return types[0] == "restaurant"
    if expected_order == "activity_first":
        return types[0] == "activity"
    return True


def _check_restaurant_substitution(
    restaurant: Dict[str, Any],
    expected: Iterable[str],
    add_issue: Any,
) -> None:
    expected_tags = set(str(tag) for tag in expected)
    tags = _step_tags(restaurant)
    identity_text = _step_identity_text(restaurant)
    serious_dining = {
        "buffet",
        "quality_dining",
        "beautiful_dining",
        "western_cuisine",
        "steak",
        "cuisine_japanese",
        "sushi",
        "izakaya",
        "bbq",
        "grill",
        "lamb",
        "hotpot",
    }
    if expected_tags & serious_dining and tags & {"snack_meal", "casual_chain", "low_end_chain"} and not tags & expected_tags:
        add_issue(
            "pseudo_restaurant_substitution",
            "major",
            MAJOR_PENALTY + 8,
            "用户要的是明确餐型/菜系，但餐厅槽看起来像小吃、快餐或低仪式感替代。",
            _slot_evidence(restaurant, expected_tags),
        )
    if "buffet" in expected_tags and any(token in identity_text for token in ("包子", "馒头", "牛肉汤", "面馆", "小吃")):
        add_issue(
            "buffet_replaced_by_snack",
            "critical",
            CRITICAL_PENALTY + 10,
            "自助餐诉求被小吃/简餐替代。",
            _slot_evidence(restaurant, expected_tags),
        )
    if expected_tags & serious_dining and tags & {"coffee", "dessert", "quiet_stay"} and not tags & {"proper_dining", "slow_dining", "light_meal"}:
        add_issue(
            "drink_or_dessert_as_meal",
            "major",
            MAJOR_PENALTY + 4,
            "餐饮槽像饮品甜品停靠点，不像正餐。",
            _slot_evidence(restaurant, expected_tags),
        )


def _check_route_quality(review_case: Dict[str, Any], constraints: Dict[str, Any], add_issue: Any) -> None:
    route = review_case.get("route_summary") or {}
    minutes = int(route.get("total_duration_minutes") or 0)
    distance = float(route.get("total_distance_km") or 0)
    must_have = set(str(tag) for tag in constraints.get("must_have") or [])
    route_sensitive = bool(must_have & {"nearby", "route_simple", "area_jinshahu", "area_xiasha", "area_gaojiao"})
    if minutes > 90 or distance > 6.5:
        add_issue(
            "route_too_long",
            "major",
            MAJOR_PENALTY,
            "整体转场过长，会明显伤害产品体验。",
            {"total_duration_minutes": minutes, "total_distance_km": distance},
        )
    elif minutes > 60 or distance > 4.5:
        add_issue(
            "route_long_warning",
            "warning",
            WARNING_PENALTY,
            "整体转场偏长，人工 review 时应重点看是否值得。",
            {"total_duration_minutes": minutes, "total_distance_km": distance},
        )
    elif route_sensitive and minutes > 38:
        add_issue(
            "route_simple_not_compact",
            "warning",
            WARNING_PENALTY,
            "用户有短转场/区域偏好，但方案转场不够紧凑。",
            {"total_duration_minutes": minutes, "total_distance_km": distance},
        )


def _check_solo_mood_arc(
    review_case: Dict[str, Any],
    constraints: Dict[str, Any],
    activity: Optional[Dict[str, Any]],
    restaurant: Optional[Dict[str, Any]],
    poi_steps: list[Dict[str, Any]],
    add_issue: Any,
) -> None:
    if str(review_case.get("scenario") or "") != "fallback_unknown" or int(constraints.get("party_size") or 1) != 1:
        return
    must_have = set(str(tag) for tag in constraints.get("must_have") or [])
    explicit_food_or_drink = bool(must_have & {"dinner", "proper_dining", "explicit_dining", "coffee", "alcohol", "light_drink", "buffet", "hotpot", "bbq", "grill", "cuisine_japanese", "sushi", "izakaya"})
    explicit_music = bool(must_have & {"music", "acoustic_music"})
    low_pressure_anchor_tags = {"lake", "park", "light_walk", "quiet_stay", "coffee", "music", "acoustic_music", "theater", "private_cinema"}
    if activity and not explicit_food_or_drink:
        activity_tags = _step_tags(activity)
        if activity_tags & {"food", "restaurant", "proper_dining", "casual_chain", "snack_meal", "spicy_heavy", "hotpot", "bbq", "grill"} and not activity_tags & {"coffee", "dessert", "quiet_stay"}:
            add_issue(
                "solo_food_as_activity",
                "major",
                MAJOR_PENALTY + 10,
                "单人散心活动槽被错类餐饮或小吃占用。",
                _slot_evidence(activity, low_pressure_anchor_tags),
            )
        if not activity_tags & low_pressure_anchor_tags:
            add_issue(
                "solo_low_pressure_anchor_miss",
                "major",
                MAJOR_PENALTY + 8,
                "单人散心方案没有命中低压力散步、安静停留或音乐空间。",
                _slot_evidence(activity, low_pressure_anchor_tags),
            )
    if restaurant and not explicit_food_or_drink:
        restaurant_tags = _step_tags(restaurant)
        if restaurant_tags & {"proper_dining", "casual_chain", "low_end_chain", "snack_meal", "spicy_heavy"} and not restaurant_tags & {"coffee", "dessert", "quiet_stay", "lake", "park"}:
            add_issue(
                "solo_forced_meal",
                "major",
                MAJOR_PENALTY + 10,
                "用户只是一个人散心/走走，方案却强塞了正餐或低仪式感餐饮。",
                _slot_evidence(restaurant, []),
            )
    if not explicit_food_or_drink and not explicit_music:
        foodish_steps = [
            step
            for step in poi_steps
            if step.get("type") in {"restaurant", "service"} or _step_tags(step) & {"coffee", "dessert", "food", "restaurant", "proper_dining", "snack_meal"}
        ]
        if len(foodish_steps) >= 2:
            add_issue(
                "solo_food_stop_repetition",
                "warning",
                WARNING_PENALTY,
                "单人低压力散心不应被多个餐饮/饮品停靠点稀释。",
                {"titles": [step.get("title") for step in foodish_steps]},
            )


def _check_post_meal_conversation_order(
    review_case: Dict[str, Any],
    constraints: Dict[str, Any],
    poi_steps: list[Dict[str, Any]],
    add_issue: Any,
) -> None:
    must_have = set(str(tag) for tag in constraints.get("must_have") or [])
    input_text = str(review_case.get("input_text") or "")
    text_has_post_meal_chat = any(token in input_text for token in ("饭后", "餐后", "吃完饭", "吃完晚饭", "吃好饭")) and any(
        token in input_text for token in ("聊天", "坐着聊", "聊一聊", "坐坐", "坐一会", "待一会")
    )
    if "post_meal_conversation" not in must_have and not text_has_post_meal_chat:
        return
    restaurant_indexes = [index for index, step in enumerate(poi_steps) if step.get("type") == "restaurant"]
    if not restaurant_indexes:
        add_issue(
            "post_meal_order_miss",
            "major",
            MAJOR_PENALTY,
            "用户明确要求饭后再坐着聊，但方案没有先安排正餐。",
            {"types": [step.get("type") for step in poi_steps]},
        )
        return
    first_restaurant_index = restaurant_indexes[0]
    if first_restaurant_index != 0:
        add_issue(
            "post_meal_order_miss",
            "major",
            MAJOR_PENALTY,
            "用户明确要求饭后再坐着聊，但方案把聊天/活动排在正餐前。",
            {"types": [step.get("type") for step in poi_steps]},
        )
    social_after_meal = any(_looks_like_chat_stop(step) for step in poi_steps[first_restaurant_index + 1 :])
    if not social_after_meal:
        add_issue(
            "post_meal_chat_stop_missing",
            "major",
            MAJOR_PENALTY,
            "用户明确要求饭后找地方坐着聊，但正餐后缺少低噪声停留点。",
            {"titles": [step.get("title") for step in poi_steps]},
        )


def _check_restaurant_first_request_order(
    constraints: Dict[str, Any],
    poi_steps: list[Dict[str, Any]],
    add_issue: Any,
) -> None:
    must_have = set(str(tag) for tag in constraints.get("must_have") or [])
    if "restaurant_first_request" not in must_have or "post_meal_conversation" in must_have:
        return
    if not poi_steps or poi_steps[0].get("type") != "restaurant":
        add_issue(
            "restaurant_first_order_miss",
            "major",
            MAJOR_PENALTY,
            "用户明确要求先吃饭或饭后再活动，但方案没有把正餐排在第一站。",
            {"types": [step.get("type") for step in poi_steps]},
        )


def _check_experience_arc(poi_steps: list[Dict[str, Any]], scenario: str, add_issue: Any) -> None:
    if not poi_steps:
        add_issue("empty_timeline", "critical", CRITICAL_PENALTY, "方案没有可执行 POI 节点。")
        return
    if len(poi_steps) == 1 and scenario != "fallback_unknown":
        add_issue(
            "thin_plan",
            "warning",
            WARNING_PENALTY,
            "方案只有一个 POI 节点，产品体验偏薄。",
            {"types": [step.get("type") for step in poi_steps]},
        )
    if scenario in {"family_parent_child", "anniversary_emotion", "city_light_explore"}:
        categories = [str(step.get("type") or "") for step in poi_steps]
        if "activity" not in categories or "restaurant" not in categories:
            add_issue(
                "missing_core_arc",
                "major",
                MAJOR_PENALTY,
                "当前场景应同时有活动和餐饮，方案体验链路不完整。",
                {"types": categories},
            )


def _grade(score: int, critical_count: int) -> str:
    if critical_count:
        return "fail"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 70:
        return "pass"
    if score >= 60:
        return "watch"
    return "fail"


def _step_identity_text(step: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(step.get("title") or ""),
            " ".join(str(tag) for tag in step.get("display_tags") or []),
            " ".join(str(tag) for tag in step.get("semantic_tags") or []),
        ]
    )


def _looks_like_chat_stop(step: Dict[str, Any]) -> bool:
    tags = _step_tags(step)
    text = _step_text(step)
    return bool(tags & {"coffee", "dessert", "quiet_stay", "conversation", "lake", "park"}) or any(
        token in text for token in ("聊天", "坐着聊", "坐坐", "安静", "低噪声", "咖啡", "甜品", "湖", "公园")
    )
