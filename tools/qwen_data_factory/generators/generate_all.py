from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from qwen_client import QwenClient
    from generators.common import (
        DATA_DIR,
        assert_no_forbidden_text,
        build_benchmarks,
        build_failures,
        build_inventory,
        build_routes,
        build_social,
        build_statuses,
        build_weather,
        ensure_dirs,
        load_json,
        parse_json_object,
        progress_bar,
        ISO_NOW,
        write_json,
        write_report,
    )
    from generators.generate_pois import generate_pois
    from generators.prompt_composer import FILE_CONTRACTS, compose_prompt
else:
    from ..qwen_client import QwenClient
    from .common import (
        DATA_DIR,
        assert_no_forbidden_text,
        build_benchmarks,
        build_failures,
        build_inventory,
        build_routes,
        build_social,
        build_statuses,
        build_weather,
        ensure_dirs,
        load_json,
        parse_json_object,
        progress_bar,
        ISO_NOW,
        write_json,
        write_report,
    )
    from .generate_pois import generate_pois
    from .prompt_composer import FILE_CONTRACTS, compose_prompt


DERIVED_FILES = [
    "mock_status.json",
    "mock_inventory.json",
    "mock_weather.json",
    "mock_failure_scenarios.json",
    "mock_social_signals.json",
    "benchmark_samples.json",
]

SYSTEM_PROMPT = "你是OpenAI-compatible本地Qwen数据生成API，只生成候选JSON，不写代码，不决定可执行状态。"


def generate_all(
    target_pois: int,
    batch_size: int,
    output_dir: Path,
    allow_template_fallback: bool = False,
    validate: bool = True,
    force_pois: bool = False,
    reuse_existing: bool = False,
    qwen_derived: bool = True,
    strict_qwen_derived: bool = False,
) -> dict[str, Any]:
    ensure_dirs()
    existing_pois = load_json(output_dir / "mock_pois.json", {"pois": []}).get("pois", [])
    if reuse_existing and not force_pois and isinstance(existing_pois, list) and len(existing_pois) >= target_pois:
        poi_report = {
            "task": "generate_pois",
            "success": True,
            "target": target_pois,
            "accepted": len(existing_pois),
            "reused_existing": True,
        }
    else:
        poi_report = generate_pois(target_pois, batch_size, output_dir, allow_template_fallback)
    if not poi_report.get("success"):
        report = {"task": "generate_all", "success": False, "stage": "mock_pois", "poi_report": poi_report}
        write_report("generate_all_report.json", report)
        return report

    pois_payload = load_json(output_dir / "mock_pois.json", {"pois": []})
    pois = pois_payload.get("pois", [])
    if not isinstance(pois, list) or not pois:
        report = {"task": "generate_all", "success": False, "stage": "load_pois", "message": "mock_pois.json has no pois"}
        write_report("generate_all_report.json", report)
        return report

    output_builders = [
        ("mock_status.json", lambda: build_statuses(pois)),
        ("mock_inventory.json", lambda: build_inventory(pois)),
        ("mock_routes.json", lambda: build_routes(pois)),
        ("mock_weather.json", build_weather),
        ("mock_failure_scenarios.json", lambda: build_failures(pois)),
        ("mock_social_signals.json", lambda: build_social(pois)),
        ("benchmark_samples.json", build_benchmarks),
    ]
    outputs = {}
    with progress_bar(total=len(output_builders), desc="generate_all", unit="file") as pbar:
        for filename, builder in output_builders:
            outputs[filename] = builder()
            pbar.update(1)
            pbar.set_postfix({"file": filename})

    qwen_derived_report = None
    if qwen_derived:
        outputs, qwen_derived_report = _apply_qwen_derived_outputs(
            baseline_outputs=outputs,
            pois_payload=pois_payload,
            pois=pois,
            batch_size=batch_size,
            strict=strict_qwen_derived,
        )
        if strict_qwen_derived and not qwen_derived_report["success"]:
            report = {
                "task": "generate_all",
                "success": False,
                "stage": "qwen_derived",
                "poi_report": poi_report,
                "qwen_derived": qwen_derived_report,
            }
            write_report("generate_all_report.json", report)
            return report
    for filename, payload in outputs.items():
        assert_no_forbidden_text(payload, filename)
        write_json(output_dir / filename, payload)

    prompt_preview = {
        filename: compose_prompt(filename, seed=index + 1, batch_size=batch_size, start_index=1, pois=pois)[:1800]
        for index, filename in enumerate(FILE_CONTRACTS)
    }
    write_report("prompt_preview_report.json", {"task": "prompt_preview", "files": prompt_preview})

    validation_report: dict[str, Any] | None = None
    if validate:
        validator = Path(__file__).resolve().parents[1] / "validators" / "validate_mock_data.py"
        completed = subprocess.run([sys.executable, str(validator), "--input", str(output_dir)], text=True, capture_output=True)
        validation_report = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    report = {
        "task": "generate_all",
        "success": validation_report is None or validation_report["returncode"] == 0,
        "output_dir": str(output_dir),
        "files": ["mock_pois.json", *outputs.keys()],
        "poi_report": poi_report,
        "qwen_derived": qwen_derived_report,
        "validation": validation_report,
        "prompt_preview_report": "tools/qwen_data_factory/reports/prompt_preview_report.json",
    }
    write_report("generate_all_report.json", report)
    return report


