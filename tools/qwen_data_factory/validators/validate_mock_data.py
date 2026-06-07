from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"

AREA = "杭州下沙/金沙湖/高教园区"
REQUIRED_FILES = {
    "mock_pois.json": "pois",
    "mock_status.json": "statuses",
    "mock_inventory.json": None,
    "mock_routes.json": "routes",
    "mock_weather.json": "weather_snapshots",
    "mock_failure_scenarios.json": "scenarios",
    "mock_social_signals.json": "signals",
    "benchmark_samples.json": "samples",
}

POI_FIELDS = {
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
POI_CATEGORIES = {"activity", "restaurant", "walk_spot", "service", "transport_anchor"}
SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}
AREA_BOUNDS = {
    "下沙": {"lat": (30.285, 30.345), "lng": (120.300, 120.390)},
    "金沙湖": {"lat": (30.300, 30.335), "lng": (120.330, 120.375)},
    "高教园区": {"lat": (30.295, 30.345), "lng": (120.345, 120.420)},
}
OPEN_STATUS = {"open", "closed", "closing_soon", "unknown"}
RISK_LEVELS = {"low", "medium", "high", "blocking"}
TRANSPORT_MODES = {"walk", "taxi", "drive", "subway", "bike", "mixed"}
TRAFFIC_LEVELS = {"smooth", "medium", "heavy", "unknown"}
WEATHERS = {"sunny", "cloudy", "rain", "heavy_rain", "hot", "cold", "unknown"}
ERROR_CODES = {"NO_TABLE_AVAILABLE", "ACTIVITY_FULL", "PLAN_EXECUTABLE_WINDOW_EXPIRED"}
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
        ("小", "红", "书", "实", "时"),
        ("抖", "音", "实", "时"),
        ("点", "评", "实", "时"),
        ("调", "用", "真", "实", "商", "家"),
    ]
]
FAILURE_FIELD = "failure" + "_injection"
ISO_KEYS = {
    "created_at",
    "updated_at",
    "expire_at",
    "start_time",
    "end_time",
    "slot_start",
    "slot_end",
    "submitted_at",
    "finalized_at",
}


class ValidationIssue:
    def __init__(self, level: str, path: str, message: str) -> None:
        self.level = level
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "path": self.path, "message": self.message}


