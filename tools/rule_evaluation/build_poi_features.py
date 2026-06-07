#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rules.poi_feature_store import build_poi_feature_document  # noqa: E402
from app.services.mock_api_service import MockAPIService  # noqa: E402
from app.storage.json_store import JsonFileStore  # noqa: E402


DATA_DIR = ROOT / "backend" / "data"
OUTPUT = DATA_DIR / "poi_features.json"
SAMPLE_TIMES = (
    ("afternoon", "2026-05-24T14:30:00+08:00"),
    ("dinner", "2026-05-24T17:30:00+08:00"),
    ("evening", "2026-05-24T20:00:00+08:00"),
)


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    pois = read_json(DATA_DIR / "mock_pois.json", {"pois": []}).get("pois", [])
    enrichments = read_json(DATA_DIR / "gaode_poi_enrichment.json", {"enrichments": {}}).get("enrichments", {})
    status_signals = build_status_signals(pois)
    document = build_poi_feature_document(pois, enrichments, status_signals)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} ({document['feature_count']} features)")


def build_status_signals(pois: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    service = MockAPIService(JsonFileStore(DATA_DIR), None)
    signals: Dict[str, Dict[str, Any]] = {}
    for poi in pois:
        poi_id = str(poi.get("poi_id") or "")
        category = str(poi.get("category") or "")
        if not poi_id or category not in {"restaurant", "activity"}:
            continue
        snapshots = []
        for segment, when in SAMPLE_TIMES:
            snapshot = status_snapshot(service, poi, when)
            if snapshot:
                snapshot["segment"] = segment
                snapshots.append(snapshot)
        if snapshots:
            signals[poi_id] = summarize_status_signal(snapshots)
    return signals


def status_snapshot(service: MockAPIService, poi: Dict[str, Any], when: str) -> Dict[str, Any]:
    poi_id = str(poi.get("poi_id") or "")
    category = str(poi.get("category") or "")
    try:
        if category == "restaurant":
            status = service.restaurant_status("trace_feature_build", poi_id, arrival_time=when, party_size=2)
            available = bool(status.get("available") and status.get("reservation_available") and int(status.get("available_tables") or 0) > 0)
        else:
            status = service.poi_status("trace_feature_build", poi_id, party_size=2, when=when)
            available = bool(status.get("available") and status.get("booking_available", True) and status.get("ticket_available", True))
        queue_minutes = float(status.get("queue_minutes") or 0)
        effective_queue = queue_minutes
        if not available:
            effective_queue += 35
        if str(status.get("risk_level") or "") in {"high", "blocking"}:
            effective_queue += 8
        return {
            "time": when,
            "available": available,
            "queue_minutes": queue_minutes,
            "effective_queue_minutes": effective_queue,
            "risk_level": status.get("risk_level"),
        }
    except Exception:
        return {}


def summarize_status_signal(snapshots: list[Dict[str, Any]]) -> Dict[str, Any]:
    summary = summarize_snapshot_group(snapshots)
    profile = {
        str(segment): summarize_snapshot_group([item for item in snapshots if item.get("segment") == segment])
        for segment, _ in SAMPLE_TIMES
        if any(item.get("segment") == segment for item in snapshots)
    }
    summary.update(
        {
            "source": "mock_api_status_sampling",
            "sample_times": [when for _, when in SAMPLE_TIMES],
            "queue_profile": profile,
        }
    )
    return summary


def summarize_snapshot_group(snapshots: list[Dict[str, Any]]) -> Dict[str, Any]:
    effective = [float(item.get("effective_queue_minutes") or 0) for item in snapshots]
    raw_queue = [float(item.get("queue_minutes") or 0) for item in snapshots]
    available_ratio = sum(1 for item in snapshots if item.get("available")) / len(snapshots)
    avg_effective = mean(effective)
    peak_effective = max(effective)
    if available_ratio >= 0.67 and avg_effective <= 14:
        queue_bucket = "low"
        queue_pressure = 0.14 + min(avg_effective, 14) / 100
    elif available_ratio >= 0.5 and avg_effective <= 28:
        queue_bucket = "medium"
        queue_pressure = 0.36 + min(avg_effective, 28) / 120
    else:
        queue_bucket = "high"
        queue_pressure = 0.68 + min(peak_effective, 55) / 180
    return {
        "queue_minutes_avg": round(mean(raw_queue), 2),
        "effective_queue_minutes_avg": round(avg_effective, 2),
        "effective_queue_minutes_peak": round(peak_effective, 2),
        "availability_ratio": round(available_ratio, 4),
        "queue_bucket": queue_bucket,
        "queue_pressure": round(min(queue_pressure, 1.0), 4),
    }


if __name__ == "__main__":
    main()
