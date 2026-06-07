#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402


DEFAULT_OUTPUT = ROOT / "tools" / "rule_evaluation" / "reports" / "recovery_failure_set.json"


SCENARIOS = [
    {
        "case_id": "recovery_failure_family_buffet_capacity",
        "input_text": "这周末想和老婆孩子去游乐园,然后吃一顿自助餐",
        "role": "restaurant",
        "trigger": "NO_TABLE_AVAILABLE",
        "recovery_strategy": "replace_restaurant_same_area",
    },
    {
        "case_id": "recovery_failure_date_japanese_plan_verify",
        "input_text": "周末想和女朋友出去放松一下,晚上想吃日料",
        "role": "restaurant",
        "trigger": "NO_TABLE_AVAILABLE",
        "recovery_strategy": "replace_restaurant_same_area",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export deterministic Recovery failure cases for preference/feature repair import.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("LIFEPILOT_DEMO_NOW", "2026-05-21T13:30:00+08:00")
    os.environ.setdefault("DEEPSEEK_ENABLED", "false")
    os.environ.setdefault("QWEN_ENABLED", "false")
    cases = []
    for index, scenario in enumerate(SCENARIOS, start=1):
        cases.append(run_case(scenario, index))
    failure_cases = [case for case in cases if case.get("failure_reason_code")]
    report = {
        "schema_version": "recovery_failure_set.v1",
        "case_count": len(cases),
        "failure_case_count": len(failure_cases),
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"recovery failure cases: {len(failure_cases)} / {len(cases)}")


def run_case(scenario: Dict[str, Any], index: int) -> Dict[str, Any]:
    data_dir = Path(tempfile.mkdtemp(prefix="lifepilot_recovery_failure_")) / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    api = TestClient(create_app(data_dir))
    trace_id = f"trace_recovery_failure_{index:03d}"
    body = {
        "input_text": scenario["input_text"],
        "use_memory": False,
        "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
        "preferred_start_time": "2026-05-24T14:00:00+08:00",
        "preferred_end_time": "2026-05-24T21:30:00+08:00",
    }
    created = api.post("/api/v1/plans/create", json=body, headers=headers(trace_id, f"idem_{scenario['case_id']}_plan"))
    created.raise_for_status()
    plan = created.json()["data"]["plan_contract"]
    step = target_step(plan, scenario["role"])
    recovered = api.post(
        f"/api/v1/plans/{plan['plan_id']}/recover",
        json={
            "trigger": scenario["trigger"],
            "failed_step_id": step["step_id"],
            "recovery_strategy": scenario["recovery_strategy"],
            "auto_verify": True,
        },
        headers=headers(trace_id, f"idem_{scenario['case_id']}_recover"),
    )
    recovered.raise_for_status()
    recovery_result = recovered.json()["data"]["recovery_result"]
    replacement = recovery_result.get("replacement") or {}
    diff = recovery_result.get("diff") or {}
    diagnostics = diff.get("recovery_diagnostics") or {}
    failure_reason_code = replacement.get("failure_reason_code") or diagnostics.get("failure_reason_code")
    return {
        "case_id": scenario["case_id"],
        "input_text": scenario["input_text"],
        "plan_id": plan.get("plan_id"),
        "scenario": (plan.get("user_goal") or {}).get("scenario"),
        "role": scenario["role"],
        "intent_tags": (plan.get("user_goal") or {}).get("intent_tags") or [],
        "must_have": (plan.get("constraints") or {}).get("must_have") or [],
        "trigger": scenario["trigger"],
        "failed_step_id": step.get("step_id"),
        "failed_poi_id": step.get("poi_id"),
        "failed_title": step.get("title"),
        "recovery_status": recovery_result.get("status"),
        "updated_plan_id": recovery_result.get("updated_plan_id"),
        "failure_reason_code": failure_reason_code,
        "failure_reasons": replacement.get("failure_reasons") or diagnostics.get("failure_reasons") or [],
        "candidate_summary": replacement.get("candidate_summary") or diagnostics.get("candidate_summary") or {},
        "replacement": {
            "poi_id": replacement.get("poi_id"),
            "poi_name": replacement.get("poi_name"),
            "source": replacement.get("source"),
            "relation": replacement.get("relation"),
            "available": replacement.get("available"),
        },
        "verifier_failed_checks": diagnostics.get("verifier_failed_checks") or [],
        "verifier_warnings": diagnostics.get("verifier_warnings") or [],
        "user_visible_reason": replacement.get("user_visible_reason") or diagnostics.get("user_visible_reason") or recovery_result.get("user_explanation"),
    }


def target_step(plan: Dict[str, Any], role: str) -> Dict[str, Any]:
    if role == "restaurant":
        candidates = [step for step in plan.get("timeline") or [] if step.get("type") == "restaurant"]
    else:
        candidates = [step for step in plan.get("timeline") or [] if step.get("type") not in {"transport", "restaurant"}]
    if not candidates:
        raise RuntimeError(f"no target step found for role={role} in plan={plan.get('plan_id')}")
    return candidates[-1]


def headers(trace_id: str, idempotency_key: Optional[str]) -> Dict[str, str]:
    result = {"X-Trace-Id": trace_id}
    if idempotency_key:
        result["X-Idempotency-Key"] = idempotency_key
    return result


if __name__ == "__main__":
    main()
