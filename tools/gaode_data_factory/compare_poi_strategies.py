from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from generate_pois import (
    AREA,
    ISO_NOW,
    SearchSpec,
    convert_poi,
    fetch_pois,
    request_json,
    write_json,
)


FACTORY_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = FACTORY_ROOT / "output"
REPORTS_DIR = FACTORY_ROOT / "reports"

REQUIRED_CATEGORIES = {"activity", "restaurant", "walk_spot", "service", "transport_anchor"}
REQUIRED_AREAS = {"下沙", "金沙湖", "高教园区"}
REQUIRED_SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}

AROUND_CENTERS = (
    {"name": "金沙湖中心", "location": "120.329690,30.308757", "area": "金沙湖"},
    {"name": "高教园区中心", "location": "120.365000,30.312000", "area": "高教园区"},
    {"name": "下沙中心", "location": "120.340000,30.315000", "area": "下沙"},
)

AROUND_SPECS = (
    SearchSpec("restaurant", "food_drink", "", "050000", ("family_parent_child", "friend_group", "anniversary_emotion"), ("restaurant", "food", "drink")),
    SearchSpec("activity", "leisure_play", "", "080000", ("family_parent_child", "friend_group"), ("play", "indoor", "leisure")),
    SearchSpec("walk_spot", "park_walk", "", "110000", ("family_parent_child", "friend_group", "anniversary_emotion"), ("walk", "outdoor", "mood_relief")),
    SearchSpec("service", "daily_service", "", "070000", ("family_parent_child", "friend_group"), ("service", "supply", "hygiene")),
    SearchSpec("transport_anchor", "transport", "", "150000", ("friend_group",), ("transport", "meeting", "mobility")),
)


