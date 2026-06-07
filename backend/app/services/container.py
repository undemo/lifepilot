from pathlib import Path

from app.services.agent_orchestrator import AgentOrchestrator
from app.rules.poi_feature_store import POIFeatureStore
from app.rules.recommendation_policy_engine import RecommendationPolicyEngine
from app.services.activity_semantic_agent import ActivitySemanticAgent
from app.services.candidate_critic_agent import CandidateCriticAgent
from app.services.candidate_retriever import CandidateRetriever
from app.services.consensus_service import ConsensusService
from app.services.constraint_extractor import ConstraintExtractor
from app.services.feedback_service import FeedbackService
from app.services.food_semantic_agent import FoodSemanticAgent
from app.services.executor_service import ExecutorService
from app.services.explanation_agent import ExplanationAgent
from app.services.gaode_activity_provider import GaodeActivityProvider
from app.services.idempotency_service import IdempotencyService
from app.services.intent_parser import IntentParser
from app.services.latent_intent_interpreter import LatentIntentInterpreter
from app.services.life_memory_service import LifeMemoryService
from app.services.llm_client import LLMClient
from app.services.logging_service import LoggingService
from app.services.mock_api_service import MockAPIService
from app.services.plan_contract_builder import PlanContractBuilder
from app.services.plan_critic_agent import PlanCriticAgent
from app.services.plan_generator import PlanGenerator
from app.services.plan_ranker import PlanRanker
from app.services.plan_repair_agent import PlanRepairAgent
from app.services.plan_service import PlanService
from app.services.response_assembler import ResponseAssembler
from app.services.recovery_service import RecoveryService
from app.services.retrieval_intent_compiler import RetrievalIntentCompiler
from app.services.schema_validator import SchemaValidator
from app.services.verifier_service import VerifierService
from app.storage.json_store import JsonFileStore


class ServiceContainer:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonFileStore(data_dir)
        self.schema_validator = SchemaValidator()
        self.idempotency_service = IdempotencyService(self.store)
        self.logging_service = LoggingService(self.store, self.schema_validator)
        self.life_memory_service = LifeMemoryService(self.store, self.logging_service)
        self.mock_api_service = MockAPIService(self.store, self.logging_service)
        self.verifier_service = VerifierService(
            self.store,
            self.logging_service,
            self.mock_api_service,
        )
        self.recovery_service = RecoveryService(
            self.store,
            self.schema_validator,
            self.logging_service,
            self.idempotency_service,
            self.verifier_service,
            self.mock_api_service,
        )
        self.executor_service = ExecutorService(
            self.store,
            self.schema_validator,
            self.logging_service,
            self.idempotency_service,
            self.verifier_service,
            self.mock_api_service,
            self.recovery_service,
        )
        self.llm_client = LLMClient()
        self.intent_parser = IntentParser(self.logging_service, self.llm_client)
        self.constraint_extractor = ConstraintExtractor(self.logging_service)
        self.latent_intent_interpreter = LatentIntentInterpreter(self.llm_client)
        self.food_semantic_agent = FoodSemanticAgent(data_dir, self.llm_client)
        self.activity_semantic_agent = ActivitySemanticAgent(data_dir, self.llm_client)
        self.retrieval_intent_compiler = RetrievalIntentCompiler()
        self.recommendation_policy_engine = RecommendationPolicyEngine(self.store)
        self.poi_feature_store = POIFeatureStore(self.store)
        self.gaode_activity_provider = GaodeActivityProvider(self.store)
        self.candidate_retriever = CandidateRetriever(
            self.mock_api_service,
            self.logging_service,
            self.recommendation_policy_engine,
            self.poi_feature_store,
            self.gaode_activity_provider,
        )
        self.candidate_critic_agent = CandidateCriticAgent(self.poi_feature_store, self.llm_client)
        self.plan_generator = PlanGenerator(self.logging_service, self.llm_client)
        self.plan_contract_builder = PlanContractBuilder(self.logging_service)
        self.plan_critic_agent = PlanCriticAgent(self.poi_feature_store, self.llm_client)
        self.plan_repair_agent = PlanRepairAgent(self.llm_client, max_repair_attempts=1)
        self.plan_ranker = PlanRanker(self.logging_service)
        self.explanation_agent = ExplanationAgent(self.poi_feature_store, self.llm_client)
        self.response_assembler = ResponseAssembler(self.logging_service)
        self.agent_orchestrator = AgentOrchestrator(
            self.logging_service,
            self.intent_parser,
            self.constraint_extractor,
            self.life_memory_service,
            self.latent_intent_interpreter,
            self.food_semantic_agent,
            self.activity_semantic_agent,
            self.retrieval_intent_compiler,
            self.candidate_retriever,
            self.candidate_critic_agent,
            self.plan_generator,
            self.plan_contract_builder,
            self.verifier_service,
            self.schema_validator,
            self.plan_critic_agent,
            self.plan_repair_agent,
            self.plan_ranker,
            self.explanation_agent,
            self.response_assembler,
        )
        self.plan_service = PlanService(
            self.store,
            self.schema_validator,
            self.logging_service,
            self.idempotency_service,
            self.verifier_service,
            self.agent_orchestrator,
            self.executor_service,
            self.recovery_service,
        )
        self.consensus_service = ConsensusService(
            self.store,
            self.logging_service,
            self.idempotency_service,
            self.plan_service,
        )
        self.feedback_service = FeedbackService(self.store, self.logging_service, self.plan_service, self.life_memory_service)
