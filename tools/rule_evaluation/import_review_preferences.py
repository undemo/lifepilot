#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"
DEFAULT_REVIEW_SET = ROOT / "tools" / "rule_evaluation" / "reports" / "plan_review_set.json"
DEFAULT_BASE_DATASET = ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"
DEFAULT_OUTPUT = ROOT / "tools" / "rule_evaluation" / "reports" / "ranking_preference_dataset.review_imported.json"
DEFAULT_REPORT = ROOT / "tools" / "rule_evaluation" / "reports" / "review_preference_import_report.json"

VALID_ROLES = {"activity", "restaurant", "tail", "service", "walk"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import ready pairwise preferences from plan_review_set into a ranking preference dataset.")
    parser.add_argument("--review-set", type=Path, default=DEFAULT_REVIEW_SET)
    parser.add_argument("--base-dataset", type=Path, default=DEFAULT_BASE_DATASET)
    parser.add_argument("--features", type=Path, default=DATA_DIR / "poi_features.json")
    parser.add_argument("--pois", type=Path, default=DATA_DIR / "mock_pois.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    review_set = read_json(args.review_set, {"cases": []})
    base_dataset = read_json(args.base_dataset, {"cases": [], "templates": {}})
    features = read_json(args.features, {"features": {}}).get("features", {})
    pois = read_json(args.pois, {"pois": []}).get("pois", [])
    poi_by_id = {str(poi.get("poi_id")): poi for poi in pois if poi.get("poi_id")}

    base_cases = list(base_dataset.get("cases") or [])
    existing_keys = {
        preference_key(case)
        for case in base_cases
        if case.get("preferred_poi_id") and case.get("rejected_poi_id")
    }

    imported = []
    skipped = []
    for review_case in review_set.get("cases") or []:
        result = import_candidate(review_case, features, poi_by_id, existing_keys, len(base_cases) + len(imported) + 1)
        if result.get("case"):
            imported.append(result["case"])
            existing_keys.add(preference_key(result["case"]))
        else:
            skipped.append(result["skip"])

    output_dataset = dict(base_dataset)
    output_dataset["schema_version"] = "ranking_preferences.v1"
    output_dataset["version"] = str(base_dataset.get("version") or "2026-05-24")
    output_dataset["purpose"] = str(base_dataset.get("purpose") or "Pairwise preference data for calibrating LifePilot POI ranking weights.")
    output_dataset["cases"] = [*base_cases, *imported]
    output_dataset["case_count"] = len(output_dataset["cases"])
    output_dataset.setdefault("templates", dict(base_dataset.get("templates") or {}))
    output_dataset["review_import"] = {
        "source_review_set": rel(args.review_set),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
    }

    report = {
        "schema_version": "review_preference_import_report.v1",
        "source_review_set": rel(args.review_set),
        "base_dataset": rel(args.base_dataset),
        "output_dataset": rel(args.output),
        "review_case_count": len(review_set.get("cases") or []),
        "base_case_count": len(base_cases),
        "imported_count": len(imported),
        "output_case_count": len(output_dataset["cases"]),
        "skipped_summary": summarize_skips(skipped),
        "imported": imported,
        "skipped": skipped,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"wrote {args.report}")
    print(f"imported {len(imported)} preferences; skipped {len(skipped)} review cases")


def import_candidate(
    review_case: Dict[str, Any],
    features: Dict[str, Any],
    poi_by_id: Dict[str, Dict[str, Any]],
    existing_keys: set[tuple[str, str, str, str]],
    next_index: int,
) -> Dict[str, Any]:
    source_case_id = str(review_case.get("case_id") or "")
    suggestion = review_case.get("suggested_pairwise_preference") or {}
    if not isinstance(suggestion, dict) or not suggestion.get("ready_for_import"):
        return {"skip": skip(source_case_id, "not_ready_for_import")}

    preferred_id = str(suggestion.get("preferred_poi_id") or "").strip()
    rejected_id = str(suggestion.get("rejected_poi_id") or "").strip()
    role = str(suggestion.get("role") or "").strip()
    reason = str(suggestion.get("reason") or "").strip()
    scenario = str(review_case.get("scenario") or "")
    if role not in VALID_ROLES:
        return {"skip": skip(source_case_id, "invalid_role", role=role)}
    if not preferred_id or not rejected_id:
        return {"skip": skip(source_case_id, "missing_poi_id")}
    if preferred_id == rejected_id:
        return {"skip": skip(source_case_id, "same_preferred_and_rejected", poi_id=preferred_id)}
    if preferred_id not in features or rejected_id not in features:
        return {"skip": skip(source_case_id, "unknown_poi_id", preferred_poi_id=preferred_id, rejected_poi_id=rejected_id)}
    if not reason:
        return {"skip": skip(source_case_id, "missing_reason")}

    case = {
        "case_id": f"review_pref_{next_index:03d}",
        "template": "plan_review_import",
        "source_review_case_id": source_case_id,
        "source_plan_id": review_case.get("plan_id"),
        "scenario": scenario,
        "role": role,
        "intent_tags": review_case.get("intent_tags") or [],
        "preferred_poi_id": preferred_id,
        "rejected_poi_id": rejected_id,
        "preferred_title": title_for(preferred_id, poi_by_id, features),
        "rejected_title": title_for(rejected_id, poi_by_id, features),
        "rationale": reason,
    }
    key = preference_key(case)
    if key in existing_keys:
        return {"skip": skip(source_case_id, "duplicate_preference", preferred_poi_id=preferred_id, rejected_poi_id=rejected_id, role=role)}
    return {"case": case}


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


def skip(source_case_id: str, reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {"source_review_case_id": source_case_id, "reason": reason}
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
