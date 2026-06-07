from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import EXECUTIONS_STORE_PATH, PLANS_STORE_PATH
from app.core.errors import AppError, bad_request, not_found
from app.core.ids import new_id
from app.core.time import iso_now, now_shanghai
from app.services.idempotency_service import IdempotencyService
from app.services.logging_service import LoggingService
from app.services.mock_api_service import MockAPIService
from app.services.recovery_service import EXECUTABLE_TYPES, RecoveryService
from app.services.schema_validator import SchemaValidator
from app.services.verifier_service import VerifierService
from app.storage.json_store import JsonFileStore


VOUCHER_FIELDS = {
    "booking_id": "booking_id",
    "reservation_id": "reservation_id",
    "queue_number": "queue_number",
    "order_id": "order_id",
    "message_id": "message_id",
}

RECOVERABLE_EXECUTION_ERRORS = {
    ErrorCode.NO_TABLE_AVAILABLE,
    ErrorCode.ACTIVITY_FULL,
}


class ExecutorService:
    PLANS_FILE = PLANS_STORE_PATH
    EXECUTIONS_FILE = EXECUTIONS_STORE_PATH

    def __init__(
        self,
        store: JsonFileStore,
        validator: SchemaValidator,
        logging_service: LoggingService,
        idempotency_service: IdempotencyService,
        verifier_service: VerifierService,
        mock_api_service: MockAPIService,
        recovery_service: RecoveryService,
    ) -> None:
        self.store = store
        self.validator = validator
        self.logging_service = logging_service
        self.idempotency_service = idempotency_service
        self.verifier_service = verifier_service
        self.mock_api_service = mock_api_service
        self.recovery_service = recovery_service

    def execute_plan(
        self,
        user_id: str,
        plan_id: str,
        idempotency_key: Optional[str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        key = self.idempotency_service.require_key(idempotency_key, "plans.execute")
        fingerprint = self.idempotency_service.fingerprint({"plan_id": plan_id, "body": body})
        cached = self.idempotency_service.get(user_id, key, "plans.execute", fingerprint)
        if cached:
            return cached

        if body.get("confirmed") is not True:
            raise bad_request("confirmed=true is required for execution.")
        plan = self.get_plan(plan_id)
        self._assert_plan_can_execute(plan)
        requested_action_ids = set(body.get("execute_action_ids") or [])
        self._assert_requested_actions_exist(plan, requested_action_ids)

        execution_result, active_plan = self._execute_active_plan(user_id, plan, key, body, requested_action_ids)
        data = {
            "execution_id": execution_result["execution_id"],
            "execution_result": execution_result,
            "active_plan_id": active_plan["plan_id"],
            "active_plan_contract": active_plan,
            "recovery_results": execution_result.get("recovery_results", []),
            "action_results": execution_result["action_results"],
        }
        self.idempotency_service.save(user_id, key, "plans.execute", fingerprint, data)
        return data

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        payload = self.store.read(self.PLANS_FILE, {"version": "v0.1", "plans": {}})
        plan = payload.get("plans", {}).get(plan_id)
        if not plan:
            raise not_found("plan")
        return plan

    def _execute_active_plan(
        self,
        user_id: str,
        plan: Dict[str, Any],
        idempotency_key: str,
        body: Dict[str, Any],
        requested_action_ids: set[str],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        working_plan = deepcopy(plan)
        execution_id = new_id("exec")
        action_results: List[Dict[str, Any]] = []
        vouchers: List[Dict[str, Any]] = []
        failed_actions: List[Dict[str, Any]] = []
        recovery_results: List[Dict[str, Any]] = []
        active_plan = working_plan
        allow_auto_recovery = body.get("allow_auto_recovery", True)

        working_plan["status"] = "executing"
        working_plan["updated_at"] = iso_now()
        self._update_plan(working_plan["plan_id"], working_plan)

        try:
            actions = self._actions_to_execute(working_plan, requested_action_ids, body)
            for action in actions:
                try:
                    result = self._execute_action(working_plan, action, idempotency_key, body)
                except AppError as exc:
                    failed_result = self._mark_action_failed(working_plan, action, exc)
                    action_results.append(failed_result)
                    failed_actions.append(
                        {
                            "action_id": action["action_id"],
                            "error_code": exc.code.value,
                            "recoverable": exc.code in RECOVERABLE_EXECUTION_ERRORS,
                        }
                    )
                    self._log_executor_failure(working_plan, action, exc, execution_id)
                    if exc.code in RECOVERABLE_EXECUTION_ERRORS and allow_auto_recovery:
                        recovery_data = self.recovery_service.recover_from_plan(
                            user_id,
                            working_plan,
                            f"{idempotency_key}:recover:{action['action_id']}",
                            exc.code.value,
                            deepcopy(action),
                            {
                                "trigger": exc.code.value,
                                "failed_step_id": action.get("step_id"),
                                "failed_action_id": action.get("action_id"),
                                "auto_verify": True,
                            },
                        )
                        recovery_result = recovery_data["recovery_result"]
                        recovery_results.append(recovery_result)
                        if recovery_data.get("updated_plan_contract") and recovery_result["status"] == "success":
                            active_plan = recovery_data["updated_plan_contract"]
                            replacement_result = self._execute_recovery_plan(
                                active_plan,
                                idempotency_key,
                                None,
                                action_results,
                                vouchers,
                            )
                            active_plan = replacement_result
                            working_plan = self.get_plan(working_plan["plan_id"])
                            break
                    break
                action_results.append(
                    {
                        "action_id": action["action_id"],
                        "type": action["type"],
                        "status": "success",
                        "result": result,
                    }
                )
                vouchers.extend(self._vouchers(action, result))
        finally:
            self._update_plan(working_plan["plan_id"], working_plan)

        status = self._execution_status(action_results, failed_actions, recovery_results)
        now = iso_now()
        active_plan = self._finalize_active_plan(active_plan, execution_id, status, now)
        execution_result = {
            "execution_id": execution_id,
            "plan_id": plan["plan_id"],
            "trace_id": plan["trace_id"],
            "status": status,
            "action_results": action_results,
            "vouchers": vouchers,
            "failed_actions": failed_actions,
            "recovery_results": recovery_results,
            "user_message": self._user_message(status, recovery_results),
            "created_at": now,
        }
        self._save_execution(execution_result)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.EXECUTOR_LOG,
            "ExecutorService",
            {
                "user_visible_message": self._user_message(status, recovery_results),
                "execution_id": execution_id,
                "status": status,
                "action_count": len(action_results),
            },
            plan_id=plan["plan_id"],
            level="error" if status == "failed" else "warning" if status == "partial" else "info",
        )
        return execution_result, active_plan

    def _execute_recovery_plan(
        self,
        plan: Dict[str, Any],
        idempotency_key: str,
        failed_action_type: Optional[str],
        action_results: List[Dict[str, Any]],
        vouchers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        self._assert_plan_can_execute(plan)
        for action in self._topological_actions(plan):
            if action.get("type") not in EXECUTABLE_TYPES or action.get("status") != "pending":
                continue
            if failed_action_type and action.get("type") != failed_action_type:
                continue
            result = self._execute_action(plan, action, f"{idempotency_key}:updated", {})
            action_results.append(
                {
                    "action_id": action["action_id"],
                    "type": action["type"],
                    "status": "success",
                    "result": result,
                }
            )
            vouchers.extend(self._vouchers(action, result))
        self._update_plan(plan["plan_id"], plan)
        return plan

    def _execute_action(self, plan: Dict[str, Any], action: Dict[str, Any], execution_key: str, request_body: Dict[str, Any]) -> Dict[str, Any]:
        self._assert_action_executable(plan, action)
        now = iso_now()
        action["status"] = "running"
        action["updated_at"] = now
        self._update_plan(plan["plan_id"], plan)
        payload = deepcopy(action.get("payload") or {})
        payload.update(
            {
                "plan_id": plan["plan_id"],
                "action_id": action["action_id"],
                "executable_window_expire_at": (plan.get("executable_window") or {}).get("expire_at"),
            }
        )
        if request_body.get("confirmation_note") and action.get("type") in {"reserve_restaurant", "order_item"}:
            payload.setdefault("note", request_body["confirmation_note"])
        mock_key = f"{execution_key}:{action['action_id']}"
        action_type = action["type"]
        if action_type == "book_activity":
            result = self.mock_api_service.book_activity(plan["trace_id"], action["target_poi_id"], payload, mock_key)
        elif action_type == "reserve_restaurant":
            result = self.mock_api_service.reserve_restaurant(plan["trace_id"], action["target_poi_id"], payload, mock_key)
        elif action_type == "order_item":
            if action.get("target_poi_id"):
                payload.setdefault("poi_id", action["target_poi_id"])
            result = self.mock_api_service.order_item(plan["trace_id"], payload, mock_key)
        elif action_type == "send_message":
            result = self.mock_api_service.send_message(plan["trace_id"], payload, mock_key)
        else:
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, f"unsupported executable ToolAction.type: {action_type}.", "计划动作不完整，请重新生成。", 400, True)
        action["status"] = "success"
        action["result"] = result
        action["error_code"] = None
        action["updated_at"] = iso_now()
        self._update_plan(plan["plan_id"], plan)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.EXECUTOR_LOG,
            "ExecutorService",
            {
                "user_visible_message": self._success_message(action_type),
                "action_id": action["action_id"],
                "tool_name": action_type,
                "status": "success",
            },
            plan_id=plan["plan_id"],
        )
        return result

    def _assert_plan_can_execute(self, plan: Dict[str, Any]) -> None:
        self.validator.validate_plan_contract(plan)
        if plan.get("status") not in {"executable", "confirmed"}:
            raise bad_request("PlanContract.status does not allow execution.")
        can_execute, code, message, recoverable, details = self.verifier_service.can_enter_executor(plan)
        if not can_execute:
            raise AppError(
                code or ErrorCode.VERIFIER_RESULT_INVALID,
                message,
                "当前计划未通过执行前检查，需要先处理风险。",
                409,
                recoverable,
                details,
            )
        expire_at = (plan.get("executable_window") or {}).get("expire_at")
        if not expire_at or self._parse_dt(expire_at) <= now_shanghai():
            raise AppError(
                ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED,
                f"executable_window expired at {expire_at}.",
                "当前可执行窗口已过期，需要重新检查余位和路线。",
                409,
                True,
                {"refresh_api": f"/api/v1/plans/{plan['plan_id']}/refresh-window"},
            )

    def _assert_action_executable(self, plan: Dict[str, Any], action: Dict[str, Any]) -> None:
        if action.get("type") not in EXECUTABLE_TYPES:
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "Executor can only execute executable ToolAction types.", "计划动作不完整，请重新生成。", 400, True)
        missing = [
            field
            for field in ("action_id", "plan_id", "step_id", "type", "payload", "status", "retry_count", "idempotency_key", "created_at", "updated_at")
            if action.get(field) in (None, "")
        ]
        if missing:
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "ToolAction missing required fields.", "计划动作不完整，请重新生成。", 400, True, {"missing_fields": missing})
        if action.get("plan_id") != plan.get("plan_id"):
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "ToolAction.plan_id mismatch.", "计划动作不完整，请重新生成。", 400, True)
        if action.get("status") != "pending":
            raise AppError(ErrorCode.TOOL_ACTION_INVALID, "ToolAction.status must be pending before execution.", "计划动作不完整，请重新生成。", 400, True)
        if action.get("type") in {"book_activity", "reserve_restaurant"}:
            target_poi_id = action.get("target_poi_id")
            if not target_poi_id or not str(target_poi_id).startswith("poi_"):
                raise AppError(ErrorCode.TOOL_ACTION_INVALID, "ToolAction.target_poi_id is required.", "计划动作不完整，请重新生成。", 400, True)

    def _assert_requested_actions_exist(self, plan: Dict[str, Any], requested_action_ids: set[str]) -> None:
        if not requested_action_ids:
            return
        known_action_ids = {action.get("action_id") for action in plan.get("tool_actions", [])}
        unknown = sorted(requested_action_ids - known_action_ids)
        if unknown:
            raise bad_request("execute_action_ids contains unknown action_id.")

    def _actions_to_execute(self, plan: Dict[str, Any], requested_action_ids: set[str], body: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions = []
        for action in self._topological_actions(plan):
            if requested_action_ids and action.get("action_id") not in requested_action_ids:
                continue
            if action.get("type") not in EXECUTABLE_TYPES:
                continue
            if action.get("status") != "pending":
                continue
            if body.get("allow_message_mock_send", True) is False and action.get("type") == "send_message":
                continue
            actions.append(action)
        return actions

    def _topological_actions(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        actions = list(plan.get("tool_actions") or [])
        by_id = {action.get("action_id"): action for action in actions}
        ordered: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def visit(action: Dict[str, Any]) -> None:
            action_id = action.get("action_id")
            if action_id in seen:
                return
            for dep_id in action.get("depends_on") or []:
                dep = by_id.get(dep_id)
                if dep:
                    visit(dep)
            seen.add(action_id)
            ordered.append(action)

        for action in actions:
            visit(action)
        return ordered

    def _mark_action_failed(self, plan: Dict[str, Any], action: Dict[str, Any], exc: AppError) -> Dict[str, Any]:
        action["status"] = "failed"
        action["error_code"] = exc.code.value
        action["updated_at"] = iso_now()
        self._update_plan(plan["plan_id"], plan)
        return {
            "action_id": action["action_id"],
            "type": action["type"],
            "status": "failed",
            "error_code": exc.code.value,
        }

    def _finalize_active_plan(self, plan: Dict[str, Any], execution_id: str, status: str, now: str) -> Dict[str, Any]:
        active = self.get_plan(plan["plan_id"])
        if status in {"success", "recovered"}:
            active["status"] = "completed"
            for step in active.get("timeline", []):
                if step.get("status") in {"planned", "verified"}:
                    step["status"] = "completed"
            active["execution_summary"] = {"execution_id": execution_id, "status": status, "created_at": now}
            active["executable_window"] = {
                "window_minutes": 0,
                "confidence": 1,
                "expire_at": now,
                "reasons": ["已完成Mock执行。"],
                "risk_factors": [],
                "lockable_resources": [],
                "calculated_from": ["executor"],
                "display_message": "计划已完成模拟执行。",
            }
        elif status == "partial":
            active["status"] = "executing"
            active["execution_summary"] = {"execution_id": execution_id, "status": status, "created_at": now}
        else:
            active["status"] = "failed"
            active["execution_summary"] = {"execution_id": execution_id, "status": status, "created_at": now}
        active["updated_at"] = now
        self.validator.validate_plan_contract(active)
        self._update_plan(active["plan_id"], active)
        return active

    def _execution_status(self, action_results: List[Dict[str, Any]], failed_actions: List[Dict[str, Any]], recovery_results: List[Dict[str, Any]]) -> str:
        if recovery_results and any(item.get("status") == "success" for item in recovery_results):
            return "recovered"
        if failed_actions and any(result.get("status") == "success" for result in action_results):
            return "partial"
        if failed_actions:
            return "failed"
        return "success"

    def _vouchers(self, action: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
        vouchers = []
        now = iso_now()
        for field, voucher_type in VOUCHER_FIELDS.items():
            if field not in result:
                continue
            vouchers.append(
                {
                    "type": voucher_type,
                    "value": result[field],
                    "poi_id": result.get("poi_id") or action.get("target_poi_id"),
                    "poi_name": result.get("poi_name"),
                    "display_name": self._voucher_display_name(voucher_type),
                    "mock_only": True,
                    "created_at": result.get("created_at") or now,
                }
            )
        return vouchers

    def _voucher_display_name(self, voucher_type: str) -> str:
        return {
            "booking_id": "模拟预约号",
            "reservation_id": "模拟订座号",
            "queue_number": "模拟排号",
            "order_id": "模拟订单号",
            "message_id": "模拟消息号",
        }.get(voucher_type, "模拟凭证")

    def _success_message(self, action_type: str) -> str:
        return {
            "book_activity": "Mock预约号已生成。",
            "reserve_restaurant": "Mock订座号已生成。",
            "order_item": "Mock订单号已生成。",
            "send_message": "模拟消息已生成。",
        }[action_type]

    def _user_message(self, status: str, recovery_results: List[Dict[str, Any]]) -> str:
        if status == "recovered":
            return "部分Mock执行遇到资源变化，已切换到通过校验的替代计划并生成模拟凭证。"
        if status == "partial":
            return "部分Mock执行已完成，仍有动作需要处理。"
        if status == "failed":
            return "Mock执行未完成，需要刷新窗口或重新生成计划。"
        return "Mock执行已完成，模拟凭证已生成。"

    def _log_executor_failure(self, plan: Dict[str, Any], action: Dict[str, Any], exc: AppError, execution_id: str) -> None:
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.EXECUTOR_LOG,
            "ExecutorService",
            {
                "user_visible_message": exc.user_message,
                "execution_id": execution_id,
                "action_id": action.get("action_id"),
                "tool_name": action.get("type"),
                "status": "failed",
                "error_code": exc.code.value,
            },
            plan_id=plan["plan_id"],
            level="error",
        )

    def _parse_dt(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=now_shanghai().tzinfo)
            return parsed.astimezone(now_shanghai().tzinfo)
        except ValueError as exc:
            raise bad_request("time fields must be ISO 8601.") from exc

    def _update_plan(self, plan_id: str, plan: Dict[str, Any]) -> None:
        payload = self.store.read(self.PLANS_FILE, {"version": "v0.1", "plans": {}, "owners": {}})
        payload.setdefault("plans", {})[plan_id] = plan
        self.store.write(self.PLANS_FILE, payload)

    def _save_execution(self, execution: Dict[str, Any]) -> None:
        payload = self.store.read(self.EXECUTIONS_FILE, {"version": "v0.1", "executions": []})
        executions = payload.setdefault("executions", [])
        if isinstance(executions, list):
            executions.append(execution)
        else:
            executions[execution["execution_id"]] = execution
        self.store.write(self.EXECUTIONS_FILE, payload)
