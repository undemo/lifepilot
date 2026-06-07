from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from generate_pois import AREA, DEFAULT_OPENING_HOURS, DEFAULT_OUTPUT_DIR, REPORTS_DIR, parse_float, parse_location, request_json, write_json


ISO_NOW = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
ADCODE_QIANTANG = "330114"
REQUIRED_SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}

AREA_BOUNDS = {
    "下沙": {"lat": (30.285, 30.345), "lng": (120.300, 120.390)},
    "金沙湖": {"lat": (30.300, 30.335), "lng": (120.330, 120.375)},
    "高教园区": {"lat": (30.295, 30.345), "lng": (120.345, 120.420)},
}


@dataclass(frozen=True)
class AroundCenter:
    name: str
    location: str
    area: str


@dataclass(frozen=True)
class TypeSpec:
    label: str
    types: str
    category: str
    sub_category: str
    scenarios: tuple[str, ...]
    tags: tuple[str, ...]
    default_price: float | None


CENTERS = (
    AroundCenter("金沙湖核心", "120.329690,30.308757", "金沙湖"),
    AroundCenter("湖畔中心", "120.317300,30.308880", "下沙"),
    AroundCenter("龙湖金沙天街", "120.327760,30.310820", "金沙湖"),
    AroundCenter("高沙商业街", "120.331400,30.315780", "下沙"),
    AroundCenter("吾角天街", "120.350980,30.310630", "高教园区"),
    AroundCenter("文泽路地铁", "120.349520,30.316210", "高教园区"),
    AroundCenter("下沙奥特莱斯", "120.384090,30.315000", "下沙"),
    AroundCenter("宝龙城市广场", "120.356480,30.321540", "高教园区"),
    AroundCenter("金沙印象城", "120.344360,30.309600", "金沙湖"),
)

TYPE_SPECS = (
    TypeSpec("餐饮", "050000", "restaurant", "food_drink", ("family_parent_child", "friend_group", "anniversary_emotion"), ("food", "restaurant", "indoor"), 55),
    TypeSpec("咖啡甜品", "050500|050800", "restaurant", "coffee_dessert", ("friend_group", "anniversary_emotion"), ("coffee", "dessert", "quiet_stay"), 38),
    TypeSpec("购物商场", "060000", "activity", "mall", ("family_parent_child", "friend_group", "anniversary_emotion"), ("mall", "shopping", "rain_safe"), 0),
    TypeSpec("休闲娱乐", "080000", "activity", "leisure_play", ("family_parent_child", "friend_group"), ("leisure", "indoor", "group_ok"), 80),
    TypeSpec("电影剧场", "080300", "activity", "cinema", ("friend_group", "anniversary_emotion"), ("movie", "indoor", "date_friendly"), 55),
    TypeSpec("健身运动", "080100|080600", "activity", "sports_fitness", ("friend_group",), ("sports", "fitness", "indoor"), 65),
    TypeSpec("景区公园", "110000", "walk_spot", "scenic_park", ("family_parent_child", "friend_group", "anniversary_emotion"), ("scenic", "park", "outdoor", "mood_relief"), 0),
    TypeSpec("书店文化", "141200|140500", "activity", "bookstore_culture", ("friend_group", "anniversary_emotion"), ("bookstore", "culture", "quiet_alone"), 35),
)

NOISE_TERMS = (
    "大学",
    "学院",
    "学校",
    "校区",
    "教学楼",
    "实验楼",
    "宿舍",
    "招生",
    "培训",
    "教育",
    "幼儿园",
    "小学",
    "中学",
    "公司",
    "产业园",
    "写字楼",
    "办公室",
    "房产",
    "中介",
    "公寓",
    "宿舍楼",
    "汽车",
    "汽修",
    "维修",
    "建材",
    "家具",
    "家居",
    "加油站",
    "充电站",
    "银行",
    "营业厅",
    "厕所",
    "卫生间",
)

NEGATIVE_TYPE_TERMS = ("科教文化服务;学校", "公司企业", "商务住宅", "汽车服务", "汽车维修", "生活服务;通讯营业厅")


