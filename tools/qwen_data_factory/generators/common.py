from __future__ import annotations

import json
import math
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FACTORY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FACTORY_ROOT.parents[1]
DATA_DIR = REPO_ROOT / "backend" / "data"
PROMPTS_DIR = FACTORY_ROOT / "prompts"
REPORTS_DIR = FACTORY_ROOT / "reports"
STAGING_DIR = FACTORY_ROOT / "staging"
AREA = "杭州下沙/金沙湖/高教园区"
NOW = datetime(2026, 5, 20, 13, 0, tzinfo=timezone(timedelta(hours=8)))
ISO_NOW = NOW.isoformat()

POI_ALLOWED = {
    "poi_id",
    "name",
    "category",
    "sub_category",
    "tags",
    "location",
    "area",
    "address",
    "price_per_person",
    "rating",
    "opening_hours",
    "suitable_scenarios",
    "risk_tags",
    "mock_only",
    "created_at",
    "updated_at",
}
VALID_CATEGORIES = {"activity", "restaurant", "walk_spot", "service", "transport_anchor"}
VALID_SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}
AREA_BOUNDS = {
    "下沙": {"lat": (30.285, 30.345), "lng": (120.300, 120.390)},
    "金沙湖": {"lat": (30.300, 30.335), "lng": (120.330, 120.375)},
    "高教园区": {"lat": (30.295, 30.345), "lng": (120.345, 120.420)},
}
FORBIDDEN_PATTERNS = [
    "".join(parts)
    for parts in [
        ("真", "实", "支", "付"),
        ("已", "支", "付"),
        ("微", "信", "已", "发", "送"),
        ("短", "信", "已", "发", "送"),
        ("真", "实", "微", "信"),
        ("真", "实", "短", "信"),
        ("真", "实", "订", "座"),
        ("真", "实", "锁", "票"),
        ("已", "锁", "票"),
        ("实", "时", "抓", "取"),
        ("已", "实", "时", "抓", "取"),
        ("调", "用", "真", "实", "商", "家"),
    ]
]


def ensure_dirs() -> None:
    for path in (DATA_DIR, REPORTS_DIR, STAGING_DIR):
        path.mkdir(parents=True, exist_ok=True)


def read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(name: str, payload: dict[str, Any]) -> None:
    write_json(REPORTS_DIR / name, payload)


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


def progress_bar(*, total: int, desc: str, unit: str = "item") -> Any:
    try:
        from tqdm import tqdm

        return tqdm(total=total, desc=desc, unit=unit)
    except ImportError:
        return _QuietProgress()


def progress_iter(iterable: Any, *, desc: str, total: int | None = None, unit: str = "item") -> Any:
    try:
        from tqdm import tqdm

        return tqdm(iterable, desc=desc, total=total, unit=unit)
    except ImportError:
        return iterable


def parse_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def assert_no_forbidden_text(payload: Any, source: str) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    hits = [pattern for pattern in FORBIDDEN_PATTERNS if pattern in text]
    if hits:
        raise ValueError(f"{source} contains forbidden real-platform wording: {hits}")


def sanitize_poi(candidate: dict[str, Any], sequence: int) -> dict[str, Any] | None:
    poi = {key: candidate.get(key) for key in POI_ALLOWED if key in candidate}
    category = poi.get("category")
    if category not in VALID_CATEGORIES:
        return None
    scenario_values = poi.get("suitable_scenarios")
    if not isinstance(scenario_values, list):
        return None
    scenarios = [item for item in scenario_values if item in VALID_SCENARIOS]
    if not scenarios:
        return None
    poi_id = str(poi.get("poi_id") or "")
    if not poi_id.startswith("poi_"):
        slug = _slug(category)
        poi_id = f"poi_{slug}_{sequence:03d}"
    poi["poi_id"] = _safe_id(poi_id, "poi_", sequence)
    poi["name"] = str(poi.get("name") or f"下沙Mock地点{sequence:03d}")[:40]
    poi["tags"] = [str(tag)[:40] for tag in poi.get("tags", []) if isinstance(tag, str)][:12] or ["mock"]
    poi["tags"] = _clean_incompatible_tags(poi)
    location = poi.get("location")
    if not isinstance(location, dict):
        location = {}
    location["city"] = "杭州"
    location["area"] = location.get("area") if location.get("area") in {"下沙", "金沙湖", "高教园区"} else _area_for(sequence)
    location["lat"] = _clamp_coordinate(_number(location.get("lat"), 30.31 + (sequence % 15) * 0.002), location["area"], "lat")
    location["lng"] = _clamp_coordinate(_number(location.get("lng"), 120.34 + (sequence % 15) * 0.002), location["area"], "lng")
    poi["location"] = location
    poi["area"] = location["area"]
    poi["address"] = str(poi.get("address") or f"杭州市钱塘区{location['area']}Mock地址{sequence}号")[:80]
    poi["price_per_person"] = _nullable_number(poi.get("price_per_person"))
    poi["rating"] = min(5.0, max(3.5, _number(poi.get("rating"), 4.5)))
    poi["opening_hours"] = poi.get("opening_hours") if isinstance(poi.get("opening_hours"), dict) else {"weekday": [["10:00", "21:30"]], "weekend": [["09:30", "22:00"]]}
    poi["suitable_scenarios"] = scenarios
    poi["risk_tags"] = [str(tag)[:40] for tag in poi.get("risk_tags", []) if isinstance(tag, str)][:6]
    poi["mock_only"] = True
    poi["created_at"] = _iso_or_now(poi.get("created_at"))
    poi["updated_at"] = _iso_or_now(poi.get("updated_at"))
    return poi


