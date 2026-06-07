#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rules.ranking_weights import DEFAULT_RANKING_WEIGHTS, SCHEMA_VERSION  # noqa: E402
from ranking_feature_vectors import feature_vector, score  # noqa: E402


DATA_DIR = ROOT / "backend" / "data"
DEFAULT_DATASET = ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"
DEFAULT_OUTPUT = DATA_DIR / "recommendation_ranker_weights.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate or calibrate LifePilot ranking weights from pairwise POI preferences.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--features", type=Path, default=DATA_DIR / "poi_features.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--apply-adjustments", action="store_true", help="Apply bounded perceptron-style updates instead of only reporting support.")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = read_json(args.dataset, {"cases": []})
    features = read_json(args.features, {"features": {}}).get("features", {})
    weights = dict(DEFAULT_RANKING_WEIGHTS)
    cases = [case for case in dataset.get("cases") or [] if valid_case(case, features)]

    before = evaluate(cases, features, weights)
    if args.apply_adjustments:
        train(cases, features, weights, epochs=max(1, args.epochs), learning_rate=max(0.0, args.learning_rate))
    after = evaluate(cases, features, weights)
    support = feature_support(cases, features)

    document = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-05-24T00:00:00+08:00",
        "source": str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset),
        "weights": {key: round(value, 4) for key, value in weights.items()},
        "training_summary": {
            "preference_case_count": len(cases),
            "pair_accuracy_before": before,
            "pair_accuracy": after,
            "adjustments_applied": bool(args.apply_adjustments),
            "feature_support": support,
        },
    }
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"preference pairs: {len(cases)}")
    print(f"pair_accuracy_before: {before}")
    print(f"pair_accuracy: {after}")


def read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def valid_case(case: Dict[str, Any], features: Dict[str, Any]) -> bool:
    return str(case.get("preferred_poi_id") or "") in features and str(case.get("rejected_poi_id") or "") in features


def evaluate(cases: list[Dict[str, Any]], features: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    if not cases:
        return {"passed": 0, "total": 0, "rate": 0.0}
    passed = 0
    for case in cases:
        preferred = feature_vector(case, features[str(case["preferred_poi_id"])])
        rejected = feature_vector(case, features[str(case["rejected_poi_id"])])
        if score(preferred, weights) > score(rejected, weights):
            passed += 1
    return {"passed": passed, "total": len(cases), "rate": round(passed / len(cases), 4)}


def train(cases: list[Dict[str, Any]], features: Dict[str, Any], weights: Dict[str, float], *, epochs: int, learning_rate: float) -> None:
    for _ in range(epochs):
        for case in cases:
            preferred = feature_vector(case, features[str(case["preferred_poi_id"])])
            rejected = feature_vector(case, features[str(case["rejected_poi_id"])])
            if score(preferred, weights) > score(rejected, weights):
                continue
            for key in weights:
                weights[key] += learning_rate * (preferred.get(key, 0.0) - rejected.get(key, 0.0))
                weights[key] = clamp_weight(key, weights[key])


def feature_support(cases: list[Dict[str, Any]], features: Dict[str, Any]) -> Dict[str, int]:
    support = {key: 0 for key in DEFAULT_RANKING_WEIGHTS}
    for case in cases:
        preferred = feature_vector(case, features[str(case["preferred_poi_id"])])
        rejected = feature_vector(case, features[str(case["rejected_poi_id"])])
        for key in support:
            if preferred.get(key, 0.0) != rejected.get(key, 0.0):
                support[key] += 1
    return {key: value for key, value in support.items() if value}


def clamp_weight(key: str, value: float) -> float:
    default = DEFAULT_RANKING_WEIGHTS[key]
    if default < 0:
        return max(default * 1.8, min(default * 0.2, value))
    return max(default * 0.2, min(default * 1.8, value))


if __name__ == "__main__":
    main()
