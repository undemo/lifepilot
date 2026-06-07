import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.core.data_paths import TRACES_STORE_PATH  # noqa: E402
from app.schemas.internal_intelligence import PlanCriticReport  # noqa: E402
from app.services.schema_validator import SchemaValidator  # noqa: E402


DEMO_NOW = "2026-05-21T13:30:00+08:00"
FORBIDDEN = ("chain_of_thought", "api_key", "prompt_log", "raw output", "debug payload")


@contextmanager
def _client(llm_client=None):
    old_env = {key: os.environ.get(key) for key in ("LIFEPILOT_DEMO_NOW", "QWEN_ENABLED", "DEEPSEEK_ENABLED")}
    os.environ["LIFEPILOT_DEMO_NOW"] = DEMO_NOW
    os.environ["QWEN_ENABLED"] = "false"
    os.environ["DEEPSEEK_ENABLED"] = "false"
    with tempfile.TemporaryDirectory(prefix="lifepilot_phase10_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        shutil.copytree(ROOT / "backend" / "data", data_dir)
        app = create_app(data_dir)
        if llm_client is not None:
            _install_llm(app.state.container, llm_client)
        api = TestClient(app)
        try:
            yield api, app.state.container
        finally:
            api.close()
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _install_llm(container, llm_client):
    container.llm_client = llm_client
    for service in (
        container.intent_parser,
        container.latent_intent_interpreter,
        container.food_semantic_agent,
        container.plan_generator,
        container.candidate_critic_agent,
        container.plan_critic_agent,
        container.plan_repair_agent,
        container.explanation_agent,
    ):
        if hasattr(service, "llm_client"):
            service.llm_client = llm_client


def _post(api, text, case_id):
    return api.post(
        "/api/v1/plans/create",
        json={
            "input_text": text,
            "use_memory": False,
            "current_time": DEMO_NOW,
            "user_location": {
                "label": "杭州金沙湖地铁站",
                "area": "金沙湖",
                "lat": 30.309,
                "lng": 120.319,
            },
        },
        headers={
            "X-Trace-Id": f"trace_phase10_{case_id}",
            "X-Idempotency-Key": f"idem_phase10_{case_id}",
        },
    )


def _assert_contract_compatible(payload):
    assert payload["success"] is True
    data = payload["data"]
    plan = data["plan_contract"]
    SchemaValidator().validate_plan_contract(plan)
    assert data["plan_id"] == plan["plan_id"]
    assert data["UserVisiblePlanProjection"]["plan_id"] == plan["plan_id"]
    assert "candidate_plan_ids" in data
    assert "tool_trace_summary" in data
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in serialized
    return data, plan


def _logs(container, trace_id):
    return [
        log
        for log in container.store.read(TRACES_STORE_PATH, {"version": "v0.1", "logs": []}).get("logs", [])
        if log.get("trace_id") == trace_id
    ]


def _payload_for(logs, module):
    for log in logs:
        if log.get("module") == module:
            return log.get("payload") or {}
    return {}


def test_llm_disabled_full_flow_records_internal_intelligence_and_keeps_api_compatible():
    text = "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾"
    with _client() as (api, container):
        response = _post(api, text, "llm_disabled")
        assert response.status_code == 200, response.text
        data, plan = _assert_contract_compatible(response.json())
        projection = data["UserVisiblePlanProjection"]
        assert "explanation" in projection
        assert "reason_cards" in projection

        logs = _logs(container, plan["trace_id"])
        modules = {log.get("module") for log in logs}
        assert {
            "LatentIntentInterpreter",
            "FoodSemanticAgent",
            "RetrievalIntentCompiler",
            "CandidateCriticAgent",
            "PlanCriticAgent",
            "ExplanationAgent",
        } <= modules

        latent_payload = _payload_for(logs, "LatentIntentInterpreter")
        assert {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "AVOID_LONG_QUEUE", "NEARBY_REQUIRED"} <= set(latent_payload.get("canonical_tags") or [])
        food_payload = _payload_for(logs, "FoodSemanticAgent")
        assert "小龙虾" in food_payload.get("raw_terms", [])
        assert "DISH_CRAYFISH" in food_payload.get("known_dish_ids", [])
        machine_payload = _payload_for(logs, "RetrievalIntentCompiler")
        assert machine_payload.get("soft_preference_count", 0) > 0


class InvalidLLM:
    def snapshot(self):
        return {"enabled": True}

    def generate_json(self, **kwargs):
        return {
            "scenario": "NOT_A_SCENARIO",
            "intent_tags": ["bad_tag"],
            "inferred_tags": ["NOT_A_TAG"],
            "known_dish_ids": ["DISH_NOT_ALLOWED"],
            "parent_categories": ["NOPE"],
            "reports": [{"poi_id": "unknown", "decision": "bad", "score_delta": "bad"}],
            "why_this_plan": [],
            "prompt": "must not leak",
        }


def test_invalid_llm_json_full_flow_falls_back_without_leaking_internal_payloads():
    with _client(InvalidLLM()) as (api, _container):
        response = _post(api, "晚上想吃碳烤菠萝，附近顺便逛逛", "invalid_llm")
        assert response.status_code == 200, response.text
        data, _plan = _assert_contract_compatible(response.json())
        serialized = json.dumps(data, ensure_ascii=False)

        assert "碳烤菠萝" in serialized
        assert "DISH_NOT_ALLOWED" not in serialized
        assert "must not leak" not in serialized


def test_long_tail_food_flow_has_attribute_explanation_and_no_fake_dish_id():
    with _client() as (api, _container):
        response = _post(api, "晚上想吃碳烤菠萝，附近顺便逛逛", "long_tail")
        assert response.status_code == 200, response.text
        data, _plan = _assert_contract_compatible(response.json())
        projection_text = json.dumps(data["UserVisiblePlanProjection"], ensure_ascii=False)

        assert "碳烤菠萝" in projection_text
        assert "菠萝" in projection_text
        assert "长尾" in projection_text
        assert "DISH_CHARCOAL_GRILLED_PINEAPPLE" not in projection_text


class FailingCandidateCritic:
    def review(self, **kwargs):
        raise RuntimeError("candidate critic down")


def test_candidate_critic_failure_does_not_affect_plan_creation():
    with _client() as (api, container):
        container.agent_orchestrator.candidate_critic_agent = FailingCandidateCritic()
        response = _post(api, "想吃火锅，但孩子不能吃辣，别排队", "critic_fail")

        assert response.status_code == 200, response.text
        _assert_contract_compatible(response.json())


class FailingExplanationAgent:
    def explain(self, **kwargs):
        raise RuntimeError("explanation down")


def test_explanation_failure_keeps_plan_contract_and_old_projection():
    with _client() as (api, container):
        container.agent_orchestrator.explanation_agent = FailingExplanationAgent()
        response = _post(api, "我最近学习压力很大，今天下午想出去散散心", "explanation_fail")

        assert response.status_code == 200, response.text
        data, _plan = _assert_contract_compatible(response.json())
        projection = data["UserVisiblePlanProjection"]
        assert "timeline" in projection
        assert "explanation" not in projection


class HighRiskCritic:
    def review(self, **kwargs):
        return PlanCriticReport.parse_payload(
            {
                "pass": False,
                "severity": "high",
                "issues": [
                    {
                        "code": "QUEUE_RISK_TOO_HIGH",
                        "severity": "high",
                        "step_id": "step_0001",
                        "poi_id": "poi_bad",
                        "message": "排队风险高",
                        "repair_hint": "replace_slot",
                    }
                ],
                "repair_instructions": [],
                "verifier_related_notes": [],
            }
        )


class FailingRepairAgent:
    def propose_patch(self, **kwargs):
        raise RuntimeError("repair unavailable")


def test_repair_failure_does_not_bypass_verifier_or_break_create_plan():
    with _client() as (api, container):
        container.agent_orchestrator.plan_critic_agent = HighRiskCritic()
        container.agent_orchestrator.plan_repair_agent = FailingRepairAgent()
        response = _post(api, "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾", "repair_fail")

        assert response.status_code == 200, response.text
        _data, plan = _assert_contract_compatible(response.json())
        assert plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
        assert plan["status"] in {"executable", "failed"}


class NoCandidateRetriever:
    def retrieve(self, *args, **kwargs):
        return {
            "selected_pois": {},
            "extra_pois": [],
            "backup_candidates": [],
            "itinerary_nodes": [],
            "routes": [],
            "status_snapshots": [],
            "weather": {},
            "candidate_counts": {"activity": 0, "restaurant": 0, "tail": 0},
            "planning_order": "activity_first",
        }


def test_no_candidate_path_returns_controlled_error_without_fabricating_poi():
    with _client() as (api, container):
        container.agent_orchestrator.candidate_retriever = NoCandidateRetriever()
        response = _post(api, "只有1小时，但想去三个很远的地方", "no_candidate")
        body = response.json()

        assert response.status_code == 400
        assert body["success"] is False
        assert body["error"]["code"] == "PLAN_SCHEMA_INVALID"
        assert "没有找到可执行候选" in body["error"]["user_message"]
        assert body["data"] is None