def _apply_qwen_derived_outputs(
    *,
    baseline_outputs: dict[str, Any],
    pois_payload: dict[str, Any],
    pois: list[dict[str, Any]],
    batch_size: int,
    strict: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = QwenClient()
    outputs = dict(baseline_outputs)
    attempts: list[dict[str, Any]] = []
    accepted = 0
    with progress_bar(total=len(DERIVED_FILES), desc="qwen_derived", unit="file") as pbar:
        for index, filename in enumerate(DERIVED_FILES):
            result: dict[str, Any] = {"file": filename, "status": "failed", "request_id": None, "error": None}
            try:
                prompt = compose_prompt(filename, seed=10_000 + index, batch_size=batch_size, start_index=1, pois=pois)
                request_id, text = client.generate_json(task_type=f"generate_{filename.removesuffix('.json')}", prompt=prompt, system_prompt=SYSTEM_PROMPT)
                result["request_id"] = request_id
                candidate = parse_json_object(text)
                if not isinstance(candidate, dict):
                    raise ValueError("Qwen derived candidate must be a JSON object")
                candidate.setdefault("version", "v0.1")
                assert_no_forbidden_text(candidate, f"Qwen derived response {request_id}")
                calibrated = _calibrate_qwen_candidate(filename, candidate, outputs[filename], pois)
                assert_no_forbidden_text(calibrated, f"Qwen calibrated response {request_id}")
                candidate_outputs = dict(outputs)
                candidate_outputs[filename] = calibrated
                validation = _validate_candidate_set(pois_payload, candidate_outputs)
                if validation["returncode"] != 0:
                    raise ValueError(f"candidate failed validator: {validation['stdout'][-1200:]}")
                outputs[filename] = calibrated
                accepted += 1
                result["status"] = "accepted"
                result["mode"] = "qwen_candidate_calibrated"
            except Exception as exc:
                result["error"] = str(exc)[:1200]
                result["status"] = "rejected"
                if strict:
                    attempts.append(result)
                    pbar.update(1)
                    pbar.set_postfix({"file": filename, "accepted": accepted})
                    break
            attempts.append(result)
            pbar.update(1)
            pbar.set_postfix({"file": filename, "accepted": accepted})
    report = {
        "success": accepted == len(DERIVED_FILES),
        "accepted": accepted,
        "total": len(DERIVED_FILES),
        "strict": strict,
        "attempts": attempts,
        "fallback_used_for": [item["file"] for item in attempts if item["status"] != "accepted"],
    }
    write_report("qwen_derived_report.json", report)
    return outputs, report


def _calibrate_qwen_candidate(filename: str, candidate: dict[str, Any], baseline: dict[str, Any], pois: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline, ensure_ascii=False))
    poi_by_id = {poi.get("poi_id"): poi for poi in pois if isinstance(poi, dict)}
    if filename == "mock_status.json":
        return _calibrate_status(candidate, payload, poi_by_id)
    if filename == "mock_inventory.json":
        return _calibrate_inventory(candidate, payload, poi_by_id)
    if filename == "mock_weather.json":
        return _calibrate_weather(candidate, payload)
    if filename == "mock_failure_scenarios.json":
        return _calibrate_failures(candidate, payload, pois)
    if filename == "mock_social_signals.json":
        return _calibrate_social(candidate, payload, poi_by_id)
    if filename == "benchmark_samples.json":
        return _calibrate_benchmarks(candidate, payload)
    return payload


