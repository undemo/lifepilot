from typing import Any, Dict

from app.core.constants import TraceEventType
from app.services.logging_service import LoggingService


class PlanRanker:
    def __init__(self, logging_service: LoggingService) -> None:
        self.logging_service = logging_service

    def rank(self, trace_id: str, plans: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        ranked = sorted(plans, key=self._score, reverse=True)
        self.logging_service.log(
            trace_id,
            TraceEventType.VERIFIER_LOG,
            "PlanRanker",
            {
                "user_visible_message": "已按验证结果、风险和预算对方案排序。",
                "ranked_plan_ids": [plan["plan_id"] for plan in ranked],
            },
            plan_id=ranked[0]["plan_id"] if ranked else None,
            visible_to_user=False,
        )
        return ranked

    def _score(self, plan: Dict[str, Any]) -> float:
        verifier = plan.get("verifier_result") or {}
        budget = plan.get("budget") or {}
        risk_penalty = len(plan.get("risks") or []) * 0.04
        budget_penalty = float(budget.get("price_per_person") or 0) / 10000
        return float(verifier.get("score") or 0) - risk_penalty - budget_penalty
