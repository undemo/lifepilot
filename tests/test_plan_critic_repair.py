import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import FoodIntent, MachineIntent, PlanCriticReport, PlanRepairPatch  # noqa: E402
from app.services.agent_orchestrator import AgentOrchestrator  # noqa: E402
from app.services.plan_critic_agent import PlanCriticAgent  # noqa: E402
from app.services.plan_repair_agent import PlanRepairAgent  # noqa: E402


def _machine(tags=None, food_match=None):
    return MachineIntent.parse_payload(
        {
            "canonical_tags": tags or [],
            "global_constraints": {},
            "slot_requirements": [],
            "hard_filters": [],
            "soft_preferences": [],
            "penalties": [],
            "retrieval_plan": {"food_match": food_match} if food_match else {},
            "verifier_expectations": [],
            "explanation_hints": [],
        }
    )


def _food(**kwargs):
    payload = {
        "raw_terms": [],
        "known_dish_ids": [],
        "parent_categories": [],
        "ingredients": [],
        "cooking_methods": [],
        "flavors": [],
        "forms": [],
        "scenes": [],
        "specific_tags_from_existing_taxonomy": [],
        "fallback_query_text": "",
        "retrieval_mode": "unknown",
        "child_food_required": False,
        "non_spicy_required": False,
        "low_calorie_required": False,
    }
    payload.update(kwargs)
    return FoodIntent.parse_payload(payload)


def _plan(*steps):
    return {
        "plan_id": "plan_original",
        "trace_id": "trace_test",
        "status": "executable",
        "timeline": list(steps),
        "verifier_result": {"status": "pass", "score": 0.9, "failed_checks": [], "warnings": []},
        "risks": [],
        "messages": {},
    }


def _step(step_id, step_type, poi_id, title="节点"):
    return {
        "step_id": step_id,
        "order": int(step_id.split("_")[-1]),
        "type": step_type,
        "poi_id": poi_id,
        "title": title,
    }


def _report_code(report, code):
    return any(issue.get("code") == code for issue in report.issues)


def test_plan_critic_flags_child_restaurant_without_child_food():
    agent = PlanCriticAgent()
    agent._feature_for_step = lambda step: {
        "menu_features": {"spicy_level": 0.85, "has_non_spicy": False, "has_child_friendly_food": False},
        "family_features": {"child_food_score": 0.2},
        "queue_features": {},
        "physical_features": {},
        "experience_features": {},
        "child_features": {},
    }

    report = agent.review(
        plan_contract=_plan(_step("step_0001", "restaurant", "poi_spicy")),
        user_goal={},
        constraints={},
        machine_intent=_machine(["WITH_CHILD", "CHILD_AGE_PRESCHOOL", "CHILD_FOOD_REQUIRED"]),
    )

    assert report.pass_ is False
    assert report.severity == "high"
    assert _report_code(report, "CHILD_FOOD_MISSING")
    assert _report_code(report, "NON_SPICY_OPTION_MISSING")


def test_plan_critic_flags_queue_risk():
    agent = PlanCriticAgent()
    agent._feature_for_step = lambda step: {
        "menu_features": {},
        "family_features": {},
        "queue_features": {"queue_risk": 0.9, "avg_wait_minutes_peak": 35},
        "physical_features": {},
        "experience_features": {},
        "child_features": {},
    }

    report = agent.review(
        plan_contract=_plan(_step("step_0001", "restaurant", "poi_queue")),
        user_goal={},
        constraints={},
        machine_intent=_machine(["AVOID_LONG_QUEUE"]),
    )

    assert report.severity == "high"
    assert _report_code(report, "QUEUE_RISK_TOO_HIGH")


def test_plan_critic_flags_low_calorie_mismatch():
    agent = PlanCriticAgent()
    agent._feature_for_step = lambda step: {
        "menu_features": {"oiliness_level": 0.88, "healthy_option_score": 0.2},
        "family_features": {},
        "queue_features": {},
        "physical_features": {},
        "experience_features": {},
        "child_features": {},
    }

    report = agent.review(
        plan_contract=_plan(_step("step_0001", "restaurant", "poi_oily")),
        user_goal={},
        constraints={},
        machine_intent=_machine(["LOW_CALORIE_REQUIRED"]),
    )

    assert report.severity == "high"
    assert _report_code(report, "LOW_CALORIE_MISMATCH")


