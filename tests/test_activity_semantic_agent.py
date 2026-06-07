import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.activity_semantic_agent import ActivitySemanticAgent  # noqa: E402


def _intent(text, canonical_tags=None, llm_client=None):
    return ActivitySemanticAgent(ROOT / "backend" / "data", llm_client).analyze(
        raw_user_text=text,
        constraints={},
        recommendation_profile={},
        canonical_tags=canonical_tags or [],
    )


def test_badminton_maps_to_sports_activity():
    intent = _intent("这周末和姐姐打羽毛球")

    assert "羽毛球" in intent.raw_terms
    assert "ACTIVITY_BADMINTON" in intent.activity_type_ids
    assert "SPORTS" in intent.parent_categories
    assert "羽毛球馆" in intent.facility_types
    assert intent.intensity == "medium"


def test_esports_maps_to_game_for_roommates():
    intent = _intent("今晚和室友去打电竞")

    assert "电竞" in intent.raw_terms
    assert "ACTIVITY_ESPORTS" in intent.activity_type_ids
    assert {"GAME", "SOCIAL_ENTERTAINMENT"} <= set(intent.parent_categories)
    assert intent.social_mode == "friends"


def test_play_games_maps_to_esports_activity():
    intent = _intent("周末和朋友找个地方打游戏")

    assert "打游戏" in intent.raw_terms or "游戏" in intent.raw_terms
    assert "ACTIVITY_ESPORTS" in intent.activity_type_ids
    assert {"GAME", "SOCIAL_ENTERTAINMENT"} <= set(intent.parent_categories)


def test_scenic_walk_maps_to_walk_and_scenic():
    intent = _intent("和朋友去景点逛逛", ["WITH_FRIENDS", "SCENIC"])

    assert set(intent.parent_categories) & {"SCENIC", "WALK"}
    assert set(intent.activity_type_ids) & {"ACTIVITY_SCENIC", "ACTIVITY_PARK_WALK"}
    assert "朋友" in intent.scenes


def test_milk_tea_only_does_not_create_activity_intent():
    intent = _intent("今天下午想喝奶茶")

    assert intent.retrieval_mode == "unknown"
    assert intent.raw_terms == []
    assert intent.activity_type_ids == []


def test_child_and_elderly_context_sets_suitability_flags():
    child = _intent("孩子5岁想出去玩", ["WITH_CHILD", "CHILD_AGE_PRESCHOOL"])
    elderly = _intent("带爷爷去公园散步", ["WITH_ELDERLY"])

    assert child.child_suitable_required is True
    assert elderly.elderly_suitable_required is True
    assert elderly.intensity == "low"


class InvalidActivityLLM:
    def generate_json(self, **kwargs):
        return {
            "raw_terms": ["未知活动"],
            "activity_type_ids": ["ACTIVITY_NOT_ALLOWED"],
            "parent_categories": ["UNKNOWN_ACTIVITY"],
            "retrieval_mode": "known_activity",
        }


def test_invalid_llm_output_falls_back():
    intent = _intent("帮我安排个活动", llm_client=InvalidActivityLLM())

    assert intent.retrieval_mode == "unknown"
    assert intent.activity_type_ids == []
