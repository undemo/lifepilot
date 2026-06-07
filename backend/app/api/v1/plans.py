import asyncio
import json
import threading
from queue import Queue
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_container
from app.core.constants import ErrorCode, TraceEventType
from app.core.context import RequestContext, get_context
from app.core.errors import AppError
from app.core.responses import error_payload, success_response
from app.schemas.requests import (
    PlanCreateRequest,
    PlanExecuteRequest,
    PlanRecoverRequest,
    PlanRefreshWindowRequest,
    PlanVerifyRequest,
    request_model_dump,
)
from app.services.container import ServiceContainer

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("/create")
def create_plan(
    body: PlanCreateRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.create_plan(
        context.user_id,
        context.trace_id,
        context.idempotency_key,
        request_model_dump(body),
    )
    return success_response(context.trace_id, data)


@router.post("/create/stream")
async def create_plan_stream(
    body: PlanCreateRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    request_body = request_model_dump(body)

    async def stream_events():
        terminal_key = "_stream_terminal"
        queue: Queue = Queue()

        def worker() -> None:
            try:
                data = container.plan_service.create_plan(
                    context.user_id,
                    context.trace_id,
                    context.idempotency_key,
                    request_body,
                )
                queue.put({terminal_key: "complete", "data": data})
            except AppError as exc:
                queue.put({
                    terminal_key: "error",
                    "error": error_payload(
                        exc.code,
                        exc.message,
                        exc.user_message,
                        exc.recoverable,
                        exc.details,
                    ),
                })
            except Exception:
                container.logging_service.log(
                    context.trace_id,
                    TraceEventType.ERROR_LOG,
                    "PlanCreateStream",
                    {
                        "message": "plan create stream failed.",
                        "user_visible_message": "计划生成失败。",
                    },
                    level="error",
                    visible_to_user=False,
                )
                queue.put({
                    terminal_key: "error",
                    "error": error_payload(
                        ErrorCode.INTERNAL_ERROR,
                        "unexpected internal error.",
                        "系统暂时不可用，请稍后重试。",
                        True,
                        {},
                    ),
                })

        with container.logging_service.subscribe(context.trace_id) as log_queue:
            queue = log_queue
            thread = threading.Thread(target=worker, name=f"plan-create-stream-{context.trace_id}", daemon=True)
            thread.start()
            yield _sse("start", {"trace_id": context.trace_id})
            while True:
                item = await asyncio.to_thread(queue.get)
                terminal = item.get(terminal_key) if isinstance(item, dict) else None
                if terminal == "complete":
                    yield _sse("complete", {"trace_id": context.trace_id, "data": item["data"]})
                    break
                if terminal == "error":
                    yield _sse("error", {"trace_id": context.trace_id, "error": item["error"]})
                    break
                event = _stream_event_from_log(item, container.logging_service)
                if event is not None:
                    yield _sse("agent_event", event)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": context.trace_id,
        },
    )


