import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.data_paths import MOCK_POIS_PATH  # noqa: E402
from app.rules.poi_feature_store import POIFeatureStore  # noqa: E402
from app.schemas.internal_intelligence import MachineIntent  # noqa: E402
from app.services.candidate_retriever import CandidateRetriever  # noqa: E402
from app.storage.json_store import JsonFileStore  # noqa: E402


def _store():
    temp = tempfile.TemporaryDirectory(prefix="lifepilot_poi_overlay_")
    data_dir = Path(temp.name) / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    store = JsonFileStore(data_dir)
    return temp, store, POIFeatureStore(store)


def _poi(store, poi_id):
    for item in store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", []):
        if item.get("poi_id") == poi_id:
            return item
    raise AssertionError(f"missing poi {poi_id}")


class _MockAPI:
    def __init__(self, store):
        self.store = store
        self.logger = None


def _retriever(store, feature_store):
    return CandidateRetriever(_MockAPI(store), None, poi_feature_store=feature_store)


def _machine(retrieval_plan=None, soft=None, penalties=None):
    return MachineIntent.parse_payload(
        {
            "canonical_tags": [],
            "global_constraints": {},
            "slot_requirements": [],
            "hard_filters": [],
            "soft_preferences": soft or [],
            "penalties": penalties or [],
            "retrieval_plan": retrieval_plan or {},
            "verifier_expectations": [],
            "explanation_hints": [],
        }
    ).to_dict()


def test_old_poi_without_overlay_still_gets_structured_defaults():
    temp, store, feature_store = _store()
    try:
        item = _poi(store, "poi_gaode_activity_001_5437af")

        feature = feature_store.for_item(item)

        assert feature["menu_features"]
        assert feature["queue_features"]["queue_risk"] >= 0
        assert feature["family_features"]["family_friendly_score"] >= 0
        assert "physical_features" in feature
        assert "experience_features" in feature
    finally:
        temp.cleanup()


def test_overlay_merges_crayfish_menu_and_addons():
    temp, store, feature_store = _store()
    try:
        item = _poi(store, "poi_gaode_restaurant_260_f3dfb0")

        feature = feature_store.for_item(item)
        menu = feature["menu_features"]

        assert menu["has_crayfish"] is True
        assert "DISH_CRAYFISH" in menu["dish_ids"]
        assert "CRAYFISH" in menu["parent_categories"]
        assert "湿巾" in feature["addon_features"]
        assert feature["queue_features"]["reservation_supported"] is True
    finally:
        temp.cleanup()


def test_menu_features_are_read_by_candidate_retriever_food_match():
    temp, store, feature_store = _store()
    try:
        retriever = _retriever(store, feature_store)
        crayfish = _poi(store, "poi_gaode_restaurant_260_f3dfb0")
        unrelated = _poi(store, "poi_gaode_restaurant_055_50bc27")
        machine = _machine(
            retrieval_plan={
                "food_match": {
                    "raw_terms": ["小龙虾"],
                    "known_dish_ids": ["DISH_CRAYFISH"],
                    "parent_categories": ["CRAYFISH"],
                }
            },
            soft=[
                {"feature": "exact_raw_food_match", "weight": 1.5, "scope": "meal"},
                {"feature": "known_dish_match", "weight": 1.3, "scope": "meal"},
                {"feature": "parent_category_match", "weight": 0.6, "scope": "meal"},
            ],
        )

        crayfish_score = retriever._apply_machine_intent_score(crayfish, "restaurant", 100.0, machine)
        unrelated_score = retriever._apply_machine_intent_score(unrelated, "restaurant", 100.0, machine)

        assert crayfish_score > unrelated_score
    finally:
        temp.cleanup()


def test_charcoal_pineapple_overlay_exposes_long_tail_attributes():
    temp, store, feature_store = _store()
    try:
        item = _poi(store, "poi_gaode_restaurant_002_7a101a")

        menu = feature_store.for_item(item)["menu_features"]

        assert "碳烤菠萝" in menu["raw_food_terms"]
        assert "菠萝" in menu["ingredients"]
        assert {"炭烤", "烧烤"} & set(menu["cooking_methods"])
        assert "LONG_TAIL_SNACK" in menu["parent_categories"]
    finally:
        temp.cleanup()


def test_milk_skin_tanghulu_overlay_exposes_dessert_snack_attributes():
    temp, store, feature_store = _store()
    try:
        item = _poi(store, "poi_gaode_restaurant_135_8d370b")

        menu = feature_store.for_item(item)["menu_features"]

        assert "奶皮子糖葫芦" in menu["raw_food_terms"]
        assert {"奶皮子", "糖葫芦"} <= set(menu["ingredients"])
        assert "糖葫芦" in menu["forms"]
        assert "网红小吃" in menu["scenes"]
        assert {"DESSERT", "SNACK", "LONG_TAIL_SNACK"} <= set(menu["parent_categories"])
    finally:
        temp.cleanup()


def test_child_family_queue_fields_are_available_for_activity():
    temp, store, feature_store = _store()
    try:
        item = _poi(store, "poi_gaode_activity_011_f9f2d9")

        feature = feature_store.for_item(item)

        assert feature["child_features"]["child_friendly_score"] >= 0.9
        assert feature["child_features"]["has_restroom"] is True
        assert feature["child_features"]["has_rest_area"] is True
        assert feature["queue_features"]["reservation_supported"] is True
        assert feature["physical_features"]["walking_intensity"] < 0.5
    finally:
        temp.cleanup()


def test_missing_overlay_uses_neutral_fallback_without_filtering():
    temp, store, feature_store = _store()
    try:
        item = {
            "poi_id": "poi_not_in_overlay",
            "name": "普通地点",
            "category": "activity",
            "tags": [],
        }

        feature = feature_store.for_item(item)

        assert feature["queue_features"]["queue_risk"] >= 0
        assert feature["family_features"]["family_friendly_score"] >= 0
        assert feature["menu_features"]["dish_ids"] == []
    finally:
        temp.cleanup()
