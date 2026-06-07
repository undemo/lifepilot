from copy import deepcopy
from typing import Any, Dict, Optional

from app.core.constants import PLAN_VERSION, TraceEventType
from app.core.ids import new_id
from app.core.time import iso_after, iso_now
from app.services.logging_service import LoggingService


class PlanContractBuilder:
    def __init__(self, logging_service: LoggingService) -> None:
        self.logging_service = logging_service

    def to_build_candidate(
        self,
        trace_id: str,
        draft_plan: Dict[str, Any],
        candidate_set: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidate = {
            "candidate_id": "buildcand_primary",
            "draft_id": draft_plan["draft_id"],
            "steps": deepcopy(draft_plan["steps"]),
            "messages": deepcopy(draft_plan.get("messages") or {}),
            "candidate_set": candidate_set,
        }
        if not candidate["steps"]:
            raise ValueError("PlanBuildCandidate.steps is empty.")
        self.logging_service.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "PlanBuildCandidatePrecheck",
            {
                "user_visible_message": "已完成内部候选预检。",
                "step_count": len(candidate["steps"]),
            },
            visible_to_user=False,
        )
        return candidate

    def build_for_verifier(
        self,
        trace_id: str,
        plan_id: str,
        user_goal: Dict[str, Any],
        participants: list[Dict[str, Any]],
        time_window: Dict[str, Any],
        constraints: Dict[str, Any],
        build_candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = iso_now()
        timeline, tool_actions = self._timeline_and_actions(plan_id, constraints, build_candidate["steps"], now)
        backup_plans = self._backup_plans_from_candidates(timeline, build_candidate.get("candidate_set") or {}, constraints)
        return {
            "plan_id": plan_id,
            "trace_id": trace_id,
            "version": PLAN_VERSION,
            "status": "verifying",
            "user_goal": user_goal,
            "participants": participants,
            "time_window": time_window,
            "constraints": constraints,
            "timeline": timeline,
            "budget": self._budget(constraints, build_candidate),
            "executable_window": self._default_window(),
            "risks": [],
            "backup_plans": backup_plans,
            "tool_actions": tool_actions,
            "messages": build_candidate.get("messages") or {},
            "verifier_result": self._default_verifier_result(),
            "recovery_results": [],
            "execution_summary": None,
            "memory_usage": [],
            "social_signals": [],
            "created_at": now,
            "updated_at": now,
        }

    def build_final(
        self,
        trace_id: str,
        preverified_plan: Dict[str, Any],
        verifier_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan = deepcopy(preverified_plan)
        verifier_result = verifier_output["verifier_result"]
        plan["verifier_result"] = verifier_result
        plan["executable_window"] = verifier_output["executable_window"]
        plan["risks"] = verifier_output["risks"]
        plan["status"] = "failed" if verifier_result["status"] == "fail" else "executable"
        step_status = "planned" if verifier_result["status"] == "fail" else "verified"
        for step in plan["timeline"]:
            step["status"] = step_status
        plan["backup_plans"] = self._backup_plans(plan)
        plan["updated_at"] = iso_now()
        self.logging_service.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "PlanContractBuilder",
            {
                "user_visible_message": "已组装完整PlanContract。",
                "plan_id": plan["plan_id"],
                "step_count": len(plan["timeline"]),
                "action_count": len(plan["tool_actions"]),
            },
            plan_id=plan["plan_id"],
            visible_to_user=False,
        )
        return plan

    def repair_once(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        repaired = deepcopy(plan)
        repaired.setdefault("messages", {})
        repaired.setdefault("recovery_results", [])
        repaired.setdefault("execution_summary", None)
        repaired.setdefault("memory_usage", [])
        repaired.setdefault("social_signals", [])
        if repaired.get("verifier_result", {}).get("status") not in {"pass", "warning", "fail"}:
            repaired["verifier_result"] = self._default_verifier_result()
        if not repaired.get("executable_window"):
            repaired["executable_window"] = self._default_window()
        repaired["updated_at"] = iso_now()
        return repaired

    def _timeline_and_actions(
        self,
        plan_id: str,
        constraints: Dict[str, Any],
        draft_steps: list[Dict[str, Any]],
        now: str,
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        timeline = []
        actions = []
        for index, draft_step in enumerate(draft_steps, start=1):
            step_id = f"step_{index:04d}"
            step = self._step(step_id, index, draft_step)
            action = self._action_for_step(plan_id, step, constraints, now)
            if action:
                step["related_tool_action_ids"] = [action["action_id"]]
                actions.append(action)
            timeline.append(step)
        self._link_service_order_targets(timeline, actions)
        return timeline, actions

    def _step(self, step_id: str, order: int, draft_step: Dict[str, Any]) -> Dict[str, Any]:
        route = draft_step.get("estimated_route")
        return {
            "step_id": step_id,
            "order": order,
            "type": draft_step["type"],
            "title": draft_step["title"],
            "description": draft_step.get("description", ""),
            "start_time": draft_step["start_time"],
            "end_time": draft_step["end_time"],
            "duration_minutes": draft_step["duration_minutes"],
            "poi_id": draft_step.get("poi_id"),
            "from_poi_id": draft_step.get("from_poi_id"),
            "to_poi_id": draft_step.get("to_poi_id"),
            "transport_mode": draft_step.get("transport_mode"),
            "estimated_route": route,
            "booking_required": bool(draft_step.get("booking_required", False)),
            "reservation_required": bool(draft_step.get("reservation_required", False)),
            "status": "planned",
            "related_tool_action_ids": [],
            "display_tags": draft_step.get("display_tags", []),
            "user_visible_notes": draft_step.get("user_visible_notes", ""),
        }

    def _action_for_step(
        self,
        plan_id: str,
        step: Dict[str, Any],
        constraints: Dict[str, Any],
        now: str,
    ) -> Optional[Dict[str, Any]]:
        action_type = None
        payload: Dict[str, Any] = {}
        if step["type"] == "activity" and step["booking_required"]:
            action_type = "book_activity"
            payload = {
                "party_size": constraints["party_size"],
                "booking_time": step["start_time"],
            }
        elif step["type"] == "restaurant" and step["reservation_required"]:
            action_type = "reserve_restaurant"
            payload = {
                "party_size": constraints["party_size"],
                "arrival_time": step["start_time"],
            }
        elif step["type"] == "service" and step.get("poi_id"):
            action_type = "order_item"
            payload = {
                "items": [{"name": step["title"], "quantity": 1}],
                "service_time": step["start_time"],
                "party_size": constraints["party_size"],
                "delivery_note": "按时间线送达后续节点。",
            }
        if not action_type:
            return None
        action_id = new_id("act")
        return {
            "action_id": action_id,
            "plan_id": plan_id,
            "step_id": step["step_id"],
            "type": action_type,
            "target_poi_id": step.get("poi_id"),
            "target": None,
            "payload": payload,
            "status": "pending",
            "depends_on": [],
            "retry_count": 0,
            "idempotency_key": f"idem_{plan_id}_{action_id}",
            "result": None,
            "error_code": None,
            "user_visible": True,
            "created_at": now,
            "updated_at": now,
        }

    def _link_service_order_targets(self, timeline: list[Dict[str, Any]], actions: list[Dict[str, Any]]) -> None:
        action_by_id = {action.get("action_id"): action for action in actions}
        for index, step in enumerate(timeline):
            if step.get("type") != "service":
                continue
            action_id = (step.get("related_tool_action_ids") or [None])[0]
            action = action_by_id.get(action_id)
            if not action or action.get("type") != "order_item":
                continue
            next_restaurant = next(
                (
                    candidate
                    for candidate in timeline[index + 1 :]
                    if candidate.get("type") == "restaurant" and candidate.get("poi_id")
                ),
                None,
            )
            target_restaurant = next_restaurant or next(
                (
                    candidate
                    for candidate in reversed(timeline[:index])
                    if candidate.get("type") == "restaurant" and candidate.get("poi_id")
                ),
                None,
            )
            if not target_restaurant:
                continue
            payload = action.setdefault("payload", {})
            payload["delivery_target"] = {
                "step_id": target_restaurant["step_id"],
                "poi_id": target_restaurant["poi_id"],
                "label": target_restaurant["title"],
                "deliver_at": target_restaurant["start_time"],
            }
            payload["delivery_note"] = f"送达{target_restaurant['title']}，和用餐节点合并执行。"

    def _backup_plans_from_candidates(self, timeline: list[Dict[str, Any]], candidate_set: Dict[str, Any], constraints: Dict[str, Any]) -> list[Dict[str, Any]]:
        candidates = candidate_set.get("backup_candidates") or []
        if not candidates:
            return []
        step_by_poi = {
            step.get("poi_id"): step
            for step in timeline
            if step.get("poi_id") and step.get("type") != "transport"
        }
        backups = []
        used_steps: set[str] = set()
        for index, candidate in enumerate(candidates, start=1):
            original_poi_id = candidate.get("original_poi_id")
            step = step_by_poi.get(original_poi_id)
            replacement = candidate.get("poi") or {}
            if not step or not replacement.get("poi_id") or step["step_id"] in used_steps:
                continue
            used_steps.add(step["step_id"])
            budget_multiplier = 1 if step.get("type") == "service" else max(1, int(constraints.get("party_size") or 1))
            budget_delta = round(float(candidate.get("price_delta") or 0) * budget_multiplier, 2)
            status = candidate.get("status") or {}
            queue_delta = int(status.get("queue_minutes") or 0)
            summary = self._backup_summary(step, replacement, candidate, status)
            backups.append(
                {
                    "backup_plan_id": new_id("backup"),
                    "trigger": candidate.get("trigger") or "verifier_risk",
                    "description": summary,
                    "replace_step_id": step["step_id"],
                    "original_poi_id": original_poi_id,
                    "new_poi_id": replacement["poi_id"],
                    "expected_diff": {
                        "route_extra_minutes": int(candidate.get("route_extra_minutes") or 0),
                        "budget_delta": budget_delta,
                        "queue_delta_minutes": queue_delta,
                        "replacement_poi_name": replacement.get("name"),
                        "original_poi_name": step.get("title"),
                        "user_visible_summary": summary,
                    },
                    "verifier_result": {
                        "status": "pass",
                        "score": 0.86 if status.get("risk_level") in {None, "low"} and status.get("backup_matches_queue_preference", True) else 0.72,
                    },
                    "priority": index,
                    "status": "verified",
                }
            )
        return backups[:3]

    def _backup_summary(
        self,
        step: Dict[str, Any],
        replacement: Dict[str, Any],
        candidate: Dict[str, Any],
        status: Dict[str, Any],
    ) -> str:
        name = replacement.get("name") or "同区域备选"
        original = step.get("title") or "当前节点"
        route_extra = int(candidate.get("route_extra_minutes") or 0)
        budget_delta = float(candidate.get("price_delta") or 0)
        if step.get("type") == "restaurant":
            tables = status.get("available_tables")
            queue = status.get("queue_minutes")
            status_text = f"Mock余{tables}桌" if tables is not None else "Mock状态可用"
            if queue is not None:
                status_text += f"，预计等{queue}分钟"
            return f"若{original}余位变化，切换到{name}；{status_text}，转场约增加{route_extra}分钟，人均变化{budget_delta:+.0f}元。"
        if step.get("type") == "activity":
            tickets = status.get("remaining_tickets")
            status_text = f"Mock余票{tickets}张" if tickets is not None else "Mock状态可预约"
            return f"若{original}名额变化，切换到{name}；{status_text}，转场约增加{route_extra}分钟，人均变化{budget_delta:+.0f}元。"
        if step.get("type") == "service":
            return f"若{original}服务档期变化，切换到{name}；Mock服务可用，仍绑定后续用餐节点，总价变化{budget_delta:+.0f}元。"
        return f"若{original}不适合停留，切换到{name}；Mock状态可用，转场约增加{route_extra}分钟。"

    def _budget(self, constraints: Dict[str, Any], build_candidate: Dict[str, Any]) -> Dict[str, Any]:
        poi_map = {
            poi["poi_id"]: poi
            for poi in (build_candidate.get("candidate_set", {}).get("selected_pois") or {}).values()
            if poi
        }
        for poi in build_candidate.get("candidate_set", {}).get("extra_pois") or []:
            if poi and poi.get("poi_id"):
                poi_map[poi["poi_id"]] = poi
        for node in build_candidate.get("candidate_set", {}).get("itinerary_nodes") or []:
            poi = node.get("poi") if isinstance(node, dict) else None
            if poi and poi.get("poi_id"):
                poi_map[poi["poi_id"]] = poi
        party_size = constraints["party_size"]
        items = []
        for step in build_candidate["steps"]:
            poi_id = step.get("poi_id")
            if not poi_id:
                continue
            poi = poi_map.get(poi_id, {})
            price = float(poi.get("price_per_person") or 0)
            if step["type"] in {"activity", "restaurant"}:
                amount = price * party_size
            elif step["type"] == "service":
                amount = price
            else:
                amount = 0
            if amount > 0:
                items.append({"name": step["title"], "amount": amount, "source": "mock_api"})
        estimated_total = round(sum(item["amount"] for item in items), 2)
        return {
            "currency": "CNY",
            "estimated_total": estimated_total,
            "price_per_person": round(estimated_total / party_size, 2) if party_size else None,
            "items": items or [{"name": "低成本节点", "amount": 0, "source": "rule_generated"}],
        }

    def _default_window(self) -> Dict[str, Any]:
        return {
            "window_minutes": 20,
            "confidence": 0.8,
            "expire_at": iso_after(20),
            "reasons": ["等待Verifier刷新Mock状态。"],
            "risk_factors": [],
            "lockable_resources": [],
            "calculated_from": ["rule_generated"],
            "display_message": "正在校验可执行窗口。",
        }

    def _default_verifier_result(self) -> Dict[str, Any]:
        return {
            "status": "pass",
            "score": 0.8,
            "checks": [],
            "failed_checks": [],
            "warnings": [],
            "required_recovery": False,
            "suggestions": [],
            "created_at": iso_now(),
        }

    def _backup_plans(self, plan: Dict[str, Any]) -> list[Dict[str, Any]]:
        existing = list(plan.get("backup_plans") or [])
        if not plan.get("risks"):
            if existing:
                return existing
            return [
                {
                    "backup_plan_id": new_id("backup"),
                    "trigger": "verifier_risk",
                    "description": "PlanB：如果余位、天气或路线变化，先刷新窗口，再切换同区域低强度备选。",
                    "replace_step_id": None,
                    "original_poi_id": None,
                    "new_poi_id": None,
                    "expected_diff": {
                        "route_extra_minutes": 0,
                        "budget_delta": 0,
                        "queue_delta_minutes": 0,
                        "user_visible_summary": "保留同区域、同预算、低强度备选。",
                    },
                    "verifier_result": {
                        "status": plan["verifier_result"]["status"],
                        "score": plan["verifier_result"]["score"],
                    },
                    "priority": 1,
                    "status": "verified",
            }
        ]
        if existing:
            covered_steps = {backup.get("replace_step_id") for backup in existing}
            uncovered_risks = [
                risk
                for risk in plan.get("risks", [])
                if risk.get("related_step_id") and risk.get("related_step_id") not in covered_steps
            ]
            if not uncovered_risks:
                return existing
            first_risk = uncovered_risks[0]
            return existing + [
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
                        "user_visible_summary": "该风险需要刷新状态后确定替代点。",
                    },
                    "verifier_result": {
                        "status": plan["verifier_result"]["status"],
                        "score": plan["verifier_result"]["score"],
                    },
                    "priority": len(existing) + 1,
                    "status": "candidate",
                }
            ]
        first_risk = plan["risks"][0]
        return [
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
                    "status": plan["verifier_result"]["status"],
                    "score": plan["verifier_result"]["score"],
                },
                "priority": 1,
                "status": "candidate",
            }
        ]
