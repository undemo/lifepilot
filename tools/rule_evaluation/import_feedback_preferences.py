#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from ranking_feature_vectors import feature_vector, score  # noqa: E402


DATA_DIR = ROOT / "backend" / "data"
DEFAULT_FEEDBACK = DATA_DIR / "feedback.json"
DEFAULT_PLANS = DATA_DIR / "plans.json"
DEFAULT_BASE_DATASET = ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"
DEFAULT_OUTPUT = ROOT / "tools" / "rule_evaluation" / "reports" / "ranking_preference_dataset.feedback_imported.json"
DEFAULT_REPORT = ROOT / "tools" / "rule_evaluation" / "reports" / "feedback_import_report.json"

OPTION_ISSUES = {
    "queue": "queue_pressure",
    "queue_too_long": "queue_pressure",
    "restaurant": "restaurant_fit",
    "restaurant_not_good": "restaurant_fit",
    "too_rushed": "route_tempo",
    "distance": "route_tempo",
    "child_bored": "activity_interest",
    "child_not_interested": "activity_interest",
    "budget": "budget_fit",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert user feedback into ranking preferences and feature correction candidates.")
    parser.add_argument("--feedback", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--plans", type=Path, default=DEFAULT_PLANS)
    parser.add_argument("--base-dataset", type=Path, default=DEFAULT_BASE_DATASET)
    parser.add_argument("--features", type=Path, default=DATA_DIR / "poi_features.json")
    parser.add_argument("--pois", type=Path, default=DATA_DIR / "mock_pois.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    feedback_document = read_json(args.feedback, {"feedback": {}})
    plans = read_json(args.plans, {"plans": {}}).get("plans") or {}
    base_dataset = read_json(args.base_dataset, {"cases": [], "templates": {}})
    features = read_json(args.features, {"features": {}}).get("features", {})
    pois = read_json(args.pois, {"pois": []}).get("pois", [])
    poi_by_id = {str(poi.get("poi_id")): poi for poi in pois if poi.get("poi_id")}
    feedback_records = list((feedback_document.get("feedback") or {}).values())

    base_cases = list(base_dataset.get("cases") or [])
    existing_keys = {preference_key(case) for case in base_cases}
    imported: list[Dict[str, Any]] = []
    feature_corrections: list[Dict[str, Any]] = []
    skipped: list[Dict[str, Any]] = []

    for record in feedback_records:
        result = import_feedback_record(
            record,
            plans,
            features,
            poi_by_id,
            existing_keys,
            len(base_cases) + len(imported) + 1,
        )
        imported.extend(result["cases"])
        feature_corrections.extend(result["feature_corrections"])
        skipped.extend(result["skipped"])
        for case in result["cases"]:
            existing_keys.add(preference_key(case))

    output_dataset = dict(base_dataset)
    output_dataset["schema_version"] = str(base_dataset.get("schema_version") or "ranking_preferences.v2")
    output_dataset["version"] = str(base_dataset.get("version") or "2026-05-24")
    output_dataset["purpose"] = str(base_dataset.get("purpose") or "Pairwise preference data for calibrating LifePilot POI ranking weights.")
    output_dataset["cases"] = [*base_cases, *imported]
    output_dataset["case_count"] = len(output_dataset["cases"])
    output_dataset.setdefault("templates", dict(base_dataset.get("templates") or {}))
    output_dataset["feedback_import"] = {
        "source_feedback": rel(args.feedback),
        "imported_count": len(imported),
        "feature_correction_count": len(feature_corrections),
        "skipped_count": len(skipped),
    }

    negative_count = sum(1 for record in feedback_records if extract_issues(record))
    report = {
        "schema_version": "feedback_import_report.v1",
        "source_feedback": rel(args.feedback),
        "source_plans": rel(args.plans),
        "base_dataset": rel(args.base_dataset),
        "output_dataset": rel(args.output),
        "feedback_count": len(feedback_records),
        "negative_signal_count": negative_count,
        "base_case_count": len(base_cases),
        "imported_count": len(imported),
        "feature_correction_count": len(feature_corrections),
        "output_case_count": len(output_dataset["cases"]),
        "skipped_summary": summarize_skips(skipped),
        "feature_corrections": feature_corrections,
        "imported": imported,
        "skipped": skipped,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"wrote {args.report}")
    print(f"imported {len(imported)} preferences; feature corrections {len(feature_corrections)}; skipped {len(skipped)}")


def import_feedback_record(
    record: Dict[str, Any],
    plans: Dict[str, Any],
    features: Dict[str, Any],
    poi_by_id: Dict[str, Dict[str, Any]],
    existing_keys: set[tuple[str, str, str, str]],
    next_index: int,
) -> Dict[str, list[Dict[str, Any]]]:
    feedback_id = str(record.get("feedback_id") or "")
    plan_id = str(record.get("plan_id") or "")
    issues = extract_issues(record)
    if not issues:
        return {"cases": [], "feature_corrections": [], "skipped": [skip(feedback_id, "no_negative_signal")]}
    plan = plans.get(plan_id)
    if not isinstance(plan, dict):
        return {
            "cases": [],
            "feature_corrections": [feature_correction(record, None, issues, "missing_plan")],
            "skipped": [skip(feedback_id, "missing_plan", plan_id=plan_id)],
        }

    imported: list[Dict[str, Any]] = []
    skipped: list[Dict[str, Any]] = []
    corrections = [feature_correction(record, plan, issues, "feedback_signal")]
    for issue in issues:
        rejected_slots = affected_slots(plan, issue)
        if not rejected_slots:
            skipped.append(skip(feedback_id, "no_affected_slot", issue=issue))
            continue
        for slot in rejected_slots:
            rejected_id = str(slot.get("poi_id") or "")
            if rejected_id not in features:
                mapped = resolve_stale_slot(slot, plan, features)
                if not mapped:
                    skipped.append(skip(feedback_id, "rejected_poi_not_in_feature_store", issue=issue, rejected_poi_id=rejected_id))
                    corrections.append(feature_correction(record, plan, [issue], "stale_or_external_poi", affected_poi_id=rejected_id))
                    continue
                slot = dict(slot)
                slot["source_poi_id"] = rejected_id
                slot["poi_id"] = mapped["poi_id"]
                slot["mapping_confidence"] = mapped["confidence"]
                slot["mapping_reason"] = mapped["reason"]
                corrections.append(
                    feature_correction(
                        record,
                        plan,
                        [issue],
                        "mapped_stale_poi",
                        affected_poi_id=rejected_id,
                        mapped_poi_id=mapped["poi_id"],
                        mapping_confidence=mapped["confidence"],
                        mapping_reason=mapped["reason"],
                    )
                )
                rejected_id = str(slot.get("poi_id") or "")
            candidates = preferred_candidates(plan, slot, issue, features, poi_by_id)
            if not candidates:
                skipped.append(skip(feedback_id, "no_preferred_candidate", issue=issue, rejected_poi_id=rejected_id))
                continue
            for preferred_id in candidates[:3]:
                case = build_preference_case(record, plan, issue, slot, preferred_id, features, poi_by_id, next_index + len(imported))
                key = preference_key(case)
                if key in existing_keys:
                    skipped.append(skip(feedback_id, "duplicate_preference", issue=issue, preferred_poi_id=preferred_id, rejected_poi_id=rejected_id))
                    continue
                preferred_score = score(feature_vector(case, features[preferred_id]))
                rejected_score = score(feature_vector(case, features[rejected_id]))
                if preferred_score <= rejected_score:
                    skipped.append(
                        skip(
                            feedback_id,
                            "unsupported_by_current_ranker",
                            issue=issue,
                            preferred_poi_id=preferred_id,
                            rejected_poi_id=rejected_id,
                            preferred_score=round(preferred_score, 4),
                            rejected_score=round(rejected_score, 4),
                        )
                    )
                    continue
                case["preferred_score"] = round(preferred_score, 4)
                case["rejected_score"] = round(rejected_score, 4)
                imported.append(case)
                existing_keys.add(key)
                break
    return {"cases": imported, "feature_corrections": dedupe_corrections(corrections), "skipped": skipped}


def extract_issues(record: Dict[str, Any]) -> list[str]:
    text = str(record.get("free_text") or "")
    options = [str(item) for item in record.get("selected_options") or []]
    issues = [OPTION_ISSUES[item] for item in options if item in OPTION_ISSUES]
    if any(token in text for token in ("排队", "等太久", "少排队", "不想排")):
        issues.append("queue_pressure")
    if any(token in text for token in ("餐厅不", "不好吃", "吃的不", "自助不像", "不是自助")):
        issues.append("restaurant_fit")
    if any(token in text for token in ("太赶", "太远", "走太多", "折腾")):
        issues.append("route_tempo")
    if any(token in text for token in ("孩子无聊", "孩子不", "小朋友不")):
        issues.append("activity_interest")
    if str(record.get("rating") or "") in {"bad", "poor", "not_good"} and not issues:
        issues.append("overall_fit")
    return list(dict.fromkeys(issues))


def affected_slots(plan: Dict[str, Any], issue: str) -> list[Dict[str, Any]]:
    slots = [
        step
        for step in plan.get("timeline") or []
        if step.get("type") in {"activity", "restaurant", "walk", "service"} and step.get("poi_id")
    ]
    if issue == "restaurant_fit":
        return [step for step in slots if step.get("type") == "restaurant"]
    if issue == "activity_interest":
        return [step for step in slots if step.get("type") == "activity"]
    if issue == "route_tempo":
        return [step for step in slots if step.get("type") in {"walk", "service"}]
    if issue == "queue_pressure":
        warned_ids = {
            str(check.get("related_poi_id"))
            for check in (plan.get("verifier_result") or {}).get("checks") or []
            if check.get("name") in {"queue_time", "restaurant_capacity", "activity_ticket"} and check.get("status") != "pass"
        }
        if warned_ids:
            return [step for step in slots if str(step.get("poi_id")) in warned_ids]
        return [step for step in slots if step.get("type") in {"restaurant", "activity"}]
    return slots[:1]


def preferred_candidates(
    plan: Dict[str, Any],
    rejected_slot: Dict[str, Any],
    issue: str,
    features: Dict[str, Any],
    poi_by_id: Dict[str, Dict[str, Any]],
) -> list[str]:
    rejected_id = str(rejected_slot.get("poi_id") or "")
    rejected = features.get(rejected_id) or {}
    rejected_tags = set(str(tag) for tag in rejected.get("semantic_tags") or [])
    rejected_queue_pressure = queue_pressure_for_slot(rejected, rejected_slot)
    scenario = str((plan.get("user_goal") or {}).get("scenario") or "")
    role = role_for_step(rejected_slot)
    intent_tags = set(str(tag) for tag in (plan.get("user_goal") or {}).get("intent_tags") or [])
    intent_tags.update(str(tag) for tag in (plan.get("constraints") or {}).get("must_have") or [])
    rows = []
    for poi_id, feature in features.items():
        if str(poi_id) == rejected_id or not role_category_matches(role, str(feature.get("category") or "")):
            continue
        tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
        if scenario and scenario not in tags:
            continue
        if issue == "queue_pressure":
            candidate_queue_pressure = queue_pressure_for_slot(feature, rejected_slot)
            if candidate_queue_pressure >= rejected_queue_pressure - 0.02:
                continue
            if not (tags & intent_tags or tags & rejected_tags & {"restaurant", "food", "light_meal", "family_friendly", "date_friendly", "group_ok", "child_friendly", "quiet_stay"}):
                continue
        elif issue == "restaurant_fit":
            if not tags & {"proper_dining", "slow_dining", "quality_dining", "light_meal", "family_friendly", "date_friendly", "group_ok"}:
                continue
            if tags & {"snack_meal", "casual_chain"} and not rejected_tags & {"snack_meal", "casual_chain"}:
                continue
        elif issue == "activity_interest":
            if not tags & {"child_friendly", "kid_safe", "family_time", "hands_on", "craft", "amusement", "quiet_stay"}:
                continue
        else:
            if not tags & {"rain_safe", "indoor", "quiet_stay", "coffee", "dessert", "route_simple"}:
                continue
        poi = poi_by_id.get(str(poi_id), {})
        same_area_bonus = 0.08 if (poi.get("area") and poi.get("area") == (poi_by_id.get(rejected_id, {}).get("area"))) else 0.0
        base_score = score(feature_vector(preference_probe(plan, issue, role), feature))
        queue_bonus = 0.0
        if issue == "queue_pressure":
            queue_bonus = (rejected_queue_pressure - queue_pressure_for_slot(feature, rejected_slot)) * 80.0
        rows.append((base_score + same_area_bonus + queue_bonus, str(poi_id)))
    return [poi_id for _, poi_id in sorted(rows, reverse=True)]


def resolve_stale_slot(slot: Dict[str, Any], plan: Dict[str, Any], features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    role = role_for_step(slot)
    scenario = str((plan.get("user_goal") or {}).get("scenario") or "")
    title = str(slot.get("title") or "")
    display_tags = set(str(tag) for tag in slot.get("display_tags") or [])
    title_norm = normalize_text(title)
    query_tokens = semantic_tokens(title, display_tags)
    rows = []
    for poi_id, feature in features.items():
        category = str(feature.get("category") or "")
        if not role_category_matches(role, category):
            continue
        tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
        if scenario and scenario not in tags:
            continue
        name = str(feature.get("name") or "")
        name_norm = normalize_text(name)
        if not name_norm:
            continue
        text_score = SequenceMatcher(None, title_norm, name_norm).ratio() if title_norm else 0.0
        if title_norm and (title_norm in name_norm or name_norm in title_norm):
            text_score = max(text_score, 0.72)
        target_tokens = semantic_tokens(name, tags)
        token_score = len(query_tokens & target_tokens) / max(len(query_tokens), 1)
        tag_score = len(display_tags & tags) / max(len(display_tags), 1)
        score_value = text_score * 0.48 + token_score * 0.34 + tag_score * 0.18 + domain_adjustment(query_tokens, target_tokens)
        if score_value <= 0:
            continue
        rows.append((score_value, text_score, token_score, tag_score, str(poi_id), name))
    if not rows:
        return None
    score_value, text_score, token_score, tag_score, poi_id, name = sorted(rows, reverse=True)[0]
    if score_value < 0.32:
        return None
    return {
        "poi_id": poi_id,
        "confidence": round(score_value, 4),
        "reason": {
            "source_title": title,
            "mapped_title": name,
            "text_score": round(text_score, 4),
            "token_score": round(token_score, 4),
            "tag_score": round(tag_score, 4),
        },
    }


def build_preference_case(
    record: Dict[str, Any],
    plan: Dict[str, Any],
    issue: str,
    rejected_slot: Dict[str, Any],
    preferred_id: str,
    features: Dict[str, Any],
    poi_by_id: Dict[str, Dict[str, Any]],
    index: int,
) -> Dict[str, Any]:
    rejected_id = str(rejected_slot.get("poi_id") or "")
    role = role_for_step(rejected_slot)
    intent_tags = list(dict.fromkeys(list((plan.get("user_goal") or {}).get("intent_tags") or []) + list((plan.get("constraints") or {}).get("must_have") or [])))
    explicit_markers = ["low_queue", "queue"] if issue == "queue_pressure" else []
    avoid_tags = ["queue_risk", "long_queue"] if issue == "queue_pressure" else ["snack_meal", "casual_chain", "low_fit_activity"]
    case = {
        "case_id": f"feedback_pref_{index:03d}",
        "template": "feedback_import",
        "source_feedback_id": record.get("feedback_id"),
        "source_plan_id": record.get("plan_id"),
        "feedback_issue": issue,
        "scenario": (plan.get("user_goal") or {}).get("scenario"),
        "role": role,
        "rejected_start_time": rejected_slot.get("start_time"),
        "intent_tags": intent_tags,
        "explicit_markers": explicit_markers,
        "avoid_tags": avoid_tags,
        "preferred_poi_id": preferred_id,
        "rejected_poi_id": rejected_id,
        "source_rejected_poi_id": rejected_slot.get("source_poi_id"),
        "rejected_mapping_confidence": rejected_slot.get("mapping_confidence"),
        "preferred_title": title_for(preferred_id, poi_by_id, features),
        "rejected_title": rejected_slot.get("title") or title_for(rejected_id, poi_by_id, features),
        "rationale": feedback_rationale(issue),
    }
    if issue == "queue_pressure":
        preferred_feature = features.get(preferred_id) or {}
        rejected_feature = features.get(rejected_id) or {}
        case.update(
            {
                "queue_segment": segment_for_time(rejected_slot.get("start_time")),
                "preferred_queue_pressure": round(queue_pressure_for_slot(preferred_feature, rejected_slot), 4),
                "rejected_queue_pressure": round(queue_pressure_for_slot(rejected_feature, rejected_slot), 4),
            }
        )
    return case


def preference_probe(plan: Dict[str, Any], issue: str, role: str) -> Dict[str, Any]:
    intent_tags = list((plan.get("user_goal") or {}).get("intent_tags") or []) + list((plan.get("constraints") or {}).get("must_have") or [])
    explicit_markers = ["low_queue", "queue"] if issue == "queue_pressure" else []
    return {
        "scenario": (plan.get("user_goal") or {}).get("scenario"),
        "role": role,
        "intent_tags": list(dict.fromkeys(intent_tags + explicit_markers)),
        "explicit_markers": explicit_markers,
        "avoid_tags": ["queue_risk", "long_queue"] if issue == "queue_pressure" else [],
    }


def queue_pressure_for_slot(feature: Dict[str, Any], slot: Dict[str, Any]) -> float:
    status_signals = feature.get("status_signals") if isinstance(feature, dict) else {}
    profile = (status_signals or {}).get("queue_profile") if isinstance(status_signals, dict) else {}
    segment = segment_for_time(slot.get("start_time"))
    if segment and isinstance(profile, dict) and isinstance(profile.get(segment), dict):
        return float(profile[segment].get("queue_pressure") or 0.0)
    if isinstance(status_signals, dict) and isinstance(status_signals.get("queue_pressure"), (int, float)):
        return float(status_signals.get("queue_pressure") or 0.0)
    return numeric_map(feature.get("risk_scores")).get("queue_pressure", 0.0)


def segment_for_time(value: Any) -> str:
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


def feature_correction(
    record: Dict[str, Any],
    plan: Optional[Dict[str, Any]],
    issues: Iterable[str],
    correction_type: str,
    **extra: Any,
) -> Dict[str, Any]:
    slots = []
    if isinstance(plan, dict):
        for step in plan.get("timeline") or []:
            if step.get("type") in {"activity", "restaurant", "walk", "service"}:
                slots.append({
                    "type": step.get("type"),
                    "poi_id": step.get("poi_id"),
                    "title": step.get("title"),
                    "display_tags": step.get("display_tags") or [],
                })
    payload = {
        "case_id": f"{record.get('feedback_id')}_{correction_type}",
        "type": correction_type,
        "source_feedback_id": record.get("feedback_id"),
        "source_plan_id": record.get("plan_id"),
        "rating": record.get("rating"),
        "selected_options": record.get("selected_options") or [],
        "free_text": record.get("free_text") or "",
        "issues": list(issues),
        "affected_slots": slots,
        "suggested_action": suggested_action(list(issues), correction_type),
    }
    payload.update(extra)
    return payload


def suggested_action(issues: list[str], correction_type: str) -> str:
    if correction_type == "mapped_stale_poi":
        return "反馈引用旧计划 POI，已按名称/标签/角色映射到当前 feature store；需要人工抽检映射是否准确。"
    if correction_type == "stale_or_external_poi":
        return "反馈引用的计划 POI 不在当前 feature store 中，需要保留为数据版本/特征库存修正，避免静默丢弃用户负反馈。"
    if "queue_pressure" in issues:
        return "将少排队反馈转成低队列偏好，优先补齐 queue_risk / low_queue 特征和运行时状态采样。"
    if "restaurant_fit" in issues:
        return "将餐厅不合适反馈转成餐饮语义/氛围/正餐程度修正，必要时补充同语义替代候选。"
    if "activity_interest" in issues:
        return "将活动兴趣不足反馈转成同行关系和活动类型偏好修正。"
    return "保留反馈作为人工或 AI judge 可审计的推荐质量修正样本。"


def feedback_rationale(issue: str) -> str:
    if issue == "queue_pressure":
        return "用户反馈希望少排队；低排队风险候选应优先于静态或运行时排队风险更高的当前节点。"
    if issue == "restaurant_fit":
        return "用户反馈餐厅不合适；更贴近正餐/场景语义的候选应优先于当前餐厅。"
    if issue == "activity_interest":
        return "用户反馈活动兴趣不足；更贴合同行关系和活动类型的候选应优先。"
    return "用户负反馈表明当前节点体验不佳，应优先更稳妥的替代候选。"


def role_for_step(step: Dict[str, Any]) -> str:
    if step.get("type") == "restaurant":
        return "restaurant"
    if step.get("type") == "activity":
        return "activity"
    return "tail"


def role_category_matches(role: str, category: str) -> bool:
    if role == "restaurant":
        return category == "restaurant"
    if role == "activity":
        return category in {"activity", "walk_spot", "service"}
    return category in {"activity", "walk_spot", "restaurant", "service"}


def title_for(poi_id: str, poi_by_id: Dict[str, Dict[str, Any]], features: Dict[str, Any]) -> Optional[str]:
    poi = poi_by_id.get(poi_id)
    if poi:
        return str(poi.get("name") or "")
    feature = features.get(poi_id) if isinstance(features, dict) else None
    if isinstance(feature, dict):
        return str(feature.get("name") or "")
    return None


def preference_key(case: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(case.get("scenario") or ""),
        str(case.get("role") or ""),
        str(case.get("preferred_poi_id") or ""),
        str(case.get("rejected_poi_id") or ""),
    )


def numeric_map(value: Any) -> Dict[str, float]:
    return {
        str(key): float(raw)
        for key, raw in (value or {}).items()
        if isinstance(raw, (int, float))
    }


def normalize_text(value: str) -> str:
    drop = set(" \t\r\n·・'\"‘’“”（）()[]【】<>《》,，.。:：;；-—_/|+&")
    return "".join(ch.lower() for ch in str(value or "") if ch not in drop)


def semantic_tokens(title: str, tags: Iterable[str]) -> set[str]:
    text = str(title or "")
    tokens = {str(tag) for tag in tags if str(tag)}
    aliases = {
        "coffee": "咖啡",
        "light_meal": "轻食",
        "light_food": "轻食",
        "quiet_stay": "安静",
        "quiet_alone": "安静",
        "work_friendly": "阅读",
        "pet_friendly": "宠物",
        "rain_safe": "避雨",
        "indoor": "室内",
    }
    tokens.update(alias for tag, alias in aliases.items() if tag in tokens)
    known = (
        "金沙湖",
        "下沙",
        "高教园",
        "宝龙",
        "银泰",
        "天街",
        "湖畔",
        "雨歇",
        "咖啡",
        "轻食",
        "阅读",
        "静读",
        "静音",
        "萌宠",
        "宠物",
        "室内",
        "地下",
        "连廊",
        "连通",
        "林荫",
        "休息",
        "广场",
        "公园",
    )
    tokens.update(token for token in known if token in text)
    normalized = normalize_text(text)
    if normalized:
        tokens.update(normalized[index : index + 2] for index in range(max(0, len(normalized) - 1)))
    return tokens


def domain_adjustment(query_tokens: set[str], target_tokens: set[str]) -> float:
    adjustment = 0.0
    for token in ("咖啡", "轻食", "阅读", "宠物", "室内", "避雨"):
        if token not in query_tokens:
            continue
        adjustment += 0.12 if token in target_tokens else -0.08
    return adjustment


def skip(feedback_id: str, reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {"source_feedback_id": feedback_id, "reason": reason}
    payload.update(extra)
    return payload


def summarize_skips(skipped: list[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


def dedupe_corrections(corrections: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    seen = set()
    result = []
    for item in corrections:
        key = (item.get("case_id"), item.get("type"), item.get("affected_poi_id"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
