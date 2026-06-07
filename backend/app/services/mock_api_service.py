import copy
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import (
    EXECUTIONS_STORE_PATH,
    MOCK_FAILURE_SCENARIOS_PATH,
    MOCK_IDEMPOTENCY_STORE_PATH,
    MOCK_INVENTORY_PATH,
    MOCK_POIS_PATH,
    MOCK_ROUTES_PATH,
    MOCK_SOCIAL_SIGNALS_PATH,
    MOCK_STATUS_PATH,
    MOCK_WEATHER_PATH,
    RUNTIME_ACTIVITY_POIS_PATH,
)
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.time import iso_now
from app.services.logging_service import LoggingService
from app.services.mock_state_engine import (
    DeterministicSeedService,
    InventoryMockEngine,
    MockClock,
    SocialSignalMockEngine,
    StatusMockEngine,
    WeatherMockEngine,
)
from app.storage.json_store import JsonFileStore


AREA_ALIASES = {
    "xiasha": "下沙",
    "下沙": "下沙",
    "jinshahu": "金沙湖",
    "金沙湖": "金沙湖",
    "gaojiao": "高教园区",
    "gaojiaoyuan": "高教园区",
    "高教园区": "高教园区",
}


EXECUTION_PATHS = {
    "book_activity": "POST /api/v1/mock/activities/{poi_id}/book",
    "reserve_restaurant": "POST /api/v1/mock/restaurants/{poi_id}/reserve",
    "order_item": "POST /api/v1/mock/orders/create",
    "send_message": "POST /api/v1/mock/messages/send",
}


