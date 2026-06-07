from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FACTORY_ROOT = Path(__file__).resolve().parent
REPO_ROOT = FACTORY_ROOT.parents[1]
DEFAULT_OUTPUT_DIR = FACTORY_ROOT / "output"
REPORTS_DIR = FACTORY_ROOT / "reports"

AREA = "杭州下沙/金沙湖/高教园区"
ISO_NOW = datetime(2026, 5, 22, 13, 0, tzinfo=timezone(timedelta(hours=8))).isoformat()

AREA_BOUNDS = {
    "下沙": {"lat": (30.285, 30.345), "lng": (120.300, 120.390)},
    "金沙湖": {"lat": (30.300, 30.335), "lng": (120.330, 120.375)},
    "高教园区": {"lat": (30.295, 30.345), "lng": (120.345, 120.420)},
}

VALID_SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}


@dataclass(frozen=True)
class SearchSpec:
    category: str
    sub_category: str
    keywords: str
    types: str | None
    scenarios: tuple[str, ...]
    tags: tuple[str, ...]


SEARCH_SPECS = (
    SearchSpec("restaurant", "coffee_shop", "金沙湖 咖啡", "050500", ("friend_group", "anniversary_emotion"), ("coffee", "work_friendly", "rain_safe")),
    SearchSpec("activity", "bookstore", "高教园区 书店 书房", "141200", ("friend_group", "anniversary_emotion"), ("quiet_alone", "indoor", "work_friendly")),
    SearchSpec("walk_spot", "lake_walk", "金沙湖 公园 步道", "110000", ("family_parent_child", "friend_group", "anniversary_emotion"), ("lake_walk", "mood_relief", "outdoor")),
    SearchSpec("service", "clean_restroom", "金沙湖 卫生间 服务", "070000", ("family_parent_child", "friend_group"), ("clean_restroom", "service", "rain_safe")),
    SearchSpec("transport_anchor", "metro", "金沙湖 地铁站", "150500", ("friend_group", "anniversary_emotion"), ("metro", "easy_meeting", "visitor_friendly")),
    SearchSpec("restaurant", "light_food", "下沙 轻食 简餐", "050000", ("family_parent_child", "friend_group"), ("restaurant", "quick_meal", "budget")),
    SearchSpec("restaurant", "local_food", "高教园区 面馆 餐厅", "050000", ("friend_group", "family_parent_child"), ("local_flavor", "visitor_friendly", "quick_meal")),
    SearchSpec("activity", "sports", "下沙 运动 健身", "080000", ("friend_group",), ("sports_friendly", "indoor", "mood_relief")),
    SearchSpec("activity", "family_activity", "金沙湖 亲子 儿童", "080000", ("family_parent_child",), ("child_friendly", "interactive", "rain_safe")),
    SearchSpec("walk_spot", "quiet_walk", "高教园区 公园 散步", "110000", ("friend_group", "anniversary_emotion"), ("quiet_alone", "shade", "walk")),
    SearchSpec("service", "pharmacy", "下沙 药店 便利", "090600", ("family_parent_child", "friend_group"), ("pharmacy", "late_supply", "emergency_supply")),
    SearchSpec("service", "flower_cake", "下沙 鲜花 蛋糕", "060000", ("anniversary_emotion", "friend_group"), ("flower", "cake", "anniversary")),
    SearchSpec("transport_anchor", "parking", "高教园区 停车场", "150900", ("family_parent_child", "friend_group"), ("parking", "drive", "visitor_friendly")),
)

DEFAULT_OPENING_HOURS = {
    "restaurant": {"weekday": [["10:00", "21:30"]], "weekend": [["09:30", "22:00"]]},
    "activity": {"weekday": [["10:00", "20:30"]], "weekend": [["09:30", "21:00"]]},
    "walk_spot": {"weekday": [["07:00", "22:00"]], "weekend": [["07:00", "22:00"]]},
    "service": {"weekday": [["09:00", "21:30"]], "weekend": [["09:00", "21:30"]]},
    "transport_anchor": {"weekday": [["00:00", "23:59"]], "weekend": [["00:00", "23:59"]]},
}