def fetch_around(api_key: str, center: dict[str, str], spec: SearchSpec, radius: int, page: int, offset: int, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    return request_json(
        "https://restapi.amap.com/v3/place/around",
        {
            "key": api_key,
            "location": center["location"],
            "radius": radius,
            "keywords": spec.keywords,
            "types": spec.types,
            "offset": offset,
            "page": page,
            "extensions": "all",
            "output": "json",
        },
        timeout,
        retry,
        retry_sleep,
    )


def build_around_model(api_key: str, target: int, radius: int, per_query: int, timeout: int, retry: int, retry_sleep: float, sleep_seconds: float) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_seen: set[str] = set()
    duplicates = 0
    invalid_location = 0
    requests: list[dict[str, Any]] = []

    for center in AROUND_CENTERS:
        for spec in AROUND_SPECS:
            if len(accepted) >= target:
                break
            query_accepts = 0
            for page in range(1, 4):
                if query_accepts >= per_query or len(accepted) >= target:
                    break
                payload = fetch_around(api_key, center, spec, radius, page, 25, timeout, retry, retry_sleep)
                pois = payload.get("pois", [])
                raw_responses.append(
                    {
                        "request": {
                            "endpoint": "https://restapi.amap.com/v3/place/around",
                            "center_name": center["name"],
                            "location": center["location"],
                            "radius": radius,
                            "keywords": spec.keywords,
                            "types": spec.types,
                            "offset": 25,
                            "page": page,
                            "extensions": "all",
                            "output": "json",
                        },
                        "life_pilot_mapping": {
                            "category": spec.category,
                            "sub_category": spec.sub_category,
                            "suitable_scenarios": list(spec.scenarios),
                            "base_tags": list(spec.tags),
                        },
                        "response": payload,
                    }
                )
                requests.append(
                    {
                        "center_name": center["name"],
                        "category": spec.category,
                        "sub_category": spec.sub_category,
                        "types": spec.types,
                        "page": page,
                        "count": payload.get("count"),
                        "returned": len(pois) if isinstance(pois, list) else 0,
                    }
                )
                if not isinstance(pois, list) or not pois:
                    break
                for raw in pois:
                    raw_id = str(raw.get("id") or "")
                    unique_key = raw_id or raw_fingerprint(raw)
                    if unique_key in raw_seen:
                        duplicates += 1
                        continue
                    raw_seen.add(unique_key)
                    converted = convert_poi(raw, spec, len(accepted) + 1)
                    if converted is None:
                        invalid_location += 1
                        continue
                    converted["poi_id"] = converted["poi_id"].replace("poi_gaode_", "poi_gaode_around_", 1)
                    if unique_key in seen:
                        duplicates += 1
                        continue
                    seen.add(unique_key)
                    accepted.append(converted)
                    query_accepts += 1
                    if query_accepts >= per_query or len(accepted) >= target:
                        break
                if sleep_seconds:
                    time.sleep(sleep_seconds)
            if len(accepted) >= target:
                break

    model = {"version": "v0.1", "area": AREA, "pois": accepted}
    raw_payload = {
        "version": "v0.1",
        "source": "gaode_web_service_place_around",
        "area": AREA,
        "created_at": ISO_NOW,
        "note": "Raw Gaode around-search responses are stored separately from LifePilot POI fixtures. API keys are intentionally omitted.",
        "responses": raw_responses,
    }
    report = {
        "task": "gaode_generate_around_pois",
        "success": len(accepted) >= target,
        "source": "gaode_web_service_place_around",
        "area": AREA,
        "target": target,
        "accepted": len(accepted),
        "radius": radius,
        "centers": AROUND_CENTERS,
        "requests": requests,
        "duplicates_removed": duplicates,
        "rejected_invalid_location": invalid_location,
        "category_counts": dict(Counter(poi["category"] for poi in accepted)),
        "area_counts": dict(Counter(poi["area"] for poi in accepted)),
    }
    return model, raw_payload, report


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_raw(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for response_index, entry in enumerate(raw_payload.get("responses", [])):
        pois = entry.get("response", {}).get("pois", [])
        if not isinstance(pois, list):
            continue
        for poi_index, poi in enumerate(pois):
            if isinstance(poi, dict):
                rows.append({"poi": poi, "response_index": response_index, "poi_index": poi_index, "request": entry.get("request", {})})
    return rows


def raw_fingerprint(raw: dict[str, Any]) -> str:
    value = f"{raw.get('name','')}|{raw.get('location','')}|{raw.get('address','')}"
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def raw_unique_ids(rows: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for row in rows:
        poi = row["poi"]
        values.add(str(poi.get("id") or raw_fingerprint(poi)))
    return values


def evaluate_strategy(name: str, model: dict[str, Any], raw_payload: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    pois = model.get("pois", [])
    raw_rows = flatten_raw(raw_payload)
    raw_ids = raw_unique_ids(raw_rows)
    category_counts = Counter(poi.get("category") for poi in pois)
    area_counts = Counter(poi.get("area") for poi in pois)
    scenario_values = {scenario for poi in pois for scenario in poi.get("suitable_scenarios", []) if isinstance(poi.get("suitable_scenarios"), list)}
    raw_total = len(raw_rows)
    duplicate_count = max(0, raw_total - len(raw_ids))
    request_count = len(raw_payload.get("responses", []))
    raw_field_rates = raw_field_coverage(raw_rows)
    return {
        "name": name,
        "source": raw_payload.get("source"),
        "request_count": request_count,
        "raw_poi_count": raw_total,
        "raw_unique_poi_count": len(raw_ids),
        "raw_duplicate_count": duplicate_count,
        "raw_duplicate_rate": round(duplicate_count / raw_total, 4) if raw_total else 0,
        "accepted_poi_count": len(pois),
        "accepted_per_request": round(len(pois) / request_count, 4) if request_count else 0,
        "accepted_from_raw_unique_rate": round(len(pois) / len(raw_ids), 4) if raw_ids else 0,
        "category_counts": dict(category_counts),
        "area_counts": dict(area_counts),
        "category_coverage_ratio": round(len(set(category_counts) & REQUIRED_CATEGORIES) / len(REQUIRED_CATEGORIES), 4),
        "area_coverage_ratio": round(len(set(area_counts) & REQUIRED_AREAS) / len(REQUIRED_AREAS), 4),
        "scenario_coverage_ratio": round(len(scenario_values & REQUIRED_SCENARIOS) / len(REQUIRED_SCENARIOS), 4),
        "rating_coverage": round(sum(1 for poi in pois if isinstance(poi.get("rating"), (int, float))) / len(pois), 4) if pois else 0,
        "price_coverage": round(sum(1 for poi in pois if isinstance(poi.get("price_per_person"), (int, float))) / len(pois), 4) if pois else 0,
        "opening_hours_coverage": round(sum(1 for poi in pois if isinstance(poi.get("opening_hours"), dict)) / len(pois), 4) if pois else 0,
        "coordinate_bbox_km2": coordinate_bbox_km2(pois),
        "raw_field_coverage": raw_field_rates,
        "report_summary": {
            "target": report.get("target"),
            "success": report.get("success"),
            "duplicates_removed": report.get("duplicates_removed"),
            "rejected_invalid_location": report.get("rejected_invalid_location"),
            "rejected_out_of_area": report.get("rejected_out_of_area"),
        },
    }


def raw_field_coverage(raw_rows: list[dict[str, Any]]) -> dict[str, float]:
    fields = {
        "id": lambda poi: poi.get("id"),
        "type": lambda poi: poi.get("type"),
        "typecode": lambda poi: poi.get("typecode"),
        "location": lambda poi: poi.get("location"),
        "address": lambda poi: poi.get("address"),
        "rating": lambda poi: poi.get("biz_ext", {}).get("rating") if isinstance(poi.get("biz_ext"), dict) else None,
        "cost": lambda poi: poi.get("biz_ext", {}).get("cost") if isinstance(poi.get("biz_ext"), dict) else None,
        "open_time": lambda poi: poi.get("biz_ext", {}).get("open_time") if isinstance(poi.get("biz_ext"), dict) else None,
        "photos": lambda poi: poi.get("photos") if poi.get("photos") not in ([], "") else None,
        "tel": lambda poi: poi.get("tel") if poi.get("tel") not in ([], "") else None,
    }
    total = len(raw_rows)
    if not total:
        return {field: 0 for field in fields}
    return {field: round(sum(1 for row in raw_rows if getter(row["poi"]) not in (None, "", [])) / total, 4) for field, getter in fields.items()}


def coordinate_bbox_km2(pois: list[dict[str, Any]]) -> float:
    coords = [
        (poi.get("location", {}).get("lat"), poi.get("location", {}).get("lng"))
        for poi in pois
        if isinstance(poi.get("location"), dict)
    ]
    coords = [(lat, lng) for lat, lng in coords if isinstance(lat, (int, float)) and isinstance(lng, (int, float))]
    if len(coords) < 2:
        return 0.0
    lats = [lat for lat, _ in coords]
    lngs = [lng for _, lng in coords]
    avg_lat = sum(lats) / len(lats)
    height_km = (max(lats) - min(lats)) * 111.32
    width_km = (max(lngs) - min(lngs)) * 111.32 * abs(__import__("math").cos(__import__("math").radians(avg_lat)))
    return round(max(0.0, height_km * width_km), 4)


def dedupe_combined(keyword_model: dict[str, Any], around_model: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    combined: list[dict[str, Any]] = []
    removed = 0
    for source, model in (("keyword", keyword_model), ("around", around_model)):
        for poi in model.get("pois", []):
            fp = f"{poi.get('name','')}|{poi.get('location', {}).get('lng')}|{poi.get('location', {}).get('lat')}"
            if fp in seen:
                removed += 1
                continue
            seen.add(fp)
            item = dict(poi)
            item["poi_id"] = item["poi_id"].replace("poi_gaode_around_", "poi_gaode_", 1)
            combined.append(item)
    return {"version": "v0.1", "area": AREA, "pois": combined, "_dedupe_removed": removed}


def metric_winners(keyword: dict[str, Any], around: dict[str, Any]) -> dict[str, Any]:
    specs = {
        "accepted_poi_count": "higher",
        "raw_unique_poi_count": "higher",
        "raw_duplicate_rate": "lower",
        "accepted_per_request": "higher",
        "accepted_from_raw_unique_rate": "higher",
        "category_coverage_ratio": "higher",
        "area_coverage_ratio": "higher",
        "scenario_coverage_ratio": "higher",
        "price_coverage": "higher",
        "coordinate_bbox_km2": "higher",
    }
    winners: dict[str, Any] = {}
    for metric, direction in specs.items():
        left = keyword.get(metric, 0)
        right = around.get(metric, 0)
        if left == right:
            winner = "tie"
        elif direction == "higher":
            winner = "keyword" if left > right else "around"
        else:
            winner = "keyword" if left < right else "around"
        winners[metric] = {"direction": direction, "keyword": left, "around": right, "winner": winner}
    return winners


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare keyword POI modeling with coordinate around-search POI modeling.")
    parser.add_argument("--key", default=os.environ.get("AMAP_KEY"), help="Gaode Web Service API key. Defaults to AMAP_KEY.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target", type=int, default=60)
    parser.add_argument("--radius", type=int, default=1800)
    parser.add_argument("--per-query", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retry", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
    parser.add_argument("--sleep", type=float, default=0.35)
    args = parser.parse_args()
    if not args.key:
        parser.error("Gaode key is required. Pass --key or set AMAP_KEY.")

    keyword_model = load_json(args.output / "mock_pois.json", {"pois": []})
    keyword_raw = load_json(args.output / "gaode_raw_poi_responses.json", {"responses": []})
    keyword_report = load_json(REPORTS_DIR / "generate_pois_report.json", {})
    if not keyword_model.get("pois") or not keyword_raw.get("responses"):
        raise SystemExit("keyword strategy files are missing. Run generate_pois.py first.")

    around_model, around_raw, around_report = build_around_model(args.key, args.target, args.radius, args.per_query, args.timeout, args.retry, args.retry_sleep, args.sleep)
    write_json(args.output / "around_mock_pois.json", around_model)
    write_json(args.output / "gaode_around_raw_poi_responses.json", around_raw)
    write_json(REPORTS_DIR / "generate_around_pois_report.json", around_report)

    keyword_eval = evaluate_strategy("keyword_text_search", keyword_model, keyword_raw, keyword_report)
    around_eval = evaluate_strategy("coordinate_around_search", around_model, around_raw, around_report)
    keyword_ids = raw_unique_ids(flatten_raw(keyword_raw))
    around_ids = raw_unique_ids(flatten_raw(around_raw))
    combined = dedupe_combined(keyword_model, around_model)
    combined_removed = combined.pop("_dedupe_removed")
    write_json(args.output / "combined_deduped_mock_pois.json", combined)

    evaluation = {
        "version": "v0.1",
        "created_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "area": AREA,
        "strategies": {
            "keyword": keyword_eval,
            "around": around_eval,
        },
        "overlap": {
            "raw_unique_keyword": len(keyword_ids),
            "raw_unique_around": len(around_ids),
            "raw_overlap_count": len(keyword_ids & around_ids),
            "raw_overlap_ratio_of_keyword": round(len(keyword_ids & around_ids) / len(keyword_ids), 4) if keyword_ids else 0,
            "raw_overlap_ratio_of_around": round(len(keyword_ids & around_ids) / len(around_ids), 4) if around_ids else 0,
            "combined_mock_poi_count": len(combined["pois"]),
            "combined_mock_duplicates_removed": combined_removed,
        },
        "metric_winners": metric_winners(keyword_eval, around_eval),
        "metric_notes": {
            "accepted_poi_count": "转换后符合 LifePilot POI 字段的数量，越高越好。",
            "raw_unique_poi_count": "高德返回的去重原始 POI 数，越高越好。",
            "raw_duplicate_rate": "同一策略内部 raw POI 重复比例，越低越好。",
            "accepted_per_request": "每次 API 响应最终留下的可用 POI 数，越高表示请求效率越高。",
            "accepted_from_raw_unique_rate": "去重 raw POI 进入 LifePilot 边界和字段转换的比例，越高表示过滤损耗越低。",
            "category_coverage_ratio": "五类 LifePilot POI 覆盖比例。",
            "area_coverage_ratio": "下沙/金沙湖/高教园区覆盖比例。",
            "scenario_coverage_ratio": "三类 P0 scenario 覆盖比例。",
            "price_coverage": "转换后有数值型人均价格的 POI 比例。",
            "coordinate_bbox_km2": "转换后 POI 坐标外接矩形面积，用于观察空间覆盖范围，越大不必然越好，但表示覆盖更分散。",
        },
    }
    write_json(args.output / "poi_strategy_evaluation.json", evaluation)
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0 if around_report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
