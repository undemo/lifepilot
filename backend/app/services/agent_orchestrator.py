from typing import Any, Dict, Optional

from app.core.constants import ErrorCode, TraceEventType
from app.core.errors import AppError
from app.core.ids import new_id
from app.services.activity_semantic_agent import ActivitySemanticAgent
from app.services.candidate_critic_agent import CandidateCriticAgent
from app.services.candidate_retriever import CandidateRetriever
from app.services.constraint_extractor import ConstraintExtractor
from app.services.explanation_agent import ExplanationAgent
from app.services.food_semantic_agent import FoodSemanticAgent
from app.services.intent_parser import IntentParser
from app.services.latent_intent_interpreter import LatentIntentInterpreter
from app.services.life_memory_service import LifeMemoryService
from app.services.logging_service import LoggingService
from app.services.plan_contract_builder import PlanContractBuilder
from app.services.plan_critic_agent import PlanCriticAgent
from app.services.plan_generator import PlanGenerator
from app.services.plan_ranker import PlanRanker
from app.services.plan_repair_agent import PlanRepairAgent
from app.services.retrieval_intent_compiler import RetrievalIntentCompiler
from app.services.response_assembler import ResponseAssembler
from app.services.schema_validator import SchemaValidator
from app.services.verifier_service import VerifierService