DEFAULT_PRICE = {
    "restaurant": 45,
    "activity": 35,
    "walk_spot": 0,
    "service": None,
    "transport_anchor": None,
}


class GaodeError(RuntimeError):
    pass


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_json(url: str, params: dict[str, Any], timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    encoded = urllib.parse.urlencode({key: value for key, value in params.items() if value not in {None, ""}})
    request = urllib.request.Request(f"{url}?{encoded}", headers={"User-Agent": "LifePilot-Gaode-DataFactory/0.1"})
    last_payload: dict[str, Any] | None = None
    for attempt in range(retry + 1):
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") == "1":
            return payload
        last_payload = payload
        if payload.get("infocode") == "10021" and attempt < retry:
            time.sleep(retry_sleep * (2**attempt))
            continue
        break
    raise GaodeError(f"Gaode API failed: infocode={last_payload.get('infocode') if last_payload else None} info={last_payload.get('info') if last_payload else None}")


def fetch_pois(api_key: str, spec: SearchSpec, page: int, offset: int, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    return request_json(
        "https://restapi.amap.com/v3/place/text",
        {
            "key": api_key,
            "keywords": spec.keywords,
            "types": spec.types,
            "city": "杭州",
            "citylimit": "true",
            "children": 0,
            "offset": offset,
            "page": page,
            "extensions": "all",
            "output": "json",
        },
        timeout,
        retry,
        retry_sleep,
    )


def build_pois(target: int, per_spec: int, api_key: str, timeout: int, sleep_seconds: float, retry: int, retry_sleep: float) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_responses: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "task": "gaode_generate_pois",
        "success": False,
        "source": "gaode_web_service_place_text",
        "area": AREA,
        "target": target,
        "accepted": 0,
        "rejected_out_of_area": 0,
        "rejected_invalid_location": 0,
        "duplicates": 0,
        "requests": [],
        "category_counts": {},
        "area_counts": {},
    }

    for spec in SEARCH_SPECS:
        if len(accepted) >= target:
            break
        spec_accepts = 0
        page = 1
        while spec_accepts < per_spec and len(accepted) < target and page <= 3:
            payload = fetch_pois(api_key, spec, page=page, offset=25, timeout=timeout, retry=retry, retry_sleep=retry_sleep)
            pois = payload.get("pois", [])
            raw_responses.append(
                {
                    "request": {
                        "endpoint": "https://restapi.amap.com/v3/place/text",
                        "keywords": spec.keywords,
                        "types": spec.types,
                        "city": "杭州",
                        "citylimit": "true",
                        "children": 0,
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
            stats["requests"].append(
                {
                    "category": spec.category,
                    "sub_category": spec.sub_category,
                    "keywords": spec.keywords,
                    "types": spec.types,
                    "page": page,
                    "count": payload.get("count"),
                    "returned": len(pois) if isinstance(pois, list) else 0,
                }
            )
            if not isinstance(pois, list) or not pois:
                break
            for raw in pois:
                converted = convert_poi(raw, spec, len(accepted) + 1)
                if converted is None:
                    stats["rejected_invalid_location"] += 1
                    continue
                unique_key = str(raw.get("id") or "") or f"{converted['name']}@{converted['location']['lng']},{converted['location']['lat']}"
                if unique_key in seen:
                    stats["duplicates"] += 1
                    continue
                if converted["area"] not in AREA_BOUNDS:
                    stats["rejected_out_of_area"] += 1
                    continue
                seen.add(unique_key)
                accepted.append(converted)
                spec_accepts += 1
                stats["category_counts"][converted["category"]] = stats["category_counts"].get(converted["category"], 0) + 1
                stats["area_counts"][converted["area"]] = stats["area_counts"].get(converted["area"], 0) + 1
                if spec_accepts >= per_spec or len(accepted) >= target:
                    break
            page += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)

    payload = {"version": "v0.1", "area": AREA, "pois": accepted[:target]}
    raw_payload = {
        "version": "v0.1",
        "source": "gaode_web_service_place_text",
        "area": AREA,
        "created_at": ISO_NOW,
        "note": "Raw Gaode API responses are stored separately from LifePilot POI fixtures. API keys are intentionally omitted.",
        "responses": raw_responses,
    }
    stats["accepted"] = len(payload["pois"])
    stats["success"] = len(payload["pois"]) >= target
    stats["missing_categories"] = sorted({"activity", "restaurant", "walk_spot", "service", "transport_anchor"} - set(stats["category_counts"]))
    stats["missing_scenarios"] = sorted(VALID_SCENARIOS - {scenario for poi in payload["pois"] for scenario in poi["suitable_scenarios"]})
    return payload, raw_payload, stats


def convert_poi(raw: dict[str, Any], spec: SearchSpec, sequence: int) -> dict[str, Any] | None:
    lng, lat = parse_location(raw.get("location"))
    if lng is None or lat is None:
        return None
    area = infer_area(lat, lng, raw)
    if area is None:
        return None

    raw_id = str(raw.get("id") or "")
    suffix = sequence_suffix(raw_id, sequence)
    name = clean_text(raw.get("name"), default=f"高德POI{sequence:03d}", limit=40)
    address = clean_text(raw.get("address"), default=f"杭州市钱塘区{area}", limit=80)
    tags = build_tags(raw, spec)
    rating = parse_float(raw.get("biz_ext", {}).get("rating"), default=4.3)
    cost = parse_float(raw.get("biz_ext", {}).get("cost"), default=None)

    return {
        "poi_id": f"poi_gaode_{spec.category}_{suffix}",
        "name": name,
        "category": spec.category,
        "sub_category": spec.sub_category,
        "tags": tags,
        "location": {
            "city": "杭州",
            "area": area,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
        },
        "area": area,
        "address": address,
        "price_per_person": normalize_price(cost, spec.category),
        "rating": normalize_rating(rating),
        "opening_hours": parse_opening_hours(raw.get("biz_ext", {}).get("open_time")) or DEFAULT_OPENING_HOURS[spec.category],
        "suitable_scenarios": list(spec.scenarios),
        "risk_tags": risk_tags_for(spec.category, tags),
        "mock_only": True,
        "created_at": ISO_NOW,
        "updated_at": ISO_NOW,
    }


def parse_location(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, str) or "," not in value:
        return None, None
    lng_text, lat_text = value.split(",", 1)
    try:
        return float(lng_text), float(lat_text)
    except ValueError:
        return None, None


def infer_area(lat: float, lng: float, raw: dict[str, Any]) -> str | None:
    text = f"{raw.get('name', '')} {raw.get('address', '')} {raw.get('business_area', '')}"
    preferred = []
    if "金沙湖" in text:
        preferred.append("金沙湖")
    if "高教" in text or "学源" in text or "文渊" in text or "文海" in text:
        preferred.append("高教园区")
    if "下沙" in text:
        preferred.append("下沙")
    preferred.extend(["金沙湖", "高教园区", "下沙"])
    for area in dict.fromkeys(preferred):
        bounds = AREA_BOUNDS[area]
        if bounds["lat"][0] <= lat <= bounds["lat"][1] and bounds["lng"][0] <= lng <= bounds["lng"][1]:
            return area
    return None


def clean_text(value: Any, *, default: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text or text == "[]":
        text = default
    return re.sub(r"\s+", " ", text)[:limit]


def build_tags(raw: dict[str, Any], spec: SearchSpec) -> list[str]:
    tags = ["gaode_poi", *spec.tags]
    type_text = str(raw.get("type") or "")
    name_address = f"{raw.get('name', '')} {raw.get('address', '')}"
    if "地铁" in type_text or "地铁" in name_address:
        tags.extend(["metro", "easy_meeting"])
    if "停车" in type_text or "停车" in name_address:
        tags.extend(["parking", "drive"])
    if "咖啡" in type_text or "咖啡" in name_address:
        tags.extend(["coffee", "quiet_stay"])
    if "公园" in type_text or "湖" in name_address:
        tags.extend(["outdoor", "mood_relief"])
    if "药" in type_text or "药" in name_address:
        tags.extend(["pharmacy", "emergency_supply"])
    if "卫生间" in name_address or "厕所" in name_address:
        tags.extend(["clean_restroom", "hygiene"])
    return list(dict.fromkeys(tag for tag in tags if tag))[:12]


def parse_float(value: Any, default: float | None) -> float | None:
    try:
        if value in {None, "", "[]"}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_price(value: float | None, category: str) -> float | None:
    if value is None:
        fallback = DEFAULT_PRICE[category]
        return float(fallback) if fallback is not None else None
    if value <= 0:
        return 0.0
    return round(min(value, 500.0), 1)


def normalize_rating(value: float | None) -> float:
    if value is None:
        value = 4.3
    return round(min(5.0, max(3.5, value)), 1)


def parse_opening_hours(value: Any) -> dict[str, list[list[str]]] | None:
    if not isinstance(value, str):
        return None
    ranges = re.findall(r"([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)", value)
    if not ranges:
        return None
    normalized = [[f"{start_h}:{start_m}", f"{end_h}:{end_m}"] for start_h, start_m, end_h, end_m in ranges[:3]]
    return {"weekday": normalized, "weekend": normalized}


def risk_tags_for(category: str, tags: list[str]) -> list[str]:
    risks: list[str] = []
    if category == "restaurant":
        risks.append("queue_risk")
    if category == "activity":
        risks.append("capacity_risk")
    if category == "walk_spot" or "outdoor" in tags:
        risks.append("weather_risk")
    if "parking" in tags:
        risks.append("parking_shortage")
    return risks[:6]


def sequence_suffix(raw_id: str, sequence: int) -> str:
    digest = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:6] if raw_id else f"{sequence:06d}"
    return f"{sequence:03d}_{digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Gaode POIs and convert them to LifePilot mock_pois.json format.")
    parser.add_argument("--key", default=os.environ.get("AMAP_KEY"), help="Gaode Web Service API key. Defaults to AMAP_KEY.")
    parser.add_argument("--target", type=int, default=60, help="Target number of POIs to write.")
    parser.add_argument("--per-spec", type=int, default=10, help="Maximum accepted POIs per search spec.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory that receives mock_pois.json and raw Gaode JSON.")
    parser.add_argument("--raw-filename", default="gaode_raw_poi_responses.json", help="Raw Gaode response filename written under --output.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds per Gaode request.")
    parser.add_argument("--sleep", type=float, default=0.35, help="Seconds to sleep between API pages.")
    parser.add_argument("--retry", type=int, default=3, help="Retry count for Gaode QPS limit responses.")
    parser.add_argument("--retry-sleep", type=float, default=1.0, help="Base seconds for exponential backoff when Gaode returns QPS limit.")
    args = parser.parse_args()

    if not args.key:
        parser.error("Gaode key is required. Pass --key or set AMAP_KEY.")
    if args.target < 1:
        parser.error("--target must be positive.")
    if args.per_spec < 1:
        parser.error("--per-spec must be positive.")

    payload, raw_payload, report = build_pois(args.target, args.per_spec, args.key, args.timeout, args.sleep, args.retry, args.retry_sleep)
    write_json(args.output / "mock_pois.json", payload)
    write_json(args.output / args.raw_filename, raw_payload)
    write_json(REPORTS_DIR / "generate_pois_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] and not report["missing_scenarios"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
