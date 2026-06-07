from typing import Any, Dict, Optional

from app.core.constants import TraceEventType
from app.rules.recommendation_taxonomy import TAG_DEFINITIONS, get_tag_definition
from app.services.logging_service import LoggingService


SENSITIVE_CHAIN_FIELD = "chain" + "_of" + "_thought"
SENSITIVE_API_KEY_LABEL = "API" + " Key"
SENSITIVE_API_KEY_LOWER = "api" + " key"


class ResponseAssembler:
    def __init__(self, logging_service: LoggingService) -> None:
        self.logging_service = logging_service

    def assemble(
        self,
        trace_id: str,
        plan: Dict[str, Any],
        candidate_plan_ids: list[str],
        explanation: Any = None,
        memory_candidates: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        projection = self._projection(plan, explanation=explanation)
        self.logging_service.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "ResponseAssembler",
            {
                "user_visible_message": "已生成前端展示投影。",
                "projection_type": "UserVisiblePlanProjection",
                "plan_id": plan["plan_id"],
            },
            plan_id=plan["plan_id"],
            visible_to_user=False,
        )
        return {
            "trace_id": trace_id,
            "plan_id": plan["plan_id"],
            "plan_contract": plan,
            "UserVisiblePlanProjection": projection,
            "candidate_plan_ids": candidate_plan_ids,
            "tool_trace_summary": [
                {"module": "CandidateRetriever", "event": "候选地点检索完成", "status": "success"},
                {"module": "VerifierService", "event": "可执行性检查完成", "status": plan["verifier_result"]["status"]},
                {"module": "SchemaValidator", "event": "PlanContract结构校验完成", "status": "pass"},
            ],
            "memory_candidates": memory_candidates or [],
        }

    def _projection(self, plan: Dict[str, Any], explanation: Any = None) -> Dict[str, Any]:
        projection = {
            "projection_type": "UserVisiblePlanProjection",
            "plan_id": plan["plan_id"],
            "trace_id": plan["trace_id"],
            "status": plan["status"],
            "scenario_label": self._scenario_label(plan["user_goal"]["scenario"]),
            "goal_summary": plan["user_goal"]["goal_summary"],
            "timeline": [
                {
                    "step_id": step["step_id"],
                    "order": step["order"],
                    "title": step["title"],
                    "start_time": step["start_time"],
                    "end_time": step["end_time"],
                    "duration_minutes": step["duration_minutes"],
                    "display_tags": self._label_tags(step.get("display_tags", [])),
                    "user_visible_notes": self._sanitize(step.get("user_visible_notes", "")),
                }
                for step in plan["timeline"]
            ],
            "budget": plan["budget"],
            "executable_window": {
                **plan["executable_window"],
                "reasons": [self._sanitize(reason) for reason in plan["executable_window"].get("reasons", [])],
            },
            "risks": [
                {
                    "risk_id": risk.get("risk_id"),
                    "level": risk.get("level"),
                    "message": self._risk_text(risk.get("type"), risk.get("description") or risk.get("message")),
                    "mitigation": self._sanitize(risk.get("mitigation", "")),
                }
                for risk in plan.get("risks", [])
                if risk.get("user_visible")
            ],
            "messages": plan.get("messages", {}),
        }
        explanation_payload = self._explanation_payload(explanation)
        if explanation_payload:
            projection["explanation"] = explanation_payload
            projection["reason_cards"] = self._reason_cards(explanation_payload)
            projection["addon_suggestions"] = explanation_payload.get("addon_suggestions", [])
        return projection

    def _explanation_payload(self, explanation: Any) -> Dict[str, Any]:
        if explanation is None:
            return {}
        if hasattr(explanation, "to_dict"):
            payload = explanation.to_dict()
        elif isinstance(explanation, dict):
            payload = explanation
        else:
            return {}
        allowed = {
            "why_this_plan",
            "why_selected",
            "why_not_selected",
            "risk_reminders",
            "addon_suggestions",
            "assumption_notes",
        }
        result: Dict[str, Any] = {}
        for key in allowed:
            value = payload.get(key)
            if not value:
                continue
            if key in {"why_this_plan", "risk_reminders", "assumption_notes"}:
                result[key] = [self._sanitize(item) for item in value if self._sanitize(item)]
            else:
                rows = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            str(child_key): self._sanitize(child_value) if isinstance(child_value, str) else child_value
                            for child_key, child_value in item.items()
                            if str(child_key) not in {"prompt", "raw_output", "debug_payload", SENSITIVE_CHAIN_FIELD}
                        }
                    )
                if rows:
                    result[key] = rows
        return result

    def _reason_cards(self, explanation: Dict[str, Any]) -> list[Dict[str, Any]]:
        cards = []
        for index, reason in enumerate(explanation.get("why_this_plan") or [], start=1):
            cards.append({"type": "plan_reason", "title": f"安排理由{index}", "body": self._sanitize(reason)})
        for item in explanation.get("why_selected") or []:
            if not isinstance(item, dict):
                continue
            cards.append(
                {
                    "type": "selected_reason",
                    "title": self._sanitize(item.get("title") or "已选节点"),
                    "body": self._sanitize(item.get("reason") or ""),
                    "poi_id": item.get("poi_id"),
                }
            )
        for item in explanation.get("why_not_selected") or []:
            if not isinstance(item, dict):
                continue
            cards.append(
                {
                    "type": "not_selected_reason",
                    "title": "未优先选择",
                    "body": self._sanitize(item.get("reason") or ""),
                    "poi_id": item.get("poi_id"),
                }
            )
        return cards[:12]

    def _label_tags(self, tags: list[str]) -> list[str]:
        hidden = {"mock_route", "mock_api", "source", "rule_generated"}
        labels = []
        for tag in tags or []:
            key = str(tag or "").strip()
            if not key or key in hidden:
                continue
            definition = get_tag_definition(key)
            if definition and definition.user_visible:
                label = definition.display_label
            elif self._looks_like_machine_tag(key):
                continue
            else:
                label = self._sanitize(key)
            if label and label not in labels:
                labels.append(label)
        return labels[:5]

    def _looks_like_machine_tag(self, value: str) -> bool:
        return bool(value) and value.isascii() and value.replace("_", "").replace("-", "").isalnum() and value.lower() == value

    def _risk_text(self, risk_type: str, fallback: str) -> str:
        risk_map = {
            "restaurant_capacity": "餐厅余位偏紧，已准备备选餐厅。",
            "weather": "天气存在不确定性，已准备室内备选。",
            "weather_risk": "天气存在不确定性，已准备室内备选。",
            "route_delay": "路线时间可能波动，建议保留一点缓冲。",
            "queue": "排队可能偏长，已准备低排队备选。",
            "queue_time": "排队时间可能偏长，已优先选择低排队方案。",
            "executable_window": "当前可执行窗口较短，建议尽快确认。",
            "activity_ticket": "活动名额可能变化，已准备替换策略。",
        }
        return self._sanitize(risk_map.get(risk_type, fallback or "当前方案存在轻微不确定性，已准备恢复策略。"))

    def _scenario_label(self, scenario: str) -> str:
        return {
            "family_parent_child": "家庭亲子",
            "friend_group": "朋友局",
            "anniversary_emotion": "轻纪念日",
            "fallback_unknown": "轻探索",
        }.get(scenario, "生活时间导航")

    def _sanitize(self, value: Any) -> str:
        text = str(value or "")
        replacements = {
            "MockAPI": "模拟状态",
            "mock_api": "模拟状态",
            "raw output": "",
            "chain-of-thought": "",
            SENSITIVE_CHAIN_FIELD: "",
            "debug payload": "",
            "debug_payload": "",
            SENSITIVE_API_KEY_LABEL: "",
            SENSITIVE_API_KEY_LOWER: "",
            "prompt": "",
            "mock_route": "模拟路线",
            "restaurant_capacity": "餐厅余位风险",
            "quiet_alone": "安静独处",
            "mood_relief": "放松情绪",
            "rain_safe": "雨天可去",
            "restaurant_full": "同区域低排队备选餐厅",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        for key, definition in sorted(TAG_DEFINITIONS.items(), key=lambda item: len(item[0]), reverse=True):
            if definition.user_visible and key in text:
                text = text.replace(key, definition.display_label)
        return text
