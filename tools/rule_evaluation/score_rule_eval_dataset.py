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


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

os.environ["LIFEPILOT_DEMO_NOW"] = "2026-05-21T13:30:00+08:00"
os.environ["QWEN_ENABLED"] = "false"
os.environ["DEEPSEEK_ENABLED"] = "false"

from app.main import create_app  # noqa: E402


DATASET = ROOT / "tools" / "rule_evaluation" / "rule_eval_dataset.json"
REPORT_DIR = ROOT / "tools" / "rule_evaluation" / "reports"
REPORT_PATH = REPORT_DIR / "rule_eval_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score LifePilot rule evaluation dataset against /api/v1/plans/create.")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=REPORT_PATH)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any case fails.")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N cases; 0 disables progress.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    cases = dataset.get("cases") or []
    if args.limit:
        cases = cases[: args.limit]

    with tempfile.TemporaryDirectory(prefix="lifepilot_rule_eval_") as temp_root:
        data_dir = Path(temp_root) / "data"
        shutil.copytree(ROOT / "backend" / "data", data_dir)
        app = create_app(data_dir)
        app.state.container.mock_api_service.logger = None
        client = TestClient(app)
        feature_store = app.state.container.poi_feature_store
        results = []
        for index, case in enumerate(cases, start=1):
            result = score_case(client, feature_store, case, index)
            results.append(result)
            if args.progress_every and index % args.progress_every == 0:
                passed = sum(1 for item in results if item["passed"])
                print(f"progress {index}/{len(cases)}: {passed} passed", flush=True)
            if args.fail_fast and not result["passed"]:
                break

    report = build_report(dataset, results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_summary(report, args.output)
    if args.strict and report["summary"]["pass_rate"] < 1.0:
        raise SystemExit(1)


def score_case(client: TestClient, feature_store: Any, case: Dict[str, Any], index: int) -> Dict[str, Any]:
    case_id = str(case.get("case_id") or f"case_{index}")
    expected = case.get("expected") or {}
    response = client.post(
        "/api/v1/plans/create",
        json=case.get("request_body") or {},
        headers={
            "X-Trace-Id": f"trace_eval_{index:03d}",
            "X-Idempotency-Key": f"idem_eval_{index:03d}_{case_id}",
        },
    )
    if response.status_code != 200:
        return {
            "case_id": case_id,
            "group": case.get("group"),
            "passed": False,
            "checks": {"http_status": False},
            "diagnostics": {"status_code": response.status_code, "body": response.text[:800]},
        }
    payload = response.json()["data"]
    plan = payload["plan_contract"]
    slots = plan_slots(plan, feature_store)
    actual_tags = set(plan.get("user_goal", {}).get("intent_tags") or [])
    actual_tags.update(str(tag) for tag in plan.get("constraints", {}).get("must_have") or [])

    checks = {
        "scenario": plan.get("user_goal", {}).get("scenario") == expected.get("scenario"),
        "party_size": int(plan.get("constraints", {}).get("party_size") or 0) == int(expected.get("party_size") or 0),
        "must_have_tags": set(expected.get("must_have_tags") or []).issubset(actual_tags),
        "activity_slot": slot_matches(slots.get("activity"), expected.get("activity_should_match_any") or []),
        "restaurant_slot": slot_matches(slots.get("restaurant"), expected.get("restaurant_should_match_any") or []),
        "exclusions": not contains_any(plan_text(plan), expected.get("should_exclude_terms") or []),
    }
    return {
        "case_id": case_id,
        "group": case.get("group"),
        "passed": all(checks.values()),
        "checks": checks,
        "diagnostics": {
            "scenario": plan.get("user_goal", {}).get("scenario"),
            "party_size": plan.get("constraints", {}).get("party_size"),
            "missing_tags": sorted(set(expected.get("must_have_tags") or []) - actual_tags),
            "activity": slot_summary(slots.get("activity")),
            "restaurant": slot_summary(slots.get("restaurant")),
            "excluded_terms_found": sorted(term for term in expected.get("should_exclude_terms") or [] if term in plan_text(plan)),
        },
    }


def plan_slots(plan: Dict[str, Any], feature_store: Any) -> Dict[str, Dict[str, Any]]:
    slots: Dict[str, Dict[str, Any]] = {}
    for step in plan.get("timeline") or []:
        step_type = step.get("type")
        if step_type not in {"activity", "restaurant"} or step_type in slots:
            continue
        poi_id = str(step.get("poi_id") or "")
        feature = feature_store.get(poi_id) if poi_id else {}
        tags = set(str(tag) for tag in step.get("display_tags") or [])
        tags.update(str(tag) for tag in feature.get("semantic_tags") or [])
        slots[step_type] = {
            "title": str(step.get("title") or ""),
            "poi_id": poi_id,
            "tags": sorted(tags),
        }
    return slots


def slot_matches(slot: Optional[Dict[str, Any]], expected_any: Iterable[str]) -> bool:
    expected = set(str(tag) for tag in expected_any or [])
    if not expected:
        return True
    if not slot:
        return False
    title = str(slot.get("title") or "")
    tags = set(str(tag) for tag in slot.get("tags") or [])
    if tags & expected:
        return True
    return any(tag in title for tag in expected)


def slot_summary(slot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not slot:
        return {}
    return {
        "title": slot.get("title"),
        "poi_id": slot.get("poi_id"),
        "tags": slot.get("tags"),
    }


def plan_text(plan: Dict[str, Any]) -> str:
    chunks = [json.dumps(plan.get("messages") or {}, ensure_ascii=False)]
    for step in plan.get("timeline") or []:
        chunks.append(str(step.get("title") or ""))
        chunks.append(str(step.get("description") or ""))
        chunks.extend(str(tag) for tag in step.get("display_tags") or [])
    return " ".join(chunks)


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term and term in text for term in terms)


def build_report(dataset: Dict[str, Any], results: list[Dict[str, Any]]) -> Dict[str, Any]:
    groups = sorted(set(str(result.get("group")) for result in results))
    by_group = {}
    for group in groups:
        group_results = [result for result in results if str(result.get("group")) == group]
        by_group[group] = summarize(group_results)
    return {
        "schema_version": "rule_eval_report.v1",
        "dataset_version": dataset.get("version"),
        "case_count": len(results),
        "summary": summarize(results),
        "groups": by_group,
        "failures": [result for result in results if not result["passed"]],
    }


def summarize(results: list[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    check_names = sorted({name for result in results for name in result.get("checks", {})})
    checks = {}
    for name in check_names:
        checks[name] = {
            "passed": sum(1 for result in results if result.get("checks", {}).get(name) is True),
            "total": total,
            "rate": round(sum(1 for result in results if result.get("checks", {}).get(name) is True) / total, 4) if total else 0.0,
        }
    return {
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "checks": checks,
    }


def print_summary(report: Dict[str, Any], output: Path) -> None:
    summary = report["summary"]
    print(f"scored {summary['total']} cases: {summary['passed']} passed, pass_rate={summary['pass_rate']}")
    for name, item in summary["checks"].items():
        print(f"- {name}: {item['passed']}/{item['total']} ({item['rate']})")
    print(f"report: {output}")


if __name__ == "__main__":
    main()
