from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import MOCK_POIS_PATH, MOCK_STATUS_PATH, PLANS_STORE_PATH, POI_FEATURES_PATH
from app.core.errors import AppError, bad_request, not_found
from app.core.ids import new_id
from app.core.time import iso_after, iso_now, now_shanghai
from app.services.idempotency_service import IdempotencyService
from app.services.logging_service import LoggingService
from app.services.mock_api_service import MockAPIService
from app.services.schema_validator import SchemaValidator
from app.services.verifier_service import VerifierService
from app.storage.json_store import JsonFileStore


EXECUTABLE_TYPES = {"book_activity", "reserve_restaurant", "order_item", "send_message"}
QUEUE_LIMITS = {"low": 10, "medium": 20, "high": 35}
RECOVERY_TRIGGERS = {
    ErrorCode.NO_TABLE_AVAILABLE.value,
    ErrorCode.ACTIVITY_FULL.value,
    ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED.value,
}


class RecoveryService:
    FILE = PLANS_STORE_PATH

    def __init__(
        self,
        store: JsonFileStore,
        validator: SchemaValidator,
        logging_service: LoggingService,
        idempotency_service: IdempotencyService,
        verifier_service: VerifierService,
        mock_api_service: MockAPIService,
    ) -> None:
        self.store = store
        self.validator = validator
        self.logging_service = logging_service
        self.idempotency_service = idempotency_service
        self.verifier_service = verifier_service
        self.mock_api_service = mock_api_service

    def recover_plan(
        self,
        user_id: str,
        plan_id: str,
        idempotency_key: Optional[str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        key = self.idempotency_service.require_key(idempotency_key, "plans.recover")
        plan = self.get_plan(plan_id)
        failed_action = self._failed_action_from_body(plan, body)
        return self.recover_from_plan(user_id, plan, key, body.get("trigger"), failed_action, body)

    def recover_from_plan(
        self,
        user_id: str,
        plan: Dict[str, Any],
        idempotency_key: str,
        trigger: Optional[str],
        failed_action: Optional[Dict[str, Any]],
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not trigger:
            raise bad_request("trigger is required.")
        if trigger not in RECOVERY_TRIGGERS:
            raise AppError(
                ErrorCode.RECOVERY_RESULT_INVALID,
                f"unsupported recovery trigger: {trigger}.",
                "备选方案校验失败，请重新生成计划。",
                400,
                True,
                {"trigger": trigger},
            )

        body = body or {}
        fingerprint = self.idempotency_service.fingerprint(
            {
                "plan_id": plan["plan_id"],
                "plan_updated_at": plan.get("updated_at"),
                "trigger": trigger,
                "failed_action_id": (failed_action or {}).get("action_id"),
                "failed_step_id": body.get("failed_step_id") or (failed_action or {}).get("step_id"),
                "recovery_strategy": body.get("recovery_strategy"),
            }
        )
        cached = self.idempotency_service.get(user_id, idempotency_key, "plans.recover", fingerprint)
        if cached:
            return cached

        now = iso_now()
        recovery_id = new_id("rec")
        try:
            updated, original, replacement, diff = self._build_replacement_plan(plan, trigger, failed_action, body, now)
            verifier_output = self.verifier_service.verify_plan_contract(updated, "recovery_verify")
            updated["verifier_result"] = verifier_output["verifier_result"]
            updated["executable_window"] = verifier_output["executable_window"]
            updated["risks"] = verifier_output["risks"]
            updated["status"] = "executable" if verifier_output["verifier_result"]["status"] in {"pass", "warning"} else "failed"
            updated["updated_at"] = iso_now()
            self.validator.validate_plan_contract(updated)
            status = "success" if updated["status"] == "executable" else "failed"
            updated_plan_id: Optional[str] = updated["plan_id"]
            verifier_result = verifier_output["verifier_result"]
            if status != "success":
                diagnostics = self._verifier_failure_payload(verifier_result)
                replacement.setdefault("available", True)
                replacement.update({key: diagnostics[key] for key in ("failure_reason_code", "failure_reasons", "user_visible_reason")})
                diff["recovery_diagnostics"] = diagnostics
                diff["user_visible_summary"] = diagnostics["user_visible_reason"]
        except AppError as exc:
            updated = None
            original = self._original_payload(plan, failed_action, body)
            diagnostics = self._recovery_failure_from_error(exc)
            replacement = {
                "strategy": body.get("recovery_strategy") or self._strategy_for_trigger(trigger),
                "available": False,
                **{key: diagnostics[key] for key in ("failure_reason_code", "failure_reasons", "candidate_summary", "user_visible_reason") if key in diagnostics},
            }
            diff = {
                "route_extra_minutes": 0,
                "budget_delta": 0,
                "queue_delta_minutes": 0,
                "time_shift_minutes": 0,
                "user_visible_summary": diagnostics["user_visible_reason"],
                "recovery_diagnostics": diagnostics,
            }
            status = "failed"
            updated_plan_id = None
            verifier_result = self._failed_verifier_result(exc)

        recovery_result = {
            "recovery_id": recovery_id,
            "trigger": trigger,
            "status": status,
            "original": original,
            "replacement": replacement,
            "diff": diff,
            "updated_plan_id": updated_plan_id,
            "verifier_result": verifier_result,
            "user_explanation": self._user_explanation(trigger, status, diff),
            "created_at": now,
        }
        self._validate_recovery_result(recovery_result)

        original_plan = deepcopy(plan)
        original_plan["status"] = "recovered" if status == "success" else "failed"
        original_plan.setdefault("recovery_results", []).append(recovery_result)
        original_plan["updated_at"] = iso_now()
        self.validator.validate_plan_contract(original_plan)
        self._update_plan(plan["plan_id"], original_plan)
        if updated is not None:
            self._save_plan(user_id, updated)

        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.RECOVERY_LOG,
            "RecoveryService",
            {
                "user_visible_message": "已生成替代计划。" if status == "success" else "替代计划生成失败。",
                "trigger": trigger,
                "status": status,
                "recovery_id": recovery_id,
                "updated_plan_id": updated_plan_id,
            },
            plan_id=plan["plan_id"],
            level="info" if status == "success" else "error",
        )
        data = {
            "recovery_result": recovery_result,
            "updated_plan_id": updated_plan_id,
            "updated_plan_contract": updated,
        }
        self.idempotency_service.save(user_id, idempotency_key, "plans.recover", fingerprint, data)
        return data

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}})
        plan = payload.get("plans", {}).get(plan_id)
        if not plan:
            raise not_found("plan")
        return plan

    def _build_replacement_plan(
        self,
        plan: Dict[str, Any],
        trigger: str,
        failed_action: Optional[Dict[str, Any]],
        body: Dict[str, Any],
        now: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        if trigger == ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED.value:
            return self._refresh_window_recovery(plan, failed_action, body, now)
        if not failed_action:
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "failed_action is required for replacement recovery.", "计划动作不完整，请重新生成。", 400, True)
        step = self._step_for_action(plan, failed_action)
        if trigger == ErrorCode.NO_TABLE_AVAILABLE.value:
            return self._replace_poi(plan, failed_action, step, "restaurant", now)
        if trigger == ErrorCode.ACTIVITY_FULL.value:
            return self._replace_poi(plan, failed_action, step, "activity", now)
        raise AppError(ErrorCode.RECOVERY_RESULT_INVALID, "unsupported recovery trigger.", "备选方案校验失败，请重新生成计划。", 400, True)

    def _replace_poi(
        self,
        plan: Dict[str, Any],
        failed_action: Dict[str, Any],
        step: Dict[str, Any],
        category: str,
        now: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        source_poi_id = step.get("poi_id") or failed_action.get("target_poi_id")
        candidate, status = self._candidate_for_replacement(plan, step, failed_action, category)
        updated = deepcopy(plan)
        updated_plan_id = self._next_recovery_plan_id(plan["plan_id"])
        updated["plan_id"] = updated_plan_id
        updated["status"] = "verifying"
        updated["created_at"] = now
        updated["updated_at"] = now
        updated["execution_summary"] = None
        updated["recovery_results"] = []

        updated_step = self._find_step(updated, step["step_id"])
        updated_step["poi_id"] = candidate["poi_id"]
        updated_step["title"] = candidate["name"]
        updated_step["description"] = step.get("description") or candidate.get("sub_category") or ""
        updated_step["display_tags"] = candidate.get("tags", [])[:4]
        updated_step["status"] = "planned"

        if category == "activity" and status.get("booking_available") and failed_action.get("payload", {}).get("booking_time") is None:
            failed_action.setdefault("payload", {})["booking_time"] = updated_step["start_time"]

        new_action_id = new_id("act")
        updated_step["related_tool_action_ids"] = [new_action_id]
        replacement_action = deepcopy(failed_action)
        replacement_action.update(
            {
                "action_id": new_action_id,
                "plan_id": updated_plan_id,
                "step_id": updated_step["step_id"],
                "target_poi_id": candidate["poi_id"],
                "status": "pending",
                "retry_count": 0,
                "idempotency_key": f"idem_{updated_plan_id}_{new_action_id}",
                "result": None,
                "error_code": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        if category == "restaurant":
            replacement_action["type"] = "reserve_restaurant"
            replacement_action["payload"] = {
                **replacement_action.get("payload", {}),
                "party_size": int((plan.get("constraints") or {}).get("party_size") or replacement_action.get("payload", {}).get("party_size") or 1),
                "arrival_time": updated_step["start_time"],
            }
        else:
            replacement_action["type"] = "book_activity"
            replacement_action["payload"] = {
                **replacement_action.get("payload", {}),
                "party_size": int((plan.get("constraints") or {}).get("party_size") or replacement_action.get("payload", {}).get("party_size") or 1),
                "booking_time": updated_step["start_time"],
            }
        updated_actions = []
        for action in updated.get("tool_actions", []):
            if action.get("action_id") == failed_action.get("action_id"):
                updated_actions.append(replacement_action)
                continue
            action_copy = deepcopy(action)
            action_copy["plan_id"] = updated_plan_id
            if action_copy.get("status") == "failed":
                action_copy["status"] = "pending"
                action_copy["result"] = None
                action_copy["error_code"] = None
            action_copy["updated_at"] = now
            updated_actions.append(action_copy)
        updated["tool_actions"] = updated_actions
        self._replace_transport_references(updated, source_poi_id, candidate["poi_id"])
        self._refresh_budget(updated, source_poi_id, candidate)

        original = self._original_payload(plan, failed_action, {"failed_step_id": step["step_id"]})
        replacement = {"step_id": step["step_id"], "poi_id": candidate["poi_id"], "poi_name": candidate["name"]}
        if candidate.get("_recovery_source"):
            replacement["source"] = candidate.get("_recovery_source")
        if candidate.get("_recovery_relation"):
            relation = candidate["_recovery_relation"]
            replacement["relation"] = relation.get("relation")
            replacement["relation_score"] = relation.get("score")
            replacement["reason"] = relation.get("reason")
        diff = self._diff(plan, step, candidate, status)
        return updated, original, replacement, diff

    def _refresh_window_recovery(
        self,
        plan: Dict[str, Any],
        failed_action: Optional[Dict[str, Any]],
        body: Dict[str, Any],
        now: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        updated = deepcopy(plan)
        updated_plan_id = self._next_recovery_plan_id(plan["plan_id"])
        updated["plan_id"] = updated_plan_id
        updated["status"] = "verifying"
        updated["created_at"] = now
        updated["updated_at"] = now
        updated["execution_summary"] = None
        updated["recovery_results"] = []
        updated["executable_window"] = {
            "window_minutes": 12,
            "confidence": 0.78,
            "expire_at": iso_after(12),
            "reasons": ["窗口过期后重新检查Mock状态。"],
            "risk_factors": [],
            "lockable_resources": (plan.get("executable_window") or {}).get("lockable_resources", []),
            "calculated_from": ["refresh-window", "verifier"],
            "display_message": "恢复版本已刷新可执行窗口。",
        }
        for action in updated.get("tool_actions", []):
            action["plan_id"] = updated_plan_id
            if action.get("status") in {"failed", "running"}:
                action["status"] = "pending"
                action["result"] = None
                action["error_code"] = None
            action["updated_at"] = now
        original = self._original_payload(plan, failed_action, body)
        replacement = {"plan_id": updated_plan_id, "strategy": "refresh-window"}
        diff = {
            "route_extra_minutes": 0,
            "budget_delta": 0,
            "queue_delta_minutes": 0,
            "time_shift_minutes": 0,
            "user_visible_summary": "可执行窗口已刷新，需使用新计划继续执行。",
        }
        return updated, original, replacement, diff

    def _candidate_for_replacement(
        self,
        plan: Dict[str, Any],
        step: Dict[str, Any],
        failed_action: Dict[str, Any],
        category: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        trace_id = plan["trace_id"]
        constraints = plan.get("constraints") or {}
        party_size = int(constraints.get("party_size") or failed_action.get("payload", {}).get("party_size") or 1)
        scenario = (plan.get("user_goal") or {}).get("scenario")
        source_poi = self._poi(step.get("poi_id"))
        area = (source_poi or {}).get("area")
        budget_pp = constraints.get("budget_max_per_person")
        summary = self._candidate_summary(category, step.get("poi_id"), constraints)
        if category == "restaurant":
            items = self._replacement_candidates(plan, step, category, scenario, area, budget_pp, constraints)
            summary["candidate_count"] = len(items)
            summary["relation_edge_candidates"] = sum(1 for item in items if item.get("_recovery_source") == "poi_relation_edge")
            queue_tolerance = str(constraints.get("queue_tolerance") or "medium")
            queue_limit = QUEUE_LIMITS.get(queue_tolerance, QUEUE_LIMITS["medium"])
            explicit_low_queue = "low_queue" in set(str(item) for item in constraints.get("must_have") or [])
            semantic_queue_limit = queue_limit if explicit_low_queue else max(queue_limit, int(QUEUE_LIMITS["medium"] * 1.5))
            for item in items:
                summary["considered"] += 1
                if item.get("poi_id") == step.get("poi_id"):
                    summary["same_poi"] += 1
                    continue
                if not self._restaurant_replacement_allowed(step.get("poi_id"), item.get("poi_id"), constraints):
                    summary["semantic_mismatch"] += 1
                    self._add_candidate_sample(summary, "semantic_mismatch_samples", item)
                    continue
                if budget_pp is not None and float(item.get("price_per_person") or 0) > float(budget_pp):
                    summary["budget_exceeded"] += 1
                    self._add_candidate_sample(summary, "budget_exceeded_samples", item)
                    continue
                try:
                    status = self.mock_api_service.restaurant_status(
                        trace_id,
                        item["poi_id"],
                        arrival_time=failed_action.get("payload", {}).get("arrival_time") or step["start_time"],
                        party_size=party_size,
                    )
                except AppError:
                    summary["status_error"] += 1
                    continue
                summary["status_checked"] += 1
                if (
                    int(status.get("available_tables") or 0) > 0
                    and status.get("reservation_available")
                    and int(status.get("queue_minutes") or 0) <= (semantic_queue_limit if item.get("_recovery_source") == "poi_relation_edge" else queue_limit)
                ):
                    return item, status
                if not (int(status.get("available_tables") or 0) > 0 and status.get("reservation_available")):
                    summary["not_available"] += 1
                    self._add_candidate_sample(summary, "not_available_samples", item, status)
                elif int(status.get("queue_minutes") or 0) > (semantic_queue_limit if item.get("_recovery_source") == "poi_relation_edge" else queue_limit):
                    summary["queue_exceeded"] += 1
                    self._add_candidate_sample(summary, "queue_exceeded_samples", item, status)
        else:
            items = self._replacement_candidates(plan, step, category, scenario, area, budget_pp, constraints)
            summary["candidate_count"] = len(items)
            summary["relation_edge_candidates"] = sum(1 for item in items if item.get("_recovery_source") == "poi_relation_edge")
            for item in items:
                summary["considered"] += 1
                if item.get("poi_id") == step.get("poi_id"):
                    summary["same_poi"] += 1
                    continue
                if constraints.get("weather_sensitive") is not False and not self._activity_weather_safe(item):
                    summary["weather_unsafe"] += 1
                    self._add_candidate_sample(summary, "weather_unsafe_samples", item)
                    continue
                if budget_pp is not None and float(item.get("price_per_person") or 0) > float(budget_pp):
                    summary["budget_exceeded"] += 1
                    self._add_candidate_sample(summary, "budget_exceeded_samples", item)
                    continue
                try:
                    status = self.mock_api_service.poi_status(trace_id, item["poi_id"], party_size=party_size)
                except AppError:
                    summary["status_error"] += 1
                    continue
                summary["status_checked"] += 1
                if status.get("booking_available") and status.get("ticket_available"):
                    return item, status
                summary["not_available"] += 1
                self._add_candidate_sample(summary, "not_available_samples", item, status)
        raise AppError(
            ErrorCode.RECOVERY_RESULT_INVALID,
            "no valid replacement candidate found.",
            "备选方案校验失败，请重新生成计划。",
            409,
            True,
            {"recovery_failure": self._candidate_failure_payload(summary)},
        )

    def _candidate_summary(self, category: str, source_poi_id: Optional[str], constraints: Dict[str, Any]) -> Dict[str, Any]:
        features = self._poi_features()
        source_feature = features.get(str(source_poi_id)) or {}
        source_tags = set(str(tag) for tag in source_feature.get("semantic_tags") or [])
        required_tags = sorted(self._required_dining_cluster(source_tags, constraints)) if category == "restaurant" else []
        return {
            "category": category,
            "source_poi_id": source_poi_id,
            "required_semantic_tags": required_tags,
            "candidate_count": 0,
            "relation_edge_candidates": 0,
            "considered": 0,
            "same_poi": 0,
            "semantic_mismatch": 0,
            "budget_exceeded": 0,
            "weather_unsafe": 0,
            "status_checked": 0,
            "status_error": 0,
            "not_available": 0,
            "queue_exceeded": 0,
            "semantic_mismatch_samples": [],
            "budget_exceeded_samples": [],
            "weather_unsafe_samples": [],
            "not_available_samples": [],
            "queue_exceeded_samples": [],
        }

    def _add_candidate_sample(
        self,
        summary: Dict[str, Any],
        key: str,
        item: Dict[str, Any],
        status: Optional[Dict[str, Any]] = None,
    ) -> None:
        samples = summary.setdefault(key, [])
        if not isinstance(samples, list) or len(samples) >= 5:
            return
        feature = self._poi_features().get(str(item.get("poi_id"))) or {}
        payload = {
            "poi_id": item.get("poi_id"),
            "name": item.get("name"),
            "category": item.get("category"),
            "semantic_tags": list(feature.get("semantic_tags") or item.get("tags") or [])[:12],
        }
        if item.get("_recovery_source"):
            payload["source"] = item.get("_recovery_source")
        if status:
            payload["available_tables"] = status.get("available_tables")
            payload["queue_minutes"] = status.get("queue_minutes")
            payload["reservation_available"] = status.get("reservation_available")
            payload["booking_available"] = status.get("booking_available")
            payload["ticket_available"] = status.get("ticket_available")
        samples.append(payload)

    def _candidate_failure_payload(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        code = "no_valid_replacement"
        message = "未找到通过校验的替代方案，需要刷新窗口或重新生成计划。"
        category = str(summary.get("category") or "")
        if category == "restaurant":
            required = summary.get("required_semantic_tags") or []
            if required and int(summary.get("status_checked") or 0) == 0:
                code = "no_same_semantic_restaurant_available"
                message = f"没有找到符合{self._dining_cluster_label(required)}的可订座替代餐厅。"
            elif int(summary.get("not_available") or 0) > 0 and int(summary.get("queue_exceeded") or 0) > 0:
                code = "same_semantic_restaurant_capacity_or_queue_failed"
                message = "找到同餐型候选，但桌位或排队时间未通过校验。"
            elif int(summary.get("not_available") or 0) > 0:
                code = "same_semantic_restaurant_no_capacity"
                message = "找到同餐型候选，但当前没有可订桌位。"
            elif int(summary.get("queue_exceeded") or 0) > 0:
                code = "same_semantic_restaurant_queue_exceeded"
                message = "找到同餐型候选，但排队时间超过当前偏好。"
            elif int(summary.get("budget_exceeded") or 0) > 0:
                code = "same_semantic_restaurant_budget_exceeded"
                message = "找到同餐型候选，但超出当前预算约束。"
        else:
            if int(summary.get("weather_unsafe") or 0) > 0 and int(summary.get("status_checked") or 0) == 0:
                code = "same_semantic_activity_weather_unsafe"
                message = "找到同类活动候选，但当前天气下不适合直接替换。"
            elif int(summary.get("not_available") or 0) > 0:
                code = "same_semantic_activity_no_capacity"
                message = "找到同类活动候选，但当前场次或余票未通过校验。"
            elif int(summary.get("budget_exceeded") or 0) > 0:
                code = "same_semantic_activity_budget_exceeded"
                message = "找到同类活动候选，但超出当前预算约束。"
        return {
            "failure_reason_code": code,
            "failure_reasons": [{"code": code, "message": message}],
            "candidate_summary": summary,
            "user_visible_reason": message,
        }

    def _replacement_candidates(
        self,
        plan: Dict[str, Any],
        step: Dict[str, Any],
        category: str,
        scenario: Optional[str],
        area: Optional[str],
        budget_pp: Optional[float],
        constraints: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        trace_id = plan["trace_id"]
        relation_items = self._relation_edge_candidates(step.get("poi_id"), category, constraints)
        if category == "restaurant":
            area_items = self.mock_api_service.search_restaurants(
                trace_id,
                scenario=scenario,
                area=area,
                dietary_preference=",".join(constraints.get("dietary_preference") or []) or None,
                budget_max_per_person=budget_pp,
                limit=100,
            ).get("items", [])
            fallback_items = self.mock_api_service.search_restaurants(
                trace_id,
                scenario=scenario,
                budget_max_per_person=budget_pp,
                limit=100,
            ).get("items", [])
        else:
            area_items = self.mock_api_service.search_pois(trace_id, scenario=scenario, area=area, category="activity", limit=100).get("items", [])
            fallback_items = self.mock_api_service.search_pois(trace_id, scenario=scenario, category="activity", limit=100).get("items", [])
        merged = self._merge_replacement_candidates([*relation_items, *area_items, *fallback_items])
        return sorted(
            merged,
            key=lambda item: -self._replacement_candidate_score(plan, step, item, category, constraints),
        )

    def _relation_edge_candidates(self, source_poi_id: Optional[str], category: str, constraints: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not source_poi_id:
            return []
        features = self._poi_features()
        source_feature = features.get(str(source_poi_id)) or {}
        result = []
        for edge in source_feature.get("relation_edges") or []:
            target = self._poi(str(edge.get("target_poi_id") or ""))
            if not target:
                continue
            if not self._matches_recovery_category(target, category):
                continue
            target_feature = features.get(str(target.get("poi_id"))) or {}
            if not self._relation_edge_allowed(source_feature, target_feature, category, constraints):
                continue
            item = deepcopy(target)
            item["_recovery_source"] = "poi_relation_edge"
            item["_recovery_relation"] = {
                "relation": edge.get("relation"),
                "score": float(edge.get("score") or 0),
                "reason": edge.get("reason"),
            }
            result.append(item)
        return result

    def _matches_recovery_category(self, item: Dict[str, Any], category: str) -> bool:
        if category == "restaurant":
            return item.get("category") == "restaurant"
        return item.get("category") == "activity"

    def _relation_edge_allowed(
        self,
        source_feature: Dict[str, Any],
        target_feature: Dict[str, Any],
        category: str,
        constraints: Dict[str, Any],
    ) -> bool:
        source_tags = set(str(tag) for tag in source_feature.get("semantic_tags") or [])
        target_tags = set(str(tag) for tag in target_feature.get("semantic_tags") or [])
        if category == "restaurant":
            return self._restaurant_tags_allowed(source_tags, target_tags, constraints)
        source_activity = source_tags & {"amusement", "hands_on", "craft", "karaoke", "board_game", "music", "acoustic_music", "lake", "park", "light_walk", "theater", "private_cinema"}
        if not source_activity:
            return True
        return bool(target_tags & source_activity)

    def _restaurant_replacement_allowed(self, source_poi_id: Optional[str], target_poi_id: Optional[str], constraints: Dict[str, Any]) -> bool:
        features = self._poi_features()
        source_feature = features.get(str(source_poi_id)) or {}
        target_feature = features.get(str(target_poi_id)) or {}
        source_tags = set(str(tag) for tag in source_feature.get("semantic_tags") or [])
        target_tags = set(str(tag) for tag in target_feature.get("semantic_tags") or [])
        return self._restaurant_tags_allowed(source_tags, target_tags, constraints)

    def _restaurant_tags_allowed(self, source_tags: set[str], target_tags: set[str], constraints: Dict[str, Any]) -> bool:
        required = self._required_dining_cluster(source_tags, constraints)
        if required:
            return bool(target_tags & required)
        return bool(target_tags & {"proper_dining", "slow_dining", "light_meal", "quality_dining", "buffet", "hotpot", "bbq", "grill", "western_cuisine", "cuisine_japanese"})

    def _required_dining_cluster(self, source_tags: set[str], constraints: Dict[str, Any]) -> set[str]:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if markers & {"crayfish"} or source_tags & {"crayfish"}:
            return {"crayfish"}
        if markers & {"buffet"} or source_tags & {"buffet"}:
            return {"buffet"}
        if markers & {"hotpot"} or source_tags & {"hotpot"}:
            return {"hotpot"}
        if markers & {"bbq", "grill", "lamb"} or source_tags & {"bbq", "grill", "lamb"}:
            return {"bbq", "grill", "lamb"}
        if markers & {"cuisine_japanese", "sushi", "izakaya"} or source_tags & {"cuisine_japanese", "sushi", "izakaya"}:
            return {"cuisine_japanese", "sushi", "izakaya"}
        if markers & {"western_cuisine", "steak"} or source_tags & {"western_cuisine", "steak"}:
            return {"western_cuisine", "steak"}
        if markers & {"light_meal", "light_food", "healthy_light"}:
            return {"light_meal", "light_food", "healthy_light"}
        return set()

    def _merge_replacement_candidates(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        merged = []
        for item in items:
            poi_id = item.get("poi_id")
            if not poi_id or poi_id in seen:
                continue
            seen.add(poi_id)
            merged.append(item)
        return merged

    def _replacement_candidate_score(
        self,
        plan: Dict[str, Any],
        step: Dict[str, Any],
        item: Dict[str, Any],
        category: str,
        constraints: Dict[str, Any],
    ) -> float:
        features = self._poi_features()
        feature = features.get(str(item.get("poi_id"))) or {}
        source_feature = features.get(str(step.get("poi_id"))) or {}
        source_tags = set(str(tag) for tag in source_feature.get("semantic_tags") or [])
        target_tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
        relation = item.get("_recovery_relation") or {}
        score = float(item.get("rating") or 4.2) * 8
        if item.get("_recovery_source") == "poi_relation_edge":
            score += 120 + float(relation.get("score") or 0) * 80
        if item.get("area") == (self._poi(step.get("poi_id")) or {}).get("area"):
            score += 30
        score += len(source_tags & target_tags) * 8
        score += self._neighbor_route_score(plan, step, item)
        price_delta = abs(float(item.get("price_per_person") or 0) - float((self._poi(step.get("poi_id")) or {}).get("price_per_person") or 0))
        score -= min(price_delta, 120) * 0.25
        if category == "restaurant":
            required = self._required_dining_cluster(source_tags, constraints)
            if required and target_tags & required:
                score += 80
        return score

    def _neighbor_route_score(self, plan: Dict[str, Any], step: Dict[str, Any], candidate: Dict[str, Any]) -> float:
        previous_poi, next_poi = self._neighbor_pois(plan, step)
        score = 0.0
        for neighbor in (previous_poi, next_poi):
            if not neighbor:
                continue
            distance = self._distance_km(neighbor, candidate)
            if distance is None:
                score -= 8
            else:
                score += max(-25.0, 24.0 - distance * 10)
        return score

    def _neighbor_pois(self, plan: Dict[str, Any], step: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        poi_steps = [item for item in plan.get("timeline") or [] if item.get("type") != "transport" and item.get("poi_id")]
        index = next((idx for idx, item in enumerate(poi_steps) if item.get("step_id") == step.get("step_id")), -1)
        if index < 0:
            return None, None
        previous_poi = self._poi(poi_steps[index - 1].get("poi_id")) if index > 0 else None
        next_poi = self._poi(poi_steps[index + 1].get("poi_id")) if index + 1 < len(poi_steps) else None
        return previous_poi, next_poi

    def _replace_transport_references(self, plan: Dict[str, Any], source_poi_id: Optional[str], replacement_poi_id: str) -> None:
        if not source_poi_id:
            return
        for index, step in enumerate(plan.get("timeline", [])):
            if step.get("type") != "transport":
                continue
            changed = False
            if step.get("from_poi_id") == source_poi_id:
                step["from_poi_id"] = replacement_poi_id
                changed = True
            if step.get("to_poi_id") == source_poi_id:
                step["to_poi_id"] = replacement_poi_id
                changed = True
            if not changed:
                continue
            route = self._estimate_route_any_mode(plan["trace_id"], step["from_poi_id"], step["to_poi_id"], step.get("transport_mode"), step["start_time"])
            if not route:
                continue
            old_duration = int(step.get("duration_minutes") or route["duration_minutes"])
            step["transport_mode"] = route["transport_mode"]
            step["estimated_route"] = route
            step["duration_minutes"] = int(route["duration_minutes"])
            step["end_time"] = self._shift_iso(step["start_time"], step["duration_minutes"])
            delta = step["duration_minutes"] - old_duration
            if delta:
                self._shift_later_steps(plan["timeline"], index + 1, delta)

    def _estimate_route_any_mode(
        self,
        trace_id: str,
        origin_poi_id: str,
        destination_poi_id: str,
        preferred_mode: Optional[str],
        departure_time: str,
    ) -> Optional[Dict[str, Any]]:
        modes = [preferred_mode] if preferred_mode else []
        modes += [mode for mode in ("walk", "taxi", "bike", "drive", "mixed", "subway") if mode not in modes]
        for mode in modes:
            try:
                return self.mock_api_service.estimate_route(
                    trace_id,
                    origin_poi_id=origin_poi_id,
                    destination_poi_id=destination_poi_id,
                    transport_mode=mode,
                    departure_time=departure_time,
                )
            except AppError:
                continue
        return None

    def _shift_later_steps(self, timeline: List[Dict[str, Any]], start_index: int, delta_minutes: int) -> None:
        for step in timeline[start_index:]:
            step["start_time"] = self._shift_iso(step["start_time"], delta_minutes)
            step["end_time"] = self._shift_iso(step["end_time"], delta_minutes)

    def _shift_iso(self, value: str, minutes: int) -> str:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()

    def _refresh_budget(self, plan: Dict[str, Any], source_poi_id: Optional[str], candidate: Dict[str, Any]) -> None:
        budget = plan.get("budget") or {}
        party_size = int((plan.get("constraints") or {}).get("party_size") or 1)
        old_price = float((self._poi(source_poi_id) or {}).get("price_per_person") or 0)
        new_price = float(candidate.get("price_per_person") or 0)
        delta = round((new_price - old_price) * party_size, 2)
        budget["estimated_total"] = round(float(budget.get("estimated_total") or 0) + delta, 2)
        budget["price_per_person"] = round(budget["estimated_total"] / party_size, 2) if party_size else None
        for item in budget.get("items", []):
            if item.get("source") == "mock_api" and source_poi_id and str(item.get("name", "")):
                continue
        plan["budget"] = budget

    def _diff(self, plan: Dict[str, Any], step: Dict[str, Any], candidate: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
        party_size = int((plan.get("constraints") or {}).get("party_size") or 1)
        original = self._poi(step.get("poi_id")) or {}
        budget_delta = round((float(candidate.get("price_per_person") or 0) - float(original.get("price_per_person") or 0)) * party_size, 2)
        queue_delta = 0
        raw_original_status = self._raw_status(step.get("poi_id"))
        if raw_original_status.get("queue_minutes") is not None or status.get("queue_minutes") is not None:
            queue_delta = int(status.get("queue_minutes") or 0) - int(raw_original_status.get("queue_minutes") or 0)
        return {
            "route_extra_minutes": 0,
            "budget_delta": budget_delta,
            "queue_delta_minutes": queue_delta,
            "time_shift_minutes": 0,
            "diet_match": "same",
            "scenario_match": "same",
            "user_visible_summary": f"已替换为{candidate.get('name')}，预算变化{budget_delta}元，排队变化{queue_delta}分钟。",
        }

    def _original_payload(self, plan: Dict[str, Any], failed_action: Optional[Dict[str, Any]], body: Dict[str, Any]) -> Dict[str, Any]:
        step_id = body.get("failed_step_id") or (failed_action or {}).get("step_id")
        step = self._find_step(plan, step_id) if step_id else None
        poi = self._poi((step or {}).get("poi_id") or (failed_action or {}).get("target_poi_id"))
        payload = {
            "step_id": step_id,
            "action_id": (failed_action or {}).get("action_id") or body.get("failed_action_id"),
            "poi_id": (step or {}).get("poi_id") or (failed_action or {}).get("target_poi_id"),
        }
        if poi:
            payload["poi_name"] = poi.get("name")
        return payload

    def _failed_action_from_body(self, plan: Dict[str, Any], body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        action_id = body.get("failed_action_id")
        if action_id:
            return next((deepcopy(action) for action in plan.get("tool_actions", []) if action.get("action_id") == action_id), None)
        step_id = body.get("failed_step_id")
        if step_id:
            return next((deepcopy(action) for action in plan.get("tool_actions", []) if action.get("step_id") == step_id), None)
        return None

    def _step_for_action(self, plan: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
        step = self._find_step(plan, action.get("step_id"))
        if step is None:
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "failed action step_id does not exist.", "计划动作不完整，请重新生成。", 400, True)
        return step

    def _find_step(self, plan: Dict[str, Any], step_id: Optional[str]) -> Optional[Dict[str, Any]]:
        return next((step for step in plan.get("timeline", []) if step.get("step_id") == step_id), None)

    def _poi(self, poi_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not poi_id:
            return None
        return next((item for item in self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", []) if item.get("poi_id") == poi_id), None)

    def _poi_features(self) -> Dict[str, Dict[str, Any]]:
        features = self.mock_api_service.store.read(POI_FEATURES_PATH, {"features": {}}).get("features", {})
        return {str(key): value for key, value in features.items() if isinstance(value, dict)}

    def _distance_km(self, origin: Optional[Dict[str, Any]], destination: Optional[Dict[str, Any]]) -> Optional[float]:
        if not origin or not destination:
            return None
        origin_loc = origin.get("location") or {}
        destination_loc = destination.get("location") or {}
        try:
            lat1 = float(origin_loc["lat"])
            lng1 = float(origin_loc["lng"])
            lat2 = float(destination_loc["lat"])
            lng2 = float(destination_loc["lng"])
        except (KeyError, TypeError, ValueError):
            return None
        lat_km = (lat2 - lat1) * 111.0
        lng_km = (lng2 - lng1) * 96.0
        return (lat_km**2 + lng_km**2) ** 0.5

    def _raw_status(self, poi_id: Optional[str]) -> Dict[str, Any]:
        if not poi_id:
            return {}
        statuses = self.store.read(MOCK_STATUS_PATH, {"statuses": {}}).get("statuses", {})
        return (statuses.get(poi_id) or {}).get("query_status") or {}

    def _activity_weather_safe(self, item: Dict[str, Any]) -> bool:
        tags = set(item.get("tags") or [])
        if {"rain_safe", "indoor"}.intersection(tags):
            return True
        raw_status = self._raw_status(item.get("poi_id"))
        return raw_status.get("indoor") is not False

    def _next_recovery_plan_id(self, plan_id: str) -> str:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}})
        base = plan_id.split("_r", 1)[0]
        index = 1
        while f"{base}_r{index}" in payload.get("plans", {}):
            index += 1
        return f"{base}_r{index}"

    def _strategy_for_trigger(self, trigger: str) -> str:
        if trigger == ErrorCode.NO_TABLE_AVAILABLE.value:
            return "replace_restaurant_same_area"
        if trigger == ErrorCode.ACTIVITY_FULL.value:
            return "replace_activity_or_adjust_slot"
        return "refresh-window"

    def _recovery_failure_from_error(self, exc: AppError) -> Dict[str, Any]:
        failure = exc.details.get("recovery_failure") if isinstance(exc.details, dict) else None
        if isinstance(failure, dict):
            return failure
        code = exc.code.value
        message = exc.user_message or "未找到通过校验的替代方案，需要刷新窗口或重新生成计划。"
        return {
            "failure_reason_code": code,
            "failure_reasons": [{"code": code, "message": message}],
            "candidate_summary": {},
            "user_visible_reason": message,
        }

    def _verifier_failure_payload(self, verifier_result: Dict[str, Any]) -> Dict[str, Any]:
        failed_checks = [str(item) for item in verifier_result.get("failed_checks") or []]
        warnings = [str(item) for item in verifier_result.get("warnings") or []]
        code = "replacement_plan_verifier_failed"
        message = "已找到替代节点，但替代后的整条计划仍未通过校验。"
        if "weather_risk" in failed_checks:
            code = "replacement_plan_weather_failed"
            message = "已找到同语义替代，但整条路线仍有天气风险，需要优先切换室内节点或刷新天气。"
        elif "distance_constraint" in failed_checks:
            code = "replacement_plan_route_failed"
            message = "已找到同语义替代，但替代后路线转场不够稳，需要重新规划路线。"
        elif "budget_constraint" in failed_checks:
            code = "replacement_plan_budget_failed"
            message = "已找到同语义替代，但替代后预算超出当前约束。"
        elif "restaurant_capacity" in failed_checks:
            code = "replacement_plan_capacity_failed"
            message = "已找到同语义替代，但最新桌位状态未通过校验。"
        return {
            "failure_reason_code": code,
            "failure_reasons": [{"code": code, "message": message}],
            "verifier_failed_checks": failed_checks,
            "verifier_warnings": warnings,
            "user_visible_reason": message,
        }

    def _dining_cluster_label(self, tags: List[str]) -> str:
        labels = {
            "buffet": "自助餐",
            "crayfish": "小龙虾",
            "hotpot": "火锅",
            "bbq": "烤肉",
            "grill": "烤肉",
            "lamb": "羊排/羊肉",
            "cuisine_japanese": "日料",
            "sushi": "寿司/日料",
            "izakaya": "居酒屋/日料",
            "western_cuisine": "西餐",
            "steak": "牛排/西餐",
            "light_meal": "清淡餐",
            "light_food": "清淡餐",
            "healthy_light": "健康轻食",
        }
        return " / ".join(dict.fromkeys(labels.get(tag, tag) for tag in tags))

    def _user_explanation(self, trigger: str, status: str, diff: Dict[str, Any]) -> str:
        if status != "success":
            return str(diff.get("user_visible_summary") or "未找到通过校验的替代版本，需要重新检查窗口或重新生成计划。")
        if trigger == ErrorCode.NO_TABLE_AVAILABLE.value:
            return "原餐厅Mock桌位已满，已切换到同区域可订座餐厅。"
        if trigger == ErrorCode.ACTIVITY_FULL.value:
            return "原活动Mock场次已满，已切换到可预约活动或调整场次。"
        return "当前可执行窗口已过期，已生成刷新窗口后的新版本。"

    def _failed_verifier_result(self, exc: AppError) -> Dict[str, Any]:
        return {
            "status": "fail",
            "score": 0,
            "checks": [],
            "failed_checks": [exc.code.value],
            "warnings": [],
            "required_recovery": True,
            "suggestions": ["PlanB：刷新窗口或重新生成计划。"],
            "created_at": iso_now(),
        }

    def _validate_recovery_result(self, result: Dict[str, Any]) -> None:
        required = {"recovery_id", "trigger", "status", "original", "replacement", "diff", "updated_plan_id", "verifier_result", "user_explanation", "created_at"}
        missing = sorted(required - set(result.keys()))
        forbidden = {f"original_{'step'}_id", f"original_{'poi'}", f"new_{'poi'}", "changes"}
        present_forbidden = sorted(key for key in forbidden if key in result)
        if missing or present_forbidden:
            raise AppError(
                ErrorCode.RECOVERY_RESULT_INVALID,
                "RecoveryResult contract invalid.",
                "备选方案校验失败，请重新生成计划。",
                400,
                True,
                {"missing_fields": missing, "forbidden_fields": present_forbidden},
            )
        if not isinstance(result.get("verifier_result"), dict) or result["verifier_result"].get("status") not in {"pass", "warning", "fail"}:
            raise AppError(ErrorCode.RECOVERY_RESULT_INVALID, "recovery result has invalid verifier_result.", "备选方案校验失败，请重新生成计划。", 400, True)

    def _save_plan(self, user_id: str, plan: Dict[str, Any]) -> None:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}, "owners": {}})
        payload.setdefault("plans", {})[plan["plan_id"]] = plan
        payload.setdefault("owners", {})[plan["plan_id"]] = user_id
        self.store.write(self.FILE, payload)

    def _update_plan(self, plan_id: str, plan: Dict[str, Any]) -> None:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}, "owners": {}})
        payload.setdefault("plans", {})[plan_id] = plan
        self.store.write(self.FILE, payload)
