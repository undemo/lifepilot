from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from app.schemas.internal_intelligence import PlanCriticReport, PlanRepairPatch


class PlanRepairAgent:
    """Generate local repair patches for PlanCritic issues."""

    def __init__(self, llm_client: Optional[Any] = None, max_repair_attempts: int = 1) -> None:
        self.llm_client = llm_client
        self.max_repair_attempts = max(0, int(max_repair_attempts or 1))

    def propose_patch(
        self,
        *,
        plan_contract: Dict[str, Any],
        critic_report: Any,
        candidate_set: Dict[str, Any],
        repair_attempts: int = 0,
    ) -> PlanRepairPatch:
        if repair_attempts >= self.max_repair_attempts:
            return PlanRepairPatch.fallback(reason="repair attempt limit reached")
        report = self._report(critic_report)
        if report.pass_ or report.severity in {"none", "low"}:
            return PlanRepairPatch.fallback(reason="no blocking semantic issue")
        issue = self._first_repairable_issue(report.issues)
        if not issue:
            return PlanRepairPatch.fallback(reason="no repairable issue")
        patch_type = str(issue.get("repair_hint") or "fail")
        if patch_type == "replace_slot":
            replacement_ids = self._replacement_ids(issue, candidate_set)
            if not replacement_ids:
                return PlanRepairPatch.fallback(
                    patch_type="fail",
                    target_slot=issue.get("step_id"),
                    reason=f"no backup candidate for {issue.get('code')}",
                    must_reverify=True,
                )
            payload = {
                "patch_type": "replace_slot",
                "target_slot": issue.get("step_id"),
                "replacement_candidate_ids": replacement_ids[:3],
                "reason": issue.get("message") or issue.get("code") or "semantic repair",
                "must_reverify": True,
            }
            return PlanRepairPatch.parse_payload(payload, fallback_on_error=True, **payload)
        if patch_type == "add_addon":
            payload = {
                "patch_type": "add_addon",
                "target_slot": issue.get("step_id"),
                "replacement_candidate_ids": [],
                "reason": issue.get("message") or "add-on suggestion required",
                "must_reverify": True,
            }
            return PlanRepairPatch.parse_payload(payload, fallback_on_error=True, **payload)
        if patch_type == "reorder_slots":
            payload = {
                "patch_type": "reorder_slots",
                "target_slot": issue.get("step_id"),
                "replacement_candidate_ids": [],
                "reason": issue.get("message") or "slot order issue",
                "must_reverify": True,
            }
            return PlanRepairPatch.parse_payload(payload, fallback_on_error=True, **payload)
        return PlanRepairPatch.fallback(target_slot=issue.get("step_id"), reason=issue.get("message") or "unsupported repair")

    def _report(self, critic_report: Any) -> PlanCriticReport:
        if isinstance(critic_report, PlanCriticReport):
            return critic_report
        if isinstance(critic_report, dict):
            return PlanCriticReport.parse_payload(critic_report, fallback_on_error=True, **critic_report)
        return PlanCriticReport.fallback()

    def _first_repairable_issue(self, issues: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        ranked = {"high": 0, "medium": 1, "low": 2}
        candidates = [issue for issue in issues or [] if isinstance(issue, dict)]
        candidates.sort(key=lambda issue: ranked.get(str(issue.get("severity") or "low"), 9))
        for issue in candidates:
            if issue.get("repair_hint") in {"replace_slot", "add_addon", "reorder_slots", "adjust_time"}:
                return issue
        return candidates[0] if candidates else None

    def _replacement_ids(self, issue: Dict[str, Any], candidate_set: Dict[str, Any]) -> list[str]:
        original_poi_id = str(issue.get("poi_id") or "")
        target_step = str(issue.get("step_id") or "")
        ids: list[str] = []
        for backup in candidate_set.get("backup_candidates") or []:
            if not isinstance(backup, dict):
                continue
            if original_poi_id and str(backup.get("original_poi_id") or "") != original_poi_id:
                continue
            poi = backup.get("poi") if isinstance(backup.get("poi"), dict) else {}
            poi_id = str(poi.get("poi_id") or "")
            if poi_id and poi_id not in ids:
                ids.append(poi_id)
        if ids:
            return ids
        role_hint = self._role_from_step_id(target_step, candidate_set)
        for backup in candidate_set.get("backup_candidates") or []:
            if not isinstance(backup, dict) or (role_hint and backup.get("role") != role_hint):
                continue
            poi = backup.get("poi") if isinstance(backup.get("poi"), dict) else {}
            poi_id = str(poi.get("poi_id") or "")
            if poi_id and poi_id not in ids:
                ids.append(poi_id)
        return ids

    def _role_from_step_id(self, target_step: str, candidate_set: Dict[str, Any]) -> str:
        if not target_step:
            return ""
        try:
            index = int(target_step.split("_")[-1]) - 1
        except (TypeError, ValueError):
            return ""
        nodes = candidate_set.get("itinerary_nodes") or []
        if 0 <= index < len(nodes):
            role = nodes[index].get("role") if isinstance(nodes[index], dict) else ""
            return str(role or "")
        return ""
