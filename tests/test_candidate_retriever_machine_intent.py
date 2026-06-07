import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
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


def _machine(*, soft=None, penalties=None, retrieval_plan=None, hard_filters=None):
    return MachineIntent.parse_payload(
        {
            "canonical_tags": [],
            "global_constraints": {},
            "slot_requirements": [],
            "hard_filters": hard_filters or [],
            "soft_preferences": soft or [],
            "penalties": penalties or [],
            "retrieval_plan": retrieval_plan or {},
            "verifier_expectations": [],
            "explanation_hints": [],
        }
    ).to_dict()


def _score(retriever, item, machine, role="restaurant", base=100.0):
    return retriever._apply_machine_intent_score(item, role, base, machine)


def test_machine_intent_none_keeps_retrieve_compatible():
    with tempfile.TemporaryDirectory(prefix="lifepilot_candidate_machine_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        shutil.copytree(ROOT / "backend" / "data", data_dir)
        app = create_app(data_dir)
        container = app.state.container
        trace_id = "trace_candidate_machine_none"
        text = "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭想吃小龙虾"
        user_goal = container.intent_parser.parse(trace_id, text, None)
        extracted = container.constraint_extractor.extract(trace_id, text, user_goal, {"use_memory": False}, "user_demo_001")

        candidate_set = container.candidate_retriever.retrieve(
            trace_id,
            user_goal,
            extracted["constraints"],
            extracted["time_window"],
            machine_intent=None,
        )

        assert candidate_set["selected_pois"]
        assert candidate_set["candidate_counts"]["activity"] >= 0
        assert "planning_order" in candidate_set


def test_avoid_long_queue_demotes_high_queue_candidate():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "reservation_supported", "weight": 0.8, "scope": "all"},
            {"feature": "low_queue_score", "weight": 1.2, "scope": "all"},
        ],
        penalties=[{"feature": "high_queue_risk", "weight": -1.0, "scope": "all"}],
    )
    low_queue = {"poi_id": "low", "name": "低排队餐厅", "category": "restaurant", "_machine_features": {"queue_risk": 0.15, "reservation_supported": True}}
    high_queue = {"poi_id": "high", "name": "高排队网红店", "category": "restaurant", "_machine_features": {"queue_risk": 0.9, "reservation_supported": False}}

    assert _score(retriever, low_queue, machine) > _score(retriever, high_queue, machine)


def test_with_child_promotes_family_friendly_candidate():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "child_friendly_score", "weight": 1.4, "scope": "activity"},
            {"feature": "family_friendly_score", "weight": 1.0, "scope": "all"},
            {"feature": "restroom_score", "weight": 0.6, "scope": "all"},
            {"feature": "rest_area_score", "weight": 0.6, "scope": "all"},
        ],
        penalties=[
            {"feature": "high_noise_level", "weight": -0.5, "scope": "all"},
            {"feature": "high_walking_intensity", "weight": -0.8, "scope": "activity"},
        ],
    )
    family = {
        "poi_id": "family",
        "name": "亲子手作乐园",
        "category": "activity",
        "tags": ["child_friendly", "family_time"],
        "_machine_features": {"family_friendly_score": 0.95, "has_restroom": True, "has_rest_area": True, "route_fragility": 0.1, "noise_level": 0.2},
    }
    noisy = {
        "poi_id": "noisy",
        "name": "高噪声电玩城",
        "category": "activity",
        "tags": ["strong_social"],
        "_machine_features": {"family_friendly_score": 0.1, "has_restroom": False, "has_rest_area": False, "route_fragility": 0.8, "noise_level": 0.9},
    }

    assert _score(retriever, family, machine, role="activity") > _score(retriever, noisy, machine, role="activity")


def test_nearby_required_promotes_nearby_low_transfer_candidate():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "nearby_score", "weight": 1.2, "scope": "route"},
            {"feature": "low_transfer_score", "weight": 1.0, "scope": "route"},
        ],
        penalties=[{"feature": "long_transfer", "weight": -1.0, "scope": "route"}],
    )
    nearby = {"poi_id": "near", "name": "附近公园", "category": "activity", "_machine_features": {"nearby_score": 0.9, "low_transfer_score": 0.9, "long_transfer": 0.1}}
    far = {"poi_id": "far", "name": "远距离景点", "category": "activity", "_machine_features": {"nearby_score": 0.1, "low_transfer_score": 0.2, "long_transfer": 0.9}}

    assert _score(retriever, nearby, machine, role="activity") > _score(retriever, far, machine, role="activity")


