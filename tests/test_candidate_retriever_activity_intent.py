import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.internal_intelligence import MachineIntent  # noqa: E402
from app.services.candidate_retriever import CandidateRetriever  # noqa: E402


class _Store:
    def read(self, filename, default):
        return default


class _MockAPI:
    store = _Store()
    logger = None


def _retriever():
    return CandidateRetriever(_MockAPI(), None)


def _machine(activity_match, *, soft=None, penalties=None):
    return MachineIntent.parse_payload(
        {
            "canonical_tags": [],
            "global_constraints": {},
            "slot_requirements": [{"slot_type": "activity", "activity_match": activity_match}],
            "hard_filters": [],
            "soft_preferences": soft
            or [
                {"feature": "exact_raw_activity_match", "weight": 2.0, "scope": "activity"},
                {"feature": "known_activity_match", "weight": 1.6, "scope": "activity"},
                {"feature": "activity_attribute_match", "weight": 1.0, "scope": "activity"},
                {"feature": "parent_activity_category_match", "weight": 0.7, "scope": "activity"},
                {"feature": "activity_scene_match", "weight": 0.5, "scope": "activity"},
                {"feature": "companion_activity_fit", "weight": 1.0, "scope": "activity"},
            ],
            "penalties": penalties or [],
            "retrieval_plan": {"activity_match": activity_match},
            "verifier_expectations": [],
            "explanation_hints": [],
        }
    ).to_dict()


def _score(retriever, item, machine, base=100.0):
    return retriever._apply_machine_intent_score(item, "activity", base, machine)


def test_badminton_activity_match_promotes_badminton_over_generic_mall():
    retriever = _retriever()
    machine = _machine(
        {
            "raw_terms": ["羽毛球"],
            "activity_type_ids": ["ACTIVITY_BADMINTON"],
            "parent_categories": ["SPORTS"],
            "facility_types": ["羽毛球馆"],
            "genres": ["球类"],
            "scenes": ["朋友"],
            "social_mode": "friends",
        }
    )
    badminton = {
        "poi_id": "badminton",
        "name": "乐动力钱塘体育中心羽毛球馆",
        "category": "activity",
        "tags": ["sports"],
        "activity_features": {
            "raw_activity_terms": ["羽毛球"],
            "activity_type_ids": ["ACTIVITY_BADMINTON"],
            "parent_categories": ["SPORTS"],
            "facility_types": ["羽毛球馆"],
            "genres": ["球类"],
            "scenes": ["朋友"],
        },
    }
    mall = {"poi_id": "mall", "name": "普通商场", "category": "activity", "tags": ["mall"]}

    assert _score(retriever, badminton, machine) > _score(retriever, mall, machine)


def test_esports_activity_match_promotes_esports_for_roommates():
    retriever = _retriever()
    machine = _machine(
        {
            "raw_terms": ["电竞"],
            "activity_type_ids": ["ACTIVITY_ESPORTS"],
            "parent_categories": ["GAME", "SOCIAL_ENTERTAINMENT"],
            "facility_types": ["电竞馆"],
            "genres": ["电子游戏"],
            "scenes": ["室友", "朋友"],
            "social_mode": "friends",
        }
    )
    esports = {"poi_id": "esports", "name": "杰拉电竞网咖", "category": "activity", "tags": ["esports", "group_ok"]}
    cinema = {"poi_id": "cinema", "name": "横店电影城", "category": "activity", "tags": ["theater", "movie"]}
    climbing = {"poi_id": "climbing", "name": "噜呐攀岩(金沙店)", "category": "activity", "tags": ["sports", "fitness", "low_fit_activity"]}
    karaoke = {"poi_id": "karaoke", "name": "银乐迪KTV量贩", "category": "activity", "tags": ["karaoke", "low_fit_activity"]}

    assert _score(retriever, esports, machine) > _score(retriever, cinema, machine)
    assert _score(retriever, cinema, machine) <= -9000
    assert retriever._activity_match_score(esports, machine["retrieval_plan"]["activity_match"]) > 0
    assert retriever._activity_match_score(climbing, machine["retrieval_plan"]["activity_match"]) == 0
    assert retriever._activity_match_score(karaoke, machine["retrieval_plan"]["activity_match"]) == 0


def test_child_context_penalizes_esports_even_if_activity_requested():
    retriever = _retriever()
    activity_match = {
        "raw_terms": ["电竞"],
        "activity_type_ids": ["ACTIVITY_ESPORTS"],
        "parent_categories": ["GAME", "SOCIAL_ENTERTAINMENT"],
        "facility_types": ["电竞馆"],
        "child_suitable_required": True,
        "social_mode": "family",
    }
    machine = _machine(
        activity_match,
        penalties=[{"feature": "child_incompatible_activity", "weight": -1.8, "scope": "activity"}],
    )
    esports = {"poi_id": "esports", "name": "杰拉电竞网咖", "category": "activity", "tags": ["esports", "low_fit_activity", "strong_social"]}
    handcraft = {
        "poi_id": "craft",
        "name": "亲子DIY手工坊",
        "category": "activity",
        "tags": ["hands_on", "craft", "child_friendly", "kid_safe"],
    }

    assert _score(retriever, handcraft, machine) > _score(retriever, esports, machine)


def test_elderly_context_penalizes_high_intensity_football():
    retriever = _retriever()
    machine = _machine(
        {
            "raw_terms": ["足球"],
            "activity_type_ids": ["ACTIVITY_FOOTBALL"],
            "parent_categories": ["SPORTS"],
            "facility_types": ["足球场"],
            "elderly_suitable_required": True,
            "social_mode": "elderly",
        },
        penalties=[
            {"feature": "elderly_incompatible_activity", "weight": -1.5, "scope": "activity"},
            {"feature": "high_physical_intensity", "weight": -1.2, "scope": "activity"},
        ],
    )
    football = {"poi_id": "football", "name": "钱塘Parking足球公园", "category": "activity", "tags": ["sports"]}
    park = {"poi_id": "park", "name": "金沙湖湖畔慢行环线", "category": "walk_spot", "tags": ["lake", "park", "light_walk", "quiet"]}

    assert _score(retriever, park, machine) > _score(retriever, football, machine)


def test_activity_need_prevents_solo_optional_filter_from_rejecting_requested_sports():
    retriever = _retriever()
    machine = _machine(
        {
            "raw_terms": ["羽毛球"],
            "activity_type_ids": ["ACTIVITY_BADMINTON"],
            "parent_categories": ["SPORTS"],
            "facility_types": ["羽毛球馆"],
        }
    )
    item = {"poi_id": "badminton", "name": "乐动力钱塘体育中心羽毛球馆", "category": "activity", "tags": ["sports"]}
    score = retriever._item_score(
        item,
        "activity",
        {"scenario": "fallback_unknown"},
        {"party_size": 1, "recommendation_profile": {}},
        set(),
        set(),
        None,
        machine,
    )

    assert score > -9000