def seed_pois(target: int) -> list[dict[str, Any]]:
    bases = [
        ("activity", "pet_corner", "金沙湖小动物友好草坪", ["pet_friendly", "outdoor", "mood_relief", "shade"], ["family_parent_child", "friend_group"], 0),
        ("restaurant", "clean_light_food", "金沙湖明档轻食厨房", ["clean_table", "low_calorie", "bright", "work_lunch"], ["family_parent_child", "friend_group", "anniversary_emotion"], 58),
        ("walk_spot", "quiet_walk", "金沙湖西岸放空步道", ["quiet_alone", "mood_relief", "lake_walk", "low_budget"], ["family_parent_child", "friend_group", "anniversary_emotion"], 0),
        ("activity", "sports_recovery", "下沙河岸慢跑补给点", ["sports_friendly", "water_supply", "stretch", "outdoor"], ["friend_group"], 20),
        ("restaurant", "visitor_noodle", "高教园烟火面馆", ["visitor_friendly", "budget", "quick_meal", "local_flavor"], ["friend_group", "family_parent_child"], 32),
        ("activity", "quiet_bookstore", "文海路独处书店角", ["quiet_alone", "work_friendly", "clean_restroom", "indoor"], ["friend_group", "anniversary_emotion"], 28),
        ("restaurant", "coffee_work", "金沙湖插座咖啡吧", ["coffee_quality", "work_friendly", "socket", "noise_risk"], ["friend_group", "anniversary_emotion"], 42),
        ("service", "clean_restroom", "金沙湖干净洗手间补给点", ["clean_restroom", "handwash", "rain_safe", "service"], ["family_parent_child", "friend_group"], None),
        ("service", "pharmacy", "下沙夜间便利药箱", ["late_supply", "pharmacy", "bright", "emergency_supply"], ["family_parent_child", "friend_group"], 15),
        ("transport_anchor", "parking", "下沙高教园区东共享停车点B区", ["parking_easy", "parking_shortage", "visitor_friendly"], ["family_parent_child", "friend_group"], None),
        ("transport_anchor", "metro", "金沙湖地铁口好找集合点", ["metro", "easy_meeting", "visitor_friendly", "rain_safe"], ["friend_group", "anniversary_emotion"], None),
        ("activity", "indoor_exhibit", "金沙湖小型展览走廊", ["indoor", "visitor_friendly", "photo", "rain_safe"], ["friend_group", "anniversary_emotion"], 35),
        ("service", "changing_room", "高教园运动后更衣洗手点", ["changing_room", "sports_friendly", "cleanliness_risk", "indoor"], ["family_parent_child", "friend_group"], None),
        ("activity", "low_noise_game", "下沙低噪桌游室", ["low_noise", "light_entertainment", "group_ok", "indoor"], ["friend_group"], 55),
        ("walk_spot", "shade_walk", "高教园林荫散心小路", ["shade", "mood_relief", "quiet_alone", "walk"], ["family_parent_child", "friend_group", "anniversary_emotion"], 0),
    ]
    pois: list[dict[str, Any]] = []
    for index in progress_iter(range(target), desc="seed_pois", total=target, unit="poi"):
        category, sub, name, tags, scenarios, price = bases[index % len(bases)]
        area = _area_for(index)
        poi = {
            "poi_id": f"poi_{sub}_{index + 1:03d}",
            "name": f"{name}{'' if index < len(bases) else f' {index // len(bases) + 1}'}",
            "category": category,
            "sub_category": sub,
            "tags": tags + [area],
            "location": {"city": "杭州", "area": area, "lat": 30.306 + (index % 20) * 0.0021, "lng": 120.331 + (index % 18) * 0.0024},
            "area": area,
            "address": f"杭州市钱塘区{area}Mock地址{index + 1}号",
            "price_per_person": price,
            "rating": round(4.2 + (index % 8) * 0.08, 1),
            "opening_hours": {"weekday": [["10:00", "21:30"]], "weekend": [["09:30", "22:00"]]},
            "suitable_scenarios": scenarios,
            "risk_tags": _risk_tags(category, sub),
            "mock_only": True,
            "created_at": ISO_NOW,
            "updated_at": ISO_NOW,
        }
        pois.append(poi)
    return pois