class AgentOrchestrator:
    def __init__(
        self,
        logging_service: LoggingService,
        intent_parser: IntentParser,
        constraint_extractor: ConstraintExtractor,
        life_memory_service: Optional[LifeMemoryService],
        latent_intent_interpreter: Optional[LatentIntentInterpreter],
        food_semantic_agent: Optional[FoodSemanticAgent],
        activity_semantic_agent: Optional[ActivitySemanticAgent],
        retrieval_intent_compiler: Optional[RetrievalIntentCompiler],
        candidate_retriever: CandidateRetriever,
        candidate_critic_agent: Optional[CandidateCriticAgent],
        plan_generator: PlanGenerator,
        plan_contract_builder: PlanContractBuilder,
        verifier_service: VerifierService,
        schema_validator: SchemaValidator,
        plan_critic_agent: Optional[PlanCriticAgent],
        plan_repair_agent: Optional[PlanRepairAgent],
        plan_ranker: PlanRanker,
        explanation_agent: Optional[ExplanationAgent],
        response_assembler: ResponseAssembler,
    ) -> None:
        self.logging_service = logging_service
        self.intent_parser = intent_parser
        self.constraint_extractor = constraint_extractor
        self.life_memory_service = life_memory_service
        self.latent_intent_interpreter = latent_intent_interpreter
        self.food_semantic_agent = food_semantic_agent
        self.activity_semantic_agent = activity_semantic_agent
        self.retrieval_intent_compiler = retrieval_intent_compiler
        self.candidate_retriever = candidate_retriever
        self.candidate_critic_agent = candidate_critic_agent
        self.plan_generator = plan_generator
        self.plan_contract_builder = plan_contract_builder
        self.verifier_service = verifier_service
        self.schema_validator = schema_validator
        self.plan_critic_agent = plan_critic_agent
        self.plan_repair_agent = plan_repair_agent
        self.plan_ranker = plan_ranker
        self.explanation_agent = explanation_agent
        self.response_assembler = response_assembler

    def create_plan(
        self,
        user_id: str,
        trace_id: str,
        input_text: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.logging_service.log(
            trace_id,
            TraceEventType.INPUT_LOG,
            "InputGateway",
            {
                "user_visible_message": "已收到用户目标。",
                "input_length": len(input_text),
            },
        )
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "AgentOrchestrator",
            {
                "user_visible_message": "大模型正在理解目标和偏好。"
                if self._llm_enabled()
                else "正在理解目标和偏好。",
                "llm_enabled": self._llm_enabled(),
            },
        )
        user_goal = self.intent_parser.parse(trace_id, input_text, body.get("scenario_hint"))
        extracted = self.constraint_extractor.extract(trace_id, input_text, user_goal, body, user_id)
        extracted = self._prepare_memory_context(user_id, trace_id, input_text, user_goal, extracted, body)
        latent_intent = self._interpret_latent_intent(trace_id, input_text, user_goal, extracted["constraints"])
        if latent_intent is not None:
            extracted.setdefault("_internal_intelligence", {})["latent_intent"] = latent_intent.to_dict()
        food_intent = self._interpret_food_intent(trace_id, input_text, extracted["constraints"], latent_intent)
        if food_intent is not None:
            extracted.setdefault("_internal_intelligence", {})["food_intent"] = food_intent.to_dict()
        activity_intent = self._interpret_activity_intent(trace_id, input_text, extracted["constraints"], latent_intent)
        if activity_intent is not None:
            extracted.setdefault("_internal_intelligence", {})["activity_intent"] = activity_intent.to_dict()
        machine_intent = self._compile_machine_intent(
            trace_id,
            input_text,
            user_goal,
            extracted["constraints"],
            latent_intent,
            food_intent,
            activity_intent,
        )
        if machine_intent is not None:
            extracted.setdefault("_internal_intelligence", {})["machine_intent"] = machine_intent.to_dict()
        self.logging_service.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "AgentOrchestrator",
            {
                "user_visible_message": "开始调用数字孪生工具检索候选地点。",
                "tool_family": "digital_twin",
            },
        )
        candidate_set = self.candidate_retriever.retrieve(
            trace_id,
            user_goal,
            extracted["constraints"],
            extracted["time_window"],
            machine_intent=machine_intent,
        )
        if not self._has_selected_candidate(candidate_set):
            raise AppError(
                ErrorCode.PLAN_SCHEMA_INVALID,
                "no candidate POI found for current constraints.",
                "没有找到可执行候选，请放宽距离、时间或餐饮条件后重试。",
                400,
                True,
            )
        critic_reports = self._review_candidates(
            trace_id,
            user_goal,
            extracted["constraints"],
            candidate_set,
            latent_intent,
            food_intent,
            machine_intent,
            )
        if critic_reports:
            candidate_set = self.candidate_retriever.apply_critic_reports(candidate_set, [report.to_dict() for report in critic_reports])
            extracted.setdefault("_internal_intelligence", {})["candidate_critic_reports"] = [
                report.to_dict() for report in critic_reports
            ]
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "AgentOrchestrator",
            {
                "user_visible_message": "正在把候选地点组织成时间线草案。",
                "selected_slot_count": len(candidate_set.get("selected_pois") or {}),
            },
        )
        draft_plans = self.plan_generator.generate(
            trace_id,
            user_goal,
            extracted["constraints"],
            extracted["time_window"],
            candidate_set,
        )

        built_plans = []
        for draft_plan in draft_plans:
            self.logging_service.log(
                trace_id,
                TraceEventType.VERIFIER_LOG,
                "AgentOrchestrator",
                {
                    "user_visible_message": "正在检查时间、路线、预算和可执行窗口。",
                    "draft_id": draft_plan.get("draft_id"),
                },
            )
            built_plans.append(
                self._build_verified_plan(
                    trace_id=trace_id,
                    user_goal=user_goal,
                    extracted=extracted,
                    candidate_set=candidate_set,
                    draft_plan=draft_plan,
                )
            )
        ranked = self.plan_ranker.rank(trace_id, built_plans)
        if not ranked:
            raise AppError(
                ErrorCode.PLAN_SCHEMA_INVALID,
                "no valid PlanContract generated.",
                "计划结构生成失败，请重试。",
                400,
                True,
            )
        primary = ranked[0]
        candidate_plan_ids = [plan["plan_id"] for plan in ranked[1:]]
        if candidate_plan_ids:
            primary.setdefault("messages", {})["consensus_candidate_plan_ids"] = [primary["plan_id"], *candidate_plan_ids]
        memory_candidates = self._create_plan_memory_candidates(
            user_id,
            trace_id,
            input_text,
            user_goal,
            extracted,
            primary,
            body,
        )
        explanation = self._generate_explanation(
            trace_id,
            primary,
            user_goal,
            extracted,
            candidate_set,
        )
        self.logging_service.log(
            trace_id,
            TraceEventType.TOOL_LOG,
            "AgentOrchestrator",
            {
                "user_visible_message": "校验通过，开始渲染最终时间线。",
                "plan_id": primary["plan_id"],
                "step_count": len(primary.get("timeline") or []),
            },
            plan_id=primary["plan_id"],
        )
        data = self.response_assembler.assemble(
            trace_id,
            primary,
            [primary["plan_id"], *candidate_plan_ids] if candidate_plan_ids else [],
            explanation=explanation,
            memory_candidates=memory_candidates,
        )
        data["_candidate_plan_contracts"] = ranked[1:]
        return data

    def _llm_enabled(self) -> bool:
        client = getattr(self.intent_parser, "llm_client", None)
        if not client:
            return False
        try:
            return bool(client.snapshot().get("enabled"))
        except Exception:
            return False

    def _prepare_memory_context(
        self,
        user_id: str,
        trace_id: str,
        input_text: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.life_memory_service is None:
            return extracted
        try:
            return self.life_memory_service.prepare_for_planning(
                user_id=user_id,
                trace_id=trace_id,
                raw_text=input_text,
                user_goal=user_goal,
                extracted=extracted,
                use_memory=bool(body.get("use_memory", True)),
            )
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "LifeMemoryService",
                {
                    "message": "life memory retrieval failed; continuing without memory.",
                    "error_type": exc.__class__.__name__,
                    "user_visible_message": "记忆服务暂不可用，本次将不使用长期记忆。",
                },
                level="warning",
            )
            extracted["memory_usage"] = []
            return extracted

    def _create_plan_memory_candidates(
        self,
        user_id: str,
        trace_id: str,
        input_text: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        primary_plan: Dict[str, Any],
        body: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        if self.life_memory_service is None:
            return []
        try:
            return self.life_memory_service.create_candidates_from_input(
                user_id=user_id,
                trace_id=trace_id,
                raw_text=input_text,
                user_goal=user_goal,
                constraints=extracted.get("constraints") or {},
                plan_id=primary_plan.get("plan_id"),
                use_memory=bool(body.get("use_memory", True)),
            )
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "LifeMemoryService",
                {
                    "message": "memory candidate generation failed; continuing without candidates.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return []

    def _has_selected_candidate(self, candidate_set: Dict[str, Any]) -> bool:
        selected = candidate_set.get("selected_pois") if isinstance(candidate_set, dict) else {}
        if not isinstance(selected, dict):
            return False
        return any(isinstance(poi, dict) and poi.get("poi_id") for poi in selected.values())

    def _interpret_latent_intent(
        self,
        trace_id: str,
        input_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ):
        if self.latent_intent_interpreter is None:
            return None
        try:
            latent_intent = self.latent_intent_interpreter.interpret(
                raw_user_text=input_text,
                user_goal=user_goal,
                constraints=constraints,
                recommendation_profile=constraints.get("recommendation_profile") or {},
                dining_preference=constraints.get("dining_preference") or {},
            )
            tag_set = latent_intent.canonical_tag_set
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "LatentIntentInterpreter",
                {
                    "canonical_tags": [tag.value for tag in tag_set.canonical_tags],
                    "inferred_tags": [tag.value for tag in tag_set.inferred_tags],
                    "source_tag_count": len(tag_set.source_tags),
                    "missing_fields": latent_intent.missing_fields,
                },
                visible_to_user=False,
            )
            return latent_intent
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "LatentIntentInterpreter",
                {
                    "message": "latent intent interpretation failed; continuing with legacy flow.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return None

    def _interpret_food_intent(
        self,
        trace_id: str,
        input_text: str,
        constraints: Dict[str, Any],
        latent_intent,
    ):
        if self.food_semantic_agent is None:
            return None
        try:
            canonical_tags = []
            if latent_intent is not None:
                canonical_tags = [tag.value for tag in latent_intent.canonical_tag_set.canonical_tags]
            food_intent = self.food_semantic_agent.analyze(
                raw_user_text=input_text,
                constraints=constraints,
                dining_preference=constraints.get("dining_preference") or {},
                recommendation_profile=constraints.get("recommendation_profile") or {},
                canonical_tags=canonical_tags,
            )
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "FoodSemanticAgent",
                {
                    "retrieval_mode": food_intent.retrieval_mode,
                    "raw_terms": food_intent.raw_terms[:5],
                    "known_dish_ids": food_intent.known_dish_ids[:5],
                    "parent_categories": food_intent.parent_categories[:6],
                    "attribute_counts": {
                        "ingredients": len(food_intent.ingredients),
                        "cooking_methods": len(food_intent.cooking_methods),
                        "flavors": len(food_intent.flavors),
                        "forms": len(food_intent.forms),
                        "scenes": len(food_intent.scenes),
                    },
                    "child_food_required": food_intent.child_food_required,
                    "non_spicy_required": food_intent.non_spicy_required,
                    "low_calorie_required": food_intent.low_calorie_required,
                },
                visible_to_user=False,
            )
            return food_intent
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "FoodSemanticAgent",
                {
                    "message": "food semantic interpretation failed; continuing with legacy flow.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return None

    def _interpret_activity_intent(
        self,
        trace_id: str,
        input_text: str,
        constraints: Dict[str, Any],
        latent_intent,
    ):
        if self.activity_semantic_agent is None:
            return None
        try:
            canonical_tags = []
            if latent_intent is not None:
                canonical_tags = [tag.value for tag in latent_intent.canonical_tag_set.canonical_tags]
            activity_intent = self.activity_semantic_agent.analyze(
                raw_user_text=input_text,
                constraints=constraints,
                recommendation_profile=constraints.get("recommendation_profile") or {},
                canonical_tags=canonical_tags,
            )
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "ActivitySemanticAgent",
                {
                    "retrieval_mode": activity_intent.retrieval_mode,
                    "raw_terms": activity_intent.raw_terms[:5],
                    "activity_type_ids": activity_intent.activity_type_ids[:6],
                    "parent_categories": activity_intent.parent_categories[:6],
                    "attribute_counts": {
                        "facility_types": len(activity_intent.facility_types),
                        "genres": len(activity_intent.genres),
                        "styles": len(activity_intent.styles),
                        "scenes": len(activity_intent.scenes),
                    },
                    "intensity": activity_intent.intensity,
                    "child_suitable_required": activity_intent.child_suitable_required,
                    "elderly_suitable_required": activity_intent.elderly_suitable_required,
                    "quiet_required": activity_intent.quiet_required,
                },
                visible_to_user=False,
            )
            return activity_intent
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "ActivitySemanticAgent",
                {
                    "message": "activity semantic interpretation failed; continuing with legacy flow.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return None

    def _review_candidates(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        candidate_set: Dict[str, Any],
        latent_intent,
        food_intent,
        machine_intent,
    ) -> list:
        if self.candidate_critic_agent is None:
            return []
        try:
            top_candidates = self._critic_top_candidates(candidate_set)
            reports = self.candidate_critic_agent.review(
                user_goal=user_goal,
                constraints=constraints,
                latent_intent=latent_intent,
                food_intent=food_intent,
                machine_intent=machine_intent,
                top_candidates=top_candidates,
                backup_candidates=candidate_set.get("backup_candidates") or [],
            )
            decisions = {}
            for report in reports:
                decisions[report.decision] = decisions.get(report.decision, 0) + 1
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "CandidateCriticAgent",
                {
                    "reviewed_count": len(reports),
                    "decision_counts": decisions,
                    "demoted_poi_ids": [
                        report.poi_id
                        for report in reports
                        if report.decision in {"demote", "backup_only", "reject"} and report.score_delta < 0
                    ][:10],
                },
                visible_to_user=False,
            )
            return reports
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "CandidateCriticAgent",
                {
                    "message": "candidate critic failed; continuing with retriever ranking.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return []

    def _critic_top_candidates(self, candidate_set: Dict[str, Any]) -> list[Dict[str, Any]]:
        items: list[Dict[str, Any]] = []
        seen: set[str] = set()

        def add(poi: Any) -> None:
            if not isinstance(poi, dict):
                return
            poi_id = str(poi.get("poi_id") or "")
            if not poi_id or poi_id in seen:
                return
            seen.add(poi_id)
            items.append(poi)

        for poi in (candidate_set.get("selected_pois") or {}).values():
            add(poi)
        for poi in candidate_set.get("extra_pois") or []:
            add(poi)
        return items

    def _compile_machine_intent(
        self,
        trace_id: str,
        input_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        latent_intent,
        food_intent,
        activity_intent,
    ):
        if self.retrieval_intent_compiler is None:
            return None
        try:
            machine_intent = self.retrieval_intent_compiler.compile(
                raw_user_text=input_text,
                user_goal=user_goal,
                constraints=constraints,
                latent_intent=latent_intent,
                food_intent=food_intent,
                activity_intent=activity_intent,
            )
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "RetrievalIntentCompiler",
                {
                    "canonical_tag_count": len(machine_intent.canonical_tags),
                    "slot_requirement_count": len(machine_intent.slot_requirements),
                    "hard_filter_count": len(machine_intent.hard_filters),
                    "soft_preference_count": len(machine_intent.soft_preferences),
                    "penalty_count": len(machine_intent.penalties),
                    "retrieval_indexes": machine_intent.retrieval_plan.get("indexes", []),
                    "verifier_expectations": machine_intent.verifier_expectations,
                },
                visible_to_user=False,
            )
            return machine_intent
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "RetrievalIntentCompiler",
                {
                    "message": "machine intent compilation failed; continuing with legacy flow.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return None

    def _generate_explanation(
        self,
        trace_id: str,
        final_plan: Dict[str, Any],
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        candidate_set: Dict[str, Any],
    ):
        if self.explanation_agent is None:
            return None
        try:
            latent_intent, food_intent, machine_intent = self._internal_intelligence_objects(extracted)
            internal = extracted.get("_internal_intelligence") or {}
            explanation = self.explanation_agent.explain(
                final_plan_contract=final_plan,
                user_goal=user_goal,
                constraints=extracted["constraints"],
                latent_intent=latent_intent,
                food_intent=food_intent,
                machine_intent=machine_intent,
                selected_candidates=candidate_set,
                critic_reports=internal.get("candidate_critic_reports") or [],
                verifier_notes=self._verifier_notes(final_plan),
                plan_critic_notes=self._plan_critic_notes(final_plan),
            )
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "ExplanationAgent",
                {
                    "why_this_plan_count": len(explanation.why_this_plan),
                    "why_selected_count": len(explanation.why_selected),
                    "why_not_selected_count": len(explanation.why_not_selected),
                    "risk_reminder_count": len(explanation.risk_reminders),
                    "addon_suggestion_count": len(explanation.addon_suggestions),
                },
                plan_id=final_plan.get("plan_id"),
                visible_to_user=False,
            )
            return explanation
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "ExplanationAgent",
                {
                    "message": "explanation generation failed; returning plan without optional explanation.",
                    "error_type": exc.__class__.__name__,
                },
                plan_id=final_plan.get("plan_id"),
                level="warning",
                visible_to_user=False,
            )
            return None

    def _verifier_notes(self, plan: Dict[str, Any]) -> list:
        verifier = plan.get("verifier_result") or {}
        notes = []
        notes.extend(str(item) for item in verifier.get("failed_checks") or [])
        notes.extend(str(item) for item in verifier.get("warnings") or [])
        for risk in plan.get("risks") or []:
            message = risk.get("message") or risk.get("description") or risk.get("mitigation")
            if message:
                notes.append(str(message))
        return notes[:12]

    def _plan_critic_notes(self, plan: Dict[str, Any]) -> list:
        summary = (plan.get("messages") or {}).get("plan_critic_summary") or {}
        if not summary:
            return []
        return [f"计划语义审稿：severity={summary.get('severity')}, issue_count={summary.get('issue_count')}"]

    def _build_verified_plan(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        candidate_set: Dict[str, Any],
        draft_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_id = new_id("plan")
        build_candidate = self.plan_contract_builder.to_build_candidate(trace_id, draft_plan, candidate_set)
        final_plan = self._build_verify_and_validate(
            trace_id,
            plan_id,
            user_goal,
            extracted,
            build_candidate,
        )
        final_plan = self._plan_critic_and_repair(
            trace_id=trace_id,
            user_goal=user_goal,
            extracted=extracted,
            candidate_set=candidate_set,
            draft_plan=draft_plan,
            final_plan=final_plan,
        )
        final_plan["memory_usage"] = extracted.get("memory_usage") or []
        memory_profile = extracted.get("_memory_profile") or {}
        if memory_profile:
            final_plan.setdefault("messages", {})["memory_profile_summary"] = {
                "used_long_term_count": len(final_plan["memory_usage"]),
                "short_term_summary": (memory_profile.get("short_term_profile") or {}).get("summary"),
                "personalization_enabled": bool(memory_profile.get("personalization_enabled", True)),
            }
        return final_plan

    def _build_verify_and_validate(
        self,
        trace_id: str,
        plan_id: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        build_candidate: Dict[str, Any],
        reason: str = "plan_create",
    ) -> Dict[str, Any]:
        preverified = self.plan_contract_builder.build_for_verifier(
            trace_id,
            plan_id,
            user_goal,
            extracted["participants"],
            extracted["time_window"],
            extracted["constraints"],
            build_candidate,
        )
        verifier_output = self.verifier_service.verify_plan_contract(preverified, reason)
        final_plan = self.plan_contract_builder.build_final(trace_id, preverified, verifier_output)
        return self._validate_with_one_repair(trace_id, final_plan)

    def _plan_critic_and_repair(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        candidate_set: Dict[str, Any],
        draft_plan: Dict[str, Any],
        final_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.plan_critic_agent is None:
            return final_plan
        latent_intent, food_intent, machine_intent = self._internal_intelligence_objects(extracted)
        try:
            critic_report = self.plan_critic_agent.review(
                plan_contract=final_plan,
                user_goal=user_goal,
                constraints=extracted["constraints"],
                latent_intent=latent_intent,
                food_intent=food_intent,
                machine_intent=machine_intent,
                verifier_result=final_plan.get("verifier_result") or {},
            )
            self._log_plan_critic(trace_id, final_plan, critic_report)
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "PlanCriticAgent",
                {
                    "message": "plan critic failed; keeping verified plan.",
                    "error_type": exc.__class__.__name__,
                },
                level="warning",
                visible_to_user=False,
            )
            return final_plan
        final_plan.setdefault("messages", {})["plan_critic_summary"] = {
            "severity": critic_report.severity,
            "issue_count": len(critic_report.issues),
        }
        if critic_report.pass_ or critic_report.severity not in {"high"} or self.plan_repair_agent is None:
            return final_plan
        try:
            patch = self.plan_repair_agent.propose_patch(
                plan_contract=final_plan,
                critic_report=critic_report,
                candidate_set=candidate_set,
                repair_attempts=0,
            )
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "PlanRepairAgent",
                {
                    "message": "plan repair patch proposal failed; keeping original verified plan.",
                    "error_type": exc.__class__.__name__,
                },
                plan_id=final_plan.get("plan_id"),
                level="warning",
                visible_to_user=False,
            )
            return self._with_repair_risk_note(final_plan, critic_report, None)
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "PlanRepairAgent",
            {
                "patch_type": patch.patch_type,
                "target_slot": patch.target_slot,
                "replacement_candidate_ids": patch.replacement_candidate_ids[:3],
                "must_reverify": patch.must_reverify,
            },
            plan_id=final_plan.get("plan_id"),
            visible_to_user=False,
        )
        if patch.patch_type != "replace_slot" or not patch.replacement_candidate_ids:
            return self._with_repair_risk_note(final_plan, critic_report, patch)
        try:
            patched_draft, patched_candidate_set = self._apply_plan_repair_patch(draft_plan, candidate_set, final_plan, patch)
            repaired_build_candidate = self.plan_contract_builder.to_build_candidate(trace_id, patched_draft, patched_candidate_set)
            repaired_plan = self._build_verify_and_validate(
                trace_id,
                new_id("plan"),
                user_goal,
                extracted,
                repaired_build_candidate,
                reason="plan_semantic_repair",
            )
            if repaired_plan.get("verifier_result", {}).get("status") == "fail":
                return self._with_repair_risk_note(final_plan, critic_report, patch)
            return repaired_plan
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "PlanRepairAgent",
                {
                    "message": "plan repair failed; keeping original verified plan.",
                    "error_type": exc.__class__.__name__,
                },
                plan_id=final_plan.get("plan_id"),
                level="warning",
                visible_to_user=False,
            )
            return self._with_repair_risk_note(final_plan, critic_report, patch)

    def _internal_intelligence_objects(self, extracted: Dict[str, Any]) -> tuple[Any, Any, Any]:
        internal = extracted.get("_internal_intelligence") or {}
        return internal.get("latent_intent"), internal.get("food_intent"), internal.get("machine_intent")

    def _log_plan_critic(self, trace_id: str, plan: Dict[str, Any], critic_report) -> None:
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "PlanCriticAgent",
            {
                "pass": critic_report.pass_,
                "severity": critic_report.severity,
                "issue_count": len(critic_report.issues),
                "issue_codes": [issue.get("code") for issue in critic_report.issues[:8]],
                "verifier_note_count": len(critic_report.verifier_related_notes),
            },
            plan_id=plan.get("plan_id"),
            visible_to_user=False,
        )

    def _with_repair_risk_note(self, plan: Dict[str, Any], critic_report, patch) -> Dict[str, Any]:
        if plan.get("status") != "executable":
            return plan
        noted = dict(plan)
        noted["risks"] = list(plan.get("risks") or [])
        if critic_report.issues:
            issue = critic_report.issues[0]
            noted["risks"].append(
                {
                    "type": "semantic_fit",
                    "level": "medium" if critic_report.severity == "high" else critic_report.severity,
                    "message": issue.get("message") or "语义适配存在风险。",
                    "related_step_id": issue.get("step_id"),
                    "related_poi_id": issue.get("poi_id"),
                    "mitigation": getattr(patch, "reason", "") or "保留备选，执行前刷新状态。",
                }
            )
        return noted

    def _apply_plan_repair_patch(
        self,
        draft_plan: Dict[str, Any],
        candidate_set: Dict[str, Any],
        final_plan: Dict[str, Any],
        patch,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        from copy import deepcopy

        target_slot = str(patch.target_slot or "")
        if not target_slot:
            raise ValueError("repair patch target_slot is required")
        replacement_id = str((patch.replacement_candidate_ids or [None])[0] or "")
        replacement = self._replacement_candidate(candidate_set, replacement_id)
        if not replacement:
            raise ValueError("repair replacement candidate not found")
        timeline = final_plan.get("timeline") or []
        target_step = next((step for step in timeline if step.get("step_id") == target_slot), None)
        if not target_step:
            raise ValueError("repair target slot not found")
        try:
            draft_index = int(target_step.get("order") or 0) - 1
        except (TypeError, ValueError):
            draft_index = -1
        patched_draft = deepcopy(draft_plan)
        patched_candidate_set = deepcopy(candidate_set)
        if draft_index < 0 or draft_index >= len(patched_draft.get("steps") or []):
            raise ValueError("repair target draft step not found")
        step = patched_draft["steps"][draft_index]
        step["poi_id"] = replacement["poi_id"]
        step["title"] = replacement.get("name") or step.get("title") or "备选地点"
        step["display_tags"] = replacement.get("tags") or step.get("display_tags") or []
        step["user_visible_notes"] = step.get("user_visible_notes") or "已根据语义审稿切换到同类备选。"
        role = str(target_step.get("type") or "")
        selected = patched_candidate_set.setdefault("selected_pois", {})
        if role in {"activity", "restaurant", "tail", "service", "walk"}:
            selected["tail" if role in {"walk", "service"} else role] = replacement
        extras = patched_candidate_set.setdefault("extra_pois", [])
        if replacement["poi_id"] not in {str(item.get("poi_id")) for item in extras if isinstance(item, dict)}:
            extras.append(replacement)
        return patched_draft, patched_candidate_set

    def _replacement_candidate(self, candidate_set: Dict[str, Any], replacement_id: str) -> Optional[Dict[str, Any]]:
        for backup in candidate_set.get("backup_candidates") or []:
            poi = backup.get("poi") if isinstance(backup, dict) else None
            if isinstance(poi, dict) and str(poi.get("poi_id") or "") == replacement_id:
                return poi
        for poi in candidate_set.get("extra_pois") or []:
            if isinstance(poi, dict) and str(poi.get("poi_id") or "") == replacement_id:
                return poi
        for poi in (candidate_set.get("selected_pois") or {}).values():
            if isinstance(poi, dict) and str(poi.get("poi_id") or "") == replacement_id:
                return poi
        return None

    def _validate_with_one_repair(self, trace_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.schema_validator.validate_plan_contract(plan)
            return plan
        except AppError as first_error:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "SchemaValidator",
                {
                    "error_code": first_error.code.value,
                    "message": first_error.message,
                    "repair_attempt": 1,
                },
                plan_id=plan.get("plan_id"),
                level="warning",
                visible_to_user=False,
            )
            repaired = self.plan_contract_builder.repair_once(plan)
            try:
                self.schema_validator.validate_plan_contract(repaired)
                return repaired
            except AppError as second_error:
                self.logging_service.log(
                    trace_id,
                    TraceEventType.ERROR_LOG,
                    "SchemaValidator",
                    {
                        "error_code": second_error.code.value,
                        "message": second_error.message,
                        "repair_attempt": "exhausted",
                    },
                    plan_id=plan.get("plan_id"),
                    level="error",
                    visible_to_user=False,
                )
                raise second_error