class MockAPIService:
    IDEMPOTENCY_FILE = MOCK_IDEMPOTENCY_STORE_PATH
    EXECUTIONS_FILE = EXECUTIONS_STORE_PATH

    def __init__(self, store: JsonFileStore, logger: Optional[LoggingService] = None) -> None:
        self.store = store
        self.logger = logger
        self.clock = MockClock()
        self.seed_service = DeterministicSeedService()
        self.inventory_engine = InventoryMockEngine(self.clock, self.seed_service)
        self.status_engine = StatusMockEngine(self.clock, self.seed_service)
        self.weather_engine = WeatherMockEngine(self.clock, self.seed_service)
        self.social_signal_engine = SocialSignalMockEngine(self.clock, self.seed_service)

    @classmethod
    def from_data_dir(cls, data_dir: Path, logger: Optional[LoggingService] = None) -> "MockAPIService":
        return cls(JsonFileStore(data_dir), logger)

    def search_pois(
        self,
        trace_id: str,
        *,
        scenario: Optional[str] = None,
        area: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 10,
        debug: bool = False,
    ) -> Dict[str, Any]:
        items = self._pois()
        normalized_area = self._normalize_area(area)
        requested_tags = self._split_csv(tags)
        if scenario:
            items = [item for item in items if scenario in item.get("suitable_scenarios", [])]
        if normalized_area:
            items = [item for item in items if item.get("area") == normalized_area or item.get("location", {}).get("area") == normalized_area]
        if category:
            items = [item for item in items if item.get("category") == category or item.get("mock_group") == category]
        if requested_tags:
            items = [item for item in items if set(requested_tags).issubset(set(item.get("tags", [])))]
        projected = [self._project_poi(item) for item in items[: self._limit(limit)]]
        self._log_tool(trace_id, "search_poi", {"count": len(projected), "category": category})
        data = {"items": projected, "page_info": self._page_info(len(projected), limit)}
        if debug:
            data["debug"] = {"fixture": "mock_pois.json", "matched_count": len(projected)}
        return data

    def search_restaurants(
        self,
        trace_id: str,
        *,
        scenario: Optional[str] = None,
        area: Optional[str] = None,
        dietary_preference: Optional[str] = None,
        budget_max_per_person: Optional[float] = None,
        tags: Optional[str] = None,
        limit: int = 10,
        debug: bool = False,
    ) -> Dict[str, Any]:
        requested_tags = self._split_csv(tags) + self._split_csv(dietary_preference)
        normalized_area = self._normalize_area(area)
        items = [item for item in self._pois() if item.get("category") == "restaurant"]
        if scenario:
            items = [item for item in items if scenario in item.get("suitable_scenarios", [])]
        if normalized_area:
            items = [item for item in items if item.get("area") == normalized_area or item.get("location", {}).get("area") == normalized_area]
        if budget_max_per_person is not None:
            items = [item for item in items if float(item.get("price_per_person") or 0) <= budget_max_per_person]
        if requested_tags:
            items = [item for item in items if set(requested_tags).intersection(set(item.get("tags", [])))]
        items = sorted(items, key=lambda item: (-float(item.get("rating") or 0), float(item.get("price_per_person") or 0)))
        projected = [self._project_poi(item) for item in items[: self._limit(limit)]]
        self._log_tool(trace_id, "search_restaurant", {"count": len(projected)})
        data = {"items": projected, "page_info": self._page_info(len(projected), limit)}
        if debug:
            data["debug"] = {"fixture": "mock_pois.json", "matched_count": len(projected)}
        return data

    def poi_status(
        self,
        trace_id: str,
        poi_id: str,
        *,
        party_size: Optional[int] = None,
        when: Optional[str] = None,
        failure_scenario_id: Optional[str] = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        poi = self._require_poi(poi_id)
        status = self._base_status(poi, when=when, party_size=party_size, scenario=failure_scenario_id)
        if poi.get("category") == "restaurant":
            status = self._restaurant_status_from_base(status, poi_id, party_size, when)
        elif poi.get("category") == "activity":
            status = self._activity_status_from_base(status, poi_id, party_size, when)
            if self._failure_matches(failure_scenario_id, "book_activity", poi_id, ErrorCode.ACTIVITY_FULL):
                status.update(
                    {
                        "available": False,
                        "ticket_available": False,
                        "remaining_tickets": 0,
                        "booking_available": False,
                        "risk_level": "blocking",
                        "status_message": "当前场次Mock余票不足，建议切换活动或时间。",
                    }
                )
        else:
            status = self._generic_status_from_base(status)
        payload = self._status_payload(poi_id, status)
        if debug and failure_scenario_id:
            payload["debug"] = self._failure_summary(failure_scenario_id)
        self._log_tool(trace_id, "get_poi_status", {"poi_id": poi_id, "available": payload["available"]})
        return payload

    def restaurant_status(
        self,
        trace_id: str,
        poi_id: str,
        *,
        arrival_time: str,
        party_size: int,
        failure_scenario_id: Optional[str] = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        poi = self._require_poi(poi_id)
        if poi.get("category") != "restaurant":
            raise AppError(
                ErrorCode.PLAN_STEP_POI_NOT_FOUND,
                f"{poi_id} is not a restaurant.",
                "当前餐厅数据缺失，换一个方案。",
                404,
                True,
            )
        status = self._restaurant_status_from_base(
            self._base_status(poi, when=arrival_time, party_size=party_size, scenario=failure_scenario_id),
            poi_id,
            party_size,
            arrival_time,
        )
        if self._failure_matches(failure_scenario_id, "reserve_restaurant", poi_id, ErrorCode.NO_TABLE_AVAILABLE):
            status.update(
                {
                    "available": False,
                    "available_tables": 0,
                    "reservation_available": False,
                    "risk_level": "blocking",
                    "status_message": "当前时段Mock桌位已满，建议切换备选餐厅。",
                }
            )
        payload = self._status_payload(poi_id, status)
        if debug and failure_scenario_id:
            payload["debug"] = self._failure_summary(failure_scenario_id)
        self._log_tool(
            trace_id,
            "get_restaurant_status",
            {
                "poi_id": poi_id,
                "available_tables": payload["available_tables"],
                "queue_minutes": payload["queue_minutes"],
                "expire_at": payload["expire_at"],
            },
        )
        return payload

    def estimate_route(
        self,
        trace_id: str,
        *,
        origin_poi_id: str,
        destination_poi_id: str,
        transport_mode: str,
        departure_time: str,
    ) -> Dict[str, Any]:
        self._require_poi(origin_poi_id)
        self._require_poi(destination_poi_id)
        route = self._find_route(origin_poi_id, destination_poi_id, transport_mode)
        if route is None:
            route = self._generate_route(origin_poi_id, destination_poi_id, transport_mode, departure_time)
        payload = {
            "route_id": route.get("route_id") or new_id("route"),
            "origin_poi_id": origin_poi_id,
            "destination_poi_id": destination_poi_id,
            "transport_mode": transport_mode,
            "distance_km": route["distance_km"],
            "duration_minutes": route["duration_minutes"],
            "traffic_level": route.get("traffic_level", "unknown"),
            "confidence": route.get("confidence", 0.8),
            "source": "mock_api",
            "updated_at": route.get("updated_at") or iso_now(),
        }
        self._log_tool(trace_id, "estimate_route", {"duration_minutes": payload["duration_minutes"], "traffic_level": payload["traffic_level"]})
        return payload

    def weather(self, trace_id: str, *, area: str, start_time: str, end_time: str, debug: bool = False) -> Dict[str, Any]:
        normalized_area = self._normalize_area(area)
        if not normalized_area:
            raise AppError(ErrorCode.BAD_REQUEST, "area is required.", "请求参数不完整，请检查后重试。", 400, True)
        snapshots = self.store.read(MOCK_WEATHER_PATH, {"weather_snapshots": []}).get("weather_snapshots", [])
        match = next(
            (
                item
                for item in snapshots
                if item.get("area") == normalized_area and self._time_ranges_overlap(item.get("time_range") or {}, start_time, end_time)
            ),
            None,
        )
        payload = copy.deepcopy(match) if match else self.weather_engine.generate(normalized_area, start_time, end_time)
        payload["area"] = area
        payload["time_range"] = {"start_time": start_time, "end_time": end_time}
        payload["source"] = "mock_api"
        payload["mock_only"] = True
        if debug:
            payload["debug"] = {"override_fixture": "mock_weather.json" if match else None, "matched_area": normalized_area}
        self._log_tool(trace_id, "get_weather", {"area": normalized_area, "outdoor_risk_level": payload.get("outdoor_risk_level")})
        return payload

    def social_signal(self, trace_id: str, poi_id: str) -> Dict[str, Any]:
        poi = self._require_poi(poi_id)
        signals = self.store.read(MOCK_SOCIAL_SIGNALS_PATH, {"signals": []}).get("signals", [])
        signal = next((item for item in signals if item.get("poi_id") == poi_id), None)
        payload = copy.deepcopy(signal) if signal else self.social_signal_engine.generate(poi)
        payload["is_mock"] = True
        payload["source_type"] = "mock_social_signal"
        self._log_tool(trace_id, "get_social_signal_mock", {"poi_id": poi_id})
        return payload

    def book_activity(self, trace_id: str, poi_id: str, body: Dict[str, Any], idempotency_key: Optional[str], debug: bool = False) -> Dict[str, Any]:
        self._require_execution_key(idempotency_key, body)
        return self._execute_with_idempotency(
            trace_id,
            idempotency_key,
            "book_activity",
            poi_id,
            body,
            lambda: self._book_activity_once(trace_id, poi_id, body, debug),
        )

    def reserve_restaurant(self, trace_id: str, poi_id: str, body: Dict[str, Any], idempotency_key: Optional[str], debug: bool = False) -> Dict[str, Any]:
        self._require_execution_key(idempotency_key, body)
        return self._execute_with_idempotency(
            trace_id,
            idempotency_key,
            "reserve_restaurant",
            poi_id,
            body,
            lambda: self._reserve_restaurant_once(trace_id, poi_id, body, debug),
        )

    def order_item(self, trace_id: str, body: Dict[str, Any], idempotency_key: Optional[str]) -> Dict[str, Any]:
        self._require_execution_key(idempotency_key, body)
        return self._execute_with_idempotency(trace_id, idempotency_key, "order_item", body.get("poi_id"), body, lambda: self._order_once(trace_id, body))

    def send_message(self, trace_id: str, body: Dict[str, Any], idempotency_key: Optional[str]) -> Dict[str, Any]:
        self._require_execution_key(idempotency_key, body)
        return self._execute_with_idempotency(trace_id, idempotency_key, "send_message", None, body, lambda: self._message_once(trace_id, body))

    def _book_activity_once(self, trace_id: str, poi_id: str, body: Dict[str, Any], debug: bool) -> Dict[str, Any]:
        poi = self._require_poi(poi_id)
        self._require_fields(body, ["plan_id", "action_id", "party_size", "booking_time"])
        self._assert_window_open(body)
        failure_id = body.get("failure_scenario_id")
        if self._failure_matches(failure_id, "book_activity", poi_id, ErrorCode.ACTIVITY_FULL):
            self._log_tool(trace_id, "book_activity", {"poi_id": poi_id, "status": "failed", "error_code": ErrorCode.ACTIVITY_FULL.value})
            raise self._execution_error(ErrorCode.ACTIVITY_FULL, "Activity is full.", "当前场次已满，正在找替代活动。", debug, failure_id)
        status = self.poi_status(trace_id, poi_id, party_size=int(body["party_size"]), when=body["booking_time"])
        if not status["booking_available"] or not status["ticket_available"]:
            raise self._execution_error(ErrorCode.ACTIVITY_FULL, "Activity is full.", "当前场次已满，正在找替代活动。", debug, failure_id)
        data = {
            "booking_id": self._venue_bound_id("mock_booking", poi, body["plan_id"], body["action_id"], body["booking_time"], body["party_size"]),
            "poi_id": poi_id,
            "poi_name": poi.get("name"),
            "venue_snapshot": self._venue_snapshot(poi),
            "plan_id": body["plan_id"],
            "action_id": body["action_id"],
            "party_size": int(body["party_size"]),
            "booking_time": body["booking_time"],
            "remaining_tickets_before": status.get("remaining_tickets"),
            "booking_expires_at": status.get("expire_at"),
            "status": "success",
            "display_text": f"Mock预约：{poi.get('name')}，{self._time_label(body['booking_time'])}，{int(body['party_size'])}人，余票{status.get('remaining_tickets')}张",
            "mock_only": True,
            "created_at": iso_now(),
        }
        self._record_execution(trace_id, "book_activity", data)
        self._log_tool(trace_id, "book_activity", {"poi_id": poi_id, "status": "success"})
        return data

    def _reserve_restaurant_once(self, trace_id: str, poi_id: str, body: Dict[str, Any], debug: bool) -> Dict[str, Any]:
        poi = self._require_poi(poi_id)
        self._require_fields(body, ["plan_id", "action_id", "party_size", "arrival_time"])
        self._assert_window_open(body)
        failure_id = body.get("failure_scenario_id")
        if self._failure_matches(failure_id, "reserve_restaurant", poi_id, ErrorCode.NO_TABLE_AVAILABLE):
            self._log_tool(trace_id, "reserve_restaurant", {"poi_id": poi_id, "status": "failed", "error_code": ErrorCode.NO_TABLE_AVAILABLE.value})
            raise self._execution_error(ErrorCode.NO_TABLE_AVAILABLE, "No available table.", "原餐厅当前已满，我会尝试为你切换到备选餐厅。", debug, failure_id)
        status = self.restaurant_status(trace_id, poi_id, arrival_time=body["arrival_time"], party_size=int(body["party_size"]))
        if status["available_tables"] <= 0 or not status["reservation_available"]:
            raise self._execution_error(ErrorCode.NO_TABLE_AVAILABLE, "No available table.", "原餐厅当前已满，我会尝试为你切换到备选餐厅。", debug, failure_id)
        data = {
            "reservation_id": self._venue_bound_id("mock_reservation", poi, body["plan_id"], body["action_id"], body["arrival_time"], body["party_size"]),
            "reservation_type": "reservation",
            "poi_id": poi_id,
            "poi_name": poi.get("name"),
            "venue_snapshot": self._venue_snapshot(poi),
            "plan_id": body["plan_id"],
            "action_id": body["action_id"],
            "party_size": int(body["party_size"]),
            "arrival_time": body["arrival_time"],
            "available_tables_before": status.get("available_tables"),
            "queue_minutes": status.get("queue_minutes"),
            "reservation_expires_at": status.get("expire_at"),
            "status": "success",
            "display_text": f"Mock订座：{poi.get('name')}，{self._time_label(body['arrival_time'])}，{int(body['party_size'])}人，余{status.get('available_tables')}桌",
            "mock_only": True,
            "created_at": iso_now(),
        }
        self._record_execution(trace_id, "reserve_restaurant", data)
        self._log_tool(trace_id, "reserve_restaurant", {"poi_id": poi_id, "status": "success"})
        return data

    def _order_once(self, trace_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._require_fields(body, ["plan_id", "action_id", "items"])
        if not isinstance(body.get("items"), list) or not body["items"]:
            raise AppError(ErrorCode.BAD_REQUEST, "items must be a non-empty list.", "请求参数不完整，请检查后重试。", 400, True)
        poi = self._require_poi(str(body["poi_id"])) if body.get("poi_id") else None
        items = copy.deepcopy(body["items"])
        if poi:
            for item in items:
                if isinstance(item, dict):
                    item.setdefault("amount", poi.get("price_per_person"))
        data = {
            "order_id": self._venue_bound_id("mock_order", poi, body["plan_id"], body["action_id"], json.dumps(items, sort_keys=True, ensure_ascii=False)) if poi else new_id("mock_order"),
            "order_status": "created",
            "poi_id": poi.get("poi_id") if poi else body.get("poi_id"),
            "poi_name": poi.get("name") if poi else None,
            "venue_snapshot": self._venue_snapshot(poi) if poi else None,
            "items": items,
            "delivery_target": body.get("delivery_target"),
            "service_time": body.get("service_time"),
            "display_text": f"Mock订单：{poi.get('name')} 已生成" if poi else "Mock订单号已生成",
            "mock_only": True,
            "created_at": iso_now(),
        }
        self._record_execution(trace_id, "order_item", data)
        self._log_tool(trace_id, "order_item", {"status": "success"})
        return data

    def _message_once(self, trace_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self._require_fields(body, ["plan_id", "action_id", "channel", "content"])
        data = {
            "message_id": self._message_bound_id(body),
            "delivery_status": "mock_generated",
            "channel": body.get("channel"),
            "recipient_type": body.get("recipient_type"),
            "display_text": "模拟消息已生成",
            "mock_only": True,
            "created_at": iso_now(),
        }
        self._record_execution(trace_id, "send_message", data)
        self._log_tool(trace_id, "send_message", {"channel": body.get("channel"), "status": "success"})
        return data

    def _execute_with_idempotency(
        self,
        trace_id: str,
        idempotency_key: str,
        tool_name: str,
        poi_id: Optional[str],
        body: Dict[str, Any],
        execute_once,
    ) -> Dict[str, Any]:
        store = self.store.read(self.IDEMPOTENCY_FILE, {"version": "v0.1", "items": []})
        request_hash = self._request_hash(tool_name, poi_id, body)
        existing = next((item for item in store.get("items", []) if item.get("idempotency_key") == idempotency_key), None)
        if existing:
            if existing.get("request_hash") != request_hash:
                raise AppError(ErrorCode.IDEMPOTENCY_CONFLICT, "idempotency key was reused for a different request.", "请勿重复提交，刷新后再试。", 409, True)
            if existing.get("success"):
                return copy.deepcopy(existing["response"])
            error = existing.get("error") or {}
            raise AppError(
                ErrorCode(error.get("code", ErrorCode.INTERNAL_ERROR.value)),
                error.get("message", "idempotent failure replay."),
                error.get("user_message", "系统执行异常，请重试。"),
                int(error.get("status_code", 400)),
                bool(error.get("recoverable", True)),
                error.get("details", {}),
            )
        try:
            response = execute_once()
        except AppError as exc:
            store.setdefault("items", []).append(self._idempotency_record(idempotency_key, trace_id, tool_name, body, request_hash, None, exc))
            self.store.write(self.IDEMPOTENCY_FILE, store)
            raise
        store.setdefault("items", []).append(self._idempotency_record(idempotency_key, trace_id, tool_name, body, request_hash, response, None))
        self.store.write(self.IDEMPOTENCY_FILE, store)
        return response

    def _idempotency_record(
        self,
        idempotency_key: str,
        trace_id: str,
        tool_name: str,
        body: Dict[str, Any],
        request_hash: str,
        response: Optional[Dict[str, Any]],
        error: Optional[AppError],
    ) -> Dict[str, Any]:
        record = {
            "idempotency_key": idempotency_key,
            "plan_id": body.get("plan_id"),
            "action_id": body.get("action_id"),
            "tool_name": tool_name,
            "request_hash": request_hash,
            "trace_id": trace_id,
            "created_at": iso_now(),
            "success": error is None,
        }
        if response is not None:
            record["response"] = response
        if error is not None:
            record["error"] = {
                "code": error.code.value,
                "message": error.message,
                "user_message": error.user_message,
                "recoverable": error.recoverable,
                "status_code": error.status_code,
                "details": error.details,
            }
        return record

    def _request_hash(self, tool_name: str, poi_id: Optional[str], body: Dict[str, Any]) -> str:
        payload = {"tool_name": tool_name, "poi_id": poi_id, "body": body}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _require_execution_key(self, idempotency_key: Optional[str], body: Dict[str, Any]) -> None:
        if not idempotency_key:
            raise AppError(ErrorCode.BAD_REQUEST, "X-Idempotency-Key is required for execution APIs.", "请勿重复提交，刷新后再试。", 400, True)
        body_key = body.get("idempotency_key")
        if body_key is not None and body_key != idempotency_key:
            raise AppError(ErrorCode.BAD_REQUEST, "body.idempotency_key must match X-Idempotency-Key.", "请求参数不完整，请检查后重试。", 400, True)

    def _assert_window_open(self, body: Dict[str, Any]) -> None:
        expire_at = body.get("executable_window_expire_at") or body.get("expire_at")
        if expire_at:
            expire_dt = self._parse_dt(expire_at)
            now = self.clock.now()
            if expire_dt.tzinfo is not None:
                now = now.astimezone(expire_dt.tzinfo)
            if expire_dt <= now:
                raise AppError(
                    ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED,
                    "plan executable window expired.",
                    "当前窗口已过期，需要重新检查。",
                    409,
                    True,
                )
        failure_id = body.get("failure_scenario_id")
        if self._failure_matches(failure_id, None, None, ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED):
            raise AppError(
                ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED,
                "plan executable window expired.",
                "当前窗口已过期，需要重新检查。",
                409,
                True,
                self._failure_summary(failure_id) if body.get("debug") else {},
            )

    def _execution_error(
        self,
        code: ErrorCode,
        message: str,
        user_message: str,
        debug: bool,
        failure_scenario_id: Optional[str],
    ) -> AppError:
        details = self._failure_summary(failure_scenario_id) if debug and failure_scenario_id else {}
        return AppError(code, message, user_message, 409 if code == ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED else 400, True, details)

    def _failure_matches(self, failure_scenario_id: Optional[str], tool_name: Optional[str], poi_id: Optional[str], code: ErrorCode) -> bool:
        if not failure_scenario_id:
            return False
        scenario = self._failure_scenario(failure_scenario_id)
        if not scenario or not scenario.get("enabled"):
            return False
        if scenario.get("error_code") != code.value:
            return False
        trigger = scenario.get("trigger", {})
        if tool_name and trigger.get("path") != EXECUTION_PATHS[tool_name]:
            return False
        if poi_id and trigger.get("poi_id") and trigger.get("poi_id") != poi_id:
            return False
        return True

    def _failure_scenario(self, failure_scenario_id: Optional[str]) -> Optional[Dict[str, Any]]:
        scenarios = self.store.read(MOCK_FAILURE_SCENARIOS_PATH, {"scenarios": []}).get("scenarios", [])
        return next((item for item in scenarios if item.get("failure_scenario_id") == failure_scenario_id), None)

    def _failure_summary(self, failure_scenario_id: Optional[str]) -> Dict[str, Any]:
        scenario = self._failure_scenario(failure_scenario_id)
        if not scenario:
            return {}
        trigger = scenario.get("trigger", {})
        return {
            "failure_summary": {
                "error_code": scenario.get("error_code"),
                "trigger_path": trigger.get("path"),
                "poi_id": trigger.get("poi_id"),
                "visible_to_user": bool(scenario.get("visible_to_user", False)),
            }
        }

    def _base_status(
        self,
        poi: Dict[str, Any],
        *,
        when: Optional[str] = None,
        party_size: Optional[int] = None,
        scenario: Optional[str] = None,
    ) -> Dict[str, Any]:
        poi_id = str(poi.get("poi_id"))
        statuses = self.store.read(MOCK_STATUS_PATH, {"statuses": {}}).get("statuses", {})
        entry = statuses.get(poi_id)
        if entry and "query_status" in entry:
            return copy.deepcopy(entry["query_status"])
        return self.status_engine.generate(poi, when, party_size, scenario)

    def _generic_status_from_base(self, status: Dict[str, Any]) -> Dict[str, Any]:
        status.setdefault("available", True)
        status.setdefault("available_tables", None)
        status.setdefault("queue_minutes", None)
        status.setdefault("ticket_available", None)
        status.setdefault("remaining_tickets", None)
        status.setdefault("booking_available", None)
        status.setdefault("reservation_available", None)
        return status

    def _activity_status_from_base(
        self,
        status: Dict[str, Any],
        poi_id: str,
        party_size: Optional[int],
        when: Optional[str] = None,
    ) -> Dict[str, Any]:
        slot = self._slot_for_time("activity_slots", poi_id, when) if when else self._first_slot("activity_slots", poi_id)
        if slot:
            remaining = int(slot.get("remaining_tickets", status.get("remaining_tickets") or 0))
            status["remaining_tickets"] = remaining
            status["ticket_available"] = remaining >= int(party_size or 1)
            status["booking_available"] = bool(slot.get("booking_available", True)) and status["ticket_available"]
        status["available"] = bool(status.get("available", True)) and bool(status.get("booking_available", True))
        status.setdefault("available_tables", None)
        status.setdefault("reservation_available", None)
        if not status["available"]:
            status["risk_level"] = "blocking"
        return status

    def _restaurant_status_from_base(
        self,
        status: Dict[str, Any],
        poi_id: str,
        party_size: Optional[int],
        arrival_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        slot = self._slot_for_time("restaurant_slots", poi_id, arrival_time) or self._first_slot("restaurant_slots", poi_id)
        available_tables = int(status.get("available_tables") or 0)
        if slot:
            available_tables = max(0, int(slot.get("base_tables", 0)) - int(slot.get("reserved_tables", 0)))
            if party_size is not None and int(party_size) > int(slot.get("max_party_size", 0)):
                available_tables = 0
            if slot.get("queue_minutes") is not None:
                status["queue_minutes"] = int(slot.get("queue_minutes") or 0)
        status["available_tables"] = available_tables
        status["reservation_available"] = available_tables > 0
        status["available"] = bool(status.get("available", True)) and available_tables > 0
        status.setdefault("ticket_available", None)
        status.setdefault("remaining_tickets", None)
        status.setdefault("booking_available", None)
        if available_tables <= 0:
            status["risk_level"] = "blocking"
        elif available_tables == 1 or float(status.get("queue_minutes") or 0) >= 35:
            status["risk_level"] = "medium"
        else:
            status["risk_level"] = "low"
        status["status_message"] = f"Mock可用桌数{available_tables}桌，建议在可执行窗口内确认。"
        return status

    def _status_payload(self, poi_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "poi_id": poi_id,
            "available": bool(status.get("available", True)),
            "open_status": status.get("open_status", "open"),
            "available_tables": status.get("available_tables"),
            "queue_minutes": status.get("queue_minutes"),
            "ticket_available": status.get("ticket_available"),
            "remaining_tickets": status.get("remaining_tickets"),
            "booking_available": status.get("booking_available"),
            "reservation_available": status.get("reservation_available"),
            "risk_level": status.get("risk_level", "low"),
            "status_message": status.get("status_message", "Demo Mock状态快照，建议在可执行窗口内确认。"),
            "expire_at": status.get("expire_at"),
            "duration_minutes": status.get("duration_minutes"),
            "indoor": status.get("indoor"),
            "source": "mock_api",
            "mock_only": True,
            "updated_at": status.get("updated_at") or iso_now(),
        }
        for key in ("available_tables", "queue_minutes", "ticket_available", "remaining_tickets", "booking_available", "reservation_available"):
            payload.setdefault(key, None)
        return payload

    def _first_slot(self, collection: str, poi_id: str) -> Optional[Dict[str, Any]]:
        slots = self.store.read(MOCK_INVENTORY_PATH, {}).get(collection, [])
        override = next((slot for slot in slots if slot.get("poi_id") == poi_id), None)
        if override:
            return override
        poi = self._require_poi(poi_id)
        if collection == "restaurant_slots":
            return self.inventory_engine.restaurant_slot(poi, self.clock.iso_now(), None)
        if collection == "activity_slots":
            return self.inventory_engine.activity_slot(poi, self.clock.iso_now(), None)
        return None

    def _slot_for_time(self, collection: str, poi_id: str, when: Optional[str]) -> Optional[Dict[str, Any]]:
        if not when:
            return None
        target = self._parse_dt(when)
        slots = self.store.read(MOCK_INVENTORY_PATH, {}).get(collection, [])
        for slot in slots:
            if slot.get("poi_id") != poi_id:
                continue
            if self._parse_dt(slot["slot_start"]) <= target <= self._parse_dt(slot["slot_end"]):
                return slot
        poi = self._require_poi(poi_id)
        if collection == "restaurant_slots":
            return self.inventory_engine.restaurant_slot(poi, when, None)
        if collection == "activity_slots":
            return self.inventory_engine.activity_slot(poi, when, None)
        return None

    def _find_route(self, origin_poi_id: str, destination_poi_id: str, transport_mode: str) -> Optional[Dict[str, Any]]:
        routes = self.store.read(MOCK_ROUTES_PATH, {"routes": []}).get("routes", [])
        return next(
            (
                route
                for route in routes
                if route.get("origin_poi_id") == origin_poi_id
                and route.get("destination_poi_id") == destination_poi_id
                and route.get("transport_mode") == transport_mode
            ),
            None,
        )

    def _generate_route(self, origin_poi_id: str, destination_poi_id: str, transport_mode: str, departure_time: str) -> Dict[str, Any]:
        if transport_mode not in {"walk", "taxi", "bike", "drive", "mixed", "subway"}:
            raise AppError(
                ErrorCode.ROUTE_DELAY,
                "mock route is missing for requested pois and transport mode.",
                "当前路线估算异常，正在尝试更近方案。",
                409,
                True,
            )
        origin = self._require_poi(origin_poi_id)
        destination = self._require_poi(destination_poi_id)
        distance_km = self._distance_km(origin, destination)
        if distance_km is None:
            raise AppError(
                ErrorCode.ROUTE_DELAY,
                "mock route cannot be generated without coordinates.",
                "当前路线估算异常，正在尝试更近方案。",
                409,
                True,
            )
        duration_minutes = self._route_duration(distance_km, transport_mode, departure_time)
        traffic_level = self._traffic_level(transport_mode, departure_time)
        digest = self.seed_service.digest(origin_poi_id, destination_poi_id, transport_mode, self.clock.target_date(departure_time))[:10]
        return {
            "route_id": f"route_engine_{digest}",
            "origin_poi_id": origin_poi_id,
            "destination_poi_id": destination_poi_id,
            "transport_mode": transport_mode,
            "distance_km": round(distance_km, 2),
            "duration_minutes": duration_minutes,
            "traffic_level": traffic_level,
            "confidence": 0.78,
            "source": "mock_api",
            "updated_at": iso_now(),
        }

    def _distance_km(self, origin: Dict[str, Any], destination: Dict[str, Any]) -> Optional[float]:
        origin_loc = origin.get("location") or {}
        destination_loc = destination.get("location") or {}
        try:
            lat1 = math.radians(float(origin_loc["lat"]))
            lng1 = math.radians(float(origin_loc["lng"]))
            lat2 = math.radians(float(destination_loc["lat"]))
            lng2 = math.radians(float(destination_loc["lng"]))
        except (KeyError, TypeError, ValueError):
            return None
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return max(0.03, 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    def _route_duration(self, distance_km: float, transport_mode: str, departure_time: str) -> int:
        speeds = {
            "walk": 4.5,
            "bike": 12.0,
            "drive": 18.0,
            "taxi": 18.0,
            "mixed": 10.0,
            "subway": 20.0,
        }
        speed = speeds.get(transport_mode, 8.0)
        buffer = {"walk": 1, "bike": 2, "drive": 4, "taxi": 5, "mixed": 6, "subway": 8}.get(transport_mode, 3)
        multiplier = 1.0
        try:
            hour = self._parse_dt(departure_time).hour
            if transport_mode in {"drive", "taxi", "mixed"} and (8 <= hour <= 9 or 17 <= hour <= 20):
                multiplier = 1.35
        except AppError:
            pass
        return max(1, int(math.ceil(distance_km / speed * 60 * multiplier + buffer)))

    def _traffic_level(self, transport_mode: str, departure_time: str) -> str:
        if transport_mode in {"walk", "bike"}:
            return "smooth"
        try:
            hour = self._parse_dt(departure_time).hour
        except AppError:
            return "unknown"
        if 17 <= hour <= 20:
            return "medium"
        return "smooth"

    def _pois(self) -> List[Dict[str, Any]]:
        base = self.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        runtime = self.store.read(RUNTIME_ACTIVITY_POIS_PATH, {"pois": []}).get("pois", [])
        if not isinstance(base, list):
            base = []
        if not isinstance(runtime, list) or not runtime:
            return base
        seen = {str(item.get("poi_id")) for item in runtime if isinstance(item, dict) and item.get("poi_id")}
        return [item for item in runtime if isinstance(item, dict)] + [
            item for item in base if isinstance(item, dict) and str(item.get("poi_id")) not in seen
        ]

    def _require_poi(self, poi_id: str) -> Dict[str, Any]:
        poi = next((item for item in self._pois() if item.get("poi_id") == poi_id), None)
        if poi is None:
            raise AppError(ErrorCode.PLAN_STEP_POI_NOT_FOUND, f"POI not found: {poi_id}.", "当前地点数据缺失，换一个方案。", 404, True)
        return poi

    def _project_poi(self, item: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "poi_id",
            "name",
            "category",
            "sub_category",
            "tags",
            "location",
            "area",
            "address",
            "suitable_scenarios",
            "price_per_person",
            "rating",
            "opening_hours",
            "risk_tags",
            "mock_only",
            "created_at",
            "updated_at",
        }
        projected = {key: copy.deepcopy(value) for key, value in item.items() if key in allowed}
        projected["mock_only"] = True
        return projected

    def _normalize_area(self, area: Optional[str]) -> Optional[str]:
        if not area:
            return None
        return AREA_ALIASES.get(area, area)

    def _split_csv(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _limit(self, limit: int) -> int:
        return max(1, min(int(limit or 10), 100))

    def _page_info(self, count: int, limit: int) -> Dict[str, Any]:
        return {"page_size": self._limit(limit), "next_page_token": None, "has_more": False}

    def _require_fields(self, body: Dict[str, Any], fields: List[str]) -> None:
        missing = [field for field in fields if field not in body or body[field] in (None, "")]
        if missing:
            raise AppError(ErrorCode.BAD_REQUEST, f"missing required fields: {', '.join(missing)}.", "请求参数不完整，请检查后重试。", 400, True)

    def _parse_dt(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError(ErrorCode.BAD_REQUEST, "time fields must be ISO 8601.", "请求参数不完整，请检查后重试。", 400, True) from exc

    def _time_ranges_overlap(self, fixture_range: Dict[str, Any], start_time: str, end_time: str) -> bool:
        fixture_start = fixture_range.get("start_time")
        fixture_end = fixture_range.get("end_time")
        if not fixture_start or not fixture_end:
            return False
        target_start = self._parse_dt(start_time)
        target_end = self._parse_dt(end_time)
        return self._parse_dt(fixture_start) <= target_end and target_start <= self._parse_dt(fixture_end)

    def _record_execution(self, trace_id: str, tool_name: str, data: Dict[str, Any]) -> None:
        payload = self.store.read(self.EXECUTIONS_FILE, {"version": "v0.1", "executions": []})
        payload.setdefault("executions", []).append({"trace_id": trace_id, "tool_name": tool_name, "data": data, "created_at": iso_now()})
        self.store.write(self.EXECUTIONS_FILE, payload)

    def _venue_bound_id(self, prefix: str, poi: Dict[str, Any], *parts: Any) -> str:
        poi_id = str((poi or {}).get("poi_id") or "poi_unknown")
        digest = hashlib.sha256(
            json.dumps({"poi_id": poi_id, "parts": parts}, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:10]
        return f"{prefix}_{poi_id}_{digest}"

    def _message_bound_id(self, body: Dict[str, Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "plan_id": body.get("plan_id"),
                    "action_id": body.get("action_id"),
                    "channel": body.get("channel"),
                    "recipient_type": body.get("recipient_type"),
                    "content": body.get("content"),
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()[:10]
        return f"mock_msg_{digest}"

    def _venue_snapshot(self, poi: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "poi_id": poi.get("poi_id"),
            "name": poi.get("name"),
            "area": poi.get("area") or (poi.get("location") or {}).get("area"),
            "address": poi.get("address"),
            "category": poi.get("category"),
            "mock_only": True,
        }

    def _time_label(self, value: str) -> str:
        try:
            return self._parse_dt(value).strftime("%H:%M")
        except AppError:
            return str(value)

    def _log_tool(self, trace_id: str, tool_name: str, payload: Dict[str, Any]) -> None:
        if self.logger is None:
            return
        self.logger.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "MockAPIService",
            {"tool_name": tool_name, **payload},
            visible_to_user=True,
        )