def test_plan_critic_flags_ignored_long_tail_food():
    agent = PlanCriticAgent()
    agent._feature_for_step = lambda step: {
        "menu_features": {"dish_ids": ["DISH_HOTPOT"], "parent_categories": ["HOTPOT"]},
        "family_features": {},
        "queue_features": {},
        "physical_features": {},
        "experience_features": {},
        "child_features": {},
    }
    food = _food(
        raw_terms=["碳烤菠萝"],
        parent_categories=["BBQ", "LONG_TAIL_SNACK"],
        ingredients=["菠萝"],
        cooking_methods=["炭烤", "烧烤"],
        forms=["烤物"],
        retrieval_mode="long_tail_attribute",
    )

    report = agent.review(
        plan_contract=_plan(_step("step_0001", "restaurant", "poi_hotpot")),
        user_goal={},
        constraints={},
        food_intent=food,
    )

    assert report.severity == "high"
    assert _report_code(report, "FOOD_INTENT_IGNORED")


def test_plan_repair_agent_proposes_replace_slot_from_backup():
    report = PlanCriticReport.parse_payload(
        {
            "pass": False,
            "severity": "high",
            "issues": [{"code": "QUEUE_RISK_TOO_HIGH", "severity": "high", "step_id": "step_0001", "poi_id": "poi_bad", "message": "排队风险高", "repair_hint": "replace_slot"}],
            "repair_instructions": [],
            "verifier_related_notes": [],
        }
    )
    candidate_set = {
        "backup_candidates": [
            {"role": "restaurant", "original_poi_id": "poi_bad", "poi": {"poi_id": "poi_good", "name": "低排队餐厅"}},
        ]
    }

    patch = PlanRepairAgent(max_repair_attempts=1).propose_patch(
        plan_contract={},
        critic_report=report,
        candidate_set=candidate_set,
        repair_attempts=0,
    )

    assert patch.patch_type == "replace_slot"
    assert patch.target_slot == "step_0001"
    assert patch.replacement_candidate_ids == ["poi_good"]
    assert patch.must_reverify is True


def test_plan_repair_agent_respects_max_attempts():
    report = PlanCriticReport.parse_payload(
        {"pass": False, "severity": "high", "issues": [{"repair_hint": "replace_slot"}], "repair_instructions": [], "verifier_related_notes": []}
    )

    patch = PlanRepairAgent(max_repair_attempts=1).propose_patch(
        plan_contract={},
        critic_report=report,
        candidate_set={},
        repair_attempts=1,
    )

    assert patch.patch_type == "fail"
    assert "limit" in patch.reason


class _Logger:
    def log(self, *args, **kwargs):
        return None


class _Builder:
    def to_build_candidate(self, trace_id, draft_plan, candidate_set):
        return {"steps": draft_plan["steps"], "candidate_set": candidate_set}

    def build_for_verifier(self, trace_id, plan_id, user_goal, participants, time_window, constraints, build_candidate):
        timeline = []
        for index, step in enumerate(build_candidate["steps"], start=1):
            timeline.append(
                {
                    "step_id": f"step_{index:04d}",
                    "order": index,
                    "type": step["type"],
                    "title": step["title"],
                    "poi_id": step.get("poi_id"),
                    "status": "planned",
                }
            )
        return {
            "plan_id": plan_id,
            "trace_id": trace_id,
            "status": "verifying",
            "timeline": timeline,
            "messages": {},
            "risks": [],
            "verifier_result": {"status": "pass", "score": 0.8, "failed_checks": [], "warnings": []},
        }

    def build_final(self, trace_id, preverified_plan, verifier_output):
        plan = dict(preverified_plan)
        plan["verifier_result"] = verifier_output["verifier_result"]
        plan["risks"] = verifier_output.get("risks", [])
        plan["status"] = "failed" if verifier_output["verifier_result"]["status"] == "fail" else "executable"
        return plan