@router.get("/{plan_id}")
def get_plan(
    plan_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.get_plan_payload(plan_id)
    return success_response(data["plan_contract"]["trace_id"], data)


@router.post("/{plan_id}/verify")
def verify_plan(
    plan_id: str,
    body: PlanVerifyRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.verify_plan(plan_id, body.reason or "manual_verify")
    trace_id = container.plan_service.get_plan(plan_id)["trace_id"]
    return success_response(trace_id, data)


@router.post("/{plan_id}/execute")
def execute_plan(
    plan_id: str,
    body: PlanExecuteRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.execute_plan(
        context.user_id,
        plan_id,
        context.idempotency_key,
        request_model_dump(body),
    )
    return success_response(data["execution_result"]["trace_id"], data)


@router.post("/{plan_id}/recover")
def recover_plan(
    plan_id: str,
    body: PlanRecoverRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.recover_plan(
        context.user_id,
        plan_id,
        context.idempotency_key,
        request_model_dump(body),
    )
    updated_plan = data.get("updated_plan_contract") or {}
    trace_id = updated_plan.get("trace_id") or container.plan_service.get_plan(plan_id)["trace_id"]
    return success_response(trace_id, data)


@router.post("/{plan_id}/refresh-window")
def refresh_window(
    plan_id: str,
    body: PlanRefreshWindowRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.plan_service.refresh_window(plan_id, body.reason or "window_expired")
    trace_id = container.plan_service.get_plan(plan_id)["trace_id"]
    return success_response(trace_id, data)


@router.get("/{plan_id}/trace")
def plan_trace(
    plan_id: str,
    visible_only: bool = Query(default=True),
    include_debug: bool = Query(default=False),
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    plan = container.plan_service.get_plan(plan_id)
    events = container.logging_service.list_for_plan(
        plan_id,
        plan["trace_id"],
        visible_only=visible_only or not include_debug,
    )
    return success_response(plan["trace_id"], {"plan_id": plan_id, "events": events})


def _sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _stream_event_from_log(record: Dict[str, Any], logging_service) -> Optional[Dict[str, Any]]:
    if not isinstance(record, dict) or "log_id" not in record:
        return None
    module = str(record.get("module") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    visible = bool(record.get("visible_to_user", False))
    level = str(record.get("level") or "info")
    base = {
        "event_id": record.get("log_id"),
        "created_at": record.get("created_at"),
        "status": "error" if level == "error" else "warning" if level == "warning" else "success",
    }

    if module == "MockAPIService":
        tool_name = str(payload.get("tool_name") or "")
        return {
            **base,
            "phase": "tool",
            "kind": "tool_result",
            "title": "工具返回",
            "message": _friendly_tool_message(tool_name, payload),
        }
    if module == "AgentOrchestrator":
        message = str(payload.get("user_visible_message") or "正在继续规划。")
        if "数字孪生" in message:
            phase = "tool"
            kind = "tool_call"
            title = "调用工具"
        elif "渲染" in message:
            phase = "render"
            kind = "render"
            title = "渲染时间线"
        elif "校验" in message or "检查" in message:
            phase = "verify"
            kind = "verify"
            title = "校验计划"
        else:
            phase = "thinking"
            kind = "thinking"
            title = "正在思考"
        return {**base, "phase": phase, "kind": kind, "title": title, "message": message}
    if module in {
        "LLMIntentAdapter",
        "LatentIntentInterpreter",
        "FoodSemanticAgent",
        "ActivitySemanticAgent",
        "RetrievalIntentCompiler",
        "CandidateCriticAgent",
        "LLMPlanDraftAdapter",
        "PlanCriticAgent",
        "PlanRepairAgent",
        "ExplanationAgent",
    }:
        return {
            **base,
            "phase": "thinking",
            "kind": "thinking_result",
            "title": "模型思考",
            "message": _friendly_agent_message(module, str(record.get("event_type") or "")),
        }
    if module == "IntentParser":
        return {
            **base,
            "phase": "thinking",
            "kind": "thinking_result",
            "title": "目标理解",
            "message": "已识别当前生活场景。",
        }
    if module == "ConstraintExtractor":
        return {
            **base,
            "phase": "thinking",
            "kind": "thinking_result",
            "title": "约束抽取",
            "message": "已抽取人数、时间、预算和节奏偏好。",
        }
    if module == "CandidateRetriever":
        return {
            **base,
            "phase": "tool",
            "kind": "tool_result",
            "title": "工具返回",
            "message": "数字孪生返回可用候选地点、路线和状态快照。",
        }
    if module == "VerifierService":
        verifier_status = str(payload.get("status") or "")
        if verifier_status == "pass":
            verifier_message = "可执行性检查完成。"
            verifier_ui_status = "success"
        elif verifier_status == "fail":
            verifier_message = "一版候选未通过校验，继续保留可执行版本或备选。"
            verifier_ui_status = "warning"
        else:
            verifier_message = "可执行性检查完成，存在需要留意的提醒。"
            verifier_ui_status = "warning"
        return {
            **base,
            "status": verifier_ui_status,
            "phase": "verify",
            "kind": "verify_result",
            "title": "校验完成",
            "message": verifier_message,
        }
    if module in {"PlanBuildCandidatePrecheck", "PlanContractBuilder"}:
        return {
            **base,
            "phase": "render",
            "kind": "structure",
            "title": "结构化时间线",
            "message": "已把草案整理成可校验的时间线。",
        }
    if module == "ResponseAssembler":
        return {
            **base,
            "phase": "render",
            "kind": "render",
            "title": "渲染时间线",
            "message": "已生成页面可展示的计划结果。",
        }
    if not visible:
        return None
    user_event = logging_service.to_user_visible_event(record)
    return {
        **base,
        "phase": _phase_from_event_type(str(record.get("event_type") or "")),
        "kind": "trace",
        "title": _title_from_event_type(str(record.get("event_type") or "")),
        "message": user_event.get("user_visible_message") or "已完成一步规划。",
    }


def _friendly_agent_message(module: str, event_type: str) -> str:
    if event_type == TraceEventType.ERROR_LOG.value:
        return {
            "LLMIntentAdapter": "模型目标理解未返回可用结果，已切换规则兜底。",
            "LatentIntentInterpreter": "隐含偏好分析未返回可用结果，已继续使用显式约束。",
            "FoodSemanticAgent": "餐饮语义分析未返回可用结果，已继续使用规则检索。",
            "ActivitySemanticAgent": "活动语义分析未返回可用结果，已继续使用规则检索。",
            "CandidateCriticAgent": "候选复核未返回可用结果，已保留工具排序。",
            "LLMPlanDraftAdapter": "文案润色未返回可用结果，已使用结构化模板。",
            "PlanCriticAgent": "时间线复核未返回可用结果，已保留校验后计划。",
            "PlanRepairAgent": "自动修复未返回可用结果，已保留可执行备选。",
            "ExplanationAgent": "解释生成未返回可用结果，已保留计划本体。",
        }.get(module, "智能步骤未返回可用结果，已继续规划。")
    return {
        "LLMIntentAdapter": "大模型完成目标理解，不暴露推理链。",
        "LatentIntentInterpreter": "大模型补全隐含偏好，不暴露推理链。",
        "FoodSemanticAgent": "餐饮语义偏好分析完成。",
        "ActivitySemanticAgent": "活动语义偏好分析完成。",
        "RetrievalIntentCompiler": "已把偏好整理为候选检索条件。",
        "CandidateCriticAgent": "已复核候选地点是否贴合目标。",
        "LLMPlanDraftAdapter": "大模型完成时间线文案润色，不改变工具返回的地点。",
        "PlanCriticAgent": "已复核时间线语义一致性。",
        "PlanRepairAgent": "已尝试修复高风险时间线节点。",
        "ExplanationAgent": "已生成用户可见解释摘要。",
    }.get(module, "智能规划步骤完成。")


def _friendly_tool_message(tool_name: str, payload: Dict[str, Any]) -> str:
    if tool_name == "search_poi":
        count = payload.get("count")
        category = _category_label(str(payload.get("category") or ""))
        return f"地点工具返回：找到{count}个{category}候选。"
    if tool_name == "search_restaurant":
        count = payload.get("count")
        return f"餐厅工具返回：找到{count}个餐饮候选。"
    if tool_name == "get_poi_status":
        available = "可用" if payload.get("available") else "存在风险"
        return f"状态工具返回：目标地点当前{available}。"
    if tool_name == "estimate_route":
        minutes = payload.get("duration_minutes")
        traffic = _traffic_label(str(payload.get("traffic_level") or ""))
        return f"路线工具返回：转场约{minutes}分钟，路况{traffic}。"
    if tool_name == "get_weather":
        risk = _risk_label(str(payload.get("outdoor_risk_level") or ""))
        return f"天气工具返回：户外风险{risk}。"
    if tool_name == "get_social_signal_mock":
        return "热度工具返回：已读取模拟口碑和热度信号。"
    if tool_name in {"book_activity", "reserve_restaurant", "order_item", "send_message"}:
        status = "成功" if payload.get("status") == "success" else "失败"
        return f"执行工具返回：{status}。"
    return "工具调用已返回结果。"


def _phase_from_event_type(event_type: str) -> str:
    if event_type in {TraceEventType.TOOL_LOG.value, TraceEventType.POI_LOG.value}:
        return "tool"
    if event_type == TraceEventType.VERIFIER_LOG.value:
        return "verify"
    if event_type == TraceEventType.ERROR_LOG.value:
        return "error"
    return "thinking"


def _title_from_event_type(event_type: str) -> str:
    if event_type in {TraceEventType.TOOL_LOG.value, TraceEventType.POI_LOG.value}:
        return "工具步骤"
    if event_type == TraceEventType.VERIFIER_LOG.value:
        return "校验计划"
    if event_type == TraceEventType.ERROR_LOG.value:
        return "错误"
    return "正在思考"


def _category_label(category: str) -> str:
    return {
        "activity": "活动",
        "restaurant": "餐厅",
        "tail": "收尾",
    }.get(category, "地点")


def _traffic_label(level: str) -> str:
    return {
        "smooth": "通畅",
        "normal": "正常",
        "slow": "偏慢",
        "congested": "拥堵",
    }.get(level, "模拟")


def _risk_label(level: str) -> str:
    return {
        "low": "低",
        "medium": "中",
        "high": "高",
    }.get(level, "可控")
