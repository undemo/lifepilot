#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from ranking_feature_vectors import feature_vector, score


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backend" / "data"
OUTPUT = ROOT / "tools" / "rule_evaluation" / "ranking_preference_dataset.json"
MAX_PAIRS_PER_TEMPLATE = 18


TEMPLATES = [
    {
        "name": "family_activity_amusement_over_low_fit",
        "scenario": "family_parent_child",
        "role": "activity",
        "intent_tags": ["child_friendly", "kid_safe", "family_time", "amusement"],
        "avoid_tags": ["low_fit_activity", "fitness", "sports", "alcohol", "strong_social"],
        "preferred_any": ["amusement", "child_friendly", "kid_safe"],
        "rejected_any": ["low_fit_activity", "fitness", "sports", "alcohol"],
        "rationale": "亲子游乐/儿童友好活动应优先于健身、运动、酒吧等低适配活动。",
    },
    {
        "name": "family_activity_hands_on_over_movie_mall",
        "scenario": "family_parent_child",
        "role": "activity",
        "intent_tags": ["child_friendly", "kid_safe", "hands_on", "craft"],
        "avoid_tags": ["movie", "theater", "private_cinema", "mall", "mall_walk"],
        "preferred_any": ["hands_on", "craft", "child_friendly", "kid_safe"],
        "rejected_any": ["theater", "private_cinema", "mall", "mall_walk"],
        "rationale": "亲子明说手作时，应优先可参与体验，不应被电影或泛商场替代。",
    },
    {
        "name": "family_restaurant_light_over_heavy",
        "scenario": "family_parent_child",
        "role": "restaurant",
        "intent_tags": ["light_meal", "light_food", "family_friendly"],
        "avoid_tags": ["spicy_heavy", "casual_chain", "low_end_chain"],
        "preferred_any": ["light_meal", "light_food", "family_friendly"],
        "rejected_any": ["spicy_heavy", "casual_chain", "low_end_chain"],
        "rationale": "家庭清淡餐要优先正餐和低负担，不应被重口味或低质连锁替代。",
    },
    {
        "name": "family_restaurant_low_queue_over_queue_risk",
        "scenario": "family_parent_child",
        "role": "restaurant",
        "intent_tags": ["light_meal", "light_food", "family_friendly", "low_queue"],
        "avoid_tags": ["queue_risk", "spicy_heavy", "long_queue"],
        "preferred_any": ["light_meal", "light_food", "family_friendly", "rain_safe"],
        "rejected_any": ["queue_risk"],
        "rationale": "用户反馈少排队后，家庭餐厅应优先低排队风险候选，不应继续选择静态排队风险高的点。",
    },
    {
        "name": "family_restaurant_buffet_over_snack",
        "scenario": "family_parent_child",
        "role": "restaurant",
        "intent_tags": ["buffet", "dinner", "family_friendly"],
        "avoid_tags": ["snack_meal", "casual_chain", "coffee"],
        "preferred_any": ["buffet"],
        "rejected_any": ["snack_meal", "casual_chain", "coffee"],
        "rationale": "家庭明说自助餐时，自助/放题语义必须优先于小吃、饮品或普通简餐。",
    },
    {
        "name": "date_activity_hands_on_over_low_fit",
        "scenario": "anniversary_emotion",
        "role": "activity",
        "intent_tags": ["date_friendly", "hands_on", "craft", "light_ritual"],
        "avoid_tags": ["low_fit_activity", "strong_social", "sports", "fitness"],
        "preferred_any": ["hands_on", "craft", "date_friendly"],
        "rejected_any": ["low_fit_activity", "strong_social", "sports", "fitness"],
        "rationale": "约会手作要优先参与感和轻仪式感，避免强社交或运动类低适配活动。",
    },
    {
        "name": "date_activity_walk_over_movie_when_walk",
        "scenario": "anniversary_emotion",
        "role": "activity",
        "intent_tags": ["date_friendly", "light_walk", "nearby"],
        "avoid_tags": ["movie", "theater", "private_cinema", "coffee"],
        "preferred_any": ["lake", "park", "light_walk", "quiet_stay"],
        "rejected_any": ["theater", "private_cinema", "movie", "coffee"],
        "rationale": "约会明说附近散步时，应优先步道/湖边/公园，不应用电影或咖啡替代。",
    },
    {
        "name": "date_restaurant_quality_over_casual",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["date_friendly", "quality_dining", "ambience_dining"],
        "avoid_tags": ["casual_chain", "low_end_chain", "snack_meal", "coffee"],
        "preferred_any": ["quality_dining", "ambience_dining", "proper_dining", "slow_dining"],
        "rejected_any": ["casual_chain", "low_end_chain", "snack_meal", "coffee"],
        "rationale": "约会/纪念日餐厅要优先有正餐属性和氛围感，避免小吃或咖啡凑数。",
    },
    {
        "name": "date_japanese_over_casual_japanese",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["cuisine_japanese", "date_friendly", "proper_dining"],
        "avoid_tags": ["casual_chain", "low_end_chain", "coffee", "dessert"],
        "preferred_any": ["cuisine_japanese", "sushi", "izakaya", "proper_dining"],
        "rejected_any": ["casual_chain", "low_end_chain", "coffee", "dessert"],
        "rationale": "明说日料时，正式日料/居酒屋应优于咖啡、甜品和日式快餐。",
    },
    {
        "name": "date_western_over_drink",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["western_cuisine", "steak", "date_friendly", "dinner"],
        "avoid_tags": ["coffee", "dessert", "snack_meal", "casual_chain"],
        "preferred_any": ["western_cuisine", "steak", "proper_dining"],
        "rejected_any": ["coffee", "dessert", "snack_meal", "casual_chain"],
        "rationale": "明说西餐/牛排时，餐厅槽必须是西餐正餐，不应落到饮品甜品。",
    },
    {
        "name": "date_lamb_bbq_over_casual",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["lamb", "bbq", "grill", "date_friendly", "dinner"],
        "avoid_tags": ["coffee", "dessert", "snack_meal", "casual_chain"],
        "preferred_any": ["lamb", "bbq", "grill", "proper_dining"],
        "rejected_any": ["coffee", "dessert", "snack_meal", "casual_chain"],
        "rationale": "明说烤羊排/烤肉时，应命中羊肉或烤制正餐，不应被咖啡、小吃替代。",
    },
    {
        "name": "date_hotpot_over_coffee",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["hotpot", "date_friendly", "dinner"],
        "avoid_tags": ["coffee", "dessert", "snack_meal"],
        "preferred_any": ["hotpot", "proper_dining"],
        "rejected_any": ["coffee", "dessert", "snack_meal"],
        "rationale": "明说火锅时，餐厅槽必须命中火锅，不应被茶饮甜品替代。",
    },
    {
        "name": "date_light_meal_over_heavy",
        "scenario": "anniversary_emotion",
        "role": "restaurant",
        "intent_tags": ["light_meal", "light_food", "healthy_light", "dinner"],
        "avoid_tags": ["spicy_heavy", "hotpot", "bbq", "grill", "low_end_chain"],
        "preferred_any": ["light_meal", "light_food", "healthy_light"],
        "rejected_any": ["spicy_heavy", "hotpot", "bbq", "grill", "low_end_chain"],
        "rationale": "清淡/减脂晚饭要优先低负担正餐，避开火锅、烤肉和麻辣重口味。",
    },
    {
        "name": "friend_activity_board_game_over_generic",
        "scenario": "friend_group",
        "role": "activity",
        "intent_tags": ["board_game", "group_ok", "conversation"],
        "avoid_tags": ["fitness", "sports", "shopping", "low_fit_activity"],
        "preferred_any": ["board_game", "group_ok"],
        "rejected_any": ["fitness", "sports", "shopping", "low_fit_activity"],
        "rationale": "朋友局明说桌游聊天，活动槽应优先桌游/棋牌类可坐聊空间。",
    },
    {
        "name": "friend_activity_karaoke_over_generic",
        "scenario": "friend_group",
        "role": "activity",
        "intent_tags": ["karaoke", "group_ok", "indoor"],
        "avoid_tags": ["fitness", "sports", "shopping", "theater", "coffee"],
        "preferred_any": ["karaoke"],
        "rejected_any": ["fitness", "sports", "shopping", "theater", "coffee"],
        "rationale": "朋友局明说唱K/KTV时，活动槽必须优先 KTV，不应用影院、咖啡或泛娱乐替代。",
    },
    {
        "name": "friend_activity_low_queue_over_queue_risk",
        "scenario": "friend_group",
        "role": "activity",
        "intent_tags": ["group_ok", "conversation", "low_queue", "rain_safe"],
        "avoid_tags": ["queue_risk", "capacity_risk", "long_queue", "low_fit_activity"],
        "preferred_any": ["rain_safe", "indoor", "quiet_stay", "conversation"],
        "rejected_any": ["queue_risk", "capacity_risk"],
        "rationale": "用户反馈排队问题后，朋友局活动应优先低排队风险的室内/可聊天节点。",
    },
    {
        "name": "friend_post_meal_conversation_over_movie",
        "scenario": "friend_group",
        "role": "activity",
        "intent_tags": ["post_meal_conversation", "conversation", "quiet_stay"],
        "avoid_tags": ["movie", "theater", "private_cinema", "alcohol", "light_drink"],
        "preferred_any": ["coffee", "dessert", "quiet_stay", "lake", "park"],
        "rejected_any": ["theater", "private_cinema", "alcohol", "light_drink"],
        "rationale": "饭后想聊天时，应优先可坐聊或散步节点，不应直接塞电影或酒吧。",
    },
    {
        "name": "friend_restaurant_buffet_over_fast",
        "scenario": "friend_group",
        "role": "restaurant",
        "intent_tags": ["buffet", "dinner", "group_ok"],
        "avoid_tags": ["snack_meal", "casual_chain", "coffee"],
        "preferred_any": ["buffet"],
        "rejected_any": ["snack_meal", "casual_chain", "coffee"],
        "rationale": "朋友局明说自助餐时，自助/放题应优先于小吃和饮品。",
    },
    {
        "name": "friend_restaurant_bbq_over_snack",
        "scenario": "friend_group",
        "role": "restaurant",
        "intent_tags": ["bbq", "grill", "dinner", "group_ok"],
        "avoid_tags": ["snack_meal", "casual_chain", "coffee"],
        "preferred_any": ["bbq", "grill", "proper_dining"],
        "rejected_any": ["snack_meal", "casual_chain", "coffee"],
        "rationale": "朋友局明说烤肉/烧烤时，烤制正餐应优先于小吃、快餐和咖啡。",
    },
    {
        "name": "solo_music_over_strong_social",
        "scenario": "fallback_unknown",
        "role": "activity",
        "intent_tags": ["alone", "mood_relief", "music", "low_pressure"],
        "avoid_tags": ["strong_social", "low_fit_activity", "fitness", "sports"],
        "preferred_any": ["music", "acoustic_music", "quiet_stay"],
        "rejected_any": ["strong_social", "low_fit_activity", "fitness", "sports"],
        "rationale": "单人散心想听音乐，优先低压力音乐空间，避免强互动或运动项目。",
    },
    {
        "name": "solo_walk_over_alcohol_when_negated",
        "scenario": "fallback_unknown",
        "role": "activity",
        "intent_tags": ["alone", "mood_relief", "light_walk", "nearby"],
        "avoid_tags": ["alcohol", "light_drink", "strong_social"],
        "preferred_any": ["light_walk", "park", "lake", "quiet_stay"],
        "rejected_any": ["alcohol", "light_drink", "strong_social"],
        "rationale": "单人只想附近走走且不喝酒时，散步/安静停留优先于酒吧。",
    },
    {
        "name": "solo_quiet_coffee_over_low_fit",
        "scenario": "fallback_unknown",
        "role": "activity",
        "intent_tags": ["alone", "quiet", "coffee", "low_pressure"],
        "avoid_tags": ["strong_social", "low_fit_activity", "sports", "fitness"],
        "preferred_any": ["coffee", "quiet_stay", "quiet"],
        "rejected_any": ["strong_social", "low_fit_activity", "sports", "fitness"],
        "rationale": "单人低压力坐一会儿，安静咖啡/停留点优先于强社交或运动项目。",
    },
    {
        "name": "city_light_activity_showcase_over_low_fit",
        "scenario": "city_light_explore",
        "role": "activity",
        "intent_tags": ["visitor_friendly", "showcase_local", "conversation"],
        "avoid_tags": ["low_fit_activity", "strong_social", "fitness", "sports"],
        "preferred_any": ["visitor_friendly", "showcase_local", "lake", "photo_spot"],
        "rejected_any": ["low_fit_activity", "strong_social", "fitness", "sports"],
        "rationale": "招待来访家人要优先有本地识别度、好聊天的节点。",
    },
    {
        "name": "city_light_activity_lake_over_mall_when_no_mall",
        "scenario": "city_light_explore",
        "role": "activity",
        "intent_tags": ["visitor_friendly", "showcase_local", "light_walk", "route_simple"],
        "avoid_tags": ["mall", "mall_walk", "shopping"],
        "preferred_any": ["lake", "park", "light_walk", "showcase_local"],
        "rejected_any": ["mall", "mall_walk", "shopping"],
        "rationale": "招待家人且不想商场时，湖边/公园/步行节点优先于泛商场。",
    },
    {
        "name": "city_light_restaurant_quality_over_fast",
        "scenario": "city_light_explore",
        "role": "restaurant",
        "intent_tags": ["quality_dining", "proper_dining", "conversation"],
        "avoid_tags": ["casual_chain", "low_end_chain", "snack_meal", "coffee"],
        "preferred_any": ["quality_dining", "proper_dining", "ambience_dining", "slow_dining"],
        "rejected_any": ["casual_chain", "low_end_chain", "snack_meal", "coffee"],
        "rationale": "招待家人吃饭要体面但不端着，不能用快餐/饮品替代。",
    },
    {
        "name": "tail_conversation_walk_over_low_fit",
        "scenario": "city_light_explore",
        "role": "tail",
        "intent_tags": ["conversation", "light_walk", "route_simple"],
        "avoid_tags": ["low_fit_activity", "strong_social", "alcohol"],
        "preferred_any": ["coffee", "dessert", "quiet_stay", "lake", "park", "light_walk"],
        "rejected_any": ["low_fit_activity", "strong_social", "alcohol"],
        "rationale": "收尾节点应服务聊天、散步或轻停留，不应变成强社交或酒精场景。",
    },
    {
        "name": "tail_rain_safe_over_exposed_walk_when_weather_risky",
        "scenario": "anniversary_emotion",
        "role": "tail",
        "intent_tags": ["date_friendly", "conversation", "rain_safe", "route_simple"],
        "avoid_tags": ["outdoor", "weather_exposure_risk"],
        "preferred_any": ["rain_safe", "indoor", "coffee", "dessert", "quiet_stay"],
        "rejected_any": ["outdoor", "light_walk", "park"],
        "rationale": "天气风险较高时，收尾节点应优先室内/雨天友好停留点，而不是裸露步道。",
    },
]