def build_statuses(pois: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, Any] = {}
    for idx, poi in enumerate(progress_iter(pois, desc="mock_status", total=len(pois), unit="poi")):
        category = poi["category"]
        available = True
        query = {
            "available": available,
            "open_status": "open",
            "queue_minutes": 5 + idx % 18,
            "risk_level": "low" if idx % 5 else "medium",
            "status_message": "Demo Mock状态快照，建议在可执行窗口内确认。",
            "source": "mock_api",
            "updated_at": ISO_NOW,
            "expire_at": (NOW + timedelta(minutes=18 + idx % 12)).isoformat(),
        }
        if category == "restaurant":
            query.update(
                {
                    "available_tables": 1 + idx % 5,
                    "reservation_available": True,
                    "capacity_by_party_size": {"2": 4, "3": 3, "4": 2 + idx % 2, "6": 0 if idx % 3 == 0 else 1},
                    "peak_time_risk": "medium" if idx % 4 == 0 else "low",
                }
            )
            execute = {"reserve_restaurant": {"success": True, "booking_id_prefix": "MR", "mock_only": True}}
        elif category == "activity":
            query.update(
                {
                    "ticket_available": True,
                    "remaining_tickets": 8 + idx % 30,
                    "booking_required": True,
                    "booking_available": True,
                    "duration_minutes": 70 + idx % 40,
                    "indoor": "indoor" in poi.get("tags", []),
                }
            )
            execute = {"book_activity": {"success": True, "booking_id_prefix": "BA", "mock_only": True}}
        else:
            execute = {}
        statuses[poi["poi_id"]] = {
            "query_status": query,
            "execute_status": execute,
        }
    restaurants = [poi for poi in pois if poi["category"] == "restaurant"]
    activities = [poi for poi in pois if poi["category"] == "activity"]
    if restaurants:
        rid = restaurants[0]["poi_id"]
        statuses[rid]["execute_status"]["reserve_restaurant"] = {
            "success": False,
            "error_code": "NO_TABLE_AVAILABLE",
            "message": "当前时段Mock桌位已满，触发Recovery。",
            "mock_only": True,
        }
        statuses[rid]["debug_failure_ref"] = "fail_no_table_family_001"
    if activities:
        aid = activities[0]["poi_id"]
        statuses[aid]["debug_failure_ref"] = "fail_activity_full_001"
    return {"version": "v0.1", "statuses": statuses}


def build_inventory(pois: list[dict[str, Any]]) -> dict[str, Any]:
    restaurant_slots = []
    activity_slots = []
    for idx, poi in enumerate(progress_iter(pois, desc="mock_inventory", total=len(pois), unit="poi")):
        start = NOW + timedelta(hours=2 + (idx % 3))
        slot = {"poi_id": poi["poi_id"], "slot_start": start.isoformat(), "slot_end": (start + timedelta(hours=1)).isoformat()}
        if poi["category"] == "restaurant":
            restaurant_slots.append({**slot, "base_tables": 4 + idx % 4, "reserved_tables": idx % 3, "max_party_size": 4 if idx % 2 else 6})
        if poi["category"] == "activity":
            activity_slots.append({**slot, "remaining_tickets": 8 + idx % 24, "booking_available": True})
    return {"version": "v0.1", "restaurant_slots": restaurant_slots, "activity_slots": activity_slots}


def build_routes(pois: list[dict[str, Any]], max_routes: int = 260) -> dict[str, Any]:
    routes = []
    with progress_bar(total=max_routes, desc="mock_routes", unit="route") as pbar:
        for i, origin in enumerate(pois):
            if len(routes) >= max_routes:
                break
            for j, dest in enumerate(pois):
                if i == j or len(routes) >= max_routes:
                    continue
                if abs(i - j) > 7 and (i + j) % 5:
                    continue
                distance = _distance(origin, dest)
                routes.append(
                    {
                        "route_id": f"route_{len(routes) + 1:04d}",
                        "origin_poi_id": origin["poi_id"],
                        "destination_poi_id": dest["poi_id"],
                        "transport_mode": "walk" if distance < 1.2 else "taxi",
                        "distance_km": round(distance, 2),
                        "duration_minutes": max(5, int(distance * (14 if distance < 1.2 else 7) + 4)),
                        "traffic_level": "smooth" if distance < 3 else "medium",
                        "confidence": 0.82,
                        "source": "mock_api",
                        "updated_at": ISO_NOW,
                    }
                )
                pbar.update(1)
    return {"version": "v0.1", "routes": routes}


