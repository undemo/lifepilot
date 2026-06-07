from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.constants import ErrorCode, PLAN_VERSION, TraceEventType
from app.core.data_paths import EXECUTIONS_STORE_PATH, PLANS_STORE_PATH
from app.core.errors import AppError, bad_request, not_found
from app.core.ids import new_id
from app.core.time import iso_after, iso_now, now_shanghai
from app.services.idempotency_service import IdempotencyService
from app.services.logging_service import LoggingService
from app.services.schema_validator import SchemaValidator
from app.services.verifier_service import VerifierService
from app.storage.json_store import JsonFileStore


class PlanService:
    FILE = PLANS_STORE_PATH
    EXECUTIONS_FILE = EXECUTIONS_STORE_PATH

    def __init__(
        self,
        store: JsonFileStore,
        validator: SchemaValidator,
        logging_service: LoggingService,
        idempotency_service: IdempotencyService,
        verifier_service: VerifierService,
        agent_orchestrator,
        executor_service=None,
        recovery_service=None,
    ) -> None:
        self.store = store
        self.validator = validator
        self.logging_service = logging_service
        self.idempotency_service = idempotency_service
        self.verifier_service = verifier_service
        self.agent_orchestrator = agent_orchestrator
        self.executor_service = executor_service
        self.recovery_service = recovery_service

    def create_plan(self, user_id: str, trace_id: str, idempotency_key: Optional[str], body: Dict[str, Any]) -> Dict[str, Any]:
        input_text = str(body.get("input_text") or "").strip()
        if not input_text:
            raise bad_request("input_text is required.")

        fingerprint = self.idempotency_service.fingerprint({"input_text": input_text, "body": body})
        cached = self.idempotency_service.get(user_id, idempotency_key, "plans.create", fingerprint)
        if cached:
            return cached

        data = self.agent_orchestrator.create_plan(user_id, trace_id, input_text, body)
        candidate_contracts = data.pop("_candidate_plan_contracts", [])
        for candidate_plan in candidate_contracts:
            self._save_plan(user_id, candidate_plan)
        self._save_plan(user_id, data["plan_contract"])
        self.idempotency_service.save(user_id, idempotency_key, "plans.create", fingerprint, data)
        return data

    def get_plan_payload(self, plan_id: str) -> Dict[str, Any]:
        plan = self.get_plan(plan_id)
        return {
            "plan_contract": plan,
            "latest_execution_result": self.latest_execution(plan_id),
            "latest_recovery_results": plan.get("recovery_results", []),
            "candidate_plan_ids": self._candidate_plan_ids_for(plan),
        }

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}})
        plan = payload.get("plans", {}).get(plan_id)
        if not plan:
            raise not_found("plan")
        return plan

    def verify_plan(self, plan_id: str, reason: str = "manual_verify") -> Dict[str, Any]:
        plan = self.get_plan(plan_id)
        now = iso_now()
        verifier_output = self._apply_verifier_output(plan, reason)
        plan["updated_at"] = now
        self.validator.validate_plan_contract(plan)
        self._update_plan(plan_id, plan)
        return {
            "plan_id": plan_id,
            "status": plan["status"],
            "verifier_result": verifier_output["verifier_result"],
            "executable_window": verifier_output["executable_window"],
            "risks": verifier_output["risks"],
            "plan_view": {
                "plan_id": plan_id,
                "status": plan["status"],
                "updated_fields": ["verifier_result", "executable_window", "risks"],
                "updated_at": now,
            },
        }

    def execute_plan(
        self,
        user_id: str,
        plan_id: str,
        idempotency_key: Optional[str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.executor_service is not None:
            return self.executor_service.execute_plan(user_id, plan_id, idempotency_key, body)
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
        if requested_action_ids:
            known_action_ids = {action["action_id"] for action in plan.get("tool_actions", [])}
            unknown_action_ids = sorted(requested_action_ids - known_action_ids)
            if unknown_action_ids:
                raise bad_request("execute_action_ids contains unknown action_id.")
        actions_to_execute = [
            action
            for action in plan.get("tool_actions", [])
            if (not requested_action_ids or action["action_id"] in requested_action_ids)
            and action.get("status") in {"pending", "failed"}
            and (body.get("allow_message_mock_send", True) or action.get("type") != "send_message")
        ]
        execution_id = new_id("exec")
        now = iso_now()
        action_results = []
        vouchers = []
        for action in actions_to_execute:
            action["status"] = "success"
            action["updated_at"] = now
            result = self._mock_action_result(action)
            action["result"] = result
            action_results.append({
                "action_id": action["action_id"],
                "type": action["type"],
                "status": "success",
                "result": result,
            })
            if "reservation_id" in result:
                vouchers.append({
                    "type": "reservation_id",
                    "value": result["reservation_id"],
                    "poi_id": result.get("poi_id"),
                    "display_name": "模拟订座号",
                    "mock_only": True,
                    "created_at": now,
                })
            if "booking_id" in result:
                vouchers.append({
                    "type": "booking_id",
                    "value": result["booking_id"],
                    "poi_id": result.get("poi_id"),
                    "display_name": "模拟预约号",
                    "mock_only": True,
                    "created_at": now,
                })
        plan["status"] = "completed"
        plan["execution_summary"] = {"execution_id": execution_id, "status": "success", "created_at": now}
        plan["updated_at"] = now
        self.validator.validate_plan_contract(plan)
        self._update_plan(plan_id, plan)
        execution_result = {
            "execution_id": execution_id,
            "plan_id": plan_id,
            "trace_id": plan["trace_id"],
            "status": "success",
            "action_results": action_results,
            "vouchers": vouchers,
            "failed_actions": [],
            "recovery_results": [],
            "user_message": "模拟执行已完成。",
            "created_at": now,
        }
        self._save_execution(execution_result)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.EXECUTOR_LOG,
            "ExecutorService",
            {"user_visible_message": "已完成模拟预约和订座。", "execution_id": execution_id},
            plan_id=plan_id,
        )
        data = {
            "execution_id": execution_id,
            "execution_result": execution_result,
            "active_plan_id": plan_id,
            "active_plan_contract": plan,
            "recovery_results": [],
            "action_results": action_results,
        }
        self.idempotency_service.save(user_id, key, "plans.execute", fingerprint, data)
        return data

    def recover_plan(
        self,
        user_id: str,
        plan_id: str,
        idempotency_key: Optional[str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.recovery_service is not None:
            return self.recovery_service.recover_plan(user_id, plan_id, idempotency_key, body)
        key = self.idempotency_service.require_key(idempotency_key, "plans.recover")
        fingerprint = self.idempotency_service.fingerprint({"plan_id": plan_id, "body": body})
        cached = self.idempotency_service.get(user_id, key, "plans.recover", fingerprint)
        if cached:
            return cached

        trigger = body.get("trigger")
        if not trigger:
            raise bad_request("trigger is required.")
        plan = self.get_plan(plan_id)
        updated_plan_id = f"{plan_id}_r1"
        updated = deepcopy(plan)
        updated["plan_id"] = updated_plan_id
        updated["status"] = "executable"
        now = iso_now()
        updated["created_at"] = now
        updated["updated_at"] = now
        for action in updated.get("tool_actions", []):
            action["plan_id"] = updated_plan_id
            action["status"] = "pending"
            action["result"] = None
            action["error_code"] = None
            action["updated_at"] = now
        verifier_output = self._apply_verifier_output(updated, "recovery_verify")
        recovery_result = {
            "recovery_id": new_id("rec"),
            "trigger": trigger,
            "status": "success" if verifier_output["verifier_result"]["status"] in {"pass", "warning"} else "failed",
            "original": {
                "step_id": body.get("failed_step_id"),
                "action_id": body.get("failed_action_id"),
            },
            "replacement": {
                "plan_id": updated_plan_id,
                "strategy": body.get("recovery_strategy") or "replace_poi_same_area",
            },
            "diff": {
                "route_extra_minutes": 0,
                "budget_delta": 0,
                "queue_delta_minutes": 0,
                "user_visible_summary": "已生成可继续执行的替代计划。",
            },
            "updated_plan_id": updated_plan_id,
            "verifier_result": verifier_output["verifier_result"],
            "user_explanation": "原计划执行受阻，已切换到可继续执行的替代版本。",
            "created_at": now,
        }
        plan["status"] = "recovered"
        plan.setdefault("recovery_results", []).append(recovery_result)
        plan["updated_at"] = now
        self.validator.validate_plan_contract(plan)
        self.validator.validate_plan_contract(updated)
        self._update_plan(plan_id, plan)
        self._save_plan(user_id, updated)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.RECOVERY_LOG,
            "RecoveryService",
            {"user_visible_message": "已生成替代计划。", "trigger": trigger, "updated_plan_id": updated_plan_id},
            plan_id=plan_id,
        )
        data = {
            "recovery_result": recovery_result,
            "updated_plan_id": updated_plan_id,
            "updated_plan_contract": updated,
        }
        self.idempotency_service.save(user_id, key, "plans.recover", fingerprint, data)
        return data

    def refresh_window(self, plan_id: str, reason: str = "window_refresh") -> Dict[str, Any]:
        plan = self.get_plan(plan_id)
        now = iso_now()
        plan["status"] = "executable"
        plan["executable_window"]["window_minutes"] = 12
        plan["executable_window"]["confidence"] = 0.78
        plan["executable_window"]["expire_at"] = iso_after(12)
        plan["executable_window"]["display_message"] = "当前方案仍可执行，窗口已刷新。"
        plan["verifier_result"] = {
            "status": "warning",
            "score": 0.78,
            "checks": [],
            "failed_checks": [],
            "warnings": ["window_refreshed"],
            "required_recovery": False,
            "suggestions": ["建议尽快确认。"],
            "created_at": now,
        }
        plan["updated_at"] = now
        self.validator.validate_plan_contract(plan)
        self._update_plan(plan_id, plan)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.TOOL_LOG,
            "MockAPIService",
            {"user_visible_message": "已刷新可执行窗口。", "reason": reason},
            plan_id=plan_id,
        )
        return {
            "plan_id": plan_id,
            "status": plan["status"],
            "executable_window": plan["executable_window"],
            "verifier_result": plan["verifier_result"],
        }

    def latest_execution(self, plan_id: str) -> Optional[Dict[str, Any]]:
        payload = self.store.read(self.EXECUTIONS_FILE, {"version": "v0.1", "executions": []})
        executions = payload.get("executions", [])
        if isinstance(executions, dict):
            items = list(executions.values())
        else:
            items = [item for item in executions if isinstance(item, dict)]
        matches = [item for item in items if item.get("plan_id") == plan_id]
        if not matches:
            return None
        return sorted(matches, key=lambda item: item["created_at"])[-1]

    def _candidate_plan_ids_for(self, plan: Dict[str, Any]) -> List[str]:
        if (plan.get("user_goal") or {}).get("scenario") != "friend_group":
            return []
        messages = plan.get("messages") or {}
        intent_tags = set(str(tag) for tag in (plan.get("user_goal") or {}).get("intent_tags") or [])
        if "consensus" in intent_tags or messages.get("consensus_source_plan_id"):
            return []
        raw = messages.get("consensus_candidate_plan_ids")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, str) and item.startswith("plan_")]
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}})
        trace_id = plan.get("trace_id")
        candidates = [
            item
            for item in payload.get("plans", {}).values()
            if isinstance(item, dict)
            and item.get("trace_id") == trace_id
            and (item.get("user_goal") or {}).get("scenario") == "friend_group"
        ]
        return [item["plan_id"] for item in sorted(candidates, key=lambda item: item.get("created_at", ""))]

    def _build_plan_contract(
        self,
        plan_id: str,
        trace_id: str,
        input_text: str,
        scenario: str,
        user_id: str,
        status: str = "executable",
    ) -> Dict[str, Any]:
        now = iso_now()
        start = iso_after(30)
        end = iso_after(240)
        step_start = iso_after(45)
        step_end = iso_after(165)
        action_id = "act_book_0001"
        return {
            "plan_id": plan_id,
            "trace_id": trace_id,
            "version": PLAN_VERSION,
            "status": status,
            "user_goal": {
                "raw_text": input_text,
                "scenario": scenario,
                "goal_summary": "根据用户目标生成一段可验证、可执行的生活时间线占位计划。",
                "intent_tags": [scenario, "demo_placeholder"],
                "emotion_goal": None,
                "source": "user_input",
                "confidence": 0.8,
            },
            "participants": [
                {
                    "participant_id": "part_user_001",
                    "role": "user",
                    "display_name": user_id,
                    "age": None,
                    "constraints": [],
                    "preference_tags": [],
                }
            ],
            "time_window": {"start_time": start, "end_time": end, "time_flexibility": "medium"},
            "constraints": {
                "party_size": 4 if scenario == "friend_group" else 3,
                "distance_preference": "nearby",
                "budget_max": 400,
                "budget_max_per_person": 100,
                "walking_tolerance": "medium",
                "queue_tolerance": "low",
                "dietary_preference": [],
                "activity_preference": ["light"],
                "weather_sensitive": True,
                "child_friendly_required": scenario == "family_parent_child",
                "indoor_preferred": False,
                "emotion_intensity": "light",
                "time_flexibility": "medium",
                "must_have": [],
                "must_not_have": [],
            },
            "timeline": [
                {
                    "step_id": "step_0001",
                    "order": 1,
                    "type": "activity",
                    "title": "轻松活动占位",
                    "description": "后续接入Agent和MockAPI后替换为真实候选。",
                    "start_time": step_start,
                    "end_time": step_end,
                    "duration_minutes": 120,
                    "poi_id": "poi_activity_003",
                    "from_poi_id": None,
                    "to_poi_id": None,
                    "transport_mode": None,
                    "estimated_route": None,
                    "booking_required": True,
                    "reservation_required": False,
                    "status": "verified",
                    "related_tool_action_ids": [action_id],
                    "display_tags": ["室内", "可预约"],
                    "user_visible_notes": "当前为后端骨架占位计划。",
                }
            ],
            "budget": {
                "currency": "CNY",
                "estimated_total": 320,
                "price_per_person": 80,
                "items": [{"name": "活动预算", "amount": 320, "source": "rule_generated"}],
            },
            "executable_window": {
                "window_minutes": 20,
                "confidence": 0.8,
                "expire_at": iso_after(20),
                "reasons": ["占位计划已通过基础结构校验"],
                "risk_factors": [],
                "lockable_resources": ["activity_booking"],
                "calculated_from": ["rule_generated"],
                "display_message": "当前方案可执行窗口约20分钟。",
            },
            "risks": [],
            "backup_plans": [],
            "tool_actions": [
                {
                    "action_id": action_id,
                    "plan_id": plan_id,
                    "step_id": "step_0001",
                    "type": "book_activity",
                    "target_poi_id": "poi_activity_003",
                    "target": None,
                    "payload": {"party_size": 4 if scenario == "friend_group" else 3, "booking_time": step_start},
                    "status": "pending",
                    "depends_on": [],
                    "retry_count": 0,
                    "idempotency_key": f"idem_{action_id}",
                    "result": None,
                    "error_code": None,
                    "user_visible": True,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            "messages": {},
            "verifier_result": {
                "status": "pass",
                "score": 0.86,
                "checks": [],
                "failed_checks": [],
                "warnings": [],
                "required_recovery": False,
                "suggestions": [],
                "created_at": now,
            },
            "recovery_results": [],
            "execution_summary": None,
            "memory_usage": [],
            "social_signals": [],
            "created_at": now,
            "updated_at": now,
        }

    def _infer_scenario(self, input_text: str) -> str:
        if "朋友" in input_text or "投票" in input_text:
            return "friend_group"
        if "纪念" in input_text or "生日" in input_text:
            return "anniversary_emotion"
        if "孩子" in input_text or "亲子" in input_text:
            return "family_parent_child"
        return "fallback_unknown"

    def _assert_plan_can_execute(self, plan: Dict[str, Any]) -> None:
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
        expire_at = plan.get("executable_window", {}).get("expire_at")
        if expire_at and self._parse_dt(expire_at) <= now_shanghai():
            raise AppError(
                ErrorCode.PLAN_EXECUTABLE_WINDOW_EXPIRED,
                "plan executable window expired.",
                "当前窗口已过期，需要重新检查。",
                409,
                True,
            )

    def _apply_verifier_output(self, plan: Dict[str, Any], reason: str) -> Dict[str, Any]:
        verifier_output = self.verifier_service.verify_plan_contract(plan, reason)
        plan["verifier_result"] = verifier_output["verifier_result"]
        plan["executable_window"] = verifier_output["executable_window"]
        plan["risks"] = verifier_output["risks"]
        if verifier_output["verifier_result"]["status"] == "fail":
            plan["status"] = "failed"
        else:
            plan["status"] = "executable"
        self._sync_backup_plans_from_risks(plan)
        return verifier_output

    def _sync_backup_plans_from_risks(self, plan: Dict[str, Any]) -> None:
        verifier_status = (plan.get("verifier_result") or {}).get("status")
        if verifier_status not in {"warning", "fail"}:
            return
        if plan.get("backup_plans"):
            return
        risks = plan.get("risks") or []
        first_risk = risks[0] if risks else {}
        plan["backup_plans"] = [
            {
                "backup_plan_id": new_id("backup"),
                "trigger": first_risk.get("type") or "verifier_risk",
                "description": first_risk.get("mitigation") or "PlanB：刷新状态或切换同区域备选。",
                "replace_step_id": first_risk.get("related_step_id"),
                "original_poi_id": first_risk.get("related_poi_id"),
                "new_poi_id": None,
                "expected_diff": {
                    "route_extra_minutes": 0,
                    "budget_delta": 0,
                    "queue_delta_minutes": 0,
                    "user_visible_summary": "确认前保留同区域、同预算备选。",
                },
                "verifier_result": {
                    "status": verifier_status,
                    "score": (plan.get("verifier_result") or {}).get("score", 0),
                },
                "priority": 1,
                "status": "candidate",
            }
        ]

    def _parse_dt(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise bad_request("time fields must be ISO 8601.") from exc

    def _mock_action_result(self, action: Dict[str, Any]) -> Dict[str, Any]:
        now = iso_now()
        if action["type"] == "reserve_restaurant":
            return {
                "reservation_id": f"mock_reservation_{action['action_id']}",
                "poi_id": action.get("target_poi_id"),
                "mock_only": True,
                "created_at": now,
            }
        if action["type"] == "order_item":
            return {
                "order_id": f"mock_order_{action['action_id']}",
                "poi_id": action.get("target_poi_id"),
                "mock_only": True,
                "created_at": now,
            }
        if action["type"] == "send_message":
            return {
                "message_id": f"mock_msg_{action['action_id']}",
                "mock_only": True,
                "created_at": now,
            }
        return {
            "booking_id": f"mock_booking_{action['action_id']}",
            "poi_id": action.get("target_poi_id"),
            "mock_only": True,
            "created_at": now,
        }

    def _save_plan(self, user_id: str, plan: Dict[str, Any]) -> None:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}, "owners": {}})
        payload.setdefault("plans", {})[plan["plan_id"]] = plan
        payload.setdefault("owners", {})[plan["plan_id"]] = user_id
        self.store.write(self.FILE, payload)

    def _update_plan(self, plan_id: str, plan: Dict[str, Any]) -> None:
        payload = self.store.read(self.FILE, {"version": "v0.1", "plans": {}, "owners": {}})
        payload.setdefault("plans", {})[plan_id] = plan
        self.store.write(self.FILE, payload)

    def _save_execution(self, execution: Dict[str, Any]) -> None:
        payload = self.store.read(self.EXECUTIONS_FILE, {"version": "v0.1", "executions": []})
        executions = payload.setdefault("executions", [])
        if isinstance(executions, list):
            executions.append(execution)
        else:
            executions[execution["execution_id"]] = execution
        self.store.write(self.EXECUTIONS_FILE, payload)