def read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    pois = read_json(DATA_DIR / "mock_pois.json", {"pois": []}).get("pois", [])
    features = read_json(DATA_DIR / "poi_features.json", {"features": {}}).get("features", {})
    poi_by_id = {str(poi.get("poi_id")): poi for poi in pois if poi.get("poi_id")}
    cases = []
    template_counts: Dict[str, int] = {}
    for template in TEMPLATES:
        template_cases = build_template_cases(template, features, poi_by_id)
        template_counts[template["name"]] = len(template_cases)
        for case in template_cases:
            case["case_id"] = f"rank_pref_{len(cases) + 1:03d}"
            cases.append(case)
    document = {
        "schema_version": "ranking_preferences.v2",
        "version": "2026-05-24",
        "purpose": "Pairwise preference data for calibrating LifePilot POI ranking weights.",
        "case_count": len(cases),
        "template_counts": template_counts,
        "templates": {template["name"]: template for template in TEMPLATES},
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(cases)} preference pairs)")


def build_template_cases(
    template: Dict[str, Any],
    features: Dict[str, Dict[str, Any]],
    poi_by_id: Dict[str, Dict[str, Any]],
) -> list[Dict[str, Any]]:
    preferred = ranked_matches(features, poi_by_id, template, template["preferred_any"], template.get("rejected_any", []))
    rejected = ranked_matches(features, poi_by_id, template, template["rejected_any"], template.get("preferred_any", []))
    cases = []
    for preferred_id in preferred[:14]:
        for rejected_id in rejected[:14]:
            if preferred_id == rejected_id:
                continue
            preferred_score = score(feature_vector(template, features[preferred_id]))
            rejected_score = score(feature_vector(template, features[rejected_id]))
            if preferred_score <= rejected_score:
                continue
            cases.append(
                {
                    "case_id": "",
                    "template": template["name"],
                    "scenario": template["scenario"],
                    "role": template["role"],
                    "intent_tags": template["intent_tags"],
                    "avoid_tags": template.get("avoid_tags", []),
                    "preferred_poi_id": preferred_id,
                    "rejected_poi_id": rejected_id,
                    "preferred_title": poi_by_id.get(preferred_id, {}).get("name"),
                    "rejected_title": poi_by_id.get(rejected_id, {}).get("name"),
                    "preferred_score": round(preferred_score, 4),
                    "rejected_score": round(rejected_score, 4),
                    "rationale": template["rationale"],
                }
            )
            if len(cases) >= int(template.get("max_pairs") or MAX_PAIRS_PER_TEMPLATE):
                return cases
    return cases


def ranked_matches(
    features: Dict[str, Dict[str, Any]],
    poi_by_id: Dict[str, Dict[str, Any]],
    template: Dict[str, Any],
    include_any: Iterable[str],
    exclude_any: Iterable[str],
) -> list[str]:
    include = set(str(item) for item in include_any)
    exclude = set(str(item) for item in exclude_any)
    rows = []
    for poi_id, feature in features.items():
        poi = poi_by_id.get(str(poi_id), {})
        if not poi:
            continue
        category = str(feature.get("category") or poi.get("category") or "")
        role = str(template.get("role") or "")
        if role == "restaurant" and category != "restaurant" and not ({"alcohol", "light_drink"} & include):
            continue
        if role == "activity" and category not in {"activity", "walk_spot", "service", "restaurant"}:
            continue
        if role == "tail" and category not in {"activity", "walk_spot", "restaurant"}:
            continue
        tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
        if include and not tags & include:
            continue
        if exclude and tags & exclude:
            continue
        item_score = score(feature_vector(template, feature))
        rows.append((item_score, str(poi_id)))
    return [poi_id for _, poi_id in sorted(rows, reverse=True)]


if __name__ == "__main__":
    main()
