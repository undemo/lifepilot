#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from plan_quality import summarize_auto_quality


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "tools" / "rule_evaluation" / "reports"
DEFAULT_OUTPUT = REPORT_DIR / "recommendation_quality_gate.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full LifePilot recommendation quality gate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--skip-p0", action="store_true", help="Skip scripts/run_backend_p0_tests.py. Use only for local iteration.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": "backend",
            "LIFEPILOT_DEMO_NOW": "2026-05-21T13:30:00+08:00",
            "DEEPSEEK_ENABLED": "false",
            "QWEN_ENABLED": "false",
        }
    )
    steps = [
        ("build_poi_features", [sys.executable, "tools/rule_evaluation/build_poi_features.py"]),
        ("generate_rule_eval_dataset", [sys.executable, "tools/rule_evaluation/generate_rule_eval_dataset.py"]),
        ("generate_ranking_preference_dataset", [sys.executable, "tools/rule_evaluation/generate_ranking_preference_dataset.py"]),
        ("calibrate_ranker_weights", [sys.executable, "tools/rule_evaluation/calibrate_ranker_weights.py"]),
        (
            "score_rule_eval_dataset",
            [
                sys.executable,
                "tools/rule_evaluation/score_rule_eval_dataset.py",
                "--progress-every",
                str(max(0, args.progress_every)),
            ],
        ),
        (
            "export_plan_review_set",
            [
                sys.executable,
                "tools/rule_evaluation/export_plan_review_set.py",
                "--progress-every",
                str(max(0, args.progress_every)),
            ],
        ),
        ("import_review_preferences", [sys.executable, "tools/rule_evaluation/import_review_preferences.py"]),
        (
            "validate_review_imported_preferences",
            [
                sys.executable,
                "tools/rule_evaluation/calibrate_ranker_weights.py",
                "--dataset",
                "tools/rule_evaluation/reports/ranking_preference_dataset.review_imported.json",
                "--output",
                "tools/rule_evaluation/reports/recommendation_ranker_weights.review_imported.json",
            ],
        ),
        ("export_recovery_failure_set", [sys.executable, "tools/rule_evaluation/export_recovery_failure_set.py"]),
        ("import_recovery_failure_preferences", [sys.executable, "tools/rule_evaluation/import_recovery_failure_preferences.py"]),
        (
            "validate_recovery_imported_preferences",
            [
                sys.executable,
                "tools/rule_evaluation/calibrate_ranker_weights.py",
                "--dataset",
                "tools/rule_evaluation/reports/ranking_preference_dataset.recovery_imported.json",
                "--output",
                "tools/rule_evaluation/reports/recommendation_ranker_weights.recovery_imported.json",
            ],
        ),
        ("import_feedback_preferences", [sys.executable, "tools/rule_evaluation/import_feedback_preferences.py"]),
        (
            "validate_feedback_imported_preferences",
            [
                sys.executable,
                "tools/rule_evaluation/calibrate_ranker_weights.py",
                "--dataset",
                "tools/rule_evaluation/reports/ranking_preference_dataset.feedback_imported.json",
                "--output",
                "tools/rule_evaluation/reports/recommendation_ranker_weights.feedback_imported.json",
            ],
        ),
    ]
    if not args.skip_p0:
        steps.append(("backend_p0_tests", [sys.executable, "scripts/run_backend_p0_tests.py"]))

    step_results = []
    for name, command in steps:
        result = run_step(name, command, env)
        step_results.append(result)
        print(f"{name}: {'PASS' if result['exit_code'] == 0 else 'FAIL'} ({result['duration_seconds']}s)", flush=True)
        if result["exit_code"] != 0:
            break

    artifacts = collect_artifacts()
    checks = build_checks(step_results, artifacts, skip_p0=args.skip_p0)
    report = {
        "schema_version": "recommendation_quality_gate.v1",
        "generated_at": "2026-05-24T00:00:00+08:00",
        "status": "pass" if all(item["passed"] for item in checks) else "fail",
        "checks": checks,
        "steps": step_results,
        "artifacts": artifacts,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {args.output}")
    print(f"quality_gate: {report['status'].upper()}")
    if report["status"] != "pass":
        raise SystemExit(1)


def run_step(name: str, command: list[str], env: Dict[str, str]) -> Dict[str, Any]:
    started = time.time()
    process = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "name": name,
        "command": command,
        "exit_code": process.returncode,
        "duration_seconds": round(time.time() - started, 3),
        "stdout_tail": tail(process.stdout),
        "stderr_tail": tail(process.stderr),
    }


