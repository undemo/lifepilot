from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import MOCK_POIS_PATH, MOCK_ROUTES_PATH, MOCK_STATUS_PATH
from app.core.ids import new_id
from app.core.time import iso_now, now_shanghai
from app.services.logging_service import LoggingService
from app.services.mock_api_service import MockAPIService
from app.storage.json_store import JsonFileStore


QUEUE_LIMITS = {
    "low": 10,
    "medium": 20,
    "high": 35,
}

NEARBY_DISTANCE_KM = {
    "nearby": 5,
    "medium": 10,
    "far_ok": 20,
}

CHECK_TO_RISK_TYPE = {
    "opening_hours": "opening_hours",
    "budget_constraint": "budget",
    "restaurant_capacity": "restaurant_capacity",
    "activity_ticket": "activity_ticket",
    "queue_time": "queue",
    "weather_risk": "weather",
    "distance_constraint": "route_delay",
    "time_feasibility": "route_delay",
    "tool_action_integrity": "participant_conflict",
    "executable_window": "route_delay",
}


class VerifierService:
    def __init__(
        self,
        store: JsonFileStore,
        logging_service: LoggingService,
        mock_api_service: MockAPIService,
    ) -> None:
        self.store = store
        self.logging_service = logging_service
        self.mock_api_service = mock_api_service

    def verify_plan_contract(self, plan: Dict[str, Any], reason: str = "verify") -> Dict[str, Any]:
        trace_id = plan.get("trace_id") or "trace_unavailable"
        plan_id = plan.get("plan_id")
        checks: List[Dict[str, Any]] = []
        risks: List[Dict[str, Any]] = []
        status_expiries: List[Tuple[str, str]] = []
        route_confidences: List[float] = []
        calculated_from: List[str] = []
        lockable_resources: List[str] = []

        poi_map = {poi.get("poi_id"): poi for poi in self._pois()}
        timeline = plan.get("timeline") or []
        actions = plan.get("tool_actions") or []
        action_map = {action.get("action_id"): action for action in actions}
        step_map = {step.get("step_id"): step for step in timeline}
        constraints = plan.get("constraints") or {}
        party_size = int(constraints.get("party_size") or 1)

        self._check_timeline(timeline, poi_map, plan.get("time_window") or {}, checks, risks)
        self._check_budget(plan, constraints, checks, risks)
        self._check_routes(timeline, constraints, checks, risks, route_confidences)
        self._check_tool_actions(plan, timeline, actions, action_map, step_map, poi_map, checks, risks)

        for step in timeline:
            step_type = step.get("type")
            poi_id = step.get("poi_id")
            if step_type == "restaurant" and poi_id:
                self._check_restaurant_step(trace_id, step, party_size, constraints, checks, risks, status_expiries, calculated_from, lockable_resources)
            elif step_type == "activity" and poi_id:
                self._check_activity_step(trace_id, step, party_size, checks, risks, status_expiries, calculated_from, lockable_resources)
            elif step_type in {"walk", "service"} and poi_id:
                self._check_generic_poi_step(trace_id, step, party_size, checks, risks, status_expiries, calculated_from)

        self._check_weather(trace_id, timeline, poi_map, constraints, checks, risks, calculated_from)
        executable_window = self._build_executable_window(
            plan,
            checks,
            risks,
            status_expiries,
            route_confidences,
            calculated_from,
            lockable_resources,
        )
        self._check_executable_window(executable_window, checks, risks)

        verifier_result = self._build_verifier_result(checks)
        if verifier_result["status"] == "warning" and not risks:
            risks.append(self._risk("memory_uncertain", "medium", "存在可执行性提示，建议保留备选方案。", mitigation="PlanB：确认前刷新状态或切换同区域备选。"))
            verifier_result["suggestions"].append("PlanB：确认前刷新状态或切换同区域备选。")
        if verifier_result["status"] == "warning" and not verifier_result["suggestions"]:
            verifier_result["suggestions"].append("PlanB：保留同区域、同预算的备选地点。")
        if verifier_result["status"] == "fail" and verifier_result["required_recovery"] and not verifier_result["suggestions"]:
            verifier_result["suggestions"].append("需要先进入Recovery或刷新状态，不能直接执行。")

        self.logging_service.log(
            trace_id,
            TraceEventType.VERIFIER_LOG,
            "VerifierService",
            {
                "user_visible_message": "可执行性检查完成。",
                "reason": reason,
                "status": verifier_result["status"],
                "failed_checks": verifier_result["failed_checks"],
                "warnings": verifier_result["warnings"],
                "risk_count": len(risks),
                "required_recovery": verifier_result["required_recovery"],
            },
            plan_id=plan_id,
            level="error" if verifier_result["status"] == "fail" else "warning" if verifier_result["status"] == "warning" else "info",
        )
        return {
            "verifier_result": verifier_result,
            "executable_window": executable_window,
            "risks": risks,
        }

    def can_enter_executor(self, plan: Dict[str, Any]) -> Tuple[bool, Optional[ErrorCode], str, bool, Dict[str, Any]]:
        verifier = plan.get("verifier_result") or {}
        status = verifier.get("status")
        if status not in {"pass", "warning"}:
            recoverable = bool(verifier.get("required_recovery"))
            return (
                False,
                ErrorCode.VERIFIER_RESULT_INVALID,
                "PlanContract verifier_result does not allow execution.",
                recoverable,
                {"failed_checks": verifier.get("failed_checks", []), "warnings": verifier.get("warnings", [])},
            )
        for action in plan.get("tool_actions", []):
            if action.get("status") == "pending" and not action.get("idempotency_key"):
                return False, ErrorCode.TOOL_ACTION_INVALID, "ToolAction.idempotency_key is required.", True, {"action_id": action.get("action_id")}
        return True, None, "", True, {}

    def _check_timeline(
        self,
        timeline: List[Dict[str, Any]],
        poi_map: Dict[str, Dict[str, Any]],
        time_window: Dict[str, Any],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
    ) -> None:
        if not timeline:
            self._add_check(checks, risks, "time_feasibility", "fail", "timeline不能为空。", "blocking", False)
            return

        orders = [step.get("order") for step in timeline]
        if orders != list(range(1, len(timeline) + 1)):
            self._add_check(checks, risks, "time_feasibility", "fail", "timeline order必须从1连续。", "blocking", True, "regenerate_timeline")

        window_start = self._parse_dt(time_window.get("start_time"))
        window_end = self._parse_dt(time_window.get("end_time"))
        previous_end: Optional[datetime] = None
        for step in sorted(timeline, key=lambda item: item.get("order") or 0):
            step_id = step.get("step_id")
            start = self._parse_dt(step.get("start_time"))
            end = self._parse_dt(step.get("end_time"))
            if not start or not end or start >= end:
                self._add_check(checks, risks, "time_feasibility", "fail", "节点开始/结束时间非法。", "blocking", True, "regenerate_timeline", step_id, step.get("poi_id"))
                continue
            if previous_end and start < previous_end:
                self._add_check(checks, risks, "time_feasibility", "fail", "timeline时间倒序或节点重叠。", "blocking", True, "regenerate_timeline", step_id, step.get("poi_id"))
            if window_start and start < window_start:
                self._add_check(checks, risks, "time_feasibility", "fail", "timeline早于用户时间窗口。", "blocking", True, "regenerate_timeline", step_id, step.get("poi_id"))
            if window_end and end > window_end:
                self._add_check(checks, risks, "time_feasibility", "fail", "timeline超过用户时间窗口。", "blocking", True, "regenerate_timeline", step_id, step.get("poi_id"))
            previous_end = end

            if step.get("type") in {"activity", "restaurant", "walk", "service"}:
                poi_id = step.get("poi_id")
                if not poi_id or poi_id not in poi_map:
                    self._add_check(checks, risks, "tool_action_integrity", "fail", "PlanStep引用的poi_id不存在。", "blocking", True, "replace_poi", step_id, poi_id)
            if step.get("type") == "transport":
                if not step.get("from_poi_id") or not step.get("to_poi_id"):
                    self._add_check(checks, risks, "time_feasibility", "fail", "transport节点缺少from_poi_id或to_poi_id。", "blocking", True, "estimate_route", step_id)
                for poi_key in ("from_poi_id", "to_poi_id"):
                    poi_id = step.get(poi_key)
                    if poi_id and poi_id not in poi_map:
                        self._add_check(checks, risks, "tool_action_integrity", "fail", f"transport节点{poi_key}不存在。", "blocking", True, "replace_poi", step_id, poi_id)

        if not any(check["name"] == "time_feasibility" for check in checks):
            checks.append(self._check("time_feasibility", "pass", "timeline非空、order连续且时间不重叠。", "low", False))

    def _check_budget(self, plan: Dict[str, Any], constraints: Dict[str, Any], checks: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> None:
        budget = plan.get("budget") or {}
        estimated_total = float(budget.get("estimated_total") or 0)
        price_per_person = budget.get("price_per_person")
        party_size = int(constraints.get("party_size") or 1)
        if price_per_person is None and party_size > 0:
            price_per_person = estimated_total / party_size
        budget_max = constraints.get("budget_max")
        budget_max_per_person = constraints.get("budget_max_per_person")

        if budget_max is not None and estimated_total > float(budget_max):
            self._add_check(checks, risks, "budget_constraint", "fail", "预算总额超过budget_max。", "high", True, "budget_exceeded")
            return
        if budget_max_per_person is not None and float(price_per_person or 0) > float(budget_max_per_person):
            self._add_check(checks, risks, "budget_constraint", "fail", "人均预算超过budget_max_per_person。", "high", True, "budget_exceeded")
            return
        checks.append(self._check("budget_constraint", "pass", "预算未超过约束。", "low", False))

    def _check_routes(
        self,
        timeline: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        route_confidences: List[float],
    ) -> None:
        route_fail = False
        distance_warning = False
        max_distance = NEARBY_DISTANCE_KM.get(str(constraints.get("distance_preference") or "nearby"), 10)
        for step in timeline:
            route = step.get("estimated_route")
            if step.get("type") == "transport":
                if not route:
                    route_fail = True
                    self._add_check(checks, risks, "distance_constraint", "fail", "transport节点缺少RouteEstimate。", "blocking", True, "estimate_route", step.get("step_id"))
                    continue
            if not route:
                continue
            if route.get("source") != "mock_api":
                route_fail = True
                self._add_check(checks, risks, "distance_constraint", "fail", 'RouteEstimate.source必须为"mock_api"。', "blocking", True, "estimate_route", step.get("step_id"))
                continue
            if not self._route_exists(route):
                route_fail = True
                self._add_check(checks, risks, "distance_constraint", "fail", "RouteEstimate未在mock_routes.json中找到对应路线。", "blocking", True, "estimate_route", step.get("step_id"))
                continue
            route_confidences.append(float(route.get("confidence") or 0.7))
            if float(route.get("distance_km") or 0) > max_distance:
                distance_warning = True
                self._add_check(checks, risks, "distance_constraint", "warning", "路线距离超过当前距离偏好。", "medium", True, "route_delay", step.get("step_id"))
            if float(step.get("duration_minutes") or 0) and float(route.get("duration_minutes") or 0) > float(step.get("duration_minutes") or 0) + 5:
                self._add_check(checks, risks, "time_feasibility", "fail", "RouteEstimate时长超过transport节点时长。", "blocking", True, "regenerate_timeline", step.get("step_id"))
        if not route_fail and not distance_warning:
            checks.append(self._check("distance_constraint", "pass", "路线估计存在且来自mock_api。", "low", False))

    def _check_tool_actions(
        self,
        plan: Dict[str, Any],
        timeline: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        action_map: Dict[str, Dict[str, Any]],
        step_map: Dict[str, Dict[str, Any]],
        poi_map: Dict[str, Dict[str, Any]],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
    ) -> None:
        failed = False
        for step in timeline:
            related_action_ids = step.get("related_tool_action_ids") or []
            for action_id in related_action_ids:
                if action_id not in action_map:
                    failed = True
                    self._add_check(checks, risks, "tool_action_integrity", "fail", "PlanStep.related_tool_action_ids引用不存在。", "blocking", True, "rebuild_tool_actions", step.get("step_id"), step.get("poi_id"))
            if step.get("type") == "restaurant" and step.get("reservation_required"):
                if not self._has_related_action(step, action_map, "reserve_restaurant"):
                    failed = True
                    self._add_check(checks, risks, "tool_action_integrity", "fail", "需要订座的restaurant节点缺少reserve_restaurant动作。", "blocking", True, "rebuild_tool_actions", step.get("step_id"), step.get("poi_id"))
            if step.get("type") == "activity" and step.get("booking_required"):
                if not self._has_related_action(step, action_map, "book_activity"):
                    failed = True
                    self._add_check(checks, risks, "tool_action_integrity", "fail", "需要预约的activity节点缺少book_activity动作。", "blocking", True, "rebuild_tool_actions", step.get("step_id"), step.get("poi_id"))

        for action in actions:
            missing = [field for field in ("action_id", "plan_id", "step_id", "type", "payload", "status", "retry_count", "idempotency_key", "user_visible", "created_at", "updated_at") if field not in action or action.get(field) in (None, "")]
            if missing:
                failed = True
                self._add_check(checks, risks, "tool_action_integrity", "fail", f"ToolAction缺少字段：{', '.join(missing)}。", "blocking", True, "rebuild_tool_actions", action.get("step_id"), action.get("target_poi_id"))
            if action.get("plan_id") != plan.get("plan_id"):
                failed = True
                self._add_check(checks, risks, "tool_action_integrity", "fail", "ToolAction.plan_id与PlanContract不一致。", "blocking", True, "rebuild_tool_actions", action.get("step_id"), action.get("target_poi_id"))
            if action.get("step_id") not in step_map:
                failed = True
                self._add_check(checks, risks, "tool_action_integrity", "fail", "ToolAction.step_id不存在。", "blocking", True, "rebuild_tool_actions", action.get("step_id"), action.get("target_poi_id"))
            target_poi_id = action.get("target_poi_id")
            if target_poi_id and target_poi_id not in poi_map:
                failed = True
                self._add_check(checks, risks, "tool_action_integrity", "fail", "ToolAction.target_poi_id不存在。", "blocking", True, "replace_poi", action.get("step_id"), target_poi_id)
            if not self._payload_complete(action):
                failed = True
                self._add_check(checks, risks, "tool_action_integrity", "fail", "ToolAction.payload不完整。", "blocking", True, "rebuild_tool_actions", action.get("step_id"), target_poi_id)
        if not failed:
            checks.append(self._check("tool_action_integrity", "pass", "ToolAction完整且引用有效。", "low", False))

    def _check_restaurant_step(
        self,
        trace_id: str,
        step: Dict[str, Any],
        party_size: int,
        constraints: Dict[str, Any],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        status_expiries: List[Tuple[str, str]],
        calculated_from: List[str],
        lockable_resources: List[str],
    ) -> None:
        poi_id = step["poi_id"]
        try:
            status = self.mock_api_service.restaurant_status(trace_id, poi_id, arrival_time=step["start_time"], party_size=party_size)
            calculated_from.append("restaurant_status")
            if status.get("expire_at"):
                status_expiries.append((poi_id, status["expire_at"]))
            if status.get("source") != "mock_api":
                self._add_check(checks, risks, "restaurant_capacity", "fail", "RestaurantStatus必须来自mock_api。", "blocking", True, "refresh_status", step.get("step_id"), poi_id)
            self._check_open_status(status, step, checks, risks)
            available_tables = int(status.get("available_tables") or 0)
            if available_tables <= 0 or not status.get("reservation_available"):
                self._add_check(checks, risks, "restaurant_capacity", "fail", "餐厅当前无可订桌位。", "blocking", True, "restaurant_full", step.get("step_id"), poi_id)
            elif status.get("risk_level") in {"medium", "high"} or available_tables <= 1:
                self._add_check(checks, risks, "restaurant_capacity", "warning", "餐厅桌位偏紧，需展示风险和PlanB。", "medium", True, "restaurant_full", step.get("step_id"), poi_id)
            else:
                checks.append(self._check("restaurant_capacity", "pass", "餐厅有位且可订。", "low", False, step.get("step_id"), poi_id))
            self._check_queue_time(status, step, constraints, checks, risks)
            lockable_resources.append("restaurant_reservation")
        except Exception as exc:
            self._add_check(checks, risks, "restaurant_capacity", "fail", f"餐厅状态查询失败：{self._error_code(exc)}。", "blocking", True, "refresh_status", step.get("step_id"), poi_id)

    def _check_activity_step(
        self,
        trace_id: str,
        step: Dict[str, Any],
        party_size: int,
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        status_expiries: List[Tuple[str, str]],
        calculated_from: List[str],
        lockable_resources: List[str],
    ) -> None:
        poi_id = step["poi_id"]
        try:
            status = self.mock_api_service.poi_status(trace_id, poi_id, party_size=party_size, when=step.get("start_time"))
            calculated_from.append("poi_status")
            if status.get("expire_at"):
                status_expiries.append((poi_id, status["expire_at"]))
            if status.get("source") != "mock_api":
                self._add_check(checks, risks, "activity_ticket", "fail", "POIStatus必须来自mock_api。", "blocking", True, "refresh_status", step.get("step_id"), poi_id)
            self._check_open_status(status, step, checks, risks)
            if step.get("booking_required"):
                remaining = status.get("remaining_tickets")
                enough_tickets = remaining is None or int(remaining) >= party_size
                if not status.get("booking_available") or not status.get("ticket_available") or not enough_tickets:
                    self._add_check(checks, risks, "activity_ticket", "fail", "活动不可预约或余票不足。", "blocking", True, "activity_full", step.get("step_id"), poi_id)
                else:
                    checks.append(self._check("activity_ticket", "pass", "活动可预约且余票足够。", "low", False, step.get("step_id"), poi_id))
                lockable_resources.append("activity_ticket")
            elif status.get("available"):
                checks.append(self._check("activity_ticket", "pass", "活动状态可用且无需预约。", "low", False, step.get("step_id"), poi_id))
            else:
                self._add_check(checks, risks, "activity_ticket", "fail", "活动当前不可用。", "blocking", True, "activity_full", step.get("step_id"), poi_id)
        except Exception as exc:
            self._add_check(checks, risks, "activity_ticket", "fail", f"活动状态查询失败：{self._error_code(exc)}。", "blocking", True, "refresh_status", step.get("step_id"), poi_id)

    def _check_generic_poi_step(
        self,
        trace_id: str,
        step: Dict[str, Any],
        party_size: int,
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        status_expiries: List[Tuple[str, str]],
        calculated_from: List[str],
    ) -> None:
        try:
            status = self.mock_api_service.poi_status(trace_id, step["poi_id"], party_size=party_size, when=step.get("start_time"))
            calculated_from.append("poi_status")
            if status.get("expire_at"):
                status_expiries.append((step["poi_id"], status["expire_at"]))
            if status.get("source") != "mock_api":
                self._add_check(checks, risks, "opening_hours", "fail", "POIStatus必须来自mock_api。", "blocking", True, "refresh_status", step.get("step_id"), step.get("poi_id"))
            self._check_open_status(status, step, checks, risks)
        except Exception as exc:
            self._add_check(checks, risks, "opening_hours", "warning", f"POI状态缺失，降级为风险提示：{self._error_code(exc)}。", "medium", True, "refresh_status", step.get("step_id"), step.get("poi_id"))

    def _check_open_status(self, status: Dict[str, Any], step: Dict[str, Any], checks: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> None:
        open_status = status.get("open_status")
        if open_status == "closed":
            self._add_check(checks, risks, "opening_hours", "fail", "POI当前未营业。", "blocking", True, "replace_poi", step.get("step_id"), step.get("poi_id"))
        elif open_status in {"closing_soon", "unknown"}:
            self._add_check(checks, risks, "opening_hours", "warning", "POI营业状态存在不确定性。", "medium", True, "refresh_status", step.get("step_id"), step.get("poi_id"))
        else:
            checks.append(self._check("opening_hours", "pass", "POI当前营业。", "low", False, step.get("step_id"), step.get("poi_id")))

    def _check_queue_time(self, status: Dict[str, Any], step: Dict[str, Any], constraints: Dict[str, Any], checks: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> None:
        queue_minutes = status.get("queue_minutes")
        if queue_minutes is None:
            checks.append(self._check("queue_time", "pass", "无排队风险。", "low", False, step.get("step_id"), step.get("poi_id")))
            return
        tolerance = str(constraints.get("queue_tolerance") or "medium")
        limit = QUEUE_LIMITS.get(tolerance, QUEUE_LIMITS["medium"])
        queue = float(queue_minutes)
        if queue > limit * 1.5:
            status = "warning" if step.get("reservation_required") else "fail"
            level = "medium" if status == "warning" else "high"
            self._add_check(checks, risks, "queue_time", status, "排队时间超过queue_tolerance。", level, True, "restaurant_full", step.get("step_id"), step.get("poi_id"))
        elif queue > limit:
            self._add_check(checks, risks, "queue_time", "warning", "排队时间超过偏好，需展示PlanB。", "medium", True, "restaurant_full", step.get("step_id"), step.get("poi_id"))
        else:
            checks.append(self._check("queue_time", "pass", "排队时间在容忍范围内。", "low", False, step.get("step_id"), step.get("poi_id")))

    def _check_weather(
        self,
        trace_id: str,
        timeline: List[Dict[str, Any]],
        poi_map: Dict[str, Dict[str, Any]],
        constraints: Dict[str, Any],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        calculated_from: List[str],
    ) -> None:
        if constraints.get("weather_sensitive") is False:
            checks.append(self._check("weather_risk", "pass", "当前计划未标记天气敏感。", "low", False))
            return

        outdoor_steps = [step for step in timeline if self._is_outdoor_step(step, poi_map)]
        if not outdoor_steps:
            checks.append(self._check("weather_risk", "pass", "无明显户外节点。", "low", False))
            return

        checked_area_ranges = set()
        weather_failed = False
        weather_warned = False
        for step in outdoor_steps:
            poi = poi_map.get(step.get("poi_id")) or {}
            area = poi.get("area") or (poi.get("location") or {}).get("area")
            if not area:
                self._add_check(checks, risks, "weather_risk", "warning", "户外节点缺少区域，无法确认天气。", "medium", True, "refresh_weather", step.get("step_id"), step.get("poi_id"))
                weather_warned = True
                continue
            key = (area, step.get("start_time"), step.get("end_time"))
            if key in checked_area_ranges:
                continue
            checked_area_ranges.add(key)
            try:
                weather = self.mock_api_service.weather(trace_id, area=area, start_time=step["start_time"], end_time=step["end_time"])
                calculated_from.append("weather_status")
            except Exception as exc:
                self._add_check(checks, risks, "weather_risk", "warning", f"天气状态缺失：{self._error_code(exc)}。", "medium", True, "refresh_weather", step.get("step_id"), step.get("poi_id"))
                weather_warned = True
                continue
            if weather.get("source") != "mock_api":
                self._add_check(checks, risks, "weather_risk", "fail", "WeatherStatus必须来自mock_api。", "blocking", True, "refresh_weather", step.get("step_id"), step.get("poi_id"))
                weather_failed = True
                continue
            rain_probability = float(weather.get("rain_probability") or 0)
            outdoor_risk_level = weather.get("outdoor_risk_level")
            if rain_probability >= 0.6 or outdoor_risk_level in {"high", "blocking"}:
                self._add_check(checks, risks, "weather_risk", "fail", "天气会影响户外活动。", "high", True, weather.get("suggested_recovery") or "weather_rain", step.get("step_id"), step.get("poi_id"))
                weather_failed = True
            elif rain_probability >= 0.4 or outdoor_risk_level == "medium":
                self._add_check(checks, risks, "weather_risk", "warning", "天气对户外活动有中等风险。", "medium", True, weather.get("suggested_recovery") or "weather_rain", step.get("step_id"), step.get("poi_id"))
                weather_warned = True
        if not weather_failed and not weather_warned:
            checks.append(self._check("weather_risk", "pass", "天气不影响户外活动。", "low", False))

    def _build_executable_window(
        self,
        plan: Dict[str, Any],
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        status_expiries: List[Tuple[str, str]],
        route_confidences: List[float],
        calculated_from: List[str],
        lockable_resources: List[str],
    ) -> Dict[str, Any]:
        current = plan.get("executable_window") or {}
        parsed_expiries = [
            (poi_id, effective_dt, effective_iso)
            for poi_id, expire_at in status_expiries
            for effective_dt, effective_iso in [self._effective_expiry(poi_id, expire_at)]
            if effective_dt
        ]
        if parsed_expiries:
            source_poi_id, expire_dt, expire_at = min(parsed_expiries, key=lambda item: item[1])
        else:
            source_poi_id = None
            expire_at = current.get("expire_at")
            expire_dt = self._parse_dt(expire_at)

        now = now_shanghai()
        window_minutes = 0
        if expire_dt:
            window_minutes = max(0, int((expire_dt - now).total_seconds() // 60))

        status = self._status_from_checks(checks)
        base_confidence = 0.86 if status == "pass" else 0.68 if status == "warning" else 0.35
        if route_confidences:
            base_confidence = min(base_confidence, min(route_confidences))
        if expire_dt and expire_dt <= now:
            base_confidence = 0
        risk_factors = sorted({risk["type"] for risk in risks})
        reasons = self._window_reasons(status, status_expiries, route_confidences, source_poi_id)
        calculated = sorted(set(calculated_from or current.get("calculated_from") or ["rule_generated"]))
        if "verifier" not in calculated:
            calculated.append("verifier")
        return {
            "window_minutes": window_minutes,
            "confidence": round(max(0, min(1, base_confidence)), 2),
            "expire_at": expire_at or iso_now(),
            "reasons": reasons,
            "risk_factors": risk_factors,
            "lockable_resources": sorted(set(lockable_resources or current.get("lockable_resources") or [])),
            "calculated_from": calculated,
            "display_message": self._window_message(status, window_minutes),
        }

    def _check_executable_window(self, window: Dict[str, Any], checks: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> None:
        missing = [field for field in ("expire_at", "window_minutes", "confidence", "reasons") if field not in window or window.get(field) in (None, "")]
        if missing:
            self._add_check(checks, risks, "executable_window", "fail", f"ExecutableWindow缺少字段：{', '.join(missing)}。", "blocking", True, "refresh_window")
            return
        expire_dt = self._parse_dt(window.get("expire_at"))
        if expire_dt and expire_dt <= now_shanghai():
            self._add_check(checks, risks, "executable_window", "fail", "ExecutableWindow已过期。", "blocking", True, "refresh_window")
            return
        checks.append(self._check("executable_window", "pass", "ExecutableWindow字段完整且未过期。", "low", False))

    def _build_verifier_result(self, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        status = self._status_from_checks(checks)
        failed_checks = sorted({check["name"] for check in checks if check["status"] == "fail"})
        warnings = sorted({check["name"] for check in checks if check["status"] == "warning"})
        fail_count = sum(1 for check in checks if check["status"] == "fail")
        warning_count = sum(1 for check in checks if check["status"] == "warning")
        score = max(0, 1 - fail_count * 0.2 - warning_count * 0.08)
        required_recovery = any(check["status"] == "fail" and check["recoverable"] for check in checks)
        suggestions = []
        for check in checks:
            if check["status"] in {"warning", "fail"} and check.get("recovery_hint"):
                suggestions.append(self._recovery_text(check.get("recovery_hint")))
        return {
            "status": status,
            "score": round(score, 2),
            "checks": checks,
            "failed_checks": failed_checks,
            "warnings": warnings,
            "required_recovery": required_recovery,
            "suggestions": sorted(set(suggestions)),
            "created_at": iso_now(),
        }

    def _add_check(
        self,
        checks: List[Dict[str, Any]],
        risks: List[Dict[str, Any]],
        name: str,
        status: str,
        message: str,
        severity: str,
        recoverable: bool,
        recovery_hint: Optional[str] = None,
        related_step_id: Optional[str] = None,
        related_poi_id: Optional[str] = None,
    ) -> None:
        checks.append(self._check(name, status, message, severity, recoverable, related_step_id, related_poi_id, recovery_hint))
        if status in {"warning", "fail"}:
            risk_level = "blocking" if status == "fail" and severity == "blocking" else severity
            risks.append(
                self._risk(
                    CHECK_TO_RISK_TYPE.get(name, name),
                    risk_level,
                    message,
                    related_step_id=related_step_id,
                    related_poi_id=related_poi_id,
                    mitigation=self._recovery_text(recovery_hint),
                )
            )

    def _check(
        self,
        name: str,
        status: str,
        message: str,
        severity: str,
        recoverable: bool,
        related_step_id: Optional[str] = None,
        related_poi_id: Optional[str] = None,
        recovery_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "name": name,
            "status": status,
            "score": 1 if status == "pass" else 0.65 if status == "warning" else 0.2,
            "message": message,
            "related_step_id": related_step_id,
            "related_poi_id": related_poi_id,
            "severity": severity,
            "recoverable": recoverable,
            "recovery_hint": recovery_hint,
        }

    def _risk(
        self,
        risk_type: str,
        level: str,
        description: str,
        related_step_id: Optional[str] = None,
        related_poi_id: Optional[str] = None,
        mitigation: str = "PlanB：刷新状态或切换备选",
    ) -> Dict[str, Any]:
        return {
            "risk_id": new_id("risk"),
            "type": risk_type,
            "level": level,
            "description": description,
            "related_step_id": related_step_id,
            "related_poi_id": related_poi_id,
            "recovery_plan_id": None,
            "user_visible": True,
            "mitigation": mitigation,
        }

    def _recovery_text(self, recovery_hint: Optional[str]) -> str:
        labels = {
            "restaurant_full": "PlanB：同区域切换低排队备选餐厅。",
            "activity_full": "PlanB：切换同区域低强度活动。",
            "weather_rain": "PlanB：改去室内备选节点。",
            "refresh_status": "PlanB：先刷新状态，再决定是否改道。",
            "refresh_weather": "PlanB：先刷新天气，再切换室内备选。",
            "refresh_window": "PlanB：刷新可执行窗口后再确认。",
            "route_delay": "PlanB：改走更短转场路线或减少一个节点。",
            "budget_exceeded": "PlanB：切换低预算节点。",
            "regenerate_timeline": "PlanB：压缩时间线或减少一个节点。",
            "replace_poi": "PlanB：替换当前节点。",
            "rebuild_tool_actions": "PlanB：重新生成待执行动作。",
        }
        return labels.get(str(recovery_hint or ""), "PlanB：刷新状态或切换同区域备选。")

    def _has_related_action(self, step: Dict[str, Any], action_map: Dict[str, Dict[str, Any]], expected_type: str) -> bool:
        return any(action_map.get(action_id, {}).get("type") == expected_type for action_id in step.get("related_tool_action_ids") or [])

    def _payload_complete(self, action: Dict[str, Any]) -> bool:
        payload = action.get("payload")
        if not isinstance(payload, dict):
            return False
        action_type = action.get("type")
        if action_type == "book_activity":
            return bool(action.get("target_poi_id") and payload.get("party_size") and (payload.get("booking_time") or payload.get("arrival_time")))
        if action_type == "reserve_restaurant":
            return bool(action.get("target_poi_id") and payload.get("party_size") and payload.get("arrival_time"))
        if action_type == "order_item":
            return isinstance(payload.get("items"), list) and bool(payload.get("items"))
        if action_type == "send_message":
            return bool(payload.get("channel") and payload.get("content"))
        return True

    def _is_outdoor_step(self, step: Dict[str, Any], poi_map: Dict[str, Dict[str, Any]]) -> bool:
        poi = poi_map.get(step.get("poi_id")) or {}
        tags = set(poi.get("tags") or [])
        name = str(poi.get("name") or "")
        sub_category = str(poi.get("sub_category") or "")
        if {"indoor", "rain_safe"}.intersection(tags):
            return False
        if any(token in f"{name} {sub_category}" for token in ("室内", "地下", "连通", "雨天", "温室", "雨歇", "避雨")):
            return False
        if step.get("type") == "walk":
            return True
        if step.get("type") != "activity":
            return False
        raw_status = self._raw_status(step.get("poi_id"))
        if raw_status.get("indoor") is False:
            return True
        return "outdoor" in tags or "outdoor_shade" in tags

    def _window_reasons(
        self,
        status: str,
        status_expiries: List[Tuple[str, str]],
        route_confidences: List[float],
        source_poi_id: Optional[str],
    ) -> List[str]:
        if status == "fail":
            return ["存在阻断项，需先Recovery或刷新状态。"]
        reasons = []
        if status_expiries:
            reasons.append("关键余位或票务状态有短时有效期。")
        if route_confidences:
            reasons.append("路线估计来自模拟状态。")
        if status == "warning":
            reasons.append("存在可恢复风险，已准备PlanB。")
        if not reasons:
            reasons.append("基础结构校验通过。")
        return reasons

    def _window_message(self, status: str, window_minutes: int) -> str:
        if status == "fail":
            return "当前方案不可直接执行，需要先Recovery或刷新窗口。"
        if status == "warning":
            return f"当前状态约{window_minutes}分钟内有效；如余位变化，会按PlanB改道。"
        return f"当前方案可执行窗口约{window_minutes}分钟。"

    def _status_from_checks(self, checks: List[Dict[str, Any]]) -> str:
        if any(check["status"] == "fail" for check in checks):
            return "fail"
        if any(check["status"] == "warning" for check in checks):
            return "warning"
        return "pass"

    def _pois(self) -> List[Dict[str, Any]]:
        return self.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])

    def _raw_status(self, poi_id: Optional[str]) -> Dict[str, Any]:
        if not poi_id:
            return {}
        statuses = self.store.read(MOCK_STATUS_PATH, {"statuses": {}}).get("statuses", {})
        return (statuses.get(poi_id) or {}).get("query_status") or {}

    def _route_exists(self, route: Dict[str, Any]) -> bool:
        if str(route.get("route_id") or "").startswith("route_engine_") and route.get("source") == "mock_api":
            return route.get("origin_poi_id") and route.get("destination_poi_id") and route.get("duration_minutes")
        routes = self.store.read(MOCK_ROUTES_PATH, {"routes": []}).get("routes", [])
        return any(
            item.get("origin_poi_id") == route.get("origin_poi_id")
            and item.get("destination_poi_id") == route.get("destination_poi_id")
            and item.get("transport_mode") == route.get("transport_mode")
            and item.get("source") == "mock_api"
            for item in routes
        )

    def _effective_expiry(self, poi_id: str, expire_at: str) -> Tuple[Optional[datetime], str]:
        expire_dt = self._parse_dt(expire_at)
        if not expire_dt:
            return None, expire_at
        now = now_shanghai()
        if expire_dt > now:
            return expire_dt, expire_at
        raw_status = self._raw_status(poi_id)
        updated_dt = self._parse_dt(raw_status.get("updated_at"))
        raw_expire_dt = self._parse_dt(raw_status.get("expire_at"))
        if updated_dt and raw_expire_dt and raw_expire_dt > updated_dt:
            ttl = raw_expire_dt - updated_dt
            ttl = min(max(ttl, timedelta(minutes=5)), timedelta(minutes=30))
            projected = (now + ttl).replace(microsecond=0)
            return projected, projected.isoformat()
        return expire_dt, expire_at

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=now_shanghai().tzinfo)
            return parsed.astimezone(now_shanghai().tzinfo)
        except ValueError:
            return None

    def _error_code(self, exc: Exception) -> str:
        code = getattr(exc, "code", None)
        return getattr(code, "value", None) or str(code or exc.__class__.__name__)