class _Verifier:
    def __init__(self, status="pass"):
        self.status = status
        self.calls = 0

    def verify_plan_contract(self, plan, reason="verify"):
        self.calls += 1
        return {
            "verifier_result": {"status": self.status, "score": 0.8, "failed_checks": ["queue_time"] if self.status == "fail" else [], "warnings": []},
            "executable_window": {},
            "risks": [],
        }


class _Schema:
    def validate_plan_contract(self, plan):
        return None


class _Critic:
    def review(self, **kwargs):
        return PlanCriticReport.parse_payload(
            {
                "pass": False,
                "severity": "high",
                "issues": [{"code": "QUEUE_RISK_TOO_HIGH", "severity": "high", "step_id": "step_0001", "poi_id": "poi_bad", "message": "排队风险高", "repair_hint": "replace_slot"}],
                "repair_instructions": [],
                "verifier_related_notes": [],
            }
        )


class _Repair:
    def propose_patch(self, **kwargs):
        return PlanRepairPatch.parse_payload(
            {
                "patch_type": "replace_slot",
                "target_slot": "step_0001",
                "replacement_candidate_ids": ["poi_good"],
                "reason": "use low queue backup",
                "must_reverify": True,
            }
        )


def _orchestrator(verifier_status="pass"):
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.logging_service = _Logger()
    orch.plan_contract_builder = _Builder()
    orch.verifier_service = _Verifier(verifier_status)
    orch.schema_validator = _Schema()
    orch.plan_critic_agent = _Critic()
    orch.plan_repair_agent = _Repair()
    return orch


def test_orchestrator_rebuilds_reverifies_and_accepts_successful_repair():
    orch = _orchestrator("pass")
    final_plan = _plan(_step("step_0001", "restaurant", "poi_bad", "高排队餐厅"))
    draft_plan = {"draft_id": "draft", "steps": [{"type": "restaurant", "title": "高排队餐厅", "poi_id": "poi_bad"}], "messages": {}}
    candidate_set = {
        "selected_pois": {"restaurant": {"poi_id": "poi_bad", "name": "高排队餐厅"}},
        "extra_pois": [],
        "itinerary_nodes": [],
        "backup_candidates": [{"role": "restaurant", "original_poi_id": "poi_bad", "poi": {"poi_id": "poi_good", "name": "低排队餐厅"}}],
    }
    extracted = {"constraints": {}, "participants": [], "time_window": {}, "_internal_intelligence": {}}

    repaired = orch._plan_critic_and_repair(
        trace_id="trace",
        user_goal={},
        extracted=extracted,
        candidate_set=candidate_set,
        draft_plan=draft_plan,
        final_plan=final_plan,
    )

    assert orch.verifier_service.calls == 1
    assert repaired["status"] == "executable"
    assert repaired["timeline"][0]["poi_id"] == "poi_good"


def test_orchestrator_does_not_accept_failed_repair_without_verifier_pass():
    orch = _orchestrator("fail")
    final_plan = _plan(_step("step_0001", "restaurant", "poi_bad", "高排队餐厅"))
    draft_plan = {"draft_id": "draft", "steps": [{"type": "restaurant", "title": "高排队餐厅", "poi_id": "poi_bad"}], "messages": {}}
    candidate_set = {
        "selected_pois": {"restaurant": {"poi_id": "poi_bad", "name": "高排队餐厅"}},
        "extra_pois": [],
        "itinerary_nodes": [],
        "backup_candidates": [{"role": "restaurant", "original_poi_id": "poi_bad", "poi": {"poi_id": "poi_good", "name": "低排队餐厅"}}],
    }
    extracted = {"constraints": {}, "participants": [], "time_window": {}, "_internal_intelligence": {}}

    kept = orch._plan_critic_and_repair(
        trace_id="trace",
        user_goal={},
        extracted=extracted,
        candidate_set=candidate_set,
        draft_plan=draft_plan,
        final_plan=final_plan,
    )

    assert orch.verifier_service.calls == 1
    assert kept["plan_id"] == "plan_original"
    assert kept["timeline"][0]["poi_id"] == "poi_bad"
    assert kept["risks"]
