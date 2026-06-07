from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
FRONTEND_DIR = ROOT / "frontend"
DATA_FILES = {
    "mock_pois.json": ("pois", "poi_id"),
    "mock_status.json": ("statuses", "poi_id"),
    "mock_inventory.json": (None, "poi_id"),
    "mock_routes.json": ("routes", "route_id"),
    "mock_weather.json": ("weather_snapshots", "weather_id"),
    "mock_failure_scenarios.json": ("scenarios", "failure_scenario_id"),
    "mock_social_signals.json": ("signals", "signal_id"),
    "benchmark_samples.json": ("samples", "sample_id"),
}
FILE_META = {
    "mock_pois.json": {
        "title": "POI基础地点库",
        "description": "保存杭州下沙、金沙湖、高教园区的活动、餐厅、散步点、服务点和交通锚点，是所有状态、路线、口碑和Benchmark引用的基础。",
        "owner": "CandidateRetriever / MockAPI",
        "checks": ["poi_id必须存在且唯一", "mock_only必须为true", "必须覆盖家庭亲子、朋友局、纪念日"],
    },
    "mock_status.json": {
        "title": "动态状态快照",
        "description": "保存每个POI的Mock营业、排队、餐厅桌位、活动票务和可执行窗口输入；只作为Verifier和Executor的状态依据，不代表真实平台确认。",
        "owner": "MockAPI / Verifier / Executor",
        "checks": ["query_status.source必须是mock_api", "expire_at必须是ISO时间", "失败调试字段不得给普通用户展示"],
    },
    "mock_inventory.json": {
        "title": "时段库存规则",
        "description": "保存餐厅桌位和活动余票的时段库存，用于模拟查询时可用、执行时可能变化的动态不确定性。",
        "owner": "MockAPI内部规则",
        "checks": ["slot时间必须是ISO时间", "poi_id必须引用POI库", "餐厅和活动库存分开维护"],
    },
    "mock_routes.json": {
        "title": "路线估计矩阵",
        "description": "保存POI之间的Mock路线、距离、耗时和交通状态，避免LLM估算路线，供Verifier计算时间可行性和距离约束。",
        "owner": "MockAPI / Verifier",
        "checks": ["route_id必须为route_前缀", "起终点必须存在", "source必须是mock_api"],
    },
    "mock_weather.json": {
        "title": "天气风险快照",
        "description": "保存下沙、金沙湖、高教园区分时段Mock天气和户外风险，支持户外散步、湖边合照、亲子活动的PlanB判断。",
        "owner": "MockAPI / Verifier",
        "checks": ["weather_id必须为weather_前缀", "time_range必须完整", "source必须是mock_api"],
    },
    "mock_failure_scenarios.json": {
        "title": "失败注入脚本",
        "description": "保存餐厅满座、活动满员、窗口过期等Debug和测试用失败脚本，用来验证Recovery版本化修复，不进入普通用户页。",
        "owner": "Testing / Debug / Recovery",
        "checks": ["visible_to_user必须为false", "error_code必须使用契约错误码", "触发路径必须是/api/v1"],
    },
    "mock_social_signals.json": {
        "title": "口碑Mock信号",
        "description": "保存模拟社交反馈摘要，只用于展示可扩展口碑雷达能力；缺失不阻断主流程，不声称实时抓取第三方平台。",
        "owner": "SocialSignalMock",
        "checks": ["is_mock必须为true", "source_type必须是mock_social_signal", "poi_id必须存在"],
    },
    "benchmark_samples.json": {
        "title": "LifePilot-Bench样例",
        "description": "保存家庭亲子、朋友局、纪念日等评测输入和期望断言，用于回归验证Intent、Constraint、Verifier、Recovery和Mock边界。",
        "owner": "BenchmarkEvaluator",
        "checks": ["sample_id必须为bench_前缀", "三大P0场景必须覆盖", "断言不得新增未定义契约"],
    },
}


class FactoryState:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir


