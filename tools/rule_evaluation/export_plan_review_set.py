#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from fastapi.testclient import TestClient

from plan_quality import auto_quality_review, summarize_auto_quality


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

os.environ["LIFEPILOT_DEMO_NOW"] = "2026-05-21T13:30:00+08:00"
os.environ["QWEN_ENABLED"] = "false"
os.environ["DEEPSEEK_ENABLED"] = "false"

from app.main import create_app  # noqa: E402


DEFAULT_DATASET = ROOT / "tools" / "rule_evaluation" / "rule_eval_dataset.json"
DEFAULT_OUTPUT = ROOT / "tools" / "rule_evaluation" / "reports" / "plan_review_set.json"


REVIEW_DIMENSIONS = [
    {
        "key": "intent_fit",
        "scale": "1-5",
        "meaning": "方案是否真正贴合用户原始意图，而不是只命中关键词。",
    },
    {
        "key": "activity_fit",
        "scale": "1-5",
        "meaning": "活动槽是否符合同行关系、情绪目标、强度和场景。",
    },
    {
        "key": "restaurant_fit",
        "scale": "1-5",
        "meaning": "餐饮槽是否符合明说菜系/餐型/氛围/预算，不用伪正餐替代。",
    },
    {
        "key": "route_fit",
        "scale": "1-5",
        "meaning": "转场是否短、顺、符合时间窗和用户对折腾程度的要求。",
    },
    {
        "key": "product_delight",
        "scale": "1-5",
        "meaning": "这个方案是否有产品体验上的惊喜感和可执行感。",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export generated LifePilot plans for human or AI recommendation review.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--group", default="", help="Optional group filter, e.g. family_parent_child.")
    parser.add_argument("--progress-every", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = dataset.get("cases") or []
    if args.group:
        cases = [case for case in cases if str(case.get("group")) == args.group]
    if args.limit:
        cases = cases[: args.limit]

    with tempfile.TemporaryDirectory(prefix="lifepilot_plan_review_") as temp_root:
        data_dir = Path(temp_root) / "data"
        shutil.copytree(ROOT / "backend" / "data", data_dir)
        app = create_app(data_dir)
        app.state.container.mock_api_service.logger = None
        client = TestClient(app)
        feature_store = app.state.container.poi_feature_store
        review_cases = []
        failures = []
        for index, case in enumerate(cases, start=1):
            item = export_case(client, feature_store, case, index)
            if item.get("http_status") == 200:
                review_cases.append(item)
            else:
                failures.append(item)
            if args.progress_every and index % args.progress_every == 0:
                print(f"progress {index}/{len(cases)} exported={len(review_cases)} failures={len(failures)}", flush=True)

    document = {
        "schema_version": "plan_review_set.v1",
        "version": "2026-05-24",
        "source_dataset": str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset),
        "purpose": "Human or AI review of actual generated plans, focused on product-level recommendation quality.",
        "review_dimensions": REVIEW_DIMENSIONS,
        "review_guidance": [
            "Evaluate the generated plan as a user-facing product answer, not as code.",
            "A high score requires intent fit, slot fit, route plausibility, and no obvious substitution such as buns for buffet.",
            "If a better POI is obvious, fill suggested_pairwise_preference so it can be converted into ranking preference data.",
        ],
        "case_count": len(review_cases),
        "failure_count": len(failures),
        "auto_quality_summary": summarize_auto_quality(review_cases),
        "cases": review_cases,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({len(review_cases)} cases, {len(failures)} failures)")


def export_case(client: TestClient, feature_store: Any, case: Dict[str, Any], index: int) -> Dict[str, Any]:
    case_id = str(case.get("case_id") or f"case_{index:03d}")
    response = client.post(
        "/api/v1/plans/create",
        json=case.get("request_body") or {},
        headers={
            "X-Trace-Id": f"trace_review_{index:03d}",
            "X-Idempotency-Key": f"idem_review_{index:03d}_{case_id}",
        },
    )
    if response.status_code != 200:
        return {
            "case_id": case_id,
            "group": case.get("group"),
            "http_status": response.status_code,
            "error": response.text[:1200],
        }
    payload = response.json()["data"]
    plan = payload["plan_contract"]
    review_case = {
        "case_id": case_id,
        "group": case.get("group"),
        "difficulty": case.get("difficulty"),
        "input_text": (case.get("request_body") or {}).get("input_text"),
        "expected": case.get("expected"),
        "http_status": 200,
        "plan_id": plan.get("plan_id"),
        "scenario": (plan.get("user_goal") or {}).get("scenario"),
        "intent_tags": (plan.get("user_goal") or {}).get("intent_tags") or [],
        "constraints": compact_constraints(plan.get("constraints") or {}),
        "budget": plan.get("budget"),
        "verifier_result": plan.get("verifier_result"),
        "timeline": timeline_summary(plan, feature_store),
        "route_summary": route_summary(plan),
        "user_messages": plan.get("messages") or {},
        "review_form": empty_review_form(),
        "suggested_pairwise_preference": {
            "preferred_poi_id": None,
            "rejected_poi_id": None,
            "role": None,
            "reason": None,
            "ready_for_import": False,
        },
    }
    review_case["auto_quality_review"] = auto_quality_review(review_case)
    return review_case


def compact_constraints(constraints: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "party_size",
        "budget_max_per_person",
        "walking_tolerance",
        "queue_tolerance",
        "must_have",
        "must_not_have",
        "preferred_area",
        "planning_start_time",
        "planning_end_time",
    ]
    return {key: constraints.get(key) for key in keys if key in constraints}


def timeline_summary(plan: Dict[str, Any], feature_store: Any) -> list[Dict[str, Any]]:
    rows = []
    for step in plan.get("timeline") or []:
        row = {
            "type": step.get("type"),
            "title": step.get("title"),
            "start_time": step.get("start_time"),
            "end_time": step.get("end_time"),
            "duration_minutes": step.get("duration_minutes"),
            "display_tags": step.get("display_tags") or [],
            "user_visible_notes": step.get("user_visible_notes") or step.get("description"),
        }
        poi_id = step.get("poi_id")
        if poi_id:
            feature = feature_store.get(str(poi_id))
            row["poi_id"] = poi_id
            row["semantic_tags"] = sorted(set(str(tag) for tag in feature.get("semantic_tags") or []))
            row["feature_scores"] = compact_feature_scores(feature.get("scores") or {})
        if step.get("estimated_route"):
            route = step["estimated_route"]
            row["route"] = {
                "from_poi_id": route.get("origin_poi_id"),
                "to_poi_id": route.get("destination_poi_id"),
                "distance_km": route.get("distance_km"),
                "duration_minutes": route.get("duration_minutes"),
                "transport_mode": route.get("transport_mode"),
            }
        rows.append(row)
    return rows


def compact_feature_scores(scores: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "quality",
        "family_fit",
        "date_fit",
        "friend_fit",
        "solo_fit",
        "visitor_fit",
        "route_anchor",
        "proper_dining",
        "buffet_fit",
        "amusement_fit",
        "light_meal_fit",
        "low_fit_penalty",
        "casual_penalty",
    ]
    return {key: scores.get(key) for key in keys if key in scores}


def route_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    route_steps = [
        step.get("estimated_route") or {}
        for step in plan.get("timeline") or []
        if step.get("type") == "transport"
    ]
    return {
        "route_count": len(route_steps),
        "total_distance_km": round(sum(float(route.get("distance_km") or 0) for route in route_steps), 3),
        "total_duration_minutes": sum(int(route.get("duration_minutes") or 0) for route in route_steps),
    }


def empty_review_form() -> Dict[str, Any]:
    return {
        "reviewer": None,
        "scores": {item["key"]: None for item in REVIEW_DIMENSIONS},
        "overall_pass": None,
        "major_issue": None,
        "comments": None,
    }


if __name__ == "__main__":
    main()