class _QuietProgress:
    def update(self, n: int = 1) -> None:
        pass

    def set_postfix(self, *args: Any, **kwargs: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> "_QuietProgress":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def progress_bar(*, total: int, desc: str, unit: str) -> Any:
    try:
        from tqdm import tqdm

        return tqdm(total=total, desc=desc, unit=unit)
    except ImportError:
        return _QuietProgress()


def progress_iter(iterable: Any, *, desc: str, total: int | None = None, unit: str) -> Any:
    try:
        from tqdm import tqdm

        return tqdm(iterable, desc=desc, total=total, unit=unit)
    except ImportError:
        return iterable


def safe_request(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if key != "key"}


def call(endpoint: str, params: dict[str, Any], api_key: str, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    return request_json(endpoint, params | {"key": api_key}, timeout, retry, retry_sleep)


def fetch_around(api_key: str, center: AroundCenter, spec: TypeSpec, radius: int, page: int, offset: int, timeout: int, retry: int, retry_sleep: float) -> dict[str, Any]:
    return call(
        "https://restapi.amap.com/v3/place/around",
        {
            "location": center.location,
            "radius": radius,
            "types": spec.types,
            "offset": offset,
            "page": page,
            "extensions": "all",
            "output": "json",
        },
        api_key,
        timeout,
        retry,
        retry_sleep,
    )


def fetch_raw_pois(api_key: str, radius: int, pages_per_query: int, timeout: int, retry: int, retry_sleep: float, sleep_seconds: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []
    stats = Counter()
    total_requests = len(CENTERS) * len(TYPE_SPECS) * pages_per_query
    with progress_bar(total=total_requests, desc="gaode_poi_around", unit="req") as pbar:
        for center in CENTERS:
            for spec in TYPE_SPECS:
                for page in range(1, pages_per_query + 1):
                    params = {
                        "center_name": center.name,
                        "location": center.location,
                        "radius": radius,
                        "types": spec.types,
                        "offset": 25,
                        "page": page,
                        "extensions": "all",
                        "output": "json",
                    }
                    payload = fetch_around(api_key, center, spec, radius, page, 25, timeout, retry, retry_sleep)
                    pois = payload.get("pois", [])
                    raw_responses.append(
                        {
                            "request": params,
                            "life_pilot_mapping": spec_to_mapping(spec),
                            "response": payload,
                        }
                    )
                    stats["requests"] += 1
                    stats["raw_seen"] += len(pois) if isinstance(pois, list) else 0
                    pbar.update(1)
                    pbar.set_postfix({"raw": stats["raw_seen"], "center": center.name, "type": spec.label})
                    if not isinstance(pois, list) or not pois:
                        break
                    for raw in pois:
                        if isinstance(raw, dict):
                            raw_rows.append({"poi": raw, "center": center.__dict__, "spec": spec})
                    if sleep_seconds:
                        time.sleep(sleep_seconds)
    return raw_rows, raw_responses, dict(stats)


def load_rows_from_raw_archive(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    archive = json.loads(path.read_text(encoding="utf-8"))
    entries = archive.get("responses") or archive.get("poi_around_responses") or []
    rows: list[dict[str, Any]] = []
    stats = Counter()
    for entry in progress_iter(entries, desc="load_raw_archive", total=len(entries), unit="resp"):
        if not isinstance(entry, dict):
            continue
        mapping = entry.get("life_pilot_mapping") if isinstance(entry.get("life_pilot_mapping"), dict) else {}
        spec = spec_from_mapping(mapping)
        pois = entry.get("response", {}).get("pois", [])
        if not isinstance(pois, list):
            continue
        stats["raw_seen"] += len(pois)
        for raw in pois:
            if isinstance(raw, dict):
                rows.append({"poi": raw, "center": {}, "spec": spec or infer_spec(raw)})
    return rows, entries, dict(stats)


def curate_pois(raw_rows: list[dict[str, Any]], target: int, min_rating: float, allow_unrated: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    review_candidates: list[dict[str, Any]] = []
    enrichments: dict[str, Any] = {}
    seen_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    stats = Counter()
    reject_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in progress_iter(raw_rows, desc="curate_pois", total=len(raw_rows), unit="poi"):
        raw = row["poi"]
        spec: TypeSpec = row["spec"]
        stats["raw_considered"] += 1
        reject_reason = reject_raw_poi(raw, min_rating, allow_unrated)
        if reject_reason:
            stats[f"rejected_{reject_reason}"] += 1
            add_reject_example(reject_examples, reject_reason, raw)
            continue
        raw_id = str(raw.get("id") or "")
        if raw_id and raw_id in seen_ids:
            stats["rejected_duplicate_id"] += 1
            continue
        fp = raw_fingerprint(raw)
        if fp in seen_fingerprints:
            stats["rejected_duplicate_fingerprint"] += 1
            continue
        converted = convert_curated_poi(raw, spec, len(accepted) + 1)
        if converted is None:
            stats["rejected_conversion"] += 1
            add_reject_example(reject_examples, "conversion", raw)
            continue
        score = quality_score(raw, spec)
        converted["_quality_score"] = score
        enrichment = build_enrichment(raw, converted, spec, score)
        accepted.append(converted)
        enrichments[converted["poi_id"]] = enrichment
        review_candidates.append(build_review_candidate(converted, enrichment))
        if raw_id:
            seen_ids.add(raw_id)
        seen_fingerprints.add(fp)

    accepted.sort(key=lambda item: item.pop("_quality_score", 0), reverse=True)
    accepted = resequence_poi_ids(accepted[:target])
    resequenced_enrichments: dict[str, Any] = {}
    for poi in accepted:
        enrichment = dict(enrichments.get(poi.get("_old_poi_id", poi["poi_id"]), {}))
        enrichment["life_pilot_poi_id"] = poi["poi_id"]
        resequenced_enrichments[poi["poi_id"]] = enrichment
    enrichments = resequenced_enrichments
    for poi in accepted:
        poi.pop("_old_poi_id", None)
    review_candidates = [build_review_candidate(poi, enrichments[poi["poi_id"]]) for poi in accepted]

    payload = {"version": "v0.1", "area": AREA, "pois": accepted}
    enrichment_payload = {
        "version": "v0.1",
        "source": "gaode_web_service_place_around",
        "area": AREA,
        "created_at": ISO_NOW,
        "note": "Sidecar for fields useful to frontend/manual review. mock_pois.json keeps the LifePilot schema-safe POI shape.",
        "enrichments": enrichments,
    }
    report = {
        "task": "gaode_generate_lifepilot_dataset",
        "success": len(accepted) >= target,
        "target_pois": target,
        "accepted_pois": len(accepted),
        "filter_stats": dict(stats),
        "category_counts": dict(Counter(poi["category"] for poi in accepted)),
        "sub_category_counts": dict(Counter(poi["sub_category"] for poi in accepted)),
        "area_counts": dict(Counter(poi["area"] for poi in accepted)),
        "scenario_counts": dict(Counter(scenario for poi in accepted for scenario in poi["suitable_scenarios"])),
        "missing_scenarios": sorted(REQUIRED_SCENARIOS - {scenario for poi in accepted for scenario in poi["suitable_scenarios"]}),
        "reject_examples": reject_examples,
    }
    review_payload = {
        "version": "v0.1",
        "area": AREA,
        "created_at": ISO_NOW,
        "note": "给人工筛选核查用；包含高德 id、type/typecode、图片数、电话、评分、人均、质量分等，不进入业务 API 契约。",
        "candidates": review_candidates,
    }
    return payload, enrichment_payload, report | {"review_payload": review_payload},


def reject_raw_poi(raw: dict[str, Any], min_rating: float, allow_unrated: bool) -> str | None:
    lng, lat = parse_location(raw.get("location"))
    if lng is None or lat is None:
        return "invalid_location"
    if infer_area(lat, lng, raw) is None:
        return "out_of_area"
    if str(raw.get("adcode") or ADCODE_QIANTANG) != ADCODE_QIANTANG:
        return "outside_qiantang"
    text = f"{raw.get('name','')} {raw.get('type','')} {raw.get('address','')}"
    if any(term in text for term in NOISE_TERMS) or any(term in text for term in NEGATIVE_TYPE_TERMS):
        return "noise"
    rating = raw_rating(raw)
    if rating is None and not allow_unrated:
        return "missing_rating"
    if rating is not None and rating < min_rating:
        return "low_rating"
    return None


def convert_curated_poi(raw: dict[str, Any], spec: TypeSpec, sequence: int) -> dict[str, Any] | None:
    lng, lat = parse_location(raw.get("location"))
    if lng is None or lat is None:
        return None
    area = infer_area(lat, lng, raw)
    if area is None:
        return None
    raw_id = str(raw.get("id") or "")
    suffix = hashlib.sha1((raw_id or raw_fingerprint(raw)).encode("utf-8")).hexdigest()[:8]
    name = clean_text(raw.get("name"), f"高德候选{sequence:03d}", 48)
    cost = raw_cost(raw)
    rating = raw_rating(raw)
    poi_id = f"poi_gaode_curated_{spec.category}_{sequence:03d}_{suffix}"
    return {
        "poi_id": poi_id,
        "name": name,
        "category": spec.category,
        "sub_category": spec.sub_category,
        "tags": build_tags(raw, spec),
        "location": {
            "city": "杭州",
            "area": area,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
        },
        "area": area,
        "address": clean_text(raw.get("address"), f"杭州市钱塘区{area}", 96),
        "price_per_person": normalize_price(cost, spec),
        "rating": normalize_rating(rating),
        "opening_hours": parse_opening_hours(raw_open_time(raw)) or DEFAULT_OPENING_HOURS.get(spec.category, DEFAULT_OPENING_HOURS["activity"]),
        "suitable_scenarios": list(spec.scenarios),
        "risk_tags": risk_tags_for(raw, spec),
        "mock_only": True,
        "created_at": ISO_NOW,
        "updated_at": ISO_NOW,
    }


def resequence_poi_ids(pois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    category_counts = Counter()
    output: list[dict[str, Any]] = []
    for poi in pois:
        item = dict(poi)
        old_id = item["poi_id"]
        category_counts[item["category"]] += 1
        digest = hashlib.sha1(old_id.encode("utf-8")).hexdigest()[:6]
        item["_old_poi_id"] = old_id
        item["poi_id"] = f"poi_gaode_{item['category']}_{category_counts[item['category']]:03d}_{digest}"
        output.append(item)
    return output


def build_enrichment(raw: dict[str, Any], poi: dict[str, Any], spec: TypeSpec, score: float) -> dict[str, Any]:
    photos = raw.get("photos") if isinstance(raw.get("photos"), list) else []
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    return {
        "gaode_id": raw.get("id"),
        "name": raw.get("name"),
        "life_pilot_poi_id": poi["poi_id"],
        "life_pilot_category": spec.category,
        "life_pilot_sub_category": spec.sub_category,
        "gaode_type": raw.get("type"),
        "gaode_typecode": raw.get("typecode"),
        "adcode": raw.get("adcode"),
        "business_area": raw.get("business_area"),
        "address": raw.get("address"),
        "location": raw.get("location"),
        "tel": raw.get("tel") if raw.get("tel") not in ("", [], None) else None,
        "rating": raw_rating(raw),
        "cost": raw_cost(raw),
        "open_time": raw_open_time(raw),
        "photos": [{"title": photo.get("title"), "url": photo.get("url")} for photo in photos[:6] if isinstance(photo, dict)],
        "photos_count": len(photos),
        "biz_ext": {key: value for key, value in biz_ext.items() if value not in ("", [], None)},
        "quality_score": score,
        "source": "gaode_web_service_place_around",
    }


def build_review_candidate(poi: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    return {
        "poi_id": poi["poi_id"],
        "name": poi["name"],
        "category": poi["category"],
        "sub_category": poi["sub_category"],
        "area": poi["area"],
        "address": poi["address"],
        "rating": poi["rating"],
        "price_per_person": poi["price_per_person"],
        "tags": poi["tags"],
        "risk_tags": poi["risk_tags"],
        "gaode_id": enrichment.get("gaode_id"),
        "gaode_type": enrichment.get("gaode_type"),
        "gaode_typecode": enrichment.get("gaode_typecode"),
        "tel_present": bool(enrichment.get("tel")),
        "photos_count": enrichment.get("photos_count", 0),
        "first_photo_url": (enrichment.get("photos") or [{}])[0].get("url") if enrichment.get("photos") else None,
        "open_time": enrichment.get("open_time"),
        "quality_score": enrichment.get("quality_score"),
    }


def build_route_pairs(pois: list[dict[str, Any]], neighbors: int, max_pairs: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for origin in progress_iter(pois, desc="route_pairs", total=len(pois), unit="poi"):
        ranked = sorted(
            (dest for dest in pois if dest["poi_id"] != origin["poi_id"]),
            key=lambda dest: haversine_km(origin["location"], dest["location"]),
        )
        for dest in ranked[:neighbors]:
            key = (origin["poi_id"], dest["poi_id"])
            if key in seen:
                continue
            seen.add(key)
            pairs.append((origin, dest))
            if len(pairs) >= max_pairs:
                return pairs
    return pairs


def build_routes(api_key: str, pois: list[dict[str, Any]], route_neighbors: int, max_route_pairs: int, modes: tuple[str, ...], timeout: int, retry: int, retry_sleep: float, sleep_seconds: float) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    route_raw: list[dict[str, Any]] = []
    stats = Counter()
    pairs = build_route_pairs(pois, route_neighbors, max_route_pairs)
    with progress_bar(total=len(pairs) * len(modes), desc="gaode_routes", unit="req") as pbar:
        for origin, dest in pairs:
            for mode in modes:
                stats["route_attempts"] += 1
                try:
                    parsed, raw_entry = fetch_route(api_key, origin, dest, mode, timeout, retry, retry_sleep)
                except Exception as exc:
                    stats[f"route_failed_{mode}"] += 1
                    route_raw.append({"mode": mode, "origin_poi_id": origin["poi_id"], "destination_poi_id": dest["poi_id"], "error": str(exc)})
                    pbar.update(1)
                    pbar.set_postfix({"ok": len(routes), "failed": sum(value for key, value in stats.items() if key.startswith("route_failed_"))})
                    continue
                if parsed is None:
                    stats[f"route_unavailable_{mode}"] += 1
                    route_raw.append(raw_entry)
                    pbar.update(1)
                    pbar.set_postfix({"ok": len(routes), "unavailable": sum(value for key, value in stats.items() if key.startswith("route_unavailable_"))})
                    continue
                route_id = f"route_gaode_{len(routes) + 1:05d}_{mode}"
                parsed["route_id"] = route_id
                routes.append(parsed)
                raw_entry["route_id"] = route_id
                route_raw.append(raw_entry)
                stats[f"route_success_{mode}"] += 1
                pbar.update(1)
                pbar.set_postfix({"ok": len(routes), "mode": mode})
                if sleep_seconds:
                    time.sleep(sleep_seconds)
    return (
        {"version": "v0.1", "routes": routes},
        {
            "version": "v0.1",
            "source": "gaode_web_service_direction",
            "created_at": ISO_NOW,
            "note": "Raw route responses omit API keys. mock_routes.json keeps only RouteEstimate contract fields.",
            "responses": route_raw,
        },
        {"route_pair_count": len(pairs), "route_count": len(routes), **dict(stats)},
    )


def fetch_route(api_key: str, origin: dict[str, Any], dest: dict[str, Any], mode: str, timeout: int, retry: int, retry_sleep: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    origin_text = location_text(origin)
    dest_text = location_text(dest)
    if mode == "walk":
        endpoint = "https://restapi.amap.com/v3/direction/walking"
        params = {"origin": origin_text, "destination": dest_text, "output": "json"}
    elif mode == "drive":
        endpoint = "https://restapi.amap.com/v3/direction/driving"
        params = {"origin": origin_text, "destination": dest_text, "extensions": "all", "output": "json"}
    elif mode == "subway":
        endpoint = "https://restapi.amap.com/v3/direction/transit/integrated"
        params = {"origin": origin_text, "destination": dest_text, "city": "杭州", "cityd": "杭州", "strategy": 0, "extensions": "all", "output": "json"}
    else:
        raise ValueError(f"unsupported route mode: {mode}")
    response = call(endpoint, params, api_key, timeout, retry, retry_sleep)
    parsed = parse_route_response(mode, response, origin["poi_id"], dest["poi_id"])
    raw_entry = {
        "mode": mode,
        "origin_poi_id": origin["poi_id"],
        "destination_poi_id": dest["poi_id"],
        "request": safe_request(params) | {"endpoint": endpoint},
        "parsed_summary": parsed,
        "response": shrink_route_response(mode, response),
    }
    return parsed, raw_entry


def parse_route_response(mode: str, response: dict[str, Any], origin_id: str, dest_id: str) -> dict[str, Any] | None:
    if mode == "subway":
        transits = response.get("route", {}).get("transits", [])
        if not isinstance(transits, list) or not transits:
            return None
        chosen = choose_subway_transit(transits)
        distance_m = parse_float(chosen.get("distance"), None)
        duration_s = parse_float(chosen.get("duration"), None)
        if distance_m is None or duration_s is None:
            return None
        subway_found = transit_has_subway(chosen)
        return route_contract(origin_id, dest_id, "subway", distance_m, duration_s, "smooth", 0.84 if subway_found else 0.66)

    paths = response.get("route", {}).get("paths", [])
    if not isinstance(paths, list) or not paths:
        return None
    first = paths[0] if isinstance(paths[0], dict) else {}
    distance_m = parse_float(first.get("distance"), None)
    duration_s = parse_float(first.get("duration"), None)
    if distance_m is None or duration_s is None:
        return None
    traffic_level = infer_traffic_level(mode, distance_m, duration_s)
    return route_contract(origin_id, dest_id, mode, distance_m, duration_s, traffic_level, 0.9 if mode == "walk" else 0.86)


def route_contract(origin_id: str, dest_id: str, mode: str, distance_m: float, duration_s: float, traffic_level: str, confidence: float) -> dict[str, Any]:
    return {
        "route_id": "route_pending",
        "origin_poi_id": origin_id,
        "destination_poi_id": dest_id,
        "transport_mode": mode,
        "distance_km": round(distance_m / 1000, 2),
        "duration_minutes": max(1, math.ceil(duration_s / 60)),
        "traffic_level": traffic_level,
        "confidence": confidence,
        "source": "mock_api",
        "updated_at": ISO_NOW,
    }


def choose_subway_transit(transits: list[dict[str, Any]]) -> dict[str, Any]:
    for transit in transits:
        if transit_has_subway(transit):
            return transit
    return transits[0]


def transit_has_subway(transit: dict[str, Any]) -> bool:
    text = json.dumps(transit, ensure_ascii=False)
    return "地铁" in text or "轨道交通" in text


def shrink_route_response(mode: str, response: dict[str, Any]) -> dict[str, Any]:
    route = response.get("route", {})
    if mode == "subway":
        transits = route.get("transits", [])
        first = choose_subway_transit(transits) if isinstance(transits, list) and transits else {}
        return {
            "status": response.get("status"),
            "info": response.get("info"),
            "infocode": response.get("infocode"),
            "transits_count": len(transits) if isinstance(transits, list) else 0,
            "first_transit": {
                "distance": first.get("distance"),
                "duration": first.get("duration"),
                "cost": first.get("cost"),
                "segments_count": len(first.get("segments", [])) if isinstance(first.get("segments"), list) else None,
                "has_subway": transit_has_subway(first) if isinstance(first, dict) else False,
            },
        }
    paths = route.get("paths", [])
    first = paths[0] if isinstance(paths, list) and paths and isinstance(paths[0], dict) else {}
    return {
        "status": response.get("status"),
        "info": response.get("info"),
        "infocode": response.get("infocode"),
        "paths_count": len(paths) if isinstance(paths, list) else 0,
        "first_path": {
            "distance": first.get("distance"),
            "duration": first.get("duration"),
            "strategy": first.get("strategy"),
            "steps_count": len(first.get("steps", [])) if isinstance(first.get("steps"), list) else None,
        },
    }


def spec_to_mapping(spec: TypeSpec) -> dict[str, Any]:
    return {
        "label": spec.label,
        "types": spec.types,
        "category": spec.category,
        "sub_category": spec.sub_category,
        "suitable_scenarios": list(spec.scenarios),
        "base_tags": list(spec.tags),
    }


def spec_from_mapping(mapping: dict[str, Any]) -> TypeSpec | None:
    category = mapping.get("category")
    sub_category = mapping.get("sub_category")
    for spec in TYPE_SPECS:
        if spec.category == category and spec.sub_category == sub_category:
            return spec
    return None


def infer_spec(raw: dict[str, Any]) -> TypeSpec:
    typecode = str(raw.get("typecode") or "")
    type_text = str(raw.get("type") or "")
    for spec in TYPE_SPECS:
        prefixes = tuple(part[:2] for part in spec.types.split("|"))
        if typecode[:2] in prefixes:
            return spec
    if "餐饮" in type_text or typecode.startswith("05"):
        return TYPE_SPECS[0]
    if "风景" in type_text or typecode.startswith("11"):
        return TYPE_SPECS[6]
    return TYPE_SPECS[3]


def infer_area(lat: float, lng: float, raw: dict[str, Any]) -> str | None:
    text = f"{raw.get('name', '')} {raw.get('address', '')} {raw.get('business_area', '')}"
    preferred: list[str] = []
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


def raw_rating(raw: dict[str, Any]) -> float | None:
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    return parse_float(biz_ext.get("rating"), None)


def raw_cost(raw: dict[str, Any]) -> float | None:
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    return parse_float(biz_ext.get("cost"), None)


def raw_open_time(raw: dict[str, Any]) -> str | None:
    biz_ext = raw.get("biz_ext") if isinstance(raw.get("biz_ext"), dict) else {}
    value = biz_ext.get("open_time")
    return str(value) if value not in (None, "", []) else None


def quality_score(raw: dict[str, Any], spec: TypeSpec) -> float:
    rating = raw_rating(raw)
    cost = raw_cost(raw)
    photos = raw.get("photos") if isinstance(raw.get("photos"), list) else []
    score = 0.0
    if rating is not None:
        score += rating * 20
    if cost is not None:
        score += 7
    if raw_open_time(raw):
        score += 6
    if photos:
        score += min(8, len(photos) * 2)
    if raw.get("tel") not in (None, "", []):
        score += 3
    if spec.category in {"restaurant", "activity"}:
        score += 3
    return round(score, 2)


def build_tags(raw: dict[str, Any], spec: TypeSpec) -> list[str]:
    text = f"{raw.get('name','')} {raw.get('type','')} {raw.get('address','')}"
    tags = ["gaode_poi", *spec.tags]
    rules = (
        ("剧本", "script_murder"),
        ("桌游", "board_game"),
        ("足疗", "foot_massage"),
        ("按摩", "massage"),
        ("游乐", "amusement"),
        ("儿童", "child_friendly"),
        ("书店", "bookstore"),
        ("健身", "fitness"),
        ("游泳", "swimming"),
        ("电影", "movie"),
        ("影院", "movie"),
        ("电竞", "esports"),
        ("景区", "scenic"),
        ("公园", "park"),
        ("咖啡", "coffee"),
        ("甜品", "dessert"),
        ("商场", "mall"),
        ("天街", "mall"),
        ("宝龙", "mall"),
        ("金沙湖", "lake"),
    )
    for needle, tag in rules:
        if needle in text:
            tags.append(tag)
    if raw.get("photos"):
        tags.append("has_photo")
    if raw.get("tel") not in (None, "", []):
        tags.append("has_tel")
    return list(dict.fromkeys(tag for tag in tags if tag))[:14]


def risk_tags_for(raw: dict[str, Any], spec: TypeSpec) -> list[str]:
    risks: list[str] = []
    if spec.category == "restaurant":
        risks.append("queue_risk")
    if spec.category == "activity":
        risks.append("capacity_risk")
    if spec.category == "walk_spot" or "公园" in f"{raw.get('name','')} {raw.get('type','')}":
        risks.append("weather_risk")
    if raw_rating(raw) is None:
        risks.append("rating_missing")
    if raw_open_time(raw) is None:
        risks.append("opening_hours_fallback")
    return risks[:6]


def parse_opening_hours(value: Any) -> dict[str, list[list[str]]] | None:
    if not isinstance(value, str):
        return None
    import re

    ranges = re.findall(r"([01]\d|2[0-3]):([0-5]\d)\s*[-~至]\s*([01]\d|2[0-3]):([0-5]\d)", value)
    if not ranges:
        return None
    normalized = [[f"{start_h}:{start_m}", f"{end_h}:{end_m}"] for start_h, start_m, end_h, end_m in ranges[:3]]
    return {"weekday": normalized, "weekend": normalized}


def normalize_price(value: float | None, spec: TypeSpec) -> float | None:
    if value is None:
        return spec.default_price
    if value <= 0:
        return 0.0
    return round(min(value, 800.0), 1)


def normalize_rating(value: float | None) -> float:
    if value is None:
        value = 4.2
    return round(min(5.0, max(3.5, value)), 1)


def infer_traffic_level(mode: str, distance_m: float, duration_s: float) -> str:
    if mode == "walk":
        return "smooth"
    speed_kmh = (distance_m / 1000) / max(duration_s / 3600, 0.01)
    if speed_kmh < 10:
        return "congested"
    if speed_kmh < 22:
        return "medium"
    return "smooth"


def location_text(poi: dict[str, Any]) -> str:
    loc = poi["location"]
    return f"{loc['lng']},{loc['lat']}"


def haversine_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lng1 = math.radians(float(a["lat"])), math.radians(float(a["lng"]))
    lat2, lng2 = math.radians(float(b["lat"])), math.radians(float(b["lng"]))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def raw_fingerprint(raw: dict[str, Any]) -> str:
    value = f"{raw.get('name','')}|{raw.get('location','')}|{raw.get('address','')}"
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def clean_text(value: Any, default: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text or text == "[]":
        return default
    return " ".join(text.split())[:limit]


def add_reject_example(bucket: dict[str, list[dict[str, Any]]], reason: str, raw: dict[str, Any]) -> None:
    if len(bucket[reason]) >= 5:
        return
    bucket[reason].append({"id": raw.get("id"), "name": raw.get("name"), "type": raw.get("type"), "typecode": raw.get("typecode"), "address": raw.get("address")})


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a curated LifePilot 500-POI candidate pool and Gaode-backed route estimates.")
    parser.add_argument("--key", default=os.environ.get("AMAP_KEY"), help="Gaode Web Service API key. Defaults to AMAP_KEY.")
    parser.add_argument("--target-pois", type=int, default=500)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--raw-input", type=Path, help="Reuse an existing raw archive instead of calling place/around. Useful for dry runs.")
    parser.add_argument("--radius", type=int, default=2600)
    parser.add_argument("--pages-per-query", type=int, default=4)
    parser.add_argument("--min-rating", type=float, default=4.0)
    parser.add_argument("--allow-unrated", action="store_true", help="Keep POIs without Gaode rating if they otherwise look useful.")
    parser.add_argument("--skip-routes", action="store_true")
    parser.add_argument("--route-neighbors", type=int, default=4, help="Nearest destination count per POI before max-route-pairs cap.")
    parser.add_argument("--max-route-pairs", type=int, default=1600)
    parser.add_argument("--route-modes", default="walk,drive,subway")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retry", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
    parser.add_argument("--sleep", type=float, default=0.35)
    args = parser.parse_args()

    if args.target_pois < 1:
        parser.error("--target-pois must be positive.")
    if not args.raw_input and not args.key:
        parser.error("Gaode key is required unless --raw-input is provided. Pass --key or set AMAP_KEY.")
    if not args.skip_routes and not args.key:
        parser.error("Route generation requires --key or AMAP_KEY. Use --skip-routes for raw-input dry runs.")

    if args.raw_input:
        raw_rows, raw_responses, fetch_stats = load_rows_from_raw_archive(args.raw_input)
        raw_source = f"raw_input:{args.raw_input}"
    else:
        raw_rows, raw_responses, fetch_stats = fetch_raw_pois(args.key, args.radius, args.pages_per_query, args.timeout, args.retry, args.retry_sleep, args.sleep)
        raw_source = "gaode_web_service_place_around"

    poi_payload, enrichment_payload, poi_report = curate_pois(raw_rows, args.target_pois, args.min_rating, args.allow_unrated)
    review_payload = poi_report.pop("review_payload")
    route_payload = {"version": "v0.1", "routes": []}
    route_raw = {"version": "v0.1", "responses": []}
    route_report: dict[str, Any] = {"skipped": True}
    if not args.skip_routes and poi_payload["pois"]:
        modes = tuple(mode.strip() for mode in args.route_modes.split(",") if mode.strip())
        route_payload, route_raw, route_report = build_routes(args.key, poi_payload["pois"], args.route_neighbors, args.max_route_pairs, modes, args.timeout, args.retry, args.retry_sleep, args.sleep)

    raw_archive = {
        "version": "v0.1",
        "source": raw_source,
        "area": AREA,
        "created_at": ISO_NOW,
        "note": "Raw Gaode responses are stored without API keys.",
        "responses": raw_responses,
    }
    final_report = {
        **poi_report,
        "created_at": ISO_NOW,
        "raw_source": raw_source,
        "fetch_stats": fetch_stats,
        "route_report": route_report,
        "output_files": {
            "pois": str(args.output / "mock_pois.json"),
            "routes": str(args.output / "mock_routes.json"),
            "poi_enrichment": str(args.output / "gaode_poi_enrichment.json"),
            "review_candidates": str(args.output / "gaode_poi_review_candidates.json"),
            "raw": str(args.output / "gaode_lifepilot_raw.json"),
            "route_raw": str(args.output / "gaode_route_raw_responses.json"),
        },
        "manual_review_note": "POI 已按评分、噪声、重复、范围做机器筛选；建议人工重点核查 gaode_poi_review_candidates.json 的名称、类别、图片和营业时间。",
    }

    write_json(args.output / "mock_pois.json", poi_payload)
    write_json(args.output / "gaode_poi_enrichment.json", enrichment_payload)
    write_json(args.output / "gaode_poi_review_candidates.json", review_payload)
    write_json(args.output / "gaode_lifepilot_raw.json", raw_archive)
    if not args.skip_routes:
        write_json(args.output / "mock_routes.json", route_payload)
        write_json(args.output / "gaode_route_raw_responses.json", route_raw)
    write_json(REPORTS_DIR / "generate_lifepilot_dataset_report.json", final_report)
    print(json.dumps({key: final_report[key] for key in ("success", "target_pois", "accepted_pois", "category_counts", "area_counts", "route_report", "output_files")}, ensure_ascii=False, indent=2))
    return 0 if final_report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