def test_food_intent_crayfish_promotes_matching_restaurant():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "exact_raw_food_match", "weight": 1.5, "scope": "meal"},
            {"feature": "known_dish_match", "weight": 1.3, "scope": "meal"},
            {"feature": "parent_category_match", "weight": 0.6, "scope": "meal"},
        ],
        retrieval_plan={"food_match": {"raw_terms": ["小龙虾"], "known_dish_ids": ["DISH_CRAYFISH"], "parent_categories": ["CRAYFISH"]}},
    )
    crayfish = {"poi_id": "crayfish", "name": "湖畔小龙虾", "category": "restaurant", "menu_features": {"dish_ids": ["DISH_CRAYFISH"], "raw_food_terms": ["小龙虾"], "parent_categories": ["CRAYFISH"], "has_crayfish": True}}
    hotpot = {"poi_id": "hotpot", "name": "清汤火锅", "category": "restaurant", "tags": ["hotpot"], "menu_features": {"dish_ids": ["DISH_HOTPOT"], "parent_categories": ["HOTPOT"]}}

    assert _score(retriever, crayfish, machine) > _score(retriever, hotpot, machine)


def test_food_intent_hotpot_promotes_hotpot_restaurant():
    retriever = _retriever()
    machine = _machine(
        soft=[{"feature": "known_dish_match", "weight": 1.3, "scope": "meal"}],
        retrieval_plan={"food_match": {"raw_terms": ["火锅"], "known_dish_ids": ["DISH_HOTPOT"], "parent_categories": ["HOTPOT"]}},
    )
    hotpot = {"poi_id": "hotpot", "name": "清汤火锅", "category": "restaurant", "tags": ["hotpot"], "menu_features": {"dish_ids": ["DISH_HOTPOT"]}}
    bbq = {"poi_id": "bbq", "name": "炭火烧烤", "category": "restaurant", "tags": ["bbq"], "menu_features": {"dish_ids": ["DISH_BBQ"]}}

    assert _score(retriever, hotpot, machine) > _score(retriever, bbq, machine)


def test_long_tail_charcoal_pineapple_uses_attribute_match():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "exact_raw_food_match", "weight": 1.5, "scope": "meal"},
            {"feature": "attribute_combo_match", "weight": 1.0, "scope": "meal"},
            {"feature": "parent_category_match", "weight": 0.6, "scope": "meal"},
        ],
        retrieval_plan={
            "food_match": {
                "raw_terms": ["碳烤菠萝"],
                "parent_categories": ["BBQ"],
                "ingredients": ["菠萝"],
                "cooking_methods": ["炭烤", "烧烤"],
                "forms": ["烤物"],
            }
        },
    )
    creative_bbq = {
        "poi_id": "creative_bbq",
        "name": "创意炭火烧烤",
        "category": "restaurant",
        "tags": ["bbq", "grill"],
        "menu_features": {
            "raw_food_terms": ["碳烤菠萝"],
            "parent_categories": ["BBQ"],
            "ingredients": ["菠萝"],
            "cooking_methods": ["炭烤", "烧烤"],
            "forms": ["烤物"],
        },
    }
    plain_hotpot = {"poi_id": "plain_hotpot", "name": "普通火锅店", "category": "restaurant", "tags": ["hotpot"], "menu_features": {"dish_ids": ["DISH_HOTPOT"]}}

    assert _score(retriever, creative_bbq, machine) > _score(retriever, plain_hotpot, machine)


def test_long_tail_milk_skin_tanghulu_uses_dessert_snack_attributes():
    retriever = _retriever()
    machine = _machine(
        soft=[
            {"feature": "exact_raw_food_match", "weight": 1.5, "scope": "meal"},
            {"feature": "attribute_combo_match", "weight": 1.0, "scope": "meal"},
            {"feature": "scene_match", "weight": 0.4, "scope": "meal"},
        ],
        retrieval_plan={
            "food_match": {
                "raw_terms": ["奶皮子糖葫芦"],
                "parent_categories": ["DESSERT", "SNACK", "LONG_TAIL_SNACK"],
                "ingredients": ["奶皮子"],
                "flavors": ["奶香", "甜"],
                "forms": ["糖葫芦", "小吃"],
                "scenes": ["网红小吃"],
            }
        },
    )
    snack = {
        "poi_id": "snack",
        "name": "网红甜品小吃铺",
        "category": "restaurant",
        "tags": ["dessert"],
        "menu_features": {
            "raw_food_terms": ["奶皮子糖葫芦"],
            "ingredients": ["奶皮子"],
            "flavors": ["奶香", "甜"],
            "forms": ["糖葫芦", "小吃"],
            "scenes": ["网红小吃"],
        },
    }
    unrelated = {"poi_id": "unrelated", "name": "普通快餐", "category": "restaurant", "tags": ["fast_food"], "menu_features": {"dish_ids": ["DISH_RICE"]}}

    assert _score(retriever, snack, machine) > _score(retriever, unrelated, machine)


def test_missing_fields_are_neutral_not_filtered():
    retriever = _retriever()
    machine = _machine(
        soft=[{"feature": "child_friendly_score", "weight": 1.4, "scope": "all"}],
        penalties=[{"feature": "high_queue_risk", "weight": -1.0, "scope": "all"}],
    )
    sparse_item = {"poi_id": "sparse", "name": "普通地点", "category": "activity"}

    score = _score(retriever, sparse_item, machine, role="activity")

    assert score > -9000
    assert isinstance(score, float)