def _calibrate_status(candidate: dict[str, Any], payload: dict[str, Any], poi_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = candidate.get("statuses")
    target = payload.get("statuses", {})
    if not isinstance(source, dict) or not isinstance(target, dict):
        return payload
    valid_open = {"open", "closed", "closing_soon", "unknown"}
    valid_risk = {"low", "medium", "high", "blocking"}
    for poi_id, status in source.items():
        if poi_id not in poi_by_id or poi_id not in target or not isinstance(status, dict):
            continue
        query = status.get("query_status")
        target_query = target[poi_id].get("query_status", {})
        if not isinstance(query, dict) or not isinstance(target_query, dict):
            continue
        message = _clean_text(query.get("status_message"), 160)
        if message:
            target_query["status_message"] = _mock_prefix(message)
        if query.get("open_status") in valid_open:
            target_query["open_status"] = query["open_status"]
        if query.get("risk_level") in valid_risk:
            target_query["risk_level"] = query["risk_level"]
        for key in ("queue_minutes", "available_tables", "remaining_tickets"):
            if key in query:
                target_query[key] = _bounded_int(query.get(key), 0, 240, target_query.get(key, 0))
        for key in ("available", "reservation_available", "ticket_available", "booking_available"):
            if isinstance(query.get(key), bool):
                target_query[key] = query[key]
        target_query["source"] = "mock_api"
    return payload


def _calibrate_inventory(candidate: dict[str, Any], payload: dict[str, Any], poi_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    categories = {"restaurant_slots": "restaurant", "activity_slots": "activity"}
    for key, category in categories.items():
        source_slots = candidate.get(key)
        target_slots = payload.get(key)
        if not isinstance(source_slots, list) or not isinstance(target_slots, list):
            continue
        by_poi = {slot.get("poi_id"): slot for slot in target_slots if isinstance(slot, dict)}
        for slot in source_slots:
            if not isinstance(slot, dict):
                continue
            poi_id = slot.get("poi_id")
            if poi_by_id.get(poi_id, {}).get("category") != category or poi_id not in by_poi:
                continue
            target = by_poi[poi_id]
            if key == "restaurant_slots":
                target["base_tables"] = _bounded_int(slot.get("base_tables"), 1, 80, target.get("base_tables", 4))
                target["reserved_tables"] = min(
                    target["base_tables"],
                    _bounded_int(slot.get("reserved_tables"), 0, 80, target.get("reserved_tables", 0)),
                )
                target["max_party_size"] = _bounded_int(slot.get("max_party_size"), 2, 12, target.get("max_party_size", 4))
            else:
                target["remaining_tickets"] = _bounded_int(slot.get("remaining_tickets"), 0, 300, target.get("remaining_tickets", 8))
                if isinstance(slot.get("booking_available"), bool):
                    target["booking_available"] = slot["booking_available"]
    return payload


def _calibrate_weather(candidate: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    source_items = candidate.get("weather_snapshots")
    target_items = payload.get("weather_snapshots")
    if not isinstance(source_items, list) or not isinstance(target_items, list):
        return payload
    weather_map = {"晴": "sunny", "晴天": "sunny", "多云": "cloudy", "阴": "cloudy", "小雨": "rain", "雨": "rain", "中雨": "rain", "大雨": "heavy_rain", "暴雨": "heavy_rain", "高温": "hot", "炎热": "hot", "寒冷": "cold"}
    valid_weather = {"sunny", "cloudy", "rain", "heavy_rain", "hot", "cold", "unknown"}
    valid_risk = {"low", "medium", "high", "blocking"}
    by_area = {item.get("area"): item for item in target_items if isinstance(item, dict)}
    for item in source_items:
        if not isinstance(item, dict):
            continue
        area = item.get("area")
        if area not in by_area:
            continue
        target = by_area[area]
        weather = str(item.get("weather") or "")
        target["weather"] = weather if weather in valid_weather else weather_map.get(weather, target.get("weather", "unknown"))
        probability = _number(item.get("rain_probability"), target.get("rain_probability", 0))
        target["rain_probability"] = round(probability / 100 if probability > 1 else probability, 2)
        target["temperature"] = _bounded_int(item.get("temperature"), -10, 45, target.get("temperature", 25))
        if item.get("outdoor_risk_level") in valid_risk:
            target["outdoor_risk_level"] = item["outdoor_risk_level"]
        recovery = _clean_text(item.get("suggested_recovery"), 40)
        if recovery:
            target["suggested_recovery"] = recovery
        target["source"] = "mock_api"
    return payload


def _calibrate_failures(candidate: dict[str, Any], payload: dict[str, Any], pois: list[dict[str, Any]]) -> dict[str, Any]:
    source_items = candidate.get("scenarios")
    target_items = payload.get("scenarios")
    if not isinstance(source_items, list) or not isinstance(target_items, list):
        return payload
    poi_by_category = {
        "restaurant": next((poi.get("poi_id") for poi in pois if poi.get("category") == "restaurant"), None),
        "activity": next((poi.get("poi_id") for poi in pois if poi.get("category") == "activity"), None),
    }
    valid_codes = {"NO_TABLE_AVAILABLE", "ACTIVITY_FULL", "PLAN_EXECUTABLE_WINDOW_EXPIRED"}
    by_code = {item.get("error_code"): item for item in target_items if isinstance(item, dict)}
    for item in source_items:
        if not isinstance(item, dict) or item.get("error_code") not in valid_codes:
            continue
        target = by_code.get(item["error_code"])
        if not target:
            continue
        trigger = item.get("trigger")
        if isinstance(trigger, dict):
            path = _clean_text(trigger.get("path"), 120)
            if path.startswith("/api/v1/"):
                target["trigger"]["path"] = path
        if item["error_code"] == "NO_TABLE_AVAILABLE" and poi_by_category["restaurant"]:
            target["trigger"]["poi_id"] = poi_by_category["restaurant"]
        if item["error_code"] == "ACTIVITY_FULL" and poi_by_category["activity"]:
            target["trigger"]["poi_id"] = poi_by_category["activity"]
        target["enabled"] = bool(item.get("enabled", True))
        target["visible_to_user"] = False
    return payload


def _calibrate_social(candidate: dict[str, Any], payload: dict[str, Any], poi_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_items = candidate.get("signals")
    target_items = payload.get("signals")
    if not isinstance(source_items, list) or not isinstance(target_items, list):
        return payload
    by_poi = {item.get("poi_id"): item for item in target_items if isinstance(item, dict)}
    for item in source_items:
        if not isinstance(item, dict):
            continue
        poi_id = item.get("poi_id")
        if poi_id not in poi_by_id or poi_id not in by_poi:
            continue
        target = by_poi[poi_id]
        summary = _clean_text(item.get("summary"), 260)
        if summary:
            target["summary"] = _paragraph_summary(summary, poi_by_id[poi_id])
        target["positive_tags"] = _tag_list(item.get("positive_tags")) or target.get("positive_tags", [])
        target["negative_tags"] = _tag_list(item.get("negative_tags"))
        target["confidence"] = _bounded_float(item.get("confidence"), 0.0, 1.0, target.get("confidence", 0.72))
        target["heat_score"] = _bounded_float(item.get("heat_score"), 0.0, 1.0, target.get("heat_score", 0.62), scale_if_percent=True)
        target["mock_sources"] = ["link1", "link2", "link3"]
        target["is_mock"] = True
        target["source_type"] = "mock_social_signal"
        target["updated_at"] = ISO_NOW
    return payload


def _calibrate_benchmarks(candidate: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    source_items = candidate.get("samples")
    target_items = payload.get("samples")
    if not isinstance(source_items, list) or not isinstance(target_items, list):
        return payload
    valid_checks = {"restaurant_capacity", "activity_ticket", "weather_risk", "executable_window", "budget_constraint", "tool_action_integrity"}
    valid_scenarios = {"family_parent_child", "friend_group", "anniversary_emotion"}
    existing_ids = {item.get("sample_id") for item in target_items if isinstance(item, dict)}
    appended = 0
    for index, item in enumerate(source_items, start=1):
        if not isinstance(item, dict):
            continue
        scenario = item.get("scenario") if item.get("scenario") in valid_scenarios else _infer_scenario(item)
        sample_id = _clean_id(item.get("sample_id"), f"bench_qwen_{scenario}_{index:03d}")
        if sample_id in existing_ids:
            sample_id = f"bench_qwen_{scenario}_{index:03d}"
        input_text = _clean_text(item.get("input_text"), 180)
        if not input_text:
            continue
        checks = [check for check in item.get("expected_verifier_checks", []) if check in valid_checks]
        if not checks:
            checks = ["restaurant_capacity", "activity_ticket", "weather_risk", "executable_window"][:2]
        target_items.append(
            {
                "sample_id": sample_id,
                "scenario": scenario,
                "scenario_expected": scenario,
                "input_text": input_text,
                "expected_constraints": _tag_list(item.get("expected_constraints")) or ["mock_boundary", "local_life"],
                "expected_verifier_checks": checks,
            }
        )
        existing_ids.add(sample_id)
        appended += 1
        if appended >= 12:
            break
    return payload


def _validate_candidate_set(pois_payload: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lifepilot_qwen_candidate_") as tmp:
        tmp_dir = Path(tmp)
        write_json(tmp_dir / "mock_pois.json", pois_payload)
        for filename, payload in outputs.items():
            write_json(tmp_dir / filename, payload)
        validator = Path(__file__).resolve().parents[1] / "validators" / "validate_mock_data.py"
        completed = subprocess.run([sys.executable, str(validator), "--input", str(tmp_dir)], text=True, capture_output=True)
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


def _clean_text(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:max_len]


def _mock_prefix(value: str) -> str:
    return value if ("Mock" in value or "模拟" in value) else f"Mock状态摘要：{value}"


def _paragraph_summary(value: str, poi: dict[str, Any]) -> str:
    name = str(poi.get("name") or "")
    if "Mock" not in value and "模拟" not in value:
        value = f"口碑Mock归纳：{value}"
    if name and name not in value:
        value = f"口碑Mock归纳：{name}的模拟反馈显示，{value.removeprefix('口碑Mock归纳：')}"
    if not _has_category_anchor(value, poi):
        value = f"{value} {_category_social_tail(poi)}"
    if len(value) >= 80:
        return value
    tags = "、".join(poi.get("tags", [])[:4])
    return f"{value} 结合模拟反馈看，用户更关注{tags or '动线、预算、停留舒适度'}，同时会比较卫生、噪音、排队、停车、天气遮挡、是否适合独处或临时会合等具体体验。"


def _has_category_anchor(summary: str, poi: dict[str, Any]) -> bool:
    category = poi.get("category")
    anchors = {
        "restaurant": ["菜", "餐", "咖啡", "饮", "口味", "出品", "座位", "性价比"],
        "transport_anchor": ["停车", "车位", "接驳", "打车", "地铁", "上车", "入口", "等车"],
        "service": ["卫生", "服务", "补给", "更衣", "储物", "花束", "蛋糕", "休息"],
        "activity": ["体验", "互动", "排队", "票", "孩子", "展", "游乐", "噪音"],
        "walk_spot": ["步道", "湖", "拍照", "风", "遮挡", "路面", "散步", "人流"],
    }
    return any(anchor in summary for anchor in anchors.get(str(category), []))


def _category_social_tail(poi: dict[str, Any]) -> str:
    category = poi.get("category")
    if category == "restaurant":
        return "补充口碑集中在菜品/饮品出品、座位舒适度、排队和性价比，评价可能有好有坏。"
    if category == "transport_anchor":
        return "补充口碑集中在停车或接驳效率、入口好找程度、等车时间和高峰拥挤。"
    if category == "service":
        return "补充口碑集中在卫生维护、补给是否方便、空间是否够用和服务稳定性。"
    if category == "activity":
        return "补充口碑集中在体验内容、场地或座位、排队、噪音和是否匹配当前需求。"
    if category == "walk_spot":
        return "补充口碑集中在步道舒适度、拍照效果、遮挡条件、天气和人流。"
    return "补充口碑集中在具体用途、便利度和风险点。"


def _tag_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if isinstance(item, str):
            text = _clean_text(item, 40)
            if text:
                cleaned.append(text)
    return cleaned[:12]


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(default)
        except (TypeError, ValueError):
            return 0.0


def _bounded_int(value: Any, low: int, high: int, default: Any) -> int:
    return int(min(high, max(low, round(_number(value, default)))))


def _bounded_float(value: Any, low: float, high: float, default: Any, *, scale_if_percent: bool = False) -> float:
    number = _number(value, default)
    if scale_if_percent and number > 1:
        number /= 10 if number <= 10 else 100
    return round(min(high, max(low, number)), 2)


def _clean_id(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value.lower()).strip("_")
    if not cleaned.startswith("bench_"):
        cleaned = f"bench_{cleaned}"
    return cleaned[:70] or fallback


def _infer_scenario(item: dict[str, Any]) -> str:
    text = json.dumps(item, ensure_ascii=False).lower()
    if "friend" in text or "朋友" in text:
        return "friend_group"
    if "anniversary" in text or "纪念" in text or "夫妻" in text or "情侣" in text:
        return "anniversary_emotion"
    return "family_parent_child"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all LifePilot mock data files.")
    parser.add_argument("--target-pois", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    parser.add_argument("--allow-template-fallback", action="store_true", help="Use deterministic seed POIs if local Qwen is unavailable.")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing mock_pois.json instead of calling Qwen again.")
    parser.add_argument("--force-pois", action="store_true", help="Deprecated alias for the default behavior: regenerate mock_pois.json.")
    parser.add_argument("--qwen-derived", action="store_true", default=True, help="Try Qwen candidate generation for non-route derived files; invalid candidates fall back to rule-generated files.")
    parser.add_argument("--no-qwen-derived", action="store_false", dest="qwen_derived", help="Disable Qwen for derived files and use deterministic rule-derived files only.")
    parser.add_argument("--strict-qwen-derived", action="store_true", help="Fail if any Qwen-derived non-POI file is rejected instead of falling back.")
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args()
    report = generate_all(
        args.target_pois,
        args.batch_size,
        args.output,
        args.allow_template_fallback,
        not args.skip_validate,
        args.force_pois,
        args.reuse_existing,
        args.qwen_derived,
        args.strict_qwen_derived,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