def build_weather() -> dict[str, Any]:
    snapshots = []
    areas = ["下沙", "金沙湖", "高教园区"]
    for idx, area in enumerate(progress_iter(areas, desc="mock_weather", total=len(areas), unit="area")):
        snapshots.append(
            {
                "weather_id": f"weather_20260520_{idx + 1:03d}",
                "area": area,
                "time_range": {"start_time": ISO_NOW, "end_time": (NOW + timedelta(hours=5)).isoformat()},
                "weather": "cloudy" if idx != 2 else "rain",
                "temperature": 25 + idx,
                "rain_probability": 0.25 + idx * 0.2,
                "outdoor_risk_level": "low" if idx == 0 else "medium",
                "suggested_recovery": None if idx == 0 else "indoor_activity",
                "source": "mock_api",
                "updated_at": ISO_NOW,
            }
        )
    return {"version": "v0.1", "weather_snapshots": snapshots}


def build_failures(pois: list[dict[str, Any]]) -> dict[str, Any]:
    restaurant = next((poi for poi in pois if poi["category"] == "restaurant"), None)
    activity = next((poi for poi in pois if poi["category"] == "activity"), None)
    scenarios = []
    candidates = [
        {
            "enabled": restaurant is not None,
            "payload": {
                "failure_scenario_id": "fail_no_table_family_001",
                "enabled": True,
                "trigger": {"path": "POST /api/v1/mock/restaurants/{poi_id}/reserve", "poi_id": restaurant["poi_id"] if restaurant else None},
                "error_code": "NO_TABLE_AVAILABLE",
                "visible_to_user": False,
            },
        },
        {
            "enabled": activity is not None,
            "payload": {
                "failure_scenario_id": "fail_activity_full_001",
                "enabled": True,
                "trigger": {"path": "POST /api/v1/mock/activities/{poi_id}/book", "poi_id": activity["poi_id"] if activity else None},
                "error_code": "ACTIVITY_FULL",
                "visible_to_user": False,
            },
        },
        {
            "enabled": True,
            "payload": {
                "failure_scenario_id": "fail_window_expired_001",
                "enabled": True,
                "trigger": {"path": "POST /api/v1/plans/{plan_id}/execute"},
                "error_code": "PLAN_EXECUTABLE_WINDOW_EXPIRED",
                "visible_to_user": False,
            },
        },
    ]
    for candidate in progress_iter(candidates, desc="mock_failures", total=len(candidates), unit="case"):
        if candidate["enabled"]:
            scenarios.append(candidate["payload"])
    return {"version": "v0.1", "scenarios": scenarios}


def build_social(pois: list[dict[str, Any]]) -> dict[str, Any]:
    signals = []
    social_pois = pois[: max(10, min(len(pois), 60))]
    for idx, poi in enumerate(progress_iter(social_pois, desc="mock_social", total=len(social_pois), unit="signal")):
        profile = _social_profile(poi, idx)
        signals.append(
            {
                "signal_id": f"sig_{idx + 1:04d}",
                "poi_id": poi["poi_id"],
                "summary": _fallback_social_summary(poi, idx),
                "positive_tags": profile["positive_tags"],
                "negative_tags": profile["negative_tags"],
                "confidence": round(0.66 + (idx % 15) * 0.015, 2),
                "heat_score": round(0.58 + (idx % 20) * 0.018, 2),
                "is_mock": True,
                "source_type": "mock_social_signal",
                "mock_sources": [f"link{n}" for n in range(1, 4)],
                "updated_at": ISO_NOW,
            }
        )
    return {"version": "v0.1", "signals": signals}


def build_benchmarks() -> dict[str, Any]:
    samples = [
        {
            "sample_id": "bench_family_001",
            "scenario": "family_parent_child",
            "scenario_expected": "family_parent_child",
            "input_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
            "expected_constraints": ["child_friendly", "low_calorie", "nearby", "low_queue"],
            "expected_verifier_checks": ["restaurant_capacity", "activity_ticket", "weather_risk", "executable_window"],
        },
        {
            "sample_id": "bench_friend_001",
            "scenario": "friend_group",
            "scenario_expected": "friend_group",
            "input_text": "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。",
            "expected_constraints": ["budget", "low_walk", "consensus"],
            "expected_verifier_checks": ["budget_constraint", "queue_time", "tool_action_integrity"],
        },
        {
            "sample_id": "bench_anniversary_001",
            "scenario": "anniversary_emotion",
            "scenario_expected": "anniversary_emotion",
            "input_text": "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。",
            "expected_constraints": ["quiet", "light_ritual", "photo_spot"],
            "expected_verifier_checks": ["restaurant_capacity", "route_time", "executable_window"],
        },
    ]
    with progress_bar(total=len(samples), desc="benchmark_samples", unit="sample") as pbar:
        pbar.update(len(samples))
    return {
        "version": "v0.1",
        "samples": samples,
    }


