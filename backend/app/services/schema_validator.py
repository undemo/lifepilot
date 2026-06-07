from typing import Any, Dict, Iterable

from app.core.constants import ErrorCode, PLAN_VERSION, TraceEventType
from app.core.errors import AppError


class SchemaValidator:
    PLAN_REQUIRED = {
        "plan_id",
        "trace_id",
        "version",
        "status",
        "user_goal",
        "participants",
        "time_window",
        "constraints",
        "timeline",
        "budget",
        "executable_window",
        "risks",
        "backup_plans",
        "tool_actions",
        "verifier_result",
        "created_at",
        "updated_at",
    }

    PLAN_STATUSES = {
        "draft",
        "generated",
        "verifying",
        "verified",
        "executable",
        "expired",
        "confirmed",
        "executing",
        "recovered",
        "completed",
        "failed",
        "cancelled",
    }

    VERIFIER_STATUSES = {"pass", "warning", "fail"}

    def validate_plan_contract(self, plan: Dict[str, Any]) -> None:
        missing = sorted(self.PLAN_REQUIRED - set(plan.keys()))
        if missing:
            raise AppError(
                ErrorCode.PLAN_SCHEMA_INVALID,
                f"PlanContract missing fields: {', '.join(missing)}.",
                "计划结构生成失败，请重试。",
                400,
                True,
                {"missing_fields": missing},
            )
        if not str(plan["plan_id"]).startswith("plan_"):
            self._invalid_plan("plan_id must start with plan_.")
        if not str(plan["trace_id"]).startswith("trace_"):
            self._invalid_plan("trace_id must start with trace_.")
        if plan["version"] != PLAN_VERSION:
            raise AppError(
                ErrorCode.VERSION_NOT_SUPPORTED,
                "plan version is not supported.",
                "当前计划版本暂不支持。",
                400,
                True,
                {"version": plan["version"]},
            )
        if plan["status"] not in self.PLAN_STATUSES:
            self._invalid_plan("PlanContract.status is invalid.")
        if not isinstance(plan["timeline"], list) or not plan["timeline"]:
            raise AppError(
                ErrorCode.PLAN_TIMELINE_INVALID,
                "PlanContract timeline is empty.",
                "这版时间线不可执行，正在调整。",
                422,
                True,
            )
        verifier_status = plan.get("verifier_result", {}).get("status")
        if verifier_status not in self.VERIFIER_STATUSES:
            raise AppError(
                ErrorCode.VERIFIER_RESULT_INVALID,
                "verifier_result.status is invalid.",
                "校验结果异常，请重试。",
                422,
                True,
            )
        self._assert_no_forbidden_trace_fields(plan)

    def validate_trace_event_type(self, event_type: str) -> None:
        allowed = {item.value for item in TraceEventType}
        if event_type not in allowed:
            raise AppError(
                ErrorCode.PLAN_SCHEMA_INVALID,
                f"TraceLog.event_type is not allowed: {event_type}.",
                "系统追踪异常，请重试。",
                400,
                True,
                {"allowed_event_types": sorted(allowed)},
            )

    def _invalid_plan(self, message: str) -> None:
        raise AppError(ErrorCode.PLAN_SCHEMA_INVALID, message, "计划结构生成失败，请重试。", 400, True)

    def _assert_no_forbidden_trace_fields(self, value: Any) -> None:
        for key in self._iter_keys(value):
            normalized = key.lower()
            if normalized in {"mock_call", "prompt_log", "chain_of_thought", "api_key"} or "api_key" in normalized:
                raise AppError(
                    ErrorCode.PLAN_SCHEMA_INVALID,
                    f"forbidden field appears in payload: {key}.",
                    "计划结构包含不可展示信息，请重新生成。",
                    400,
                    True,
                )

    def _iter_keys(self, value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                yield str(key)
                yield from self._iter_keys(child)
        elif isinstance(value, list):
            for item in value:
                yield from self._iter_keys(item)
