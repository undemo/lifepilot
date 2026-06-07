from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.data_paths import (  # noqa: E402
    DATA_DIR,
    MOCK_FAILURE_SCENARIOS_PATH,
    MOCK_INVENTORY_PATH,
    MOCK_POIS_PATH,
    MOCK_ROUTES_PATH,
    MOCK_STATUS_PATH,
)
from app.services.mock_api_service import MockAPIService  # noqa: E402


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate LifePilot mock fixtures and deterministic mock engines.")
    parser.add_argument("--data-dir", default=os.environ.get("LIFEPILOT_DATA_DIR"), help="Optional backend/data directory to validate.")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else DATA_DIR

    errors: list[str] = []
    pois = read_json(resolve_data_path(MOCK_POIS_PATH, data_dir)).get("pois", [])
    routes = read_json(resolve_data_path(MOCK_ROUTES_PATH, data_dir)).get("routes", [])
    status_rows = read_json(resolve_data_path(MOCK_STATUS_PATH, data_dir)).get("statuses", {})
    inventory = read_json(resolve_data_path(MOCK_INVENTORY_PATH, data_dir))
    poi_ids = {item.get("poi_id") for item in pois}

    required_poi_fields = {"poi_id", "name", "category", "area", "tags", "suitable_scenarios", "price_per_person"}
    for item in pois:
        missing = required_poi_fields - set(item.keys())
        if missing:
            errors.append(f"{item.get('poi_id')}: missing {sorted(missing)}")

    for poi_id in status_rows:
        if poi_id not in poi_ids:
            errors.append(f"{poi_id}: status override references missing poi")

    for collection in ("restaurant_slots", "activity_slots"):
        for slot in inventory.get(collection, []):
            if slot.get("poi_id") not in poi_ids:
                errors.append(f"{slot.get('poi_id')}: inventory override references missing poi")

    for route in routes:
        if route.get("origin_poi_id") not in poi_ids or route.get("destination_poi_id") not in poi_ids:
            errors.append(f"{route.get('route_id')}: route references missing poi")
        if not route.get("duration_minutes"):
            errors.append(f"{route.get('route_id')}: missing duration_minutes")

    if not any(item.get("category") == "restaurant" for item in pois):
        errors.append("missing restaurant poi coverage")
    if not any(item.get("category") == "activity" for item in pois):
        errors.append("missing activity poi coverage")

    failures = {item.get("error_code") for item in read_json(resolve_data_path(MOCK_FAILURE_SCENARIOS_PATH, data_dir)).get("scenarios", [])}
    allowed_failures = {"NO_TABLE_AVAILABLE", "ACTIVITY_FULL", "PLAN_EXECUTABLE_WINDOW_EXPIRED"}
    unknown_failures = failures - allowed_failures - {None}
    for code in unknown_failures:
        errors.append(f"unknown failure scenario {code}")

    errors.extend(validate_mock_engine(data_dir))

    if errors:
        print("Mock data validation failed:")
        for error in errors[:40]:
            print(f"- {error}")
        if len(errors) > 40:
            print(f"- ... {len(errors) - 40} more")
        return 1
    print("Mock data validation passed.")
    return 0


def resolve_data_path(path: Path, data_dir: Path) -> Path:
    try:
        return data_dir / path.relative_to(DATA_DIR)
    except ValueError:
        return path


def validate_mock_engine(data_dir: Path) -> list[str]:
    previous_now = os.environ.get("LIFEPILOT_DEMO_NOW")
    previous_seed = os.environ.get("LIFEPILOT_DEMO_SEED")
    os.environ["LIFEPILOT_DEMO_NOW"] = "2026-05-20T15:00:00+08:00"
    os.environ["LIFEPILOT_DEMO_SEED"] = "validate-mock-engine"
    try:
        service = MockAPIService.from_data_dir(data_dir)
        restaurant = next((item for item in service._pois() if item.get("category") == "restaurant"), None)
        activity = next((item for item in service._pois() if item.get("category") == "activity"), None)
        errors = []
        if restaurant is None or activity is None:
            return ["mock engine requires at least one restaurant and one activity"]

        params = {"arrival_time": "2026-05-21T18:00:00+08:00", "party_size": 4}
        first = service.restaurant_status("trace_validate", restaurant["poi_id"], **params)
        second = service.restaurant_status("trace_validate", restaurant["poi_id"], **params)
        if first != second:
            errors.append("restaurant status engine is not deterministic for same input")
        if first.get("available_tables") is None or first.get("expire_at") is None:
            errors.append("restaurant status engine missing available_tables or expire_at")

        activity_status = service.poi_status("trace_validate", activity["poi_id"], party_size=2, when="2026-05-21T16:00:00+08:00")
        if activity_status.get("ticket_available") is None or activity_status.get("expire_at") is None:
            errors.append("activity status engine missing ticket_available or expire_at")

        weather_one = service.weather(
            "trace_validate",
            area="validate_area",
            start_time="2026-05-21T13:30:00+08:00",
            end_time="2026-05-21T18:00:00+08:00",
        )
        weather_two = service.weather(
            "trace_validate",
            area="validate_area",
            start_time="2026-05-22T13:30:00+08:00",
            end_time="2026-05-22T18:00:00+08:00",
        )
        if weather_one == weather_two:
            errors.append("weather engine should vary when target date changes")

        signal = service.social_signal("trace_validate", restaurant["poi_id"])
        if signal.get("is_mock") is not True or signal.get("source_type") != "mock_social_signal":
            errors.append("social signal engine missing mock markers")
        return errors
    finally:
        if previous_now is None:
            os.environ.pop("LIFEPILOT_DEMO_NOW", None)
        else:
            os.environ["LIFEPILOT_DEMO_NOW"] = previous_now
        if previous_seed is None:
            os.environ.pop("LIFEPILOT_DEMO_SEED", None)
        else:
            os.environ["LIFEPILOT_DEMO_SEED"] = previous_seed


if __name__ == "__main__":
    sys.exit(main())