def _safe_id(value: str, prefix: str, sequence: int) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.lower()).strip("_")
    if not cleaned.startswith(prefix):
        cleaned = f"{prefix}{cleaned}"
    return cleaned[:70] or f"{prefix}{sequence:03d}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "mock"


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nullable_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_or_now(value: Any) -> str:
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            pass
    return ISO_NOW


def _area_for(index: int) -> str:
    return ["下沙", "金沙湖", "高教园区"][index % 3]


def _clamp_coordinate(value: float, area: str, axis: str) -> float:
    bounds = AREA_BOUNDS.get(area)
    if not bounds:
        return value
    low, high = bounds[axis]
    return round(min(high, max(low, value)), 6)


def _fallback_social_summary(poi: dict[str, Any], index: int = 0) -> str:
    name = str(poi.get("name") or "该POI")
    profile = _social_profile(poi, index)
    return (
        f"口碑Mock归纳：{name}的模拟用户反馈呈现{profile['sentiment']}。{profile['positive_sentence']}"
        f"{profile['negative_sentence']}综合来看，它更像是{profile['fit_sentence']}，可以作为本地生活候选，但仍要结合Mock状态、库存和路线校验后再进入计划。"
    )


def _social_profile(poi: dict[str, Any], index: int = 0) -> dict[str, Any]:
    name = str(poi.get("name") or "")
    category = poi.get("category")
    sub = str(poi.get("sub_category") or "")
    tags = [str(tag) for tag in poi.get("tags", []) if isinstance(tag, str)]
    tag_set = set(tags)
    price = poi.get("price_per_person")
    budget_text = "价格感知清晰" if price in (None, 0) else f"人均约{int(price)}元，用户会拿它和周边同类点位比较"
    variants = index % 4

    if category == "restaurant":
        if "cafe" in sub or "咖啡" in name:
            positives = ["coffee_quality", "photo_spot", "light_food"]
            negatives = ["limited_seats", "not_quiet_at_peak"] if variants != 2 else ["drink_value_question"]
            return {
                "sentiment": "好坏参半",
                "positive_tags": positives,
                "negative_tags": negatives,
                "positive_sentence": "不少人会夸咖啡和轻饮出品稳定，湖边位置拍照好看，低卡小食适合不想吃太重的人或运动后补给。",
                "negative_sentence": "但也有人觉得高峰期座位少、聊天声和取餐动线会影响安静感，天气不好时户外优势会明显下降。",
                "fit_sentence": f"一个适合短暂停留、独处发呆、临时办公或饭后补给的咖啡点；{budget_text}",
            }
        if any(token in sub or token in name for token in ("hotpot", "火锅", "烧烤")):
            return {
                "sentiment": "热闹但争议明显",
                "positive_tags": ["strong_flavor", "value_for_money", "group_ok"],
                "negative_tags": ["smell_on_clothes", "peak_queue", "noise_risk"],
                "positive_sentence": "好评集中在口味直接、份量足、价格容易接受，想吃得热闹或运动后补能量的人会觉得满足。",
                "negative_sentence": "差评主要是油烟味容易留在衣服上，高峰排队和环境噪音都比较明显，想安静坐一会儿的人不一定喜欢。",
                "fit_sentence": f"一个偏烟火气的正餐候选；{budget_text}",
            }
        if any(token in sub or token in name for token in ("snack", "noodle", "面", "粉", "烧饼", "小吃")):
            return {
                "sentiment": "实惠但舒适度有限",
                "positive_tags": ["quick_meal", "local_flavor", "budget"],
                "negative_tags": ["limited_seats", "queue_risk", "hygiene_mixed"],
                "positive_sentence": "不少人认可它出餐快、价格低、味道有本地烟火气，适合外地朋友随手尝一口或赶时间垫肚子。",
                "negative_sentence": "负面集中在座位少、饭点排队和店面细节不够精致，很在意环境卫生的人会更谨慎。",
                "fit_sentence": f"一个解决快速吃饭和低预算补给的点；{budget_text}",
            }
        positives = ["taste_stable", "low_calorie", "value_for_money"] if "low_calorie" in tag_set else ["taste_stable", "group_friendly", "value_for_money"]
        negatives = ["small_portion", "peak_queue"] if variants in {0, 1} else ["flavor_not_strong"]
        return {
            "sentiment": "偏正向但有争议",
            "positive_tags": positives,
            "negative_tags": negatives,
            "positive_sentence": "评价里对菜品稳定性、低卡选择和出餐速度反馈较多，想吃清淡、午休赶时间或运动后补给的人会觉得选择不费劲。",
            "negative_sentence": "负面集中在高峰排队、部分菜量偏小和口味不够有记忆点，预算敏感用户会特别看性价比。",
            "fit_sentence": f"一个用于解决正餐或轻食约束的餐饮候选；{budget_text}",
        }

    if category == "transport_anchor":
        if "parking" in sub or "停车" in name:
            return {
                "sentiment": "偏负向且波动大",
                "positive_tags": ["parking", "low_walk", "senior_accessible"],
                "negative_tags": ["parking_shortage", "hard_to_find_entrance", "peak_congestion"],
                "positive_sentence": "用户认可它离核心动线近，带大件物品、外地朋友会合或不想多走路时比较省心，作为集合点也直观。",
                "negative_sentence": "吐槽主要是周末车位难抢、入口指示不够醒目，离场时容易排队，开车出行需要提前准备备选停车点。",
                "fit_sentence": "一个服务开车和接驳的交通锚点，不应该被包装成游玩内容本身",
            }
        if any(token in sub or token in name for token in ("metro", "bus", "地铁", "公交", "雨棚", "连廊")):
            return {
                "sentiment": "好找但高峰体验一般",
                "positive_tags": ["easy_meeting", "rain_safe", "visitor_friendly"],
                "negative_tags": ["crowded_peak", "limited_seats", "wayfinding_issue"],
                "positive_sentence": "好评集中在位置醒目、遮雨和外地人容易会合，临时等人或换乘时不用再找复杂入口。",
                "negative_sentence": "负面主要是早晚高峰人流密、座位少，部分出口标识不够直观，第一次来的人可能需要多看导航。",
                "fit_sentence": "一个解决集合、换乘和避雨的交通节点",
            }
        return {
            "sentiment": "功能性强但体验不稳定",
            "positive_tags": ["taxi_pickup", "low_walk", "easy_meeting"],
            "negative_tags": ["ride_hailing_wait", "curbside_crowding", "weather_exposure"],
            "positive_sentence": "反馈里常提到上车点好找、离校园和商圈步行距离短，带行李、赶时间或不想多走路时能降低体力消耗。",
            "negative_sentence": "问题集中在晚高峰叫车等待、路边临停拥挤和下雨天缺少遮挡，它更适合作为路线收尾或PlanB接驳。",
            "fit_sentence": "一个交通接驳节点，价值在减少走路和降低迷路成本",
        }

    if category == "service":
        if any(token in sub or token in name for token in ("work", "cowork", "co_working", "办公", "共享")):
            return {
                "sentiment": "实用但不适合久坐",
                "positive_tags": ["work_friendly", "quiet_alone", "socket"],
                "negative_tags": ["limited_seats", "noise_spillover", "unclear_stay_rule"],
                "positive_sentence": "用户会把它当作临时处理消息、等人或短暂办公的缓冲点，桌面、插座和相对安静是主要加分项。",
                "negative_sentence": "不足是座位周转慢，旁边人通话会影响专注，停留规则如果不清楚会让人有点尴尬。",
                "fit_sentence": "一个偏功能性的临时停留服务点",
            }
        if any(token in sub or token in name for token in ("convenience", "便利", "补给", "24h", "夜间")):
            return {
                "sentiment": "补给方便但库存有波动",
                "positive_tags": ["late_supply", "quick_purchase", "budget"],
                "negative_tags": ["stock_out", "checkout_queue", "small_space"],
                "positive_sentence": "好评集中在热食、饮料、纸巾和基础日用品齐全，夜间或雨天临时需要东西时很省心。",
                "negative_sentence": "吐槽主要是热门商品补货慢、结账排队和店面空间小，急着赶路时体验会打折。",
                "fit_sentence": "一个解决临时补给和夜间兜底的小服务点",
            }
        if "changing" in sub or "更衣" in name:
            return {
                "sentiment": "分歧明显",
                "positive_tags": ["changing_room", "indoor", "clean_supply"],
                "negative_tags": ["cleanliness_risk", "queue_at_peak", "limited_space"],
                "positive_sentence": "好评集中在换衣、洗手、雨天整理和运动后临时休整，位置在室内时能提高整个行程的舒适度。",
                "negative_sentence": "负面主要指向卫生维护、空间偏小和高峰排队，如果清洁状态不稳定，会直接影响停留体验。",
                "fit_sentence": "一个功能性补给节点，不是游玩主目的地，但能显著改善路线容错",
            }
        if "gift" in sub or "flower" in sub or "花" in name:
            return {
                "sentiment": "偏正向但受库存影响",
                "positive_tags": ["flower_pickup", "light_ritual", "photo_ready"],
                "negative_tags": ["limited_inventory", "price_fluctuation"],
                "positive_sentence": "评价会强调花束和小礼物适合临时表达心意、装点照片或给外地朋友准备小惊喜。",
                "negative_sentence": "不足是热门款可能缺货，临近节日价格感知会上升，审美风格也不是每个人都喜欢。",
                "fit_sentence": "一个偏轻量表达和拍照补给的小服务点",
            }
        return {
            "sentiment": "偏实用",
            "positive_tags": ["rest_area", "indoor", "clean_supply"],
            "negative_tags": ["cleanliness_risk"] if variants != 1 else ["limited_seats"],
            "positive_sentence": "模拟反馈更关注休息、补水、洗手和有人能坐一会儿，能让紧凑行程有一个缓冲点。",
            "negative_sentence": "问题通常在卫生细节、座位数量和高峰占用率，不适合作为长时间停留目标。",
            "fit_sentence": "一个提高舒适度的服务补给节点",
        }

    if category == "activity":
        if any(token in sub or token in name for token in ("pet", "萌宠", "小动物", "动物")):
            return {
                "sentiment": "治愈感强但对卫生敏感",
                "positive_tags": ["pet_friendly", "mood_relief", "photo_spot"],
                "negative_tags": ["animal_smell", "allergy_risk", "cleanliness_risk"],
                "positive_sentence": "喜欢小动物的人会觉得互动轻松、情绪被安抚，拍照和短暂停留的反馈都不错。",
                "negative_sentence": "差评集中在动物气味、毛发过敏和清洁维护，特别在雨天或高峰时段体验波动会更明显。",
                "fit_sentence": "一个偏情绪缓冲和轻互动的活动点",
            }
        if any(token in sub or token in name for token in ("sport", "sports", "滑板", "跑", "骑行", "运动")):
            sport_positive = [
                "爱运动的人会认可场地能出汗、节奏直接，雨天也能保持活动量，运动后附近补水和简餐很重要。",
                "不少反馈会提到这里适合短时间活动身体，压力大时比单纯坐着更容易转换状态。",
                "用户喜欢它的运动属性明确，不需要复杂安排，临时想活动一下也能快速进入状态。",
            ][variants % 3]
            sport_negative = [
                "负面主要是新手安全压力、器械或场地等待、声音偏大，不想被打扰或穿着不方便的人会降低兴趣。",
                "问题集中在高峰时段空间紧张、地面防滑和储物不够顺手，洁癖用户会特别关注维护频率。",
                "差评多和噪音、排队、受伤风险有关，同行人如果只是想安静聊天会觉得不匹配。",
            ][variants % 3]
            return {
                "sentiment": "适合释放精力但门槛不低",
                "positive_tags": ["sports_friendly", "energy_release", "indoor"],
                "negative_tags": ["injury_risk", "noise_risk", "equipment_wait"],
                "positive_sentence": sport_positive,
                "negative_sentence": sport_negative,
                "fit_sentence": "一个运动释放和短时训练属性很强的点位",
            }
        if any(token in sub or token in name for token in ("work", "co_working", "book", "书", "阅读", "办公")):
            work_positive = [
                "独处办公、阅读或想躲开嘈杂环境的人会喜欢桌面、插座和安静氛围，雨天停留价值也比较高。",
                "好评集中在灯光舒服、桌面够用、能安静待一段时间，适合临时处理消息或整理心情。",
                "用户会把它当成低成本缓冲点：不用强消费，也能坐下来阅读、等人或避开商场噪音。",
            ][variants % 3]
            work_negative = [
                "负面集中在座位被占、无线网络偶尔不稳，以及环境太安静不适合多人聊天。",
                "吐槽主要是热门时段插座少、久坐不够舒服，旁边有人通话时会很破坏体验。",
                "不足是停留规则不够明确，桌位周转慢，想找绝对安静的人可能需要备选点。",
            ][variants % 3]
            return {
                "sentiment": "安静需求匹配度高但座位紧张",
                "positive_tags": ["quiet_alone", "work_friendly", "socket"],
                "negative_tags": ["limited_seats", "wifi_unstable", "too_quiet_for_chat"],
                "positive_sentence": work_positive,
                "negative_sentence": work_negative,
                "fit_sentence": "一个适合独处、学习、临时处理事情的室内停留点",
            }
        if "playground" in sub or "儿童" in name:
            return {
                "sentiment": "热度高但噪音和排队争议大",
                "positive_tags": ["child_friendly", "indoor", "energy_release"],
                "negative_tags": ["noisy", "peak_queue", "safety_attention"],
                "positive_sentence": "带娃用户会说孩子放电效果好，雨天或炎热天气能转入室内，家长不用临时再找活动。",
                "negative_sentence": "差评集中在噪音、排队和低龄儿童安全看护压力，不喜欢吵闹或只想安静待一会儿的人通常不会把它当主选择。",
                "fit_sentence": "一个强儿童活动属性的点位",
            }
        if any(token in sub or token in name for token in ("board", "桌游", "game", "解压")):
            return {
                "sentiment": "适合轻娱乐但受噪音影响",
                "positive_tags": ["light_entertainment", "decompress", "group_ok"],
                "negative_tags": ["noise_risk", "table_wait", "air_quality_mixed"],
                "positive_sentence": "用户喜欢它门槛低、容易坐下来玩一会儿，压力大时能把注意力从手机和工作里拉出来。",
                "negative_sentence": "差评集中在桌位等待、隔壁桌声音大和空气流通一般，想独处或怕吵的人不一定适合。",
                "fit_sentence": "一个偏轻娱乐和短时解压的室内点",
            }
        return {
            "sentiment": "偏正向",
            "positive_tags": ["interactive", "indoor", "photo_spot"],
            "negative_tags": ["ticket_pressure", "content_light"] if variants in {0, 2} else ["peak_queue"],
            "positive_sentence": "用户会认可互动内容和拍照空间，室内属性让它适合雨天、太阳较大的下午或外地朋友短暂停留。",
            "negative_sentence": "不足是热门时段票量紧张，部分人觉得内容偏轻，停留时长不一定撑满整个下午。",
            "fit_sentence": "一个适合串联餐饮和散步的中段活动",
        }

    if category == "walk_spot":
        if any(token in sub or token in name for token in ("pet", "animal", "萌宠", "宠物", "小动物")):
            return {
                "sentiment": "轻松治愈但维护要求高",
                "positive_tags": ["pet_friendly", "mood_relief", "outdoor"],
                "negative_tags": ["cleanliness_risk", "leash_conflict", "crowded_weekend"],
                "positive_sentence": "喜欢小动物的人会觉得这里放松、容易和路过的宠物产生互动，心情不好时短暂停留也有缓冲感。",
                "negative_sentence": "负面集中在牵引绳管理、地面清洁和周末人宠混行，爱干净或怕动物的人需要谨慎选择。",
                "fit_sentence": "一个偏宠物友好和情绪放松的户外停留点",
            }
        if any(token in sub or token in name for token in ("reading", "book", "书", "廊", "长廊")):
            return {
                "sentiment": "安静舒适但座位有限",
                "positive_tags": ["quiet_alone", "rain_safe", "work_friendly"],
                "negative_tags": ["limited_seats", "humidity", "dim_lighting"],
                "positive_sentence": "不少人喜欢这里能边走边停、安静看会儿东西，雨天不用狼狈赶路，也适合独处整理思绪。",
                "negative_sentence": "不足是座位少，潮湿天气体感一般，部分角落灯光偏暗，长时间阅读或办公不如正式咖啡馆稳定。",
                "fit_sentence": "一个适合短暂停留、避雨和放空的步行廊道",
            }
        return {
            "sentiment": "景观好但受天气影响",
            "positive_tags": ["lake_walk", "photo_spot", "free"],
            "negative_tags": ["weather_sensitive", "crowded_at_sunset", "limited_shelter"],
            "positive_sentence": "多数模拟反馈会夸湖边视野、拍照角度和免费散步价值，适合饭后慢走、情绪低落时放空或带外地朋友认识周边。",
            "negative_sentence": "负面集中在日落时人多、风大或下雨时缺少遮挡，靠近水边的位置也需要注意安全。",
            "fit_sentence": "一个低成本户外串联点",
        }

    return {
        "sentiment": "信息有限",
        "positive_tags": tags[:4] or ["local_life"],
        "negative_tags": ["uncertain_fit"],
        "positive_sentence": "模拟反馈能确认它在本地生活动线中有一定补充价值。",
        "negative_sentence": "但具体体验差异较大，需要结合状态、路线和同伴约束再判断。",
        "fit_sentence": "一个需要进一步校验的候选点",
    }


def _risk_tags(category: str, sub: str) -> list[str]:
    if category == "restaurant":
        return ["limited_tables"]
    if category == "activity":
        return ["ticket_required"]
    if sub in {"lake_walk", "photo"}:
        return ["weather_sensitive"]
    return []


def _clean_incompatible_tags(poi: dict[str, Any]) -> list[str]:
    tags = list(dict.fromkeys(poi.get("tags", [])))
    text = f"{poi.get('name', '')} {poi.get('sub_category', '')}".lower()
    pet_markers = ["pet", "animal", "dog", "cat", "宠物", "小动物", "萌宠", "猫", "狗"]
    if "pet_friendly" in tags and not any(marker in text for marker in pet_markers):
        tags = [tag for tag in tags if tag != "pet_friendly"]
    return tags[:12] or ["mock"]


def _distance(origin: dict[str, Any], dest: dict[str, Any]) -> float:
    lat1, lng1 = origin["location"]["lat"], origin["location"]["lng"]
    lat2, lng2 = dest["location"]["lat"], dest["location"]["lng"]
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) * 92