def collect_artifacts() -> Dict[str, Any]:
    artifacts = {
        "poi_features": feature_summary(ROOT / "backend" / "data" / "poi_features.json"),
        "ranking_preferences": case_count_summary(ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"),
        "ranker_weights": ranker_weight_summary(ROOT / "backend" / "data" / "recommendation_ranker_weights.json"),
        "rule_eval_report": rule_eval_summary(REPORT_DIR / "rule_eval_report.json"),
        "plan_review_set": plan_review_summary(REPORT_DIR / "plan_review_set.json"),
        "review_preference_import": review_import_summary(REPORT_DIR / "review_preference_import_report.json"),
        "review_imported_ranker_weights": ranker_weight_summary(REPORT_DIR / "recommendation_ranker_weights.review_imported.json"),
        "recovery_failure_set": recovery_failure_set_summary(REPORT_DIR / "recovery_failure_set.json"),
        "recovery_failure_import": recovery_import_summary(REPORT_DIR / "recovery_failure_import_report.json"),
        "recovery_imported_ranker_weights": ranker_weight_summary(REPORT_DIR / "recommendation_ranker_weights.recovery_imported.json"),
        "feedback_import": feedback_import_summary(REPORT_DIR / "feedback_import_report.json"),
        "feedback_imported_ranker_weights": ranker_weight_summary(REPORT_DIR / "recommendation_ranker_weights.feedback_imported.json"),
        "backend_p0_tests": p0_summary(ROOT / "reports" / "backend_p0_tests.json"),
    }
    return artifacts


def build_checks(step_results: list[Dict[str, Any]], artifacts: Dict[str, Any], *, skip_p0: bool) -> list[Dict[str, Any]]:
    rule_eval = artifacts["rule_eval_report"]
    review_set = artifacts["plan_review_set"]
    ranker = artifacts["ranker_weights"]
    import_report = artifacts["review_preference_import"]
    review_ranker = artifacts["review_imported_ranker_weights"]
    recovery_set = artifacts["recovery_failure_set"]
    recovery_import = artifacts["recovery_failure_import"]
    recovery_ranker = artifacts["recovery_imported_ranker_weights"]
    feedback_import = artifacts["feedback_import"]
    feedback_ranker = artifacts["feedback_imported_ranker_weights"]
    p0 = artifacts["backend_p0_tests"]
    checks = [
        {
            "name": "all_steps_exit_zero",
            "passed": all(step["exit_code"] == 0 for step in step_results),
            "details": {step["name"]: step["exit_code"] for step in step_results},
        },
        {
            "name": "poi_features_present",
            "passed": int(artifacts["poi_features"].get("feature_count") or 0) > 0,
            "details": artifacts["poi_features"],
        },
        {
            "name": "ranker_preferences_perfect",
            "passed": is_perfect_pair_accuracy(ranker),
            "details": ranker,
        },
        {
            "name": "rule_eval_perfect",
            "passed": rule_eval.get("passed") == rule_eval.get("total") and int(rule_eval.get("total") or 0) > 0,
            "details": rule_eval,
        },
        {
            "name": "plan_review_export_complete",
            "passed": review_set.get("case_count") == rule_eval.get("total") and review_set.get("failure_count") == 0,
            "details": review_set,
        },
        {
            "name": "plan_review_auto_quality_pass",
            "passed": (
                review_set.get("auto_quality", {}).get("failed") == 0
                and int(review_set.get("auto_quality", {}).get("case_count") or 0) > 0
                and int(review_set.get("auto_quality", {}).get("min_score") or 0) >= 70
                and int(review_set.get("auto_quality", {}).get("critical_issue_count") or 0) == 0
            ),
            "details": review_set.get("auto_quality"),
        },
        {
            "name": "review_import_safe",
            "passed": import_report.get("output_case_count", 0) >= import_report.get("base_case_count", 0),
            "details": import_report,
        },
        {
            "name": "review_imported_preferences_valid",
            "passed": is_perfect_pair_accuracy(review_ranker),
            "details": review_ranker,
        },
        {
            "name": "recovery_failure_set_exported",
            "passed": int(recovery_set.get("failure_case_count") or 0) > 0,
            "details": recovery_set,
        },
        {
            "name": "recovery_failure_import_actionable",
            "passed": int(recovery_import.get("imported_count") or 0) > 0 and int(recovery_import.get("feature_correction_count") or 0) > 0,
            "details": recovery_import,
        },
        {
            "name": "recovery_imported_preferences_valid",
            "passed": is_perfect_pair_accuracy(recovery_ranker),
            "details": recovery_ranker,
        },
        {
            "name": "feedback_import_actionable",
            "passed": (
                int(feedback_import.get("negative_signal_count") or 0) > 0
                and (
                    int(feedback_import.get("imported_count") or 0) > 0
                    or int(feedback_import.get("feature_correction_count") or 0) > 0
                )
            ),
            "details": feedback_import,
        },
        {
            "name": "feedback_imported_preferences_valid",
            "passed": is_perfect_pair_accuracy(feedback_ranker),
            "details": feedback_ranker,
        },
    ]
    if not skip_p0:
        checks.append(
            {
                "name": "backend_p0_pass",
                "passed": p0.get("failed") == 0 and int(p0.get("total") or 0) > 0,
                "details": p0,
            }
        )
    return checks


def is_perfect_pair_accuracy(summary: Dict[str, Any]) -> bool:
    pair_accuracy = summary.get("pair_accuracy") or {}
    return pair_accuracy.get("passed") == pair_accuracy.get("total") and int(pair_accuracy.get("total") or 0) > 0


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def feature_summary(path: Path) -> Dict[str, Any]:
    document = read_json(path, {})
    return {
        "schema_version": document.get("schema_version"),
        "feature_count": document.get("feature_count") or len(document.get("features") or {}),
    }


def case_count_summary(path: Path) -> Dict[str, Any]:
    document = read_json(path, {})
    return {
        "schema_version": document.get("schema_version"),
        "case_count": document.get("case_count") or len(document.get("cases") or []),
    }


def ranker_weight_summary(path: Path) -> Dict[str, Any]:
    document = read_json(path, {})
    training = document.get("training_summary") or {}
    return {
        "schema_version": document.get("schema_version"),
        "preference_case_count": training.get("preference_case_count"),
        "pair_accuracy": training.get("pair_accuracy"),
        "adjustments_applied": training.get("adjustments_applied"),
        "weight_count": len(document.get("weights") or {}),
    }


def rule_eval_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    summary = report.get("summary") or {}
    return {
        "schema_version": report.get("schema_version"),
        "passed": summary.get("passed"),
        "total": summary.get("total"),
        "pass_rate": summary.get("pass_rate"),
        "failure_count": len(report.get("failures") or []),
    }


def plan_review_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    auto_quality = report.get("auto_quality_summary")
    if not auto_quality and isinstance(report.get("cases"), list):
        auto_quality = summarize_auto_quality(report.get("cases") or [])
    return {
        "schema_version": report.get("schema_version"),
        "case_count": report.get("case_count"),
        "failure_count": report.get("failure_count"),
        "review_dimensions": [item.get("key") for item in report.get("review_dimensions") or []],
        "auto_quality": auto_quality or {},
    }


def review_import_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    return {
        "schema_version": report.get("schema_version"),
        "base_case_count": report.get("base_case_count"),
        "imported_count": report.get("imported_count"),
        "output_case_count": report.get("output_case_count"),
        "skipped_summary": report.get("skipped_summary"),
    }


def recovery_failure_set_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    return {
        "schema_version": report.get("schema_version"),
        "case_count": report.get("case_count"),
        "failure_case_count": report.get("failure_case_count"),
        "failure_reason_codes": sorted(
            {
                str(case.get("failure_reason_code"))
                for case in report.get("cases") or []
                if case.get("failure_reason_code")
            }
        ),
    }


def recovery_import_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    return {
        "schema_version": report.get("schema_version"),
        "base_case_count": report.get("base_case_count"),
        "imported_count": report.get("imported_count"),
        "feature_correction_count": report.get("feature_correction_count"),
        "output_case_count": report.get("output_case_count"),
        "skipped_summary": report.get("skipped_summary"),
    }


def feedback_import_summary(path: Path) -> Dict[str, Any]:
    report = read_json(path, {})
    return {
        "schema_version": report.get("schema_version"),
        "feedback_count": report.get("feedback_count"),
        "negative_signal_count": report.get("negative_signal_count"),
        "base_case_count": report.get("base_case_count"),
        "imported_count": report.get("imported_count"),
        "feature_correction_count": report.get("feature_correction_count"),
        "output_case_count": report.get("output_case_count"),
        "skipped_summary": report.get("skipped_summary"),
    }


def p0_summary(path: Path) -> Dict[str, Any]:
    results = read_json(path, [])
    if not isinstance(results, list):
        return {"total": 0, "failed": 1}
    failed = [item for item in results if not item.get("passed")]
    return {"total": len(results), "failed": len(failed), "failed_names": [item.get("name") for item in failed]}


def tail(text: str, *, max_lines: int = 20, max_chars: int = 4000) -> str:
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    result = "\n".join(lines[-max_lines:])
    return result[-max_chars:]


if __name__ == "__main__":
    main()
