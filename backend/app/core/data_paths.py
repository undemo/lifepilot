from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"

FIXTURES_DIR = DATA_DIR / "fixtures"
RUNTIME_DIR = DATA_DIR / "runtime"

MOCK_POIS_PATH = FIXTURES_DIR / "mock_pois.json"
MOCK_ROUTES_PATH = FIXTURES_DIR / "mock_routes.json"
MOCK_STATUS_PATH = FIXTURES_DIR / "mock_status.json"
MOCK_INVENTORY_PATH = FIXTURES_DIR / "mock_inventory.json"
MOCK_WEATHER_PATH = FIXTURES_DIR / "mock_weather.json"

PLANS_STORE_PATH = RUNTIME_DIR / "plans.json"
CONSENSUS_STORE_PATH = RUNTIME_DIR / "consensus.json"
FEEDBACK_STORE_PATH = RUNTIME_DIR / "feedback.json"
TRACES_STORE_PATH = RUNTIME_DIR / "traces.json"
EXECUTIONS_STORE_PATH = RUNTIME_DIR / "executions.json"
IDEMPOTENCY_STORE_PATH = RUNTIME_DIR / "idempotency.json"
MOCK_IDEMPOTENCY_STORE_PATH = RUNTIME_DIR / "mock_idempotency_store.json"
MEMORIES_STORE_PATH = RUNTIME_DIR / "memories.json"

ACTIVITY_SEMANTICS_PATH = DATA_DIR / "activity_semantics.json"
BENCHMARK_SAMPLES_PATH = DATA_DIR / "benchmark_samples.json"
BRAIN_POLICY_PATH = DATA_DIR / "brain_policy.json"
FOOD_SEMANTICS_PATH = DATA_DIR / "food_semantics.json"
GAODE_LIFEPILOT_RAW_PATH = DATA_DIR / "gaode_lifepilot_raw.json"
GAODE_POI_ENRICHMENT_PATH = DATA_DIR / "gaode_poi_enrichment.json"
GAODE_POI_REVIEW_CANDIDATES_PATH = DATA_DIR / "gaode_poi_review_candidates.json"
GAODE_ROUTE_RAW_RESPONSES_PATH = DATA_DIR / "gaode_route_raw_responses.json"
MOCK_FAILURE_SCENARIOS_PATH = DATA_DIR / "mock_failure_scenarios.json"
MOCK_SOCIAL_SIGNALS_PATH = DATA_DIR / "mock_social_signals.json"
POI_ACTIVITY_ATTRIBUTES_PATH = DATA_DIR / "poi_activity_attributes.json"
POI_FEATURES_PATH = DATA_DIR / "poi_features.json"
POI_FOOD_ATTRIBUTES_PATH = DATA_DIR / "poi_food_attributes.json"
RECOMMENDATION_POLICY_PATH = DATA_DIR / "recommendation_policy.json"
RECOMMENDATION_RANKER_WEIGHTS_PATH = DATA_DIR / "recommendation_ranker_weights.json"
RUNTIME_ACTIVITY_POIS_PATH = RUNTIME_DIR / "runtime_activity_pois.json"

DATA_FILE_PATHS = {
    path.name: path
    for path in (
        MOCK_POIS_PATH,
        MOCK_ROUTES_PATH,
        MOCK_STATUS_PATH,
        MOCK_INVENTORY_PATH,
        MOCK_WEATHER_PATH,
        PLANS_STORE_PATH,
        CONSENSUS_STORE_PATH,
        FEEDBACK_STORE_PATH,
        TRACES_STORE_PATH,
        EXECUTIONS_STORE_PATH,
        IDEMPOTENCY_STORE_PATH,
        MOCK_IDEMPOTENCY_STORE_PATH,
        MEMORIES_STORE_PATH,
        ACTIVITY_SEMANTICS_PATH,
        BENCHMARK_SAMPLES_PATH,
        BRAIN_POLICY_PATH,
        FOOD_SEMANTICS_PATH,
        GAODE_LIFEPILOT_RAW_PATH,
        GAODE_POI_ENRICHMENT_PATH,
        GAODE_POI_REVIEW_CANDIDATES_PATH,
        GAODE_ROUTE_RAW_RESPONSES_PATH,
        MOCK_FAILURE_SCENARIOS_PATH,
        MOCK_SOCIAL_SIGNALS_PATH,
        POI_ACTIVITY_ATTRIBUTES_PATH,
        POI_FEATURES_PATH,
        POI_FOOD_ATTRIBUTES_PATH,
        RECOMMENDATION_POLICY_PATH,
        RECOMMENDATION_RANKER_WEIGHTS_PATH,
        RUNTIME_ACTIVITY_POIS_PATH,
    )
}
