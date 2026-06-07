from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from generate_pois import request_json, write_json


FACTORY_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = FACTORY_ROOT / "output"
REPORTS_DIR = FACTORY_ROOT / "reports"

ADCODE_QIANTANG = "330114"
ISO_NOW = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

CENTERS = (
    {"name": "金沙湖", "location": "120.329690,30.308757"},
    {"name": "下沙", "location": "120.340000,30.315000"},
    {"name": "高教园区", "location": "120.365000,30.312000"},
)

PREMIUM_TYPES = (
    {"label": "餐饮", "types": "050000", "category": "restaurant"},
    {"label": "咖啡甜品", "types": "050500|050800", "category": "restaurant"},
    {"label": "休闲娱乐", "types": "080000", "category": "activity"},
    {"label": "景点公园", "types": "110000", "category": "walk_spot"},
    {"label": "书店文化", "types": "141200|140500", "category": "activity"},
)

NOISE_TERMS = (
    "汽车",
    "汽修",
    "维修",
    "建材",
    "家具",
    "家居",
    "公司",
    "产业园",
    "写字楼",
    "房产",
    "中介",
    "充电站",
    "加油站",
    "银行",
    "厕所",
    "卫生间",
    "营业厅",
)


def call(endpoint: str, params: dict[str, Any], key: str, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    payload = dict(params)
    payload["key"] = key
    return request_json(endpoint, payload, timeout, retry, retry_sleep)


def safe_request(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if key != "key"}


def fetch_premium_pois(key: str, timeout: int, retry: int, retry_sleep: float, sleep_seconds: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_responses: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats = Counter()

    for center in CENTERS:
        for spec in PREMIUM_TYPES:
            params = {
                "location": center["location"],
                "radius": 2500,
                "types": spec["types"],
                "offset": 20,
                "page": 1,
                "extensions": "all",
                "output": "json",
            }
            response = call("https://restapi.amap.com/v3/place/around", params, key, timeout, retry, retry_sleep)
            raw_responses.append({"request": safe_request(params) | {"center_name": center["name"], "label": spec["label"]}, "response": response})
            for poi in response.get("pois", []):
                stats["raw_seen"] += 1
                if not isinstance(poi, dict):
                    continue
                poi_id = str(poi.get("id") or "")
                if not poi_id or poi_id in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(poi_id)
                if poi.get("adcode") != ADCODE_QIANTANG:
                    stats["outside_qiantang"] += 1
                    continue
                text = f"{poi.get('name','')} {poi.get('type','')} {poi.get('address','')}"
                if any(term in text for term in NOISE_TERMS):
                    stats["noise_filtered"] += 1
                    continue
                rating = parse_float(poi.get("biz_ext", {}).get("rating") if isinstance(poi.get("biz_ext"), dict) else None)
                cost = parse_float(poi.get("biz_ext", {}).get("cost") if isinstance(poi.get("biz_ext"), dict) else None)
                if rating is not None and rating < 4.0:
                    stats["low_rating_filtered"] += 1
                    continue
                accepted.append(
                    {
                        "id": poi_id,
                        "name": poi.get("name"),
                        "type": poi.get("type"),
                        "typecode": poi.get("typecode"),
                        "location": poi.get("location"),
                        "address": poi.get("address"),
                        "adcode": poi.get("adcode"),
                        "rating": rating,
                        "cost": cost,
                        "open_time": poi.get("biz_ext", {}).get("open_time") if isinstance(poi.get("biz_ext"), dict) else None,
                        "photos_count": len(poi.get("photos", [])) if isinstance(poi.get("photos"), list) else 0,
                        "tel_present": bool(poi.get("tel") not in (None, "", [])),
                        "life_pilot_category": spec["category"],
                        "center_name": center["name"],
                        "quality_score": quality_score(rating, cost, poi),
                    }
                )
            if sleep_seconds:
                time.sleep(sleep_seconds)

    accepted.sort(key=lambda item: (item["quality_score"], item["rating"] or 0, item["photos_count"]), reverse=True)
    return accepted, raw_responses, dict(stats)


def fetch_detail(key: str, poi_id: str, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    params = {"id": poi_id, "extensions": "all", "output": "json"}
    return {"request": safe_request(params), "response": call("https://restapi.amap.com/v3/place/detail", params, key, timeout, retry, retry_sleep)}


def fetch_routes(key: str, pois: list[dict[str, Any]], timeout: int, retry: int, retry_sleep: float) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    pairs = [(pois[i], pois[i + 1]) for i in range(min(2, max(0, len(pois) - 1)))]
    for origin, dest in pairs:
        o = origin["location"]
        d = dest["location"]
        for mode, endpoint, extra in (
            ("walk", "https://restapi.amap.com/v3/direction/walking", {}),
            ("drive", "https://restapi.amap.com/v3/direction/driving", {"extensions": "all"}),
            ("transit", "https://restapi.amap.com/v3/direction/transit/integrated", {"city": ADCODE_QIANTANG, "cityd": ADCODE_QIANTANG, "extensions": "all"}),
        ):
            params = {"origin": o, "destination": d, "output": "json"} | extra
            try:
                response = call(endpoint, params, key, timeout, retry, retry_sleep)
            except Exception as exc:
                samples.append({"mode": mode, "origin": origin["name"], "destination": dest["name"], "request": safe_request(params), "error": str(exc)})
                continue
            samples.append(
                {
                    "mode": mode,
                    "origin": origin["name"],
                    "destination": dest["name"],
                    "request": safe_request(params),
                    "parsed": parse_route(mode, response),
                    "response_sample": shrink_route_response(mode, response),
                }
            )
    return samples


def fetch_weather(key: str, timeout: int, retry: int, retry_sleep: float) -> list[dict[str, Any]]:
    outputs = []
    for extensions in ("base", "all"):
        params = {"city": ADCODE_QIANTANG, "extensions": extensions, "output": "json"}
        outputs.append({"request": safe_request(params), "response": call("https://restapi.amap.com/v3/weather/weatherInfo", params, key, timeout, retry, retry_sleep)})
    return outputs


def parse_route(mode: str, response: dict[str, Any]) -> dict[str, Any]:
    route = response.get("route", {})
    if mode == "transit":
        transits = route.get("transits", [])
        first = transits[0] if isinstance(transits, list) and transits else {}
        return {
            "distance_m": parse_float(first.get("distance")),
            "duration_s": parse_float(first.get("duration")),
            "cost": parse_float(first.get("cost")),
            "segments_count": len(first.get("segments", [])) if isinstance(first.get("segments"), list) else None,
        }
    paths = route.get("paths", [])
    first = paths[0] if isinstance(paths, list) and paths else {}
    return {
        "distance_m": parse_float(first.get("distance")),
        "duration_s": parse_float(first.get("duration")),
        "strategy": first.get("strategy"),
        "steps_count": len(first.get("steps", [])) if isinstance(first.get("steps"), list) else None,
    }


def shrink_route_response(mode: str, response: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_route(mode, response)
    return {"status": response.get("status"), "info": response.get("info"), "infocode": response.get("infocode"), "parsed": parsed}


def quality_score(rating: float | None, cost: float | None, poi: dict[str, Any]) -> float:
    score = 0.0
    if rating is not None:
        score += rating * 20
    if cost is not None:
        score += 8
    if poi.get("biz_ext", {}).get("open_time") if isinstance(poi.get("biz_ext"), dict) else None:
        score += 6
    if poi.get("photos"):
        score += 5
    if poi.get("tel") not in (None, "", []):
        score += 3
    return round(score, 2)


def parse_float(value: Any) -> float | None:
    try:
        if value in (None, "", []):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_capability_matrix(pois: list[dict[str, Any]], routes: list[dict[str, Any]], weather: list[dict[str, Any]]) -> list[dict[str, Any]]:
    poi_count = len(pois)
    field_rate = lambda field: round(sum(1 for poi in pois if poi.get(field) not in (None, "", [])) / poi_count, 4) if poi_count else 0
    successful_routes = [item for item in routes if item.get("parsed", {}).get("duration_s")]
    weather_ok = any(item.get("response", {}).get("status") == "1" for item in weather)
    return [
        {
            "file": "mock_pois.json",
            "gaode_restore_level": "high",
            "real_fields": ["name", "category/type", "sub_category/typecode", "location", "area/adcode", "address", "price_per_person/cost", "rating", "opening_hours/open_time", "photos", "tel"],
            "field_coverage_in_probe": {"rating": field_rate("rating"), "cost": field_rate("cost"), "open_time": field_rate("open_time"), "photos": field_rate("photos_count"), "tel": field_rate("tel_present")},
            "still_mock_or_rule": ["suitable_scenarios", "risk_tags", "LifePilot category mapping", "curated tags"],
        },
        {
            "file": "mock_routes.json",
            "gaode_restore_level": "high",
            "real_fields": ["distance_km", "duration_minutes", "transport_mode", "route steps/polyline from raw"],
            "field_coverage_in_probe": {"route_success_count": len(successful_routes), "route_attempt_count": len(routes)},
            "still_mock_or_rule": ["confidence", "traffic_level normalization for non-driving modes", "which POI pairs to precompute"],
        },
        {
            "file": "mock_weather.json",
            "gaode_restore_level": "medium",
            "real_fields": ["weather", "temperature", "winddirection", "windpower", "humidity", "forecast casts"],
            "field_coverage_in_probe": {"weather_api_ok": weather_ok},
            "still_mock_or_rule": ["rain_probability", "outdoor_risk_level", "suggested_recovery", "LifePilot time_range slicing"],
        },
        {
            "file": "mock_status.json",
            "gaode_restore_level": "low_to_medium",
            "real_fields": ["open_status can be inferred from open_time", "available can be rule-derived from current time"],
            "field_coverage_in_probe": {"open_time": field_rate("open_time")},
            "still_mock_or_rule": ["available_tables", "queue_minutes", "ticket_available", "remaining_tickets", "reservation_available", "execute_status"],
        },
        {
            "file": "mock_inventory.json",
            "gaode_restore_level": "low",
            "real_fields": ["opening hour windows can anchor slots"],
            "field_coverage_in_probe": {"open_time": field_rate("open_time")},
            "still_mock_or_rule": ["base_tables", "reserved_tables", "max_party_size", "remaining_tickets", "booking_available"],
        },
        {
            "file": "mock_social_signals.json",
            "gaode_restore_level": "medium_for_metadata_low_for_reviews",
            "real_fields": ["rating", "cost", "tag", "photos_count can seed summaries"],
            "field_coverage_in_probe": {"rating": field_rate("rating"), "cost": field_rate("cost"), "photos": field_rate("photos_count")},
            "still_mock_or_rule": ["review text", "全网口碑归纳", "positive_tags", "negative_tags", "heat_score", "mock_sources"],
        },
        {
            "file": "mock_failure_scenarios.json",
            "gaode_restore_level": "none",
            "real_fields": [],
            "field_coverage_in_probe": {},
            "still_mock_or_rule": ["failure injection remains Demo/test fixture"],
        },
        {
            "file": "benchmark_samples.json",
            "gaode_restore_level": "none",
            "real_fields": [],
            "field_coverage_in_probe": {},
            "still_mock_or_rule": ["evaluation prompts and assertions remain product-designed"],
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe which LifePilot mock data fields can be restored from Gaode APIs.")
    parser.add_argument("--key", default=os.environ.get("AMAP_KEY"), help="Gaode Web Service API key. Defaults to AMAP_KEY.")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retry", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--sample-details", type=int, default=3)
    args = parser.parse_args()
    if not args.key:
        parser.error("Gaode key is required. Pass --key or set AMAP_KEY.")

    pois, raw_poi_responses, poi_stats = fetch_premium_pois(args.key, args.timeout, args.retry, args.retry_sleep, args.sleep)
    sample_pois = pois[: args.sample_details]
    detail_samples = []
    for poi in sample_pois:
        try:
            detail_samples.append({"poi_id": poi["id"], "name": poi["name"], "detail": fetch_detail(args.key, poi["id"], args.timeout, args.retry, args.retry_sleep)})
        except Exception as exc:
            detail_samples.append({"poi_id": poi["id"], "name": poi["name"], "error": str(exc)})
    route_samples = fetch_routes(args.key, sample_pois, args.timeout, args.retry, args.retry_sleep) if len(sample_pois) >= 2 else []
    weather_samples = fetch_weather(args.key, args.timeout, args.retry, args.retry_sleep)

    capability_matrix = build_capability_matrix(pois, route_samples, weather_samples)
    report = {
        "version": "v0.1",
        "created_at": ISO_NOW,
        "scope": "钱塘区精品吃喝玩乐小样本能力验证",
        "principle": "能真实采用的字段尽量来自高德；商家库存、真实排队、订座、评论正文等高德 Web 服务不直接提供的字段继续 Mock/规则/AI。",
        "sample_limits": {
            "centers": CENTERS,
            "type_specs": PREMIUM_TYPES,
            "radius_m": 2500,
            "pages_per_query": 1,
            "detail_samples": args.sample_details,
        },
        "premium_poi_filter": {
            "adcode": ADCODE_QIANTANG,
            "noise_terms": NOISE_TERMS,
            "min_rating_when_present": 4.0,
        },
        "poi_stats": poi_stats | {"accepted_after_filter": len(pois)},
        "top_pois": pois[:20],
        "capability_matrix": capability_matrix,
        "route_samples": route_samples,
        "weather_samples": weather_samples,
        "detail_samples": detail_samples,
    }
    raw_archive = {
        "version": "v0.1",
        "created_at": ISO_NOW,
        "source": "gaode_web_service_probe",
        "note": "Raw probe responses omit API keys.",
        "poi_around_responses": raw_poi_responses,
    }
    write_json(OUTPUT_DIR / "gaode_capability_probe_report.json", report)
    write_json(OUTPUT_DIR / "gaode_capability_probe_raw.json", raw_archive)
    write_json(REPORTS_DIR / "gaode_capability_probe_summary.json", {k: report[k] for k in ("version", "created_at", "scope", "poi_stats", "capability_matrix")})
    print(json.dumps({k: report[k] for k in ("scope", "poi_stats", "capability_matrix")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
