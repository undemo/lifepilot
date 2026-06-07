from app.rules.recommendation_policy_engine import (
    DEFAULT_RECOMMENDATION_POLICY,
    RecommendationPolicyEngine,
    RecommendationScore,
)


DEFAULT_BRAIN_POLICY = DEFAULT_RECOMMENDATION_POLICY
BrainRecommendationEngine = RecommendationPolicyEngine
BrainScore = RecommendationScore

__all__ = [
    "DEFAULT_BRAIN_POLICY",
    "BrainRecommendationEngine",
    "BrainScore",
]