class Handler(BaseHTTPRequestHandler):
    state: FactoryState

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/factory":
            self._send_file(FRONTEND_DIR / "index.html")
            return
        if parsed.path.startswith("/factory/assets/"):
            self._send_file(FRONTEND_DIR / parsed.path.removeprefix("/factory/assets/"))
            return
        if parsed.path == "/factory/api/data":
            self._send_json(self._query_data(parse_qs(parsed.query)))
            return
        if parsed.path == "/factory/api/reports":
            self._send_json(self._reports())
            return
        self._send_json({"success": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/factory/api/validate":
            validator = ROOT / "validators" / "validate_mock_data.py"
            completed = subprocess.run([sys.executable, str(validator), "--input", str(self.state.data_dir)], text=True, capture_output=True)
            self._send_json({"success": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr})
            return
        self._send_json({"success": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/factory/api/items":
            self._send_json({"success": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        params = parse_qs(parsed.query)
        filename = _one(params, "file")
        item_id = _one(params, "id")
        if filename not in DATA_FILES or not item_id:
            self._send_json({"success": False, "error": "file and id are required"}, HTTPStatus.BAD_REQUEST)
            return
        result = self._delete_item(filename, item_id)
        self._send_json(result, HTTPStatus.OK if result["success"] else HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _query_data(self, params: dict[str, list[str]]) -> dict[str, Any]:
        filename_filter = _one(params, "file")
        scenario_filter = _one(params, "scenario")
        category_filter = _one(params, "category")
        area_filter = _one(params, "area")
        q = (_one(params, "q") or "").lower()
        items: list[dict[str, Any]] = []
        for filename, (top_key, id_key) in DATA_FILES.items():
            if filename_filter and filename_filter != filename:
                continue
            payload = _load(self.state.data_dir / filename)
            records = _records(filename, payload)
            for record in records:
                flat = _project_record(filename, record, id_key)
                if scenario_filter and scenario_filter not in flat.get("scenarios", []):
                    continue
                if category_filter and flat.get("category") != category_filter:
                    continue
                if area_filter and flat.get("area") != area_filter:
                    continue
                haystack = json.dumps(flat, ensure_ascii=False).lower()
                if q and q not in haystack:
                    continue
                items.append(flat)
        return {
            "success": True,
            "data_dir": str(self.state.data_dir),
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "files": list(DATA_FILES.keys()),
            "file_meta": FILE_META,
            "items": items,
            "counts": _counts(self.state.data_dir),
        }

    def _reports(self) -> dict[str, Any]:
        reports_dir = ROOT / "reports"
        reports = []
        if reports_dir.exists():
            for path in sorted(reports_dir.glob("*.json")):
                reports.append({"name": path.name, "updated_at": path.stat().st_mtime, "payload": _load(path)})
            qlog = reports_dir / "qwen_requests.jsonl"
            if qlog.exists():
                reports.append({"name": qlog.name, "updated_at": qlog.stat().st_mtime, "tail": qlog.read_text(encoding="utf-8").splitlines()[-20:]})
        return {"success": True, "reports": reports}

    def _delete_item(self, filename: str, item_id: str) -> dict[str, Any]:
        path = self.state.data_dir / filename
        payload = _load(path)
        if not payload:
            return {"success": False, "deleted": 0}
        deleted = 0
        if filename == "mock_status.json":
            statuses = payload.get("statuses", {})
            if item_id in statuses:
                del statuses[item_id]
                deleted = 1
        elif filename == "mock_inventory.json":
            for key in ("restaurant_slots", "activity_slots"):
                rows = payload.get(key, [])
                if isinstance(rows, list):
                    kept = [row for row in rows if not isinstance(row, dict) or row.get("poi_id") != item_id]
                    deleted += len(rows) - len(kept)
                    payload[key] = kept
        else:
            top_key, id_key = DATA_FILES[filename]
            rows = payload.get(top_key or "", [])
            if isinstance(rows, list):
                kept = [row for row in rows if not isinstance(row, dict) or row.get(id_key) != item_id]
                deleted = len(rows) - len(kept)
                payload[top_key] = kept
        if deleted:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if filename == "mock_pois.json":
                deleted += self._cascade_delete_poi(item_id)
        return {"success": deleted > 0, "deleted": deleted}

    def _cascade_delete_poi(self, poi_id: str) -> int:
        deleted = 0
        for filename in ("mock_status.json", "mock_inventory.json", "mock_social_signals.json"):
            result = self._delete_item(filename, poi_id)
            deleted += int(result.get("deleted", 0))
        route_path = self.state.data_dir / "mock_routes.json"
        routes_payload = _load(route_path)
        routes = routes_payload.get("routes", [])
        if isinstance(routes, list):
            kept = [
                route
                for route in routes
                if not isinstance(route, dict)
                or (route.get("origin_poi_id") != poi_id and route.get("destination_poi_id") != poi_id)
            ]
            route_deleted = len(routes) - len(kept)
            if route_deleted:
                routes_payload["routes"] = kept
                route_path.write_text(json.dumps(routes_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                deleted += route_deleted
        return deleted

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"success": False, "error": "file not found"}, HTTPStatus.NOT_FOUND)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _load(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _records(filename: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if filename == "mock_status.json":
        statuses = payload.get("statuses", {})
        return [{"poi_id": key, **value} for key, value in statuses.items()] if isinstance(statuses, dict) else []
    if filename == "mock_inventory.json":
        rows = []
        for key in ("restaurant_slots", "activity_slots"):
            for row in payload.get(key, []) if isinstance(payload.get(key, []), list) else []:
                if isinstance(row, dict):
                    rows.append({"inventory_type": key, **row})
        return rows
    top_key, _ = DATA_FILES[filename]
    rows = payload.get(top_key or "", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _project_record(filename: str, record: dict[str, Any], id_key: str) -> dict[str, Any]:
    query_status = record.get("query_status", {}) if isinstance(record.get("query_status"), dict) else {}
    location = record.get("location", {}) if isinstance(record.get("location"), dict) else {}
    item_id = record.get(id_key) or record.get("poi_id")
    scenarios = record.get("suitable_scenarios")
    if not isinstance(scenarios, list):
        scenario = record.get("scenario_expected") or record.get("scenario")
        scenarios = [scenario] if scenario else []
    return {
        "file": filename,
        "id": item_id,
        "name": record.get("name") or record.get("summary") or record.get("input_text") or item_id,
        "category": record.get("category"),
        "area": record.get("area") or location.get("area"),
        "scenarios": scenarios,
        "mock": bool(record.get("mock_only") or record.get("is_mock") or query_status.get("source") == "mock_api"),
        "status": query_status.get("risk_level") or record.get("error_code") or record.get("weather") or record.get("transport_mode"),
        "record": record,
    }


def _counts(data_dir: Path) -> dict[str, int]:
    counts = {}
    for filename in DATA_FILES:
        counts[filename] = len(_records(filename, _load(data_dir / filename)))
    return counts


def _one(params: dict[str, list[str]], key: str) -> str | None:
    value = params.get(key, [None])[0]
    return value or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve LifePilot Qwen data factory viewer.")
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "backend" / "data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    Handler.state = FactoryState(args.data)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"LifePilot data factory: http://{args.host}:{args.port}/factory")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
