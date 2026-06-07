#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from ranking_feature_vectors import feature_vector, score  # noqa: E402


DATA_DIR = ROOT / "backend" / "data"
DEFAULT_FAILURE_SET = ROOT / "tools" / "rule_evaluation" / "reports" / "recovery_failure_set.json"
DEFAULT_BASE_DATASET = ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"
DEFAULT_OUTPUT = ROOT / "tools" / "rule_evaluation" / "reports" / "ranking_preference_dataset.recovery_imported.json"
DEFAULT_REPORT = ROOT / "tools" / "rule_evaluation" / "reports" / "recovery_failure_import_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Recovery failure diagnostics into preference pairs and feature correction candidates.")
    parser.add_argument("--failure-set", type=Path, default=DEFAULT_FAILURE_SET)
    parser.add_argument("--base-dataset", type=Path, default=DEFAULT_BASE_DATASET)
    parser.add_argument("--features", type=Path, default=DATA_DIR / "poi_features.json")
    parser.add_argument("--pois", type=Path, default=DATA_DIR / "mock_pois.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    failure_set = read_json(args.failure_set, {"cases": []})
    base_dataset = read_json(args.base_dataset, {"cases": [], "templates": {}})
    features = read_json(args.features, {"features": {}}).get("features", {})
    pois = read_json(args.pois, {"pois": []}).get("pois", [])
    poi_by_id = {str(poi.get("poi_id")): poi for poi in pois if poi.get("poi_id")}

    base_cases = list(base_dataset.get("cases") or [])
    existing_keys = {preference_key(case) for case in base_cases}
    imported = []
    feature_corrections = []
    skipped = []

    for failure_case in failure_set.get("cases") or []:
        corrections = feature_correction_candidates(failure_case)
        feature_corrections.extend(corrections)
        result = import_preferences_from_failure(
            failure_case,
            features,
            poi_by_id,
            existing_keys,
            len(base_cases) + len(imported) + 1,
        )
        imported.extend(result["cases"])
        for case in result["cases"]:
            existing_keys.add(preference_key(case))
        skipped.extend(result["skipped"])

    output_dataset = dict(base_dataset)
    output_dataset["schema_version"] = str(base_dataset.get("schema_version") or "ranking_preferences.v2")
    output_dataset["version"] = str(base_dataset.get("version") or "2026-05-24")
    output_dataset["purpose"] = str(base_dataset.get("purpose") or "Pairwise preference data for calibrating LifePilot POI ranking weights.")
    output_dataset["cases"] = [*base_cases, *imported]
    output_dataset["case_count"] = len(output_dataset["cases"])
    output_dataset.setdefault("templates", dict(base_dataset.get("templates") or {}))
    output_dataset["recovery_failure_import"] = {
        "source_failure_set": rel(args.failure_set),
        "imported_count": len(imported),
        "feature_correction_count": len(feature_corrections),
        "skipped_count": len(skipped),
    }

    report = {
        "schema_version": "recovery_failure_import_report.v1",
        "source_failure_set": rel(args.failure_set),
        "base_dataset": rel(args.base_dataset),
        "output_dataset": rel(args.output),
        "failure_case_count": len(failure_set.get("cases") or []),
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


def import_preferences_from_failure(
    failure_case: Dict[str, Any],
    features: Dict[str, Any],
    poi_by_id: Dict[str, Dict[str, Any]],
    existing_keys: set[tuple[str, str, str, str]],
    next_index: int,
) -> Dict[str, list[Dict[str, Any]]]:
    summary = failure_case.get("candidate_summary") or {}
    preferred_samples = list(summary.get("not_available_samples") or []) + list(summary.get("queue_exceeded_samples") or [])
    rejected_samples = list(summary.get("semantic_mismatch_samples") or [])
    cases = []
    skipped = []
    for preferred in preferred_samples[:4]:
        for rejected in rejected_samples[:4]:
            preferred_id = str(preferred.get("poi_id") or "")
            rejected_id = str(rejected.get("poi_id") or "")
            if not preferred_id or not rejected_id or preferred_id == rejected_id:
                skipped.append(skip(failure_case, "missing_or_same_poi", preferred_poi_id=preferred_id, rejected_poi_id=rejected_id))
                continue
            if preferred_id not in features or rejected_id not in features:
                skipped.append(skip(failure_case, "unknown_poi_id", preferred_poi_id=preferred_id, rejected_poi_id=rejected_id))
                continue
            case = build_preference_case(failure_case, preferred_id, rejected_id, poi_by_id, features, next_index + len(cases))
            key = preference_key(case)
            if key in existing_keys:
                skipped.append(skip(failure_case, "duplicate_preference", preferred_poi_id=preferred_id, rejected_poi_id=rejected_id))
                continue
            preferred_score = score(feature_vector(case, features[preferred_id]))
            rejected_score = score(feature_vector(case, features[rejected_id]))
            if preferred_score <= rejected_score:
                skipped.append(
                    skip(
                        failure_case,
                        "unsupported_by_current_ranker",
                        preferred_poi_id=preferred_id,
                        rejected_poi_id=rejected_id,
                        preferred_score=round(preferred_score, 4),
                        rejected_score=round(rejected_score, 4),
                    )
                )
                continue
            case["preferred_score"] = round(preferred_score, 4)
            case["rejected_score"] = round(rejected_score, 4)
            cases.append(case)
            existing_keys.add(key)
    if not cases and not skipped:
        skipped.append(skip(failure_case, "no_pairwise_samples"))
    return {"cases": cases, "skipped": skipped}


def build_preference_case(
    failure_case: Dict[str, Any],
    preferred_id: str,
    rejected_id: str,
    poi_by_id: Dict[str, Dict[str, Any]],
    features: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    required = list((failure_case.get("candidate_summary") or {}).get("required_semantic_tags") or [])
    intent_tags = list(dict.fromkeys(list(failure_case.get("intent_tags") or []) + list(failure_case.get("must_have") or []) + required))
    return {
        "case_id": f"recovery_pref_{index:03d}",
        "template": "recovery_failure_semantic_guard",
        "source_recovery_case_id": failure_case.get("case_id"),
        "failure_reason_code": failure_case.get("failure_reason_code"),
        "scenario": failure_case.get("scenario"),
        "role": failure_case.get("role") or "restaurant",
        "intent_tags": intent_tags,
        "explicit_markers": required,
        "avoid_tags": ["snack_meal", "casual_chain", "coffee", "dessert"],
        "preferred_poi_id": preferred_id,
        "rejected_poi_id": rejected_id,
        "preferred_title": title_for(preferred_id, poi_by_id, features),
        "rejected_title": title_for(rejected_id, poi_by_id, features),
        "rationale": "Recovery 诊断显示：即使同语义候选当前受资源约束，它仍应优先于语义不匹配的硬替代候选。",
    }


def feature_correction_candidates(failure_case: Dict[str, Any]) -> list[Dict[str, Any]]:
    code = str(failure_case.get("failure_reason_code") or "")
    summary = failure_case.get("candidate_summary") or {}
    required = list(summary.get("required_semantic_tags") or [])
    corrections = []
    if code.startswith("same_semantic_restaurant") or code == "no_same_semantic_restaurant_available":
        corrections.append(
            {
                "case_id": f"{failure_case.get('case_id')}_feature_fix",
                "type": "restaurant_semantic_inventory_or_relation_gap",
                "failure_reason_code": code,
                "source_recovery_case_id": failure_case.get("case_id"),
                "source_poi_id": failure_case.get("failed_poi_id"),
                "required_semantic_tags": required,
                "candidate_summary": {
                    "candidate_count": summary.get("candidate_count"),
                    "relation_edge_candidates": summary.get("relation_edge_candidates"),
                    "semantic_mismatch": summary.get("semantic_mismatch"),
                    "status_checked": summary.get("status_checked"),
                    "not_available": summary.get("not_available"),
                    "queue_exceeded": summary.get("queue_exceeded"),
                },
                "suggested_action": "补充同餐型可用候选、修正 relation_edges，或把资源状态不足作为召回缺口进入后续数据采集。",
            }
        )
    if code == "replacement_plan_weather_failed":
        corrections.append(
            {
                "case_id": f"{failure_case.get('case_id')}_weather_fix",
                "type": "route_weather_risk_training_case",
                "failure_reason_code": code,
                "source_recovery_case_id": failure_case.get("case_id"),
                "source_poi_id": failure_case.get("failed_poi_id"),
                "suggested_action": "在初始候选排序阶段提高中高天气风险下的户外/步道惩罚，减少事后 Recovery 才发现天气失败。",
            }
        )
    return corrections


def preference_key(case: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(case.get("scenario") or ""),
        str(case.get("role") or ""),
        str(case.get("preferred_poi_id") or ""),
        str(case.get("rejected_poi_id") or ""),
    )


def title_for(poi_id: str, poi_by_id: Dict[str, Dict[str, Any]], features: Dict[str, Any]) -> Optional[str]:
    poi = poi_by_id.get(poi_id)
    if poi:
        return str(poi.get("name") or "")
    feature = features.get(poi_id) if isinstance(features, dict) else None
    if isinstance(feature, dict):
        return str(feature.get("name") or "")
    return None


def skip(failure_case: Dict[str, Any], reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {"source_recovery_case_id": failure_case.get("case_id"), "reason": reason}
    payload.update(extra)
    return payload


def summarize_skips(skipped: list[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


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
