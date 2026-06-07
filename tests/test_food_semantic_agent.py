import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.food_semantic_agent import FoodSemanticAgent  # noqa: E402


def _agent(llm_client=None):
    return FoodSemanticAgent(ROOT / "backend" / "data", llm_client)


def _intent(text, canonical_tags=None, llm_client=None):
    return _agent(llm_client).analyze(
        raw_user_text=text,
        constraints={},
        dining_preference={},
        recommendation_profile={},
        canonical_tags=canonical_tags or [],
    )


def test_crayfish_maps_to_known_dish():
    intent = _intent("晚饭想吃小龙虾")

    assert "小龙虾" in intent.raw_terms
    assert "DISH_CRAYFISH" in intent.known_dish_ids
    assert "CRAYFISH" in intent.parent_categories
    assert intent.retrieval_mode == "known_dish"


def test_hotpot_maps_to_known_dish():
    intent = _intent("想吃火锅")

    assert "DISH_HOTPOT" in intent.known_dish_ids
    assert "HOTPOT" in intent.parent_categories


def test_bbq_maps_to_known_dish():
    intent = _intent("周末想吃烧烤烤串")

    assert "DISH_BBQ" in intent.known_dish_ids
    assert "BBQ" in intent.parent_categories


def test_charcoal_pineapple_is_long_tail_attribute():
    intent = _intent("晚上想吃碳烤菠萝，附近顺便逛逛")

    assert intent.retrieval_mode == "long_tail_attribute"
    assert "碳烤菠萝" in intent.raw_terms
    assert "菠萝" in intent.ingredients
    assert {"炭烤", "烧烤"} & set(intent.cooking_methods)
    assert "BBQ" in intent.parent_categories
    assert "DISH_BBQ" not in intent.known_dish_ids


def test_milk_skin_tanghulu_is_dessert_snack_attribute():
    intent = _intent("想吃奶皮子糖葫芦，再找个地方散步")

    assert intent.retrieval_mode == "long_tail_attribute"
    assert "奶皮子糖葫芦" in intent.raw_terms
    assert "奶皮子" in intent.ingredients
    assert "糖葫芦" in intent.forms
    assert {"DESSERT", "SNACK", "LONG_TAIL_SNACK"} & set(intent.parent_categories)
    assert "网红小吃" in intent.scenes


def test_rattan_pepper_beef_noodles_has_attributes():
    intent = _intent("晚上想吃藤椒牛肉拌面，不想走太远")

    assert "藤椒牛肉拌面" in intent.raw_terms
    assert "牛肉" in intent.ingredients
    assert {"藤椒", "麻"} & set(intent.flavors)
    assert {"面", "主食"} & set(intent.forms)
    assert "NOODLES" in intent.parent_categories


def test_matcha_pistachio_basque_has_dessert_attributes():
    intent = _intent("抹茶开心果巴斯克")

    assert "抹茶开心果巴斯克" in intent.raw_terms
    assert {"抹茶", "开心果"} <= set(intent.ingredients)
    assert {"甜品", "蛋糕", "巴斯克"} & set(intent.forms)
    assert "DESSERT" in intent.parent_categories


def test_child_with_heavy_or_spicy_food_requires_child_food_and_non_spicy():
    intent = _intent("想吃火锅，但孩子不能吃辣，别排队", ["WITH_CHILD", "CHILD_AGE_PRESCHOOL"])

    assert "DISH_HOTPOT" in intent.known_dish_ids
    assert intent.child_food_required is True
    assert intent.non_spicy_required is True


def test_low_calorie_tag_sets_low_calorie_required():
    intent = _intent("老婆最近减脂，想吃点清淡的，再安排个轻松的地方走走", ["LOW_CALORIE_REQUIRED"])

    assert intent.low_calorie_required is True
    assert "DISH_LIGHT_MEAL" in intent.known_dish_ids
    assert "LIGHT_MEAL" in intent.parent_categories


class InvalidJSONLLM:
    def generate_json(self, **kwargs):
        return {
            "raw_terms": ["未知食物"],
            "known_dish_ids": ["DISH_NOT_ALLOWED"],
            "parent_categories": ["UNKNOWN_FOOD"],
            "retrieval_mode": "known_dish",
        }


def test_llm_invalid_json_fallback_does_not_crash():
    intent = _intent("帮我安排一下", llm_client=InvalidJSONLLM())

    assert intent.retrieval_mode == "unknown"
    assert intent.known_dish_ids == []
    assert intent.raw_terms == []