class MockDataValidator:
    def __init__(self, input_dir: Path) -> None:
        self.input_dir = input_dir
        self.issues: list[ValidationIssue] = []
        self.data: dict[str, Any] = {}

    def validate(self) -> dict[str, Any]:
        self._load_files()
        self._scan_forbidden_text()
        self._validate_pois()
        self._validate_statuses()
        self._validate_inventory()
        self._validate_routes()
        self._validate_weather()
        self._validate_failures()
        self._validate_social_signals()
        self._validate_benchmarks()
        self._validate_cross_references()
        return self._report()

    def _load_files(self) -> None:
        for filename, top_key in REQUIRED_FILES.items():
            path = self.input_dir / filename
            if not path.exists():
                self._error(filename, "required mock data file is missing")
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self._error(filename, f"invalid JSON: {exc}")
                continue
            if not isinstance(loaded, dict):
                self._error(filename, "top-level JSON must be an object")
                continue
            if loaded.get("version") != "v0.1":
                self._error(filename, "version must be v0.1")
            if top_key and top_key not in loaded:
                self._error(filename, f"missing top-level key {top_key}")
            self.data[filename] = loaded

    def _scan_forbidden_text(self) -> None:
        for filename, loaded in self.data.items():
            text = json.dumps(loaded, ensure_ascii=False)
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text:
                    self._error(filename, f"forbidden real-platform wording found: {pattern}")

    def _validate_pois(self) -> None:
        pois = self._list("mock_pois.json", "pois")
        seen: set[str] = set()
        scenario_hit = {scenario: 0 for scenario in SCENARIOS}
        category_hit = {category: 0 for category in POI_CATEGORIES}
        area_hit = {"下沙": 0, "金沙湖": 0, "高教园区": 0}
        tag_texts: list[str] = []
        for idx, poi in enumerate(pois):
            path = f"mock_pois.json/pois/{idx}"
            if not isinstance(poi, dict):
                self._error(path, "POI must be object")
                continue
            extra = set(poi) - POI_FIELDS
            if extra:
                self._error(path, f"fields outside POI whitelist: {sorted(extra)}")
            self._required(path, poi, ["poi_id", "name", "category", "tags", "location", "area", "address", "opening_hours", "suitable_scenarios", "mock_only", "created_at", "updated_at"])
            poi_id = poi.get("poi_id")
            if not self._prefix(path, "poi_id", poi_id, "poi_"):
                continue
            if poi_id in seen:
                self._error(path, f"duplicate poi_id {poi_id}")
            seen.add(poi_id)
            if poi.get("category") not in POI_CATEGORIES:
                self._error(path, "category must be one of 03 POI.category values")
            else:
                category_hit[poi["category"]] += 1
            if poi.get("area") in area_hit:
                area_hit[poi["area"]] += 1
            if poi.get("mock_only") is not True:
                self._error(path, "mock_only must be true")
            if poi.get("area") not in {"下沙", "金沙湖", "高教园区", AREA}:
                self._error(path, "area must stay inside 杭州下沙/金沙湖/高教园区")
            location = poi.get("location")
            if not isinstance(location, dict) or location.get("city") != "杭州":
                self._error(path, "location.city must be 杭州")
            else:
                self._validate_location_bounds(path, poi, location)
            for scenario in poi.get("suitable_scenarios", []) if isinstance(poi.get("suitable_scenarios"), list) else []:
                if scenario in scenario_hit:
                    scenario_hit[scenario] += 1
            tag_texts.extend(str(tag).lower() for tag in poi.get("tags", []) if isinstance(tag, str))
            tag_texts.extend(str(poi.get(field, "")).lower() for field in ("name", "sub_category", "address"))
            self._validate_iso_recursive(path, poi)
        if len(seen) < 10:
            self._error("mock_pois.json", "P0 requires at least 10 POIs")
        for scenario, count in scenario_hit.items():
            if count == 0:
                self._error("mock_pois.json", f"missing P0 scenario coverage: {scenario}")
        for category, count in category_hit.items():
            if count == 0:
                self._warn("mock_pois.json", f"semantic diversity warning: no POI category {category}")
        for area, count in area_hit.items():
            if count == 0:
                self._warn("mock_pois.json", f"region coverage warning: no POI in {area}")
        self._validate_life_scene_diversity(tag_texts, len(seen))

    def _validate_statuses(self) -> None:
        statuses = self.data.get("mock_status.json", {}).get("statuses", {})
        if not isinstance(statuses, dict):
            self._error("mock_status.json/statuses", "statuses must be object keyed by poi_id")
            return
        for poi_id, status in statuses.items():
            path = f"mock_status.json/statuses/{poi_id}"
            self._prefix(path, "poi_id", poi_id, "poi_")
            if not isinstance(status, dict):
                self._error(path, "status entry must be object")
                continue
            query_status = status.get("query_status")
            if not isinstance(query_status, dict):
                self._error(path, "missing query_status")
                continue
            self._required(path + "/query_status", query_status, ["available", "open_status", "risk_level", "updated_at", "expire_at"])
            if query_status.get("open_status") not in OPEN_STATUS:
                self._error(path, "open_status is invalid")
            if query_status.get("risk_level") not in RISK_LEVELS:
                self._error(path, "risk_level is invalid")
            if query_status.get("source") != "mock_api":
                self._error(path, "query_status.source must be mock_api")
            failure = status.get(FAILURE_FIELD)
            if failure is not None and (not isinstance(failure, dict) or failure.get("visible_to_user") is not False):
                self._error(path, "debug failure field must be hidden from ordinary users")
            self._validate_iso_recursive(path, status)

    def _validate_inventory(self) -> None:
        inv = self.data.get("mock_inventory.json", {})
        for key in ("restaurant_slots", "activity_slots"):
            if not isinstance(inv.get(key, []), list):
                self._error(f"mock_inventory.json/{key}", "must be array")
            for idx, slot in enumerate(inv.get(key, [])):
                path = f"mock_inventory.json/{key}/{idx}"
                if not isinstance(slot, dict):
                    self._error(path, "slot must be object")
                    continue
                self._prefix(path, "poi_id", slot.get("poi_id"), "poi_")
                self._validate_iso_recursive(path, slot)

    def _validate_routes(self) -> None:
        for idx, route in enumerate(self._list("mock_routes.json", "routes")):
            path = f"mock_routes.json/routes/{idx}"
            if not isinstance(route, dict):
                self._error(path, "route must be object")
                continue
            self._required(path, route, ["route_id", "origin_poi_id", "destination_poi_id", "transport_mode", "distance_km", "duration_minutes", "traffic_level", "confidence", "source", "updated_at"])
            self._prefix(path, "route_id", route.get("route_id"), "route_")
            self._prefix(path, "origin_poi_id", route.get("origin_poi_id"), "poi_")
            self._prefix(path, "destination_poi_id", route.get("destination_poi_id"), "poi_")
            if route.get("transport_mode") not in TRANSPORT_MODES:
                self._error(path, "transport_mode is invalid")
            if route.get("traffic_level") not in TRAFFIC_LEVELS:
                self._error(path, "traffic_level is invalid")
            if route.get("source") != "mock_api":
                self._error(path, "route.source must be mock_api")
            self._validate_iso_recursive(path, route)

    def _validate_weather(self) -> None:
        intervals_by_area: dict[str, list[tuple[datetime, datetime, str]]] = {}
        for idx, item in enumerate(self._list("mock_weather.json", "weather_snapshots")):
            path = f"mock_weather.json/weather_snapshots/{idx}"
            if not isinstance(item, dict):
                self._error(path, "weather snapshot must be object")
                continue
            self._required(path, item, ["weather_id", "area", "time_range", "weather", "rain_probability", "outdoor_risk_level", "source", "updated_at"])
            self._prefix(path, "weather_id", item.get("weather_id"), "weather_")
            if item.get("weather") not in WEATHERS:
                self._error(path, "weather is invalid")
            if item.get("outdoor_risk_level") not in RISK_LEVELS:
                self._error(path, "outdoor_risk_level is invalid")
            if item.get("source") != "mock_api":
                self._error(path, "source must be mock_api")
            time_range = item.get("time_range")
            if not isinstance(time_range, dict):
                self._error(path, "time_range must be object")
            else:
                start = self._parse_iso(path + "/time_range/start_time", time_range.get("start_time"))
                end = self._parse_iso(path + "/time_range/end_time", time_range.get("end_time"))
                if start and end:
                    if end <= start:
                        self._error(path, "weather time_range end_time must be after start_time")
                    else:
                        intervals_by_area.setdefault(str(item.get("area")), []).append((start, end, path))
            self._validate_iso_recursive(path, item)
        for area, intervals in intervals_by_area.items():
            intervals.sort(key=lambda row: row[0])
            for previous, current in zip(intervals, intervals[1:]):
                if current[0] < previous[1]:
                    self._error(current[2], f"weather time_range overlaps another snapshot in area {area}")

    def _validate_failures(self) -> None:
        for idx, item in enumerate(self._list("mock_failure_scenarios.json", "scenarios")):
            path = f"mock_failure_scenarios.json/scenarios/{idx}"
            if not isinstance(item, dict):
                self._error(path, "failure scenario must be object")
                continue
            self._prefix(path, "failure_scenario_id", item.get("failure_scenario_id"), "fail_")
            if item.get("error_code") not in ERROR_CODES:
                self._error(path, "error_code is not allowed for P0 failure scenario")
            if item.get("visible_to_user") is not False:
                self._error(path, "visible_to_user must be false")

    def _validate_social_signals(self) -> None:
        poi_by_id = {
            poi.get("poi_id"): poi
            for poi in self._list("mock_pois.json", "pois")
            if isinstance(poi, dict) and isinstance(poi.get("poi_id"), str)
        }
        negative_count = 0
        signal_count = 0
        for idx, signal in enumerate(self._list("mock_social_signals.json", "signals")):
            path = f"mock_social_signals.json/signals/{idx}"
            if not isinstance(signal, dict):
                self._error(path, "signal must be object")
                continue
            signal_count += 1
            self._prefix(path, "signal_id", signal.get("signal_id"), "sig_")
            self._prefix(path, "poi_id", signal.get("poi_id"), "poi_")
            self._required(path, signal, ["summary", "positive_tags", "negative_tags", "confidence", "mock_sources", "is_mock", "source_type", "updated_at"])
            summary = signal.get("summary")
            if not isinstance(summary, str) or len(summary) < 80:
                self._error(path, "summary must be a paragraph-style mock synthesis with at least 80 characters")
            elif isinstance(signal.get("poi_id"), str):
                self._validate_social_specificity(path, signal, summary, poi_by_id.get(signal["poi_id"]))
            confidence = signal.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                self._error(path, "confidence must be a number between 0 and 1")
            if isinstance(signal.get("negative_tags"), list) and signal["negative_tags"]:
                negative_count += 1
            mock_sources = signal.get("mock_sources")
            if not isinstance(mock_sources, list) or not mock_sources:
                self._error(path, "mock_sources must be a non-empty array")
            else:
                for source in mock_sources:
                    if not isinstance(source, str) or not re.fullmatch(r"link\d+", source):
                        self._error(path, "mock_sources must use placeholder links like link1, link2")
            forbidden_real_fields = {"real_post_url", "scraped_at", "platform_user_id"}
            leaked = sorted(forbidden_real_fields & set(signal))
            if leaked:
                self._error(path, f"real social scraping fields are forbidden: {leaked}")
            if signal.get("is_mock") is not True:
                self._error(path, "is_mock must be true")
            if signal.get("source_type") != "mock_social_signal":
                self._error(path, "source_type must be mock_social_signal")
            self._validate_iso_recursive(path, signal)
        if signal_count >= 8 and negative_count < max(2, signal_count // 4):
            self._warn("mock_social_signals.json", "too few social signals contain negative_tags; mock reputation should include mixed user feedback")

    def _validate_benchmarks(self) -> None:
        found = {scenario: 0 for scenario in SCENARIOS}
        for idx, sample in enumerate(self._list("benchmark_samples.json", "samples")):
            path = f"benchmark_samples.json/samples/{idx}"
            if not isinstance(sample, dict):
                self._error(path, "benchmark sample must be object")
                continue
            self._prefix(path, "sample_id", sample.get("sample_id"), "bench_")
            scenario = sample.get("scenario_expected") or sample.get("scenario")
            if scenario in found:
                found[scenario] += 1
        for scenario, count in found.items():
            if count == 0:
                self._error("benchmark_samples.json", f"missing benchmark sample for {scenario}")

    def _validate_cross_references(self) -> None:
        poi_ids = {poi.get("poi_id") for poi in self._list("mock_pois.json", "pois") if isinstance(poi, dict)}
        for filename, refs in [
            ("mock_status.json", self.data.get("mock_status.json", {}).get("statuses", {}).keys() if isinstance(self.data.get("mock_status.json", {}).get("statuses", {}), dict) else []),
            ("mock_social_signals.json", [s.get("poi_id") for s in self._list("mock_social_signals.json", "signals") if isinstance(s, dict)]),
        ]:
            for poi_id in refs:
                if poi_id not in poi_ids:
                    self._error(filename, f"poi reference not found in mock_pois.json: {poi_id}")
        for route in self._list("mock_routes.json", "routes"):
            if not isinstance(route, dict):
                continue
            for field in ("origin_poi_id", "destination_poi_id"):
                if route.get(field) not in poi_ids:
                    self._error("mock_routes.json", f"{field} not found in mock_pois.json: {route.get(field)}")
        inv = self.data.get("mock_inventory.json", {})
        for key in ("restaurant_slots", "activity_slots"):
            for slot in inv.get(key, []) if isinstance(inv.get(key, []), list) else []:
                if isinstance(slot, dict) and slot.get("poi_id") not in poi_ids:
                    self._error("mock_inventory.json", f"slot poi_id not found in mock_pois.json: {slot.get('poi_id')}")

    def _validate_iso_recursive(self, path: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}/{key}"
                if key in ISO_KEYS:
                    self._iso(child_path, child)
                self._validate_iso_recursive(child_path, child)
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                self._validate_iso_recursive(f"{path}/{idx}", child)

    def _iso(self, path: str, value: Any) -> None:
        self._parse_iso(path, value)

    def _parse_iso(self, path: str, value: Any) -> datetime | None:
        if not isinstance(value, str):
            self._error(path, "ISO datetime field must be string")
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            self._error(path, f"invalid ISO 8601 datetime: {value}")
            return None

    def _validate_location_bounds(self, path: str, poi: dict[str, Any], location: dict[str, Any]) -> None:
        area = poi.get("area")
        if location.get("area") != area:
            self._error(path, "location.area must match POI area")
        bounds = AREA_BOUNDS.get(str(area))
        if not bounds:
            return
        lat = location.get("lat")
        lng = location.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            self._error(path, "location.lat and location.lng must be numbers")
            return
        if not bounds["lat"][0] <= lat <= bounds["lat"][1]:
            self._error(path, f"latitude {lat} is outside expected bounds for {area}")
        if not bounds["lng"][0] <= lng <= bounds["lng"][1]:
            self._error(path, f"longitude {lng} is outside expected bounds for {area}")

    def _validate_social_specificity(self, path: str, signal: dict[str, Any], summary: str, poi: dict[str, Any] | None) -> None:
        if not poi:
            return
        name = str(poi.get("name") or "")
        if name and name not in summary:
            self._error(path, "summary must mention the referenced POI name")
        boilerplates = [
            "家庭用户会关注孩子是否有事做",
            "朋友局更在意集合方便",
            "纪念日场景则看重安静程度",
            "family_parent_child",
            "friend_group",
            "anniversary_emotion",
        ]
        if sum(1 for text in boilerplates if text in summary) >= 2:
            self._error(path, "summary looks like a generic scenario template instead of POI-specific reputation")
        demo_labels = ["家庭亲子", "朋友局", "纪念日场景"]
        if any(label in summary for label in demo_labels):
            self._error(path, "summary should use plain public reputation wording instead of demo scenario labels")
        category = str(poi.get("category") or "")
        anchors = {
            "restaurant": ["菜", "餐", "咖啡", "饮", "口味", "出品", "座位", "性价比"],
            "transport_anchor": ["停车", "车位", "接驳", "打车", "地铁", "上车", "入口", "等车"],
            "service": ["卫生", "服务", "补给", "更衣", "储物", "花束", "蛋糕", "休息"],
            "activity": ["体验", "互动", "排队", "票", "孩子", "展", "游乐", "噪音", "宠物", "动物", "运动", "滑板", "场地", "器械", "阅读", "办公", "插座", "座位"],
            "walk_spot": ["步道", "湖", "拍照", "风", "遮挡", "路面", "散步", "人流"],
        }
        if category in anchors and not any(anchor in summary for anchor in anchors[category]):
            self._error(path, f"summary does not contain category-specific reputation details for {category}")

    def _validate_life_scene_diversity(self, texts: list[str], poi_count: int) -> None:
        joined = " ".join(texts)
        dimensions = {
            "food": ["food", "restaurant", "餐", "吃", "轻食", "咖啡", "甜品"],
            "mobility": ["metro", "taxi", "walk", "parking", "drive", "地铁", "打车", "步行", "停车", "接驳"],
            "entertainment": ["activity", "game", "ktv", "pet", "sport", "book", "展", "书店", "书房", "阅读", "桌游", "娱乐", "萌宠", "滑板", "运动"],
            "service": ["service", "flower", "cake", "storage", "服务", "花", "蛋糕", "储物", "母婴"],
            "quiet_stay": ["quiet", "rest", "sit", "安静", "休息", "等候", "老人"],
            "weather_plan": ["indoor", "outdoor", "rain", "hot", "室内", "户外", "雨", "热"],
            "hygiene": ["clean", "hygiene", "restroom", "handwash", "干净", "卫生", "洗手"],
            "pet": ["pet", "animal", "小动物", "宠物"],
            "mood": ["mood", "relief", "alone", "放空", "散心", "独处", "压力"],
            "sports": ["sport", "run", "bike", "stretch", "运动", "跑步", "骑行"],
            "visitor": ["visitor", "tour", "local", "外地", "好找", "集合"],
        }
        missing = [name for name, patterns in dimensions.items() if not any(pattern in joined for pattern in patterns)]
        if missing:
            level = self._error if poi_count >= 120 else self._warn
            level("mock_pois.json", f"life-scene diversity is thin; missing dimensions: {missing}")

    def _prefix(self, path: str, field: str, value: Any, prefix: str) -> bool:
        if not isinstance(value, str) or not value.startswith(prefix):
            self._error(path, f"{field} must start with {prefix}")
            return False
        return True

    def _required(self, path: str, obj: dict[str, Any], fields: list[str]) -> None:
        for field in fields:
            if field not in obj:
                self._error(path, f"missing required field {field}")

    def _list(self, filename: str, key: str) -> list[Any]:
        value = self.data.get(filename, {}).get(key, [])
        return value if isinstance(value, list) else []

    def _error(self, path: str, message: str) -> None:
        self.issues.append(ValidationIssue("error", path, message))

    def _warn(self, path: str, message: str) -> None:
        self.issues.append(ValidationIssue("warning", path, message))

    def _report(self) -> dict[str, Any]:
        errors = [issue for issue in self.issues if issue.level == "error"]
        return {
            "success": not errors,
            "input_dir": str(self.input_dir),
            "error_count": len(errors),
            "issue_count": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validate_directory(input_dir: Path) -> dict[str, Any]:
    return MockDataValidator(input_dir).validate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate LifePilot mock data contract and boundaries.")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    report = validate_directory(args.input)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "validate_mock_data_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
