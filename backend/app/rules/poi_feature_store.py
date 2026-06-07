from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from app.core.data_paths import (
    GAODE_POI_ENRICHMENT_PATH,
    MOCK_POIS_PATH,
    POI_ACTIVITY_ATTRIBUTES_PATH,
    POI_FEATURES_PATH,
    POI_FOOD_ATTRIBUTES_PATH,
)
from app.rules.recommendation_taxonomy import get_tag_keywords


SCHEMA_VERSION = "poi_features.v1"
GENERATED_AT = "2026-05-24T00:00:00+08:00"

ALCOHOL_WORDS = get_tag_keywords("alcohol")
AMUSEMENT_WORDS = get_tag_keywords("amusement")
BBQ_WORDS = get_tag_keywords("bbq")
BUFFET_WORDS = get_tag_keywords("buffet")
CASUAL_CHAIN_WORDS = (
    "米村",
    "拌饭",
    "麦当劳",
    "肯德基",
    "德克士",
    "老乡鸡",
    "老娘舅",
    "萨莉亚",
    "必胜客",
    "达美乐",
    "麻辣烫",
)
COFFEE_WORDS = ("咖啡", "Coffee", "COFFEE", "M Stand", "Manner", "星巴克", "瑞幸", "库迪")
DESSERT_WORDS = ("甜品", "蛋糕", "面包", "泡芙", "酸奶", "奶吧", "鲜奶", "牛奶", "奶茶", "茶姬")
FAMILY_ACTIVITY_WORDS = ("亲子", "儿童", "童宇宙", "手作", "手工", "手工坊", "DIY", "diy", "陶艺", "拼豆", "油画", "烘焙")
HANDS_ON_WORDS = get_tag_keywords("hands_on")
HANDMADE_FOOD_FALSE_POSITIVE_WORDS = ("手工粉", "手工面", "手擀面", "手工水饺", "手工饺", "手工馄饨", "手工米粉", "手作酸奶")
HEALTHY_LIGHT_WORDS = get_tag_keywords("healthy_light")
HEAVY_SPICY_WORDS = ("火锅", "毛肚", "麻辣", "干锅", "地锅", "鸡锅", "美蛙", "酸辣", "酸菜鱼", "重庆", "烙锅", "串串", "烤鱼", "湖南菜")
HOTPOT_WORDS = get_tag_keywords("hotpot")
JAPANESE_WORDS = get_tag_keywords("cuisine_japanese")
KARAOKE_WORDS = get_tag_keywords("karaoke")
LAKE_WORDS = ("湖畔", "金沙湖", "公园", "茶空间", "沙滩")
LAMB_WORDS = get_tag_keywords("lamb")
LIGHT_MEAL_WORDS = ("粥", "蒸", "汤", "面馆", "手擀面", "牛肉面", "日式", "料理", "寿司", "鱼", "椰子鸡", "顺德小馆", "小馆", "轻食", "沙拉", "健康", "素", "食堂")
BURGER_WORDS = ("汉堡", "中国汉堡", "麦当劳", "肯德基", "德克士", "塔斯汀", "Burger", "BURGER", "burger")
LOW_FIT_ACTIVITY_WORDS = ("棋牌", "麻将", "自助棋牌", "KTV", "电竞", "网咖", "台球", "健身", "游泳", "乒乓", "电玩", "PS5", "VR", "推理", "剧本杀", "桌游", "棋遇")
BOARD_GAME_WORDS = ("桌游", "棋牌", "麻将", "狼人杀", "剧本杀")
MUSIC_WORDS = get_tag_keywords("music")
PROPER_DINING_WORDS = ("餐厅", "料理", "火锅", "烤肉", "烧肉", "烧烤", "小馆", "CANTEEN", "饭店", "酒楼", "牛排", "羊排")
QUALITY_DINING_WORDS = ("湖畔", "临湖", "西餐", "料理", "会席", "茶空间", "小馆", "CANTEEN", "Modern", "希尔顿", "皇冠", "酒店", "鮨", "融合料理", "沙滩餐厅")
SNACK_MEAL_WORDS = ("包子", "馒头", "牛肉汤", "面馆", "面家", "拉面", "拌面", "手擀面", "米粉", "螺蛳粉", "酸辣粉", "馄饨", "水饺", "饺子", "麻辣烫", "小吃")
STEAK_WORDS = get_tag_keywords("steak")
SUSHI_WORDS = get_tag_keywords("sushi")
IZAKAYA_WORDS = get_tag_keywords("izakaya")
WESTERN_WORDS = get_tag_keywords("western_cuisine")


class POIFeatureStore:
    """Read-only feature store for recommendation ranking.

    The JSON file is generated offline from mock POIs plus enrichment metadata.
    Runtime falls back to deterministic local building if the file is absent so
    tests and copied data directories keep working.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self._features: Optional[Dict[str, Dict[str, Any]]] = None
        self._food_overlay: Optional[Dict[str, Dict[str, Any]]] = None
        self._activity_overlay: Optional[Dict[str, Dict[str, Any]]] = None

    def get(self, poi_id: Optional[str]) -> Dict[str, Any]:
        if not poi_id:
            return {}
        return self._load().get(str(poi_id), {})

    def for_item(self, item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not item:
            return {}
        feature = self.get(str(item.get("poi_id") or ""))
        if feature:
            return self._with_overlay_and_derived(item, feature)
        enrichments = self.store.read(GAODE_POI_ENRICHMENT_PATH, {"enrichments": {}}).get("enrichments", {})
        built = build_poi_feature(item, enrichments.get(str(item.get("poi_id") or "")) or {})
        return self._with_overlay_and_derived(item, built)

    def semantic_tags(self, item: Optional[Dict[str, Any]]) -> set[str]:
        feature = self.for_item(item)
        return set(str(tag) for tag in feature.get("semantic_tags") or [])

    def scores(self, item: Optional[Dict[str, Any]]) -> Dict[str, float]:
        feature = self.for_item(item)
        scores = feature.get("scores") if isinstance(feature, dict) else {}
        return {str(key): float(value) for key, value in (scores or {}).items()}

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self._features is None:
            document = self.store.read(POI_FEATURES_PATH, {})
            features = document.get("features") if isinstance(document, dict) else None
            if not isinstance(features, dict) or not features:
                pois = self.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
                enrichments = self.store.read(GAODE_POI_ENRICHMENT_PATH, {"enrichments": {}}).get("enrichments", {})
                document = build_poi_feature_document(pois, enrichments)
                features = document["features"]
            self._features = {str(key): value for key, value in features.items() if isinstance(value, dict)}
        return self._features

    def _with_overlay_and_derived(self, item: Dict[str, Any], feature: Dict[str, Any]) -> Dict[str, Any]:
        poi_id = str(item.get("poi_id") or "")
        merged = _deep_copy_dict(feature)
        overlay = self._food_overlay_items().get(poi_id) or {}
        if overlay:
            merged = _merge_feature_overlay(merged, overlay)
        activity_overlay = self._activity_overlay_items().get(poi_id) or {}
        if activity_overlay:
            merged = _merge_feature_overlay(merged, activity_overlay)
        derived = _derived_structured_features(item, merged)
        merged = _merge_missing_feature_fields(merged, derived)
        _attach_structured_semantic_tags(merged)
        return merged

    def _food_overlay_items(self) -> Dict[str, Dict[str, Any]]:
        if self._food_overlay is None:
            document = self.store.read(POI_FOOD_ATTRIBUTES_PATH, {"version": "poi_food_attributes.v1", "items": {}})
            items = document.get("items") if isinstance(document, dict) else {}
            self._food_overlay = {str(key): value for key, value in (items or {}).items() if isinstance(value, dict)}
        return self._food_overlay

    def _activity_overlay_items(self) -> Dict[str, Dict[str, Any]]:
        if self._activity_overlay is None:
            document = self.store.read(POI_ACTIVITY_ATTRIBUTES_PATH, {"version": "poi_activity_attributes.v1", "items": {}})
            items = document.get("items") if isinstance(document, dict) else {}
            self._activity_overlay = {str(key): value for key, value in (items or {}).items() if isinstance(value, dict)}
        return self._activity_overlay


def build_poi_feature_document(
    pois: Iterable[Dict[str, Any]],
    enrichments: Optional[Dict[str, Dict[str, Any]]] = None,
    status_signals: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    enrichment_map = enrichments or {}
    status_signal_map = status_signals or {}
    features: Dict[str, Dict[str, Any]] = {}
    for poi in pois:
        poi_id = str(poi.get("poi_id") or "")
        if not poi_id:
            continue
        features[poi_id] = build_poi_feature(poi, enrichment_map.get(poi_id) or {}, status_signal_map.get(poi_id) or {})
    _attach_relation_edges(features)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "source": {
            "pois": "backend/data/fixtures/mock_pois.json",
            "enrichment": "backend/data/gaode_poi_enrichment.json",
        },
        "dimension_groups": [
            "semantic_tags",
            "facets",
            "scores",
            "experience_scores",
            "risk_scores",
            "relation_edges",
            "evidence_sources",
            "feature_confidence",
        ],
        "feature_count": len(features),
        "features": features,
    }


def build_poi_feature(item: Dict[str, Any], enrichment: Optional[Dict[str, Any]] = None, status_signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    enrichment = enrichment or {}
    status_signal = status_signal or {}
    name = str(item.get("name") or "")
    category = str(item.get("category") or "")
    tags = set(str(tag) for tag in item.get("tags") or [])
    tags.update(str(tag) for tag in item.get("risk_tags") or [])
    tags.update(str(tag) for tag in item.get("suitable_scenarios") or [])
    evidence: Dict[str, list[str]] = {}
    facets: Dict[str, list[str]] = {
        "activity_type": [],
        "cuisine": [],
        "meal_format": [],
        "relation_fit": [],
        "occasion_fit": [],
        "venue_type": [],
        "risk_flags": [],
    }

    haystack = _haystack(item, enrichment)

    def add(tag: str, reason: str, facet: Optional[str] = None, facet_value: Optional[str] = None) -> None:
        tags.add(tag)
        evidence.setdefault(tag, [])
        if reason not in evidence[tag]:
            evidence[tag].append(reason)
        if facet and facet_value:
            _append_unique(facets.setdefault(facet, []), facet_value)

    if category == "restaurant":
        add("food", "category:restaurant")
        add("restaurant", "category:restaurant")
    queue_bucket = str(status_signal.get("queue_bucket") or "")
    if queue_bucket == "low":
        add("low_queue", "status_signal:low_queue", "risk_flags", "low_queue")
    elif queue_bucket == "medium":
        add("queue_medium", "status_signal:queue_medium", "risk_flags", "queue_medium")
    elif queue_bucket == "high":
        add("long_queue", "status_signal:long_queue", "risk_flags", "long_queue")
    if status_signal.get("availability_ratio") is not None and float(status_signal.get("availability_ratio") or 0) < 0.5:
        add("limited_capacity", "status_signal:limited_capacity", "risk_flags", "limited_capacity")
    if category == "walk_spot":
        add("light_walk", "category:walk_spot", "activity_type", "light_walk")
        if _matches(haystack, ("室内", "地下", "连通", "雨天", "温室", "雨歇", "避雨")):
            add("indoor", "walk_spot_indoor_weather_safe", "venue_type", "indoor")
            add("rain_safe", "walk_spot_indoor_weather_safe", "venue_type", "indoor")
        else:
            add("outdoor", "category:walk_spot", "venue_type", "outdoor")
    if _matches(haystack, ALCOHOL_WORDS):
        add("alcohol", "name_or_type:alcohol", "venue_type", "bar")
        add("light_drink", "name_or_type:alcohol", "venue_type", "bar")
    if _matches(haystack, BUFFET_WORDS):
        add("buffet", "name_or_type:buffet", "meal_format", "buffet")
        add("proper_dining", "buffet_implies_meal")
        add("slow_dining", "buffet_implies_meal")
        add("dinner", "buffet_implies_meal")
    if _matches(haystack, HOTPOT_WORDS):
        add("hotpot", "name_or_type:hotpot", "cuisine", "hotpot")
        add("proper_dining", "hotpot_implies_meal")
        add("slow_dining", "hotpot_implies_meal")
        add("dinner", "hotpot_implies_meal")
    if _matches(haystack, BBQ_WORDS):
        add("bbq", "name_or_type:bbq", "cuisine", "bbq")
        add("grill", "name_or_type:bbq", "cuisine", "grill")
        add("proper_dining", "bbq_implies_meal")
        add("slow_dining", "bbq_implies_meal")
        add("dinner", "bbq_implies_meal")
    if _matches(haystack, JAPANESE_WORDS):
        add("cuisine_japanese", "name_or_type:japanese", "cuisine", "japanese")
        add("proper_dining", "japanese_implies_meal")
        add("slow_dining", "japanese_implies_meal")
        add("date_friendly", "japanese_date_fit", "relation_fit", "date")
        add("dinner", "japanese_implies_meal")
    if _matches(haystack, SUSHI_WORDS):
        add("sushi", "name_or_type:sushi", "cuisine", "sushi")
        add("cuisine_japanese", "sushi_implies_japanese", "cuisine", "japanese")
    if _matches(haystack, IZAKAYA_WORDS):
        add("izakaya", "name_or_type:izakaya", "cuisine", "izakaya")
        add("cuisine_japanese", "izakaya_implies_japanese", "cuisine", "japanese")
    if _matches(haystack, WESTERN_WORDS):
        add("western_cuisine", "name_or_type:western", "cuisine", "western")
        add("proper_dining", "western_implies_meal")
        add("slow_dining", "western_implies_meal")
        add("date_friendly", "western_date_fit", "relation_fit", "date")
    if _matches(haystack, STEAK_WORDS):
        add("steak", "name_or_type:steak", "cuisine", "steak")
        add("western_cuisine", "steak_implies_western", "cuisine", "western")
    if _matches(haystack, LAMB_WORDS):
        add("lamb", "name_or_type:lamb", "cuisine", "lamb")
        add("proper_dining", "lamb_implies_meal")
    if _matches(haystack, HEALTHY_LIGHT_WORDS):
        add("healthy_light", "name_or_type:healthy_light", "meal_format", "light_meal")
        add("light_meal", "healthy_implies_light", "meal_format", "light_meal")
        add("light_food", "healthy_implies_light", "meal_format", "light_meal")
        add("low_calorie", "healthy_implies_light")
    if _matches(haystack, LIGHT_MEAL_WORDS):
        add("light_meal", "name_or_type:light_meal", "meal_format", "light_meal")
        add("light_food", "name_or_type:light_meal", "meal_format", "light_meal")
        add("family_friendly", "light_meal_family_fit", "relation_fit", "family")
    if _matches(haystack, PROPER_DINING_WORDS):
        add("proper_dining", "name_or_type:proper_dining")
        add("slow_dining", "name_or_type:proper_dining")
    if _matches(haystack, QUALITY_DINING_WORDS):
        add("quality_dining", "name_or_type:quality_dining", "occasion_fit", "quality_meal")
        add("ambience_dining", "name_or_type:quality_dining", "occasion_fit", "date")
        add("proper_dining", "quality_implies_proper")
        add("slow_dining", "quality_implies_proper")
    if _matches(haystack, COFFEE_WORDS):
        add("coffee", "name_or_type:coffee", "venue_type", "coffee")
        add("quiet_stay", "coffee_implies_stay", "occasion_fit", "conversation")
        add("conversation", "coffee_implies_conversation", "occasion_fit", "conversation")
    if _matches(haystack, DESSERT_WORDS):
        add("dessert", "name_or_type:dessert", "venue_type", "dessert")
        add("quiet_stay", "dessert_implies_stay", "occasion_fit", "conversation")
    if _matches(haystack, HEAVY_SPICY_WORDS):
        add("spicy_heavy", "name_or_type:spicy_heavy", "risk_flags", "heavy_meal")
    if _matches(haystack, SNACK_MEAL_WORDS):
        add("snack_meal", "name_or_type:snack_meal", "venue_type", "snack")
        add("casual_chain", "snack_meal_low_ritual", "risk_flags", "low_ritual_meal")
    if _matches(haystack, CASUAL_CHAIN_WORDS):
        add("casual_chain", "name_or_type:casual_chain", "risk_flags", "low_ritual_meal")
        add("low_end_chain", "name_or_type:casual_chain", "risk_flags", "low_ritual_meal")

    music_haystack = " ".join(
        str(value or "")
        for value in (
            item.get("name"),
            item.get("sub_category"),
            " ".join(str(tag) for tag in item.get("tags") or []),
            enrichment.get("name"),
            enrichment.get("gaode_type"),
            enrichment.get("business_area"),
        )
    )
    if _matches(music_haystack, MUSIC_WORDS):
        add("music", "name_or_type:music", "activity_type", "music")
        add("acoustic_music", "name_or_type:music", "activity_type", "music")
    if _matches(haystack, BOARD_GAME_WORDS):
        add("board_game", "name_or_type:board_game", "activity_type", "board_game")
        add("group_ok", "board_game_group_fit", "relation_fit", "group")
    karaoke_haystack = " ".join(
        str(value or "")
        for value in (
            item.get("name"),
            item.get("sub_category"),
            " ".join(str(tag) for tag in item.get("tags") or []),
            enrichment.get("name"),
            enrichment.get("gaode_type"),
        )
    )
    if _matches(karaoke_haystack, KARAOKE_WORDS):
        add("karaoke", "name_or_type:karaoke", "activity_type", "karaoke")
        add("group_ok", "karaoke_group_fit", "relation_fit", "group")
        add("indoor", "karaoke_indoor", "venue_type", "indoor")
        add("rain_safe", "karaoke_indoor", "venue_type", "indoor")
    if _looks_like_hands_on_experience(item, haystack):
        add("hands_on", "name_or_type:hands_on", "activity_type", "hands_on")
        add("craft", "name_or_type:hands_on", "activity_type", "hands_on")
        add("date_friendly", "hands_on_date_fit", "relation_fit", "date")
        add("visitor_friendly", "hands_on_visitor_fit", "relation_fit", "visitor")
        add("indoor", "hands_on_indoor")
        if category == "activity":
            add("child_friendly", "hands_on_family_fit", "relation_fit", "family")
            add("kid_safe", "hands_on_family_fit", "relation_fit", "family")
            add("family_time", "hands_on_family_fit", "relation_fit", "family")
    if _matches(haystack, AMUSEMENT_WORDS):
        add("amusement", "name_or_type:amusement", "activity_type", "amusement")
        add("child_friendly", "amusement_family_fit", "relation_fit", "family")
        add("kid_safe", "amusement_family_fit", "relation_fit", "family")
        add("family_time", "amusement_family_fit", "relation_fit", "family")
    if _matches(haystack, FAMILY_ACTIVITY_WORDS):
        add("child_friendly", "name_or_type:family_activity", "relation_fit", "family")
        add("kid_safe", "name_or_type:family_activity", "relation_fit", "family")
        add("family_time", "name_or_type:family_activity", "relation_fit", "family")
    if "影院" in haystack or "剧院" in haystack:
        add("theater", "name_or_type:theater", "activity_type", "theater")
        add("date_friendly", "theater_date_fit", "relation_fit", "date")
    if "私人影院" in haystack or "点播影院" in haystack:
        add("private_cinema", "name_or_type:private_cinema", "activity_type", "private_cinema")
        add("quiet", "private_cinema_quiet")
    if _matches(haystack, LAKE_WORDS):
        add("lake", "name_or_type:lake", "venue_type", "lake")
        add("visitor_friendly", "lake_visitor_fit", "relation_fit", "visitor")
        add("showcase_local", "lake_local_fit", "occasion_fit", "showcase")
        add("photo_spot", "lake_photo_fit", "occasion_fit", "photo")
        add("light_walk", "lake_walk_fit", "activity_type", "walk")
    if _matches(haystack, LOW_FIT_ACTIVITY_WORDS) or tags & {"esports", "fitness", "sports", "swimming"}:
        add("low_fit_activity", "name_or_type:low_fit_activity", "risk_flags", "low_fit_activity")
        add("strong_social", "name_or_type:low_fit_activity", "risk_flags", "strong_social")

    if "friend_group" in tags and tags & {"conversation", "quiet_stay", "coffee", "dessert", "mall", "board_game", "karaoke"}:
        add("group_ok", "friend_group_social_stay_fit", "relation_fit", "group")
    if "group_ok" in tags or "friend_group" in tags:
        _append_unique(facets["relation_fit"], "group")
    if "mall" in tags:
        add("mall_walk", "tag:mall", "activity_type", "mall_walk")
        add("rain_safe", "tag:mall", "venue_type", "mall")
        _append_unique(facets["venue_type"], "mall")
    if "indoor" in tags:
        add("rain_safe", "tag:indoor", "venue_type", "indoor")
        _append_unique(facets["venue_type"], "indoor")

    scores = _scores(item, enrichment, tags)
    experience_scores = _experience_scores(item, enrichment, tags)
    risk_scores = _risk_scores(item, enrichment, tags, status_signal)
    scores.update(_compatibility_scores(experience_scores, risk_scores))
    feature_confidence = _feature_confidence(item, enrichment, evidence)
    confidence = feature_confidence["overall"]
    return {
        "poi_id": str(item.get("poi_id") or ""),
        "name": name,
        "category": category,
        "area": item.get("area") or (item.get("location") or {}).get("area"),
        "semantic_tags": sorted(tags),
        "facets": {key: sorted(set(value)) for key, value in facets.items()},
        "scores": scores,
        "experience_scores": experience_scores,
        "risk_scores": risk_scores,
        "status_signals": status_signal,
        "relation_edges": [],
        "evidence": {key: value[:4] for key, value in sorted(evidence.items())},
        "evidence_sources": _evidence_sources(item, enrichment, evidence),
        "feature_confidence": feature_confidence,
        "review_summary": _review_summary(item, tags, experience_scores, risk_scores),
        "confidence": confidence,
    }


def _scores(item: Dict[str, Any], enrichment: Dict[str, Any], tags: set[str]) -> Dict[str, float]:
    category = str(item.get("category") or "")
    rating = _float(item.get("rating"), 4.2)
    price = _float(item.get("price_per_person"), 0.0)
    raw_quality = _float(enrichment.get("quality_score"), 0.0)
    quality = _clamp(max((rating - 4.0) / 0.8, raw_quality / 140.0 if raw_quality else 0.0))
    proper_dining = _clamp((0.75 if tags & {"proper_dining", "slow_dining"} else 0.0) + (0.2 if tags & {"quality_dining", "ambience_dining"} else 0.0))
    casual_penalty = _clamp((0.55 if tags & {"casual_chain", "low_end_chain"} else 0.0) + (0.35 if "snack_meal" in tags else 0.0))
    low_fit_penalty = _clamp(1.0 if "low_fit_activity" in tags else 0.0)
    buffet_fit = 1.0 if "buffet" in tags else 0.0
    amusement_fit = 1.0 if "amusement" in tags else 0.0
    light_meal_fit = _clamp((0.72 if tags & {"light_meal", "light_food", "healthy_light"} else 0.0) - (0.5 if "spicy_heavy" in tags else 0.0))
    family_fit = _clamp(
        (0.72 if tags & {"child_friendly", "kid_safe", "family_time", "family_friendly"} else 0.0)
        + (0.24 if tags & {"amusement", "hands_on", "craft"} else 0.0)
        + (0.12 if category == "restaurant" and tags & {"light_meal", "buffet"} else 0.0)
        - low_fit_penalty
        - (0.7 if tags & {"alcohol", "light_drink"} else 0.0)
    )
    date_fit = _clamp(
        (0.46 if tags & {"date_friendly", "quiet", "quiet_stay"} else 0.0)
        + (0.34 if tags & {"quality_dining", "ambience_dining", "proper_dining", "theater", "private_cinema", "hands_on"} else 0.0)
        + (0.14 if price >= 80 else 0.0)
        - (0.45 if tags & {"low_fit_activity", "low_end_chain"} else 0.0)
    )
    friend_fit = _clamp((0.55 if tags & {"group_ok", "friend_group", "board_game", "karaoke", "mall"} else 0.0) + (0.24 if category == "restaurant" else 0.0) - (0.18 if price > 180 else 0.0))
    solo_fit = _clamp((0.45 if tags & {"quiet", "quiet_stay", "coffee", "lake", "light_walk"} else 0.0) + (0.26 if tags & {"alcohol", "light_drink", "music", "acoustic_music"} else 0.0) - (0.36 if tags & {"strong_social", "low_fit_activity"} else 0.0))
    visitor_fit = _clamp((0.46 if tags & {"visitor_friendly", "showcase_local", "lake", "photo_spot"} else 0.0) + (0.28 if tags & {"quality_dining", "proper_dining", "conversation", "quiet_stay"} else 0.0) - (0.32 if tags & {"low_fit_activity", "low_end_chain"} else 0.0))
    route_anchor = _clamp((0.35 if tags & {"lake", "mall"} else 0.0) + (0.25 if tags & {"showcase_local", "amusement"} else 0.0))
    return {
        "quality": round(quality, 4),
        "proper_dining": round(proper_dining, 4),
        "casual_penalty": round(casual_penalty, 4),
        "low_fit_penalty": round(low_fit_penalty, 4),
        "buffet_fit": round(buffet_fit, 4),
        "amusement_fit": round(amusement_fit, 4),
        "light_meal_fit": round(light_meal_fit, 4),
        "family_fit": round(family_fit, 4),
        "date_fit": round(date_fit, 4),
        "friend_fit": round(friend_fit, 4),
        "solo_fit": round(solo_fit, 4),
        "visitor_fit": round(visitor_fit, 4),
        "route_anchor": round(route_anchor, 4),
    }


def _experience_scores(item: Dict[str, Any], enrichment: Dict[str, Any], tags: set[str]) -> Dict[str, float]:
    category = str(item.get("category") or "")
    price = _float(item.get("price_per_person"), 0.0)
    dining_substance = _clamp(
        (0.62 if category == "restaurant" and tags & {"proper_dining", "slow_dining"} else 0.0)
        + (0.22 if tags & {"buffet", "hotpot", "bbq", "grill", "cuisine_japanese", "western_cuisine", "steak", "lamb"} else 0.0)
        + (0.16 if tags & {"quality_dining", "ambience_dining", "light_meal", "healthy_light"} else 0.0)
        - (0.45 if tags & {"snack_meal", "coffee", "dessert"} and not tags & {"proper_dining", "slow_dining"} else 0.0)
    )
    ritual_fit = _clamp(
        (0.32 if tags & {"date_friendly", "quality_dining", "ambience_dining"} else 0.0)
        + (0.2 if tags & {"hands_on", "craft", "theater", "private_cinema", "lake", "photo_spot"} else 0.0)
        + (0.18 if category == "restaurant" and tags & {"proper_dining", "slow_dining"} else 0.0)
        + (0.12 if price >= 80 else 0.0)
        - (0.32 if tags & {"low_end_chain", "casual_chain", "low_fit_activity"} else 0.0)
    )
    conversation_fit = _clamp(
        (0.32 if tags & {"conversation", "quiet_stay", "coffee", "dessert"} else 0.0)
        + (0.24 if tags & {"lake", "park", "light_walk"} else 0.0)
        + (0.18 if tags & {"slow_dining", "proper_dining", "light_meal"} else 0.0)
        + (0.16 if tags & {"board_game", "group_ok"} else 0.0)
        - (0.24 if tags & {"low_fit_activity", "strong_social"} and not tags & {"karaoke", "board_game"} else 0.0)
    )
    quiet_fit = _clamp(
        (0.38 if tags & {"quiet", "quiet_stay", "coffee", "lake", "park", "light_walk"} else 0.0)
        + (0.16 if tags & {"private_cinema", "dessert"} else 0.0)
        - (0.28 if tags & {"karaoke", "board_game", "strong_social"} else 0.0)
    )
    kid_safety = _clamp(
        (0.42 if tags & {"child_friendly", "kid_safe", "family_time", "family_friendly"} else 0.0)
        + (0.28 if tags & {"amusement", "hands_on", "craft", "light_meal"} else 0.0)
        - (0.48 if tags & {"alcohol", "light_drink", "strong_social", "low_fit_activity"} else 0.0)
        - (0.22 if tags & {"spicy_heavy"} else 0.0)
    )
    walkability = _clamp(
        (0.38 if tags & {"lake", "park", "light_walk"} else 0.0)
        + (0.2 if tags & {"mall_walk", "showcase_local", "photo_spot"} else 0.0)
        + (0.12 if category == "walk_spot" else 0.0)
    )
    rain_comfort = _clamp((0.48 if tags & {"rain_safe", "indoor", "mall"} else 0.0) + (0.12 if tags & {"coffee", "dessert"} else 0.0))
    stay_duration_fit = _clamp(
        (0.24 if tags & {"slow_dining", "coffee", "quiet_stay"} else 0.0)
        + (0.24 if tags & {"hands_on", "craft", "amusement", "karaoke", "board_game"} else 0.0)
        + (0.16 if tags & {"lake", "park", "light_walk", "conversation"} else 0.0)
    )
    plan_anchor_strength = _clamp(
        max(dining_substance, ritual_fit, conversation_fit, kid_safety, walkability)
        + (0.1 if tags & {"showcase_local", "buffet", "karaoke", "amusement", "hands_on"} else 0.0)
    )
    return {
        "dining_substance": round(dining_substance, 4),
        "ritual_fit": round(ritual_fit, 4),
        "conversation_fit": round(conversation_fit, 4),
        "quiet_fit": round(quiet_fit, 4),
        "kid_safety": round(kid_safety, 4),
        "walkability": round(walkability, 4),
        "rain_comfort": round(rain_comfort, 4),
        "stay_duration_fit": round(stay_duration_fit, 4),
        "plan_anchor_strength": round(plan_anchor_strength, 4),
    }


def _risk_scores(item: Dict[str, Any], enrichment: Dict[str, Any], tags: set[str], status_signal: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    status_signal = status_signal or {}
    category = str(item.get("category") or "")
    snack_substitution = _clamp((0.62 if tags & {"snack_meal", "casual_chain", "low_end_chain"} else 0.0) + (0.2 if category == "restaurant" and not tags & {"proper_dining", "slow_dining"} else 0.0))
    heavy_meal = _clamp((0.52 if tags & {"spicy_heavy"} else 0.0) + (0.18 if tags & {"hotpot", "bbq", "grill"} else 0.0))
    low_fit_activity = _clamp(1.0 if "low_fit_activity" in tags else 0.0)
    strong_social = _clamp((0.42 if tags & {"strong_social", "board_game", "karaoke"} else 0.0) + (0.18 if tags & {"alcohol", "light_drink"} else 0.0))
    alcohol_risk = _clamp(1.0 if tags & {"alcohol", "light_drink"} else 0.0)
    mall_dependency = _clamp((0.72 if tags & {"mall", "mall_walk", "shopping"} else 0.0) + (0.12 if "rain_safe" in tags and "mall" in tags else 0.0))
    movie_dependency = _clamp(0.78 if tags & {"theater", "private_cinema", "movie"} else 0.0)
    dinner_substitution = _clamp(0.78 if category == "restaurant" and tags & {"coffee", "dessert", "snack_meal"} and not tags & {"proper_dining", "slow_dining", "light_meal"} else 0.0)
    static_queue_pressure = _clamp((0.62 if "queue_risk" in tags else 0.0) + (0.38 if "capacity_risk" in tags else 0.0) + (0.18 if tags & {"hotpot", "bbq", "grill", "buffet", "amusement"} else 0.0) - (0.28 if "low_queue" in tags else 0.0))
    if isinstance(status_signal.get("queue_pressure"), (int, float)):
        queue_pressure = _clamp(max(float(status_signal.get("queue_pressure") or 0.0), static_queue_pressure * 0.35))
    else:
        queue_pressure = static_queue_pressure
    child_safety_risk = _clamp(alcohol_risk * 0.5 + low_fit_activity * 0.34 + heavy_meal * 0.18)
    route_fragility = _clamp(0.42 if not tags & {"lake", "park", "mall", "showcase_local", "route_simple", "light_walk", "amusement"} else 0.12)
    weather_exposure = _clamp(
        0.86
        if category == "walk_spot" and not tags & {"rain_safe", "indoor", "mall"}
        else 0.68
        if tags & {"outdoor", "outdoor_shade", "lake", "park", "light_walk"} and not tags & {"rain_safe", "indoor", "mall"}
        else 0.16
        if tags & {"showcase_local", "photo_spot"} and not tags & {"rain_safe", "indoor", "mall"}
        else 0.0
    )
    intent_mismatch = _clamp(max(snack_substitution, low_fit_activity, dinner_substitution) + (0.12 if tags & {"strong_social", "alcohol"} else 0.0))
    return {
        "snack_substitution": round(snack_substitution, 4),
        "heavy_meal": round(heavy_meal, 4),
        "low_fit_activity": round(low_fit_activity, 4),
        "strong_social": round(strong_social, 4),
        "alcohol_risk": round(alcohol_risk, 4),
        "mall_dependency": round(mall_dependency, 4),
        "movie_dependency": round(movie_dependency, 4),
        "dinner_substitution": round(dinner_substitution, 4),
        "queue_pressure": round(queue_pressure, 4),
        "child_safety_risk": round(child_safety_risk, 4),
        "route_fragility": round(route_fragility, 4),
        "weather_exposure": round(weather_exposure, 4),
        "intent_mismatch": round(intent_mismatch, 4),
    }


def _compatibility_scores(experience_scores: Dict[str, float], risk_scores: Dict[str, float]) -> Dict[str, float]:
    return {
        "conversation_fit": experience_scores["conversation_fit"],
        "ritual_fit": experience_scores["ritual_fit"],
        "dining_substance": experience_scores["dining_substance"],
        "kid_safety": experience_scores["kid_safety"],
        "walkability": experience_scores["walkability"],
        "snack_substitution_risk": risk_scores["snack_substitution"],
        "heavy_meal_risk": risk_scores["heavy_meal"],
        "mall_dependency_risk": risk_scores["mall_dependency"],
        "movie_dependency_risk": risk_scores["movie_dependency"],
        "queue_pressure_risk": risk_scores["queue_pressure"],
        "weather_exposure_risk": risk_scores["weather_exposure"],
        "intent_mismatch_risk": risk_scores["intent_mismatch"],
    }


def _confidence(item: Dict[str, Any], enrichment: Dict[str, Any], evidence: Dict[str, list[str]]) -> float:
    return _feature_confidence(item, enrichment, evidence)["overall"]


def _feature_confidence(item: Dict[str, Any], enrichment: Dict[str, Any], evidence: Dict[str, list[str]]) -> Dict[str, float]:
    score = 0.42
    if item.get("tags"):
        score += 0.16
    if item.get("rating"):
        score += 0.12
    if item.get("price_per_person"):
        score += 0.08
    if enrichment.get("gaode_type") or enrichment.get("biz_ext"):
        score += 0.12
    if evidence:
        score += min(0.10, len(evidence) * 0.012)
    semantic = _clamp(0.36 + (0.26 if item.get("tags") else 0.0) + min(0.24, len(evidence) * 0.018))
    quality = _clamp(0.38 + (0.28 if item.get("rating") else 0.0) + (0.2 if enrichment.get("quality_score") else 0.0))
    price = _clamp(0.42 + (0.36 if item.get("price_per_person") else 0.0) + (0.12 if (enrichment.get("biz_ext") or {}).get("cost") else 0.0))
    hours = _clamp(0.32 + (0.24 if item.get("opening_hours") else 0.0) + (0.22 if enrichment.get("open_time") else 0.0))
    enrichment_confidence = _clamp(0.28 + (0.34 if enrichment.get("gaode_type") else 0.0) + (0.18 if enrichment.get("biz_ext") else 0.0))
    return {
        "overall": round(_clamp(score), 4),
        "semantic": round(semantic, 4),
        "quality": round(quality, 4),
        "price": round(price, 4),
        "hours": round(hours, 4),
        "enrichment": round(enrichment_confidence, 4),
    }


def _evidence_sources(item: Dict[str, Any], enrichment: Dict[str, Any], evidence: Dict[str, list[str]]) -> list[Dict[str, Any]]:
    sources = []
    if item.get("name") or item.get("sub_category"):
        sources.append({"source": "mock_poi_identity", "fields": ["name", "sub_category"], "confidence": 0.72})
    if item.get("tags") or item.get("suitable_scenarios"):
        sources.append({"source": "mock_poi_tags", "fields": ["tags", "suitable_scenarios"], "confidence": 0.78})
    if item.get("rating") or item.get("price_per_person"):
        sources.append({"source": "mock_poi_business", "fields": ["rating", "price_per_person"], "confidence": 0.68})
    if enrichment.get("gaode_type") or enrichment.get("biz_ext") or enrichment.get("open_time"):
        sources.append({"source": "gaode_enrichment", "fields": ["gaode_type", "biz_ext", "open_time"], "confidence": 0.74})
    if evidence:
        sources.append({"source": "deterministic_feature_rules", "fields": sorted(evidence)[:12], "confidence": 0.82})
    return sources


def _review_summary(item: Dict[str, Any], tags: set[str], experience_scores: Dict[str, float], risk_scores: Dict[str, float]) -> str:
    name = str(item.get("name") or "该地点")
    strengths = []
    if experience_scores["dining_substance"] >= 0.62:
        strengths.append("正餐充分")
    if experience_scores["ritual_fit"] >= 0.55:
        strengths.append("有仪式感")
    if experience_scores["conversation_fit"] >= 0.5:
        strengths.append("适合聊天停留")
    if experience_scores["kid_safety"] >= 0.52:
        strengths.append("亲子安全")
    if experience_scores["walkability"] >= 0.42:
        strengths.append("适合散步转场")
    risks = []
    if risk_scores["snack_substitution"] >= 0.5:
        risks.append("可能像小吃替代正餐")
    if risk_scores["low_fit_activity"] >= 0.8:
        risks.append("关系场景适配较窄")
    if risk_scores["mall_dependency"] >= 0.65:
        risks.append("依赖商场场景")
    if risk_scores["movie_dependency"] >= 0.65:
        risks.append("偏电影/剧场型")
    if risk_scores["queue_pressure"] >= 0.6:
        risks.append("排队压力偏高")
    if risk_scores["weather_exposure"] >= 0.65:
        risks.append("雨天户外暴露高")
    if risk_scores["alcohol_risk"] >= 0.8:
        risks.append("含酒精场景")
    strength_text = "、".join(strengths[:3]) if strengths else "基础信息可用"
    risk_text = "；风险：" + "、".join(risks[:2]) if risks else ""
    return f"{name}：{strength_text}{risk_text}。"


def _attach_relation_edges(features: Dict[str, Dict[str, Any]]) -> None:
    rows = list(features.values())
    for feature in rows:
        edges = []
        for target in rows:
            if feature is target:
                continue
            relation = _relation_type(feature, target)
            if not relation:
                continue
            score = _relation_score(feature, target, relation)
            if score <= 0.0:
                continue
            edges.append(
                {
                    "target_poi_id": target.get("poi_id"),
                    "relation": relation,
                    "score": round(score, 4),
                    "reason": _relation_reason(relation),
                }
            )
        feature["relation_edges"] = sorted(edges, key=lambda edge: (-float(edge["score"]), str(edge["target_poi_id"])))[:8]


def _relation_type(source: Dict[str, Any], target: Dict[str, Any]) -> Optional[str]:
    source_tags = set(str(tag) for tag in source.get("semantic_tags") or [])
    target_tags = set(str(tag) for tag in target.get("semantic_tags") or [])
    source_category = str(source.get("category") or "")
    target_category = str(target.get("category") or "")
    if source_category == target_category and _substitute_relation_allowed(source_category, source_tags, target_tags):
        return "substitute"
    if source_category == "restaurant" and target_category in {"activity", "walk_spot"} and target_tags & {"coffee", "dessert", "lake", "park", "light_walk", "quiet_stay", "karaoke", "board_game", "hands_on", "craft"}:
        return "pairs_after_meal"
    if source_category in {"activity", "walk_spot"} and target_category == "restaurant" and target_tags & {"proper_dining", "slow_dining", "light_meal", "quality_dining", "buffet", "bbq", "hotpot"}:
        return "pairs_with_meal"
    if source_category == "restaurant" and target_category == "restaurant" and source_tags & {"coffee", "dessert"} and target_tags & {"proper_dining", "slow_dining"}:
        return "light_stop_before_meal"
    return None


def _substitute_relation_allowed(category: str, left: set[str], right: set[str]) -> bool:
    if category == "restaurant":
        return _shared_restaurant_substitute_cluster(left, right)
    if category in {"activity", "walk_spot"}:
        return _shared_activity_substitute_cluster(left, right)
    return _shared_relation_cluster(left, right)


def _shared_restaurant_substitute_cluster(left: set[str], right: set[str]) -> bool:
    dining_clusters = (
        {"buffet"},
        {"hotpot"},
        {"bbq", "grill", "lamb"},
        {"cuisine_japanese", "sushi", "izakaya"},
        {"western_cuisine", "steak"},
    )
    if any(left & cluster and right & cluster for cluster in dining_clusters):
        return True

    meal_specific = {
        "buffet",
        "hotpot",
        "bbq",
        "grill",
        "lamb",
        "cuisine_japanese",
        "sushi",
        "izakaya",
        "western_cuisine",
        "steak",
    }
    snack_cluster = {"coffee", "dessert", "quiet_stay"}
    if left & snack_cluster and right & snack_cluster and not ((left | right) & meal_specific):
        return True

    light_cluster = {"light_meal", "light_food", "healthy_light"}
    return bool(left & light_cluster and right & light_cluster and not ((left | right) & (meal_specific | {"coffee", "dessert"})))


def _shared_activity_substitute_cluster(left: set[str], right: set[str]) -> bool:
    activity_clusters = (
        {"lake", "park", "light_walk"},
        {"hands_on", "craft"},
        {"karaoke"},
        {"board_game"},
        {"amusement"},
        {"music", "acoustic_music", "alcohol", "light_drink"},
        {"theater", "private_cinema"},
    )
    return any(left & cluster and right & cluster for cluster in activity_clusters)


def _shared_relation_cluster(left: set[str], right: set[str]) -> bool:
    primary_clusters = (
        {"buffet"},
        {"hotpot"},
        {"bbq", "grill", "lamb"},
        {"cuisine_japanese", "sushi", "izakaya"},
        {"western_cuisine", "steak"},
        {"coffee", "dessert", "quiet_stay"},
        {"lake", "park", "light_walk"},
        {"hands_on", "craft"},
        {"karaoke"},
        {"board_game"},
        {"amusement"},
        {"music", "acoustic_music", "alcohol", "light_drink"},
    )
    if any(left & cluster and right & cluster for cluster in primary_clusters):
        return True
    specific_food = {
        "buffet",
        "hotpot",
        "bbq",
        "grill",
        "lamb",
        "cuisine_japanese",
        "sushi",
        "izakaya",
        "western_cuisine",
        "steak",
        "coffee",
        "dessert",
    }
    light_cluster = {"light_meal", "light_food", "healthy_light"}
    return bool(left & light_cluster and right & light_cluster and not (left & specific_food or right & specific_food))


def _relation_score(source: Dict[str, Any], target: Dict[str, Any], relation: str) -> float:
    source_area = str(source.get("area") or "")
    target_area = str(target.get("area") or "")
    target_scores = target.get("scores") or {}
    target_experience = target.get("experience_scores") or {}
    value = 0.28
    if source_area and source_area == target_area:
        value += 0.28
    value += 0.22 if relation == "substitute" else 0.18
    value += _float(target_scores.get("quality"), 0.0) * 0.14
    value += _float(target_experience.get("plan_anchor_strength"), 0.0) * 0.12
    return _clamp(value)


def _relation_reason(relation: str) -> str:
    if relation == "substitute":
        return "同类语义候选，可作为不可用时的替代。"
    if relation == "pairs_after_meal":
        return "餐后可衔接的停留或活动节点。"
    if relation == "pairs_with_meal":
        return "活动后可衔接的正餐节点。"
    if relation == "light_stop_before_meal":
        return "正餐前后的轻停留节点。"
    return "可组合候选。"


def _deep_copy_dict(value: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, child in (value or {}).items():
        if isinstance(child, dict):
            result[key] = _deep_copy_dict(child)
        elif isinstance(child, list):
            result[key] = list(child)
        else:
            result[key] = child
    return result


def _merge_feature_overlay(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = _deep_copy_dict(base)
    for key, value in (overlay or {}).items():
        if key == "semantic_tags":
            tags = list(result.get("semantic_tags") or [])
            for tag in value or []:
                _append_unique(tags, str(tag))
            result["semantic_tags"] = sorted(tags)
        elif isinstance(value, dict):
            existing = result.get(key)
            result[key] = _merge_nested_keep_existing(existing if isinstance(existing, dict) else {}, value)
        elif isinstance(value, list):
            existing_list = list(result.get(key) or [])
            for item in value:
                if item not in existing_list:
                    existing_list.append(item)
            result[key] = existing_list
        else:
            result.setdefault(key, value)
    return result


def _merge_nested_keep_existing(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = _deep_copy_dict(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict):
            existing = result.get(key)
            result[key] = _merge_nested_keep_existing(existing if isinstance(existing, dict) else {}, value)
        elif isinstance(value, list):
            existing_list = list(result.get(key) or [])
            for item in value:
                if item not in existing_list:
                    existing_list.append(item)
            result[key] = existing_list
        elif key not in result or result.get(key) in (None, "", []):
            result[key] = value
    return result


def _merge_missing_feature_fields(base: Dict[str, Any], derived: Dict[str, Any]) -> Dict[str, Any]:
    result = _deep_copy_dict(base)
    for key, value in (derived or {}).items():
        if isinstance(value, dict):
            existing = result.get(key)
            result[key] = _merge_nested_fill_missing(existing if isinstance(existing, dict) else {}, value)
        elif isinstance(value, list):
            existing_list = list(result.get(key) or [])
            for item in value:
                if item not in existing_list:
                    existing_list.append(item)
            result[key] = existing_list
        elif key not in result or result.get(key) in (None, "", []):
            result[key] = value
    return result


def _merge_nested_fill_missing(base: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    result = _deep_copy_dict(base)
    for key, value in (defaults or {}).items():
        if isinstance(value, dict):
            existing = result.get(key)
            result[key] = _merge_nested_fill_missing(existing if isinstance(existing, dict) else {}, value)
        elif isinstance(value, list):
            existing_list = list(result.get(key) or [])
            for item in value:
                if item not in existing_list:
                    existing_list.append(item)
            result[key] = existing_list
        elif key not in result or result.get(key) in (None, "", []):
            result[key] = value
    return result


def _derived_structured_features(item: Dict[str, Any], feature: Dict[str, Any]) -> Dict[str, Any]:
    tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
    name = str(item.get("name") or feature.get("name") or "")
    category = str(item.get("category") or feature.get("category") or "")
    scores = feature.get("scores") or {}
    experience = feature.get("experience_scores") or {}
    risk = feature.get("risk_scores") or {}
    text = " ".join([name, " ".join(tags)])
    menu_features = _derived_menu_features(category, text, tags, scores, experience, risk)
    existing_activity_features = feature.get("activity_features") if isinstance(feature.get("activity_features"), dict) else None
    activity_features = existing_activity_features or _derived_activity_features(category, text, tags, scores, experience, risk)
    family_features = {
        "family_friendly_score": round(_clamp(max(_float(scores.get("family_fit"), 0.5), 1.0 if tags & {"child_friendly", "kid_safe", "family_time"} else 0.5)), 4),
        "child_food_score": round(_clamp(max(_float(experience.get("kid_safety"), 0.5), 0.8 if tags & {"light_meal", "light_food"} or _matches(text, BURGER_WORDS) else 0.5)), 4),
        "has_child_chair": False,
        "has_restroom": bool(tags & {"mall", "amusement", "child_friendly", "indoor"}),
        "noise_level": round(_clamp(max(_float(risk.get("strong_social"), 0.5), 0.75 if tags & {"karaoke", "board_game", "strong_social"} else 0.35)), 4),
    }
    queue_pressure = _float(risk.get("queue_pressure"), 0.5)
    queue_features = {
        "queue_risk": round(_clamp(queue_pressure), 4),
        "reservation_supported": category == "restaurant" or "low_queue" in tags,
        "avg_wait_minutes_peak": int(round(8 + _clamp(queue_pressure) * 28)),
        "avg_wait_minutes_offpeak": int(round(2 + _clamp(queue_pressure) * 12)),
    }
    physical_features = {
        "walking_intensity": round(_clamp(_float(risk.get("route_fragility"), 0.45)), 4),
        "weather_sensitive": bool(_float(risk.get("weather_exposure"), 0.0) >= 0.55),
        "indoor_ratio": 0.85 if tags & {"indoor", "rain_safe", "mall"} else 0.35,
    }
    experience_features = {
        "family_friendly_score": family_features["family_friendly_score"],
        "relaxation_score": round(_clamp(max(_float(experience.get("quiet_fit"), 0.45), _float(experience.get("walkability"), 0.4))), 4),
        "photo_score": 0.9 if tags & {"photo_spot", "lake", "showcase_local"} else 0.45,
        "premium_score": round(_clamp(max(_float(scores.get("quality"), 0.5), _float(experience.get("ritual_fit"), 0.35))), 4),
        "casual_score": round(_clamp(1.0 - _float(scores.get("quality"), 0.5)), 4),
    }
    child_features = {
        "suitable_age_min": 3 if tags & {"child_friendly", "kid_safe", "amusement", "hands_on"} else 8,
        "suitable_age_max": 12 if tags & {"child_friendly", "kid_safe", "amusement", "hands_on"} else 99,
        "child_friendly_score": family_features["family_friendly_score"],
        "has_restroom": family_features["has_restroom"],
        "has_rest_area": bool(tags & {"mall", "lake", "park", "quiet_stay", "amusement"}),
        "stroller_friendly": bool(tags & {"mall", "amusement", "lake", "park"}),
    }
    addon_features = _derived_addons(tags, menu_features, family_features, queue_features)
    return {
        "menu_features": menu_features,
        "activity_features": activity_features,
        "family_features": family_features,
        "queue_features": queue_features,
        "physical_features": physical_features,
        "experience_features": experience_features,
        "child_features": child_features,
        "addon_features": addon_features,
        "embedding_text": " ".join(
            str(value)
            for value in [
                name,
                category,
                " ".join(tags),
                " ".join(menu_features.get("signature_dishes") or []),
                " ".join(activity_features.get("raw_activity_terms") or []),
            ]
            if value
        ),
    }


def _derived_menu_features(
    category: str,
    text: str,
    tags: set[str],
    scores: Dict[str, Any],
    experience: Dict[str, Any],
    risk: Dict[str, Any],
) -> Dict[str, Any]:
    dish_ids: list[str] = []
    parent_categories: list[str] = []
    raw_terms: list[str] = []
    signature: list[str] = []

    def add_food(dish_id: str, category_name: str, raw_term: str) -> None:
        _append_unique(dish_ids, dish_id)
        _append_unique(parent_categories, category_name)
        _append_unique(raw_terms, raw_term)
        _append_unique(signature, raw_term)

    if "小龙虾" in text or "龙虾" in text or "虾尾" in text:
        add_food("DISH_CRAYFISH", "CRAYFISH", "小龙虾")
    if "hotpot" in tags or _matches(text, HOTPOT_WORDS):
        add_food("DISH_HOTPOT", "HOTPOT", "火锅")
    if tags & {"bbq", "grill"} or _matches(text, BBQ_WORDS):
        add_food("DISH_BBQ", "BBQ", "烧烤")
    if tags & {"light_meal", "light_food", "healthy_light", "low_calorie"} or _matches(text, HEALTHY_LIGHT_WORDS):
        add_food("DISH_LIGHT_MEAL", "LIGHT_MEAL", "轻食")
    if _matches(text, BURGER_WORDS):
        add_food("DISH_CHILD_FRIENDLY_FOOD", "CHILD_FRIENDLY", "汉堡")
    if "coffee" in tags or "咖啡" in text:
        add_food("DISH_COFFEE", "DRINK", "咖啡")
    if "奶茶" in text or "茶姬" in text or "1点点" in text:
        add_food("DISH_MILK_TEA", "DRINK", "奶茶")
    if "dessert" in tags or _matches(text, DESSERT_WORDS):
        add_food("DISH_DESSERT", "DESSERT", "甜品")
    if tags & {"snack_meal"} or _matches(text, SNACK_MEAL_WORDS):
        add_food("DISH_SNACK", "SNACK", "小吃")
    if tags & {"showcase_local"} or _matches(text, ("杭帮菜", "本地菜", "私房菜", "绿茶餐厅", "衢州人家", "東大方")):
        add_food("DISH_HANGZHOU_LOCAL", "LOCAL_FOOD", "本地菜")
    if tags & {"cuisine_japanese", "sushi", "izakaya"}:
        add_food("DISH_JAPANESE", "JAPANESE", "日料")
    if tags & {"lamb"}:
        add_food("DISH_LAMB", "LAMB", "羊肉")
    if "面" in text:
        add_food("DISH_NOODLES", "NOODLES", "面")
    if category == "restaurant" and not dish_ids:
        _append_unique(parent_categories, "UNKNOWN_FOOD")

    spicy_level = _clamp(0.75 if tags & {"spicy_heavy", "hotpot", "bbq", "grill"} else 0.25)
    oiliness = _clamp(0.75 if tags & {"spicy_heavy", "hotpot", "bbq", "grill"} else 0.35)
    healthy_score = _clamp(max(_float(scores.get("light_meal_fit"), 0.35), 0.8 if tags & {"light_meal", "light_food", "healthy_light"} else 0.35))
    has_non_spicy = bool(tags & {"light_meal", "light_food", "healthy_light", "cuisine_japanese", "western_cuisine", "coffee", "dessert"}) or spicy_level <= 0.45
    has_child_food = bool(tags & {"child_friendly", "family_friendly", "light_meal", "light_food", "dessert", "coffee"} or "DISH_CHILD_FRIENDLY_FOOD" in dish_ids) or has_non_spicy
    return {
        "signature_dishes": signature,
        "dish_ids": dish_ids,
        "parent_categories": parent_categories,
        "raw_food_terms": raw_terms,
        "ingredients": [],
        "cooking_methods": ["烧烤"] if "DISH_BBQ" in dish_ids else [],
        "flavors": ["清淡"] if "DISH_LIGHT_MEAL" in dish_ids else ["辣"] if spicy_level >= 0.7 else [],
        "forms": ["甜品"] if "DISH_DESSERT" in dish_ids else ["饮品"] if parent_categories and set(parent_categories) == {"DRINK"} else [],
        "scenes": ["朋友聚餐"] if tags & {"bbq", "hotpot", "group_ok"} else ["亲子"] if tags & {"child_friendly", "family_time"} else [],
        "has_crayfish": "DISH_CRAYFISH" in dish_ids,
        "has_bbq": "DISH_BBQ" in dish_ids,
        "has_hotpot": "DISH_HOTPOT" in dish_ids,
        "has_local_food": "DISH_HANGZHOU_LOCAL" in dish_ids,
        "has_non_spicy": has_non_spicy,
        "has_child_friendly_food": has_child_food,
        "spicy_level": round(spicy_level, 4),
        "oiliness_level": round(oiliness, 4),
        "healthy_option_score": round(healthy_score, 4),
    }


def _derived_activity_features(
    category: str,
    text: str,
    tags: set[str],
    scores: Dict[str, Any],
    experience: Dict[str, Any],
    risk: Dict[str, Any],
) -> Dict[str, Any]:
    type_ids: list[str] = []
    parent_categories: list[str] = []
    raw_terms: list[str] = []
    facilities: list[str] = []
    genres: list[str] = []
    styles: list[str] = []
    scenes: list[str] = []

    def add_activity(type_id: str, category_name: str, raw_term: str, facility: str = "", genre: str = "", style: str = "", scene: str = "") -> None:
        _append_unique(type_ids, type_id)
        _append_unique(parent_categories, category_name)
        _append_unique(raw_terms, raw_term)
        if facility:
            _append_unique(facilities, facility)
        if genre:
            _append_unique(genres, genre)
        if style:
            _append_unique(styles, style)
        if scene:
            _append_unique(scenes, scene)

    if "游乐园" in text or "儿童乐园" in text or "amusement" in tags:
        add_activity("ACTIVITY_AMUSEMENT", "AMUSEMENT", "游乐园", "游乐园", "亲子游乐", "亲子", "亲子")
    if tags & {"hands_on", "craft"} or _matches(text, HANDS_ON_WORDS):
        add_activity("ACTIVITY_HANDS_ON", "HANDS_ON", "手工", "手工坊", "手作", "低强度", "亲子")
        _append_unique(parent_categories, "FAMILY")
    if "羽毛球" in text or "badminton" in tags:
        add_activity("ACTIVITY_BADMINTON", "SPORTS", "羽毛球", "羽毛球馆", "球类", "运动", "朋友")
    if "网球" in text:
        add_activity("ACTIVITY_TENNIS", "SPORTS", "网球", "网球中心", "球类", "运动", "朋友")
    if "足球" in text:
        add_activity("ACTIVITY_FOOTBALL", "SPORTS", "足球", "足球场", "球类", "对抗运动", "朋友")
    if "篮球" in text:
        add_activity("ACTIVITY_BASKETBALL", "SPORTS", "篮球", "篮球馆", "球类", "对抗运动", "朋友")
    if "乒乓" in text:
        add_activity("ACTIVITY_TABLE_TENNIS", "SPORTS", "乒乓球", "乒乓球馆", "球类", "运动", "朋友")
    if "台球" in text:
        add_activity("ACTIVITY_BILLIARDS", "SPORTS", "台球", "台球厅", "球类", "轻社交", "朋友")
        _append_unique(parent_categories, "SOCIAL_ENTERTAINMENT")
    if "游泳" in text or "swimming" in tags:
        add_activity("ACTIVITY_SWIMMING", "SPORTS", "游泳", "游泳馆", "运动", "运动", "朋友")
    if "健身" in text or "fitness" in tags:
        add_activity("ACTIVITY_FITNESS", "SPORTS", "健身", "健身房", "运动", "运动", "朋友")
    if "瑜伽" in text or "普拉提" in text:
        add_activity("ACTIVITY_YOGA", "SPORTS", "瑜伽", "瑜伽馆", "运动", "舒缓", "放松")
        _append_unique(parent_categories, "QUIET_STAY")
    if "攀岩" in text:
        add_activity("ACTIVITY_CLIMBING", "SPORTS", "攀岩", "攀岩馆", "运动", "挑战", "朋友")
    if "电竞" in text or "网咖" in text or "网吧" in text or "esports" in tags:
        add_activity("ACTIVITY_ESPORTS", "GAME", "电竞", "电竞馆", "电子游戏", "强社交", "朋友")
        _append_unique(parent_categories, "SOCIAL_ENTERTAINMENT")
    if "剧本杀" in text or "推理" in text or "密室" in text or "script_murder" in tags:
        add_activity("ACTIVITY_SCRIPT_MURDER", "GAME", "剧本杀", "剧本杀", "推理", "沉浸", "朋友")
        _append_unique(parent_categories, "SOCIAL_ENTERTAINMENT")
    if "桌游" in text or "狼人杀" in text or "board_game" in tags:
        add_activity("ACTIVITY_BOARD_GAME", "GAME", "桌游", "桌游馆", "桌游", "轻社交", "朋友")
        _append_unique(parent_categories, "SOCIAL_ENTERTAINMENT")
    if "KTV" in text or "唱K" in text or "karaoke" in tags:
        add_activity("ACTIVITY_KARAOKE", "SOCIAL_ENTERTAINMENT", "KTV", "KTV", "唱歌", "强社交", "朋友")
    if "音乐剧" in text or "剧院" in text or "话剧" in text or "theater" in tags:
        add_activity("ACTIVITY_THEATER", "PERFORMANCE", "剧院", "剧院", "演出", "观演", "约会")
    if "影院" in text or "电影" in text or "private_cinema" in tags or "movie" in tags:
        add_activity("ACTIVITY_MOVIE", "MOVIE_THEATER", "电影", "电影院", "电影", "观影", "朋友")
    scenic_name_signal = _matches(text, ("金沙湖", "湖畔", "公园", "景点", "美景", "风景", "观景", "步道")) and not _matches(
        text,
        ("健身", "训练", "格斗", "电竞", "网咖", "KTV", "桌游", "剧本杀", "足球", "篮球", "网球", "台球", "游泳", "运动主题"),
    )
    if category == "walk_spot" or scenic_name_signal:
        add_activity("ACTIVITY_SCENIC", "SCENIC", "景点", "景点", "城市景观", "拍照", "亲友")
        add_activity("ACTIVITY_PARK_WALK", "WALK", "散步", "公园", "散步", "低强度", "散心")
    if "mall" in tags or "商场" in text:
        add_activity("ACTIVITY_MALL_WALK", "SHOPPING", "商场逛逛", "商场", "逛街", "雨天友好", "朋友")
        _append_unique(parent_categories, "WALK")
    if category in {"activity", "walk_spot"} and not type_ids:
        _append_unique(parent_categories, "UNKNOWN_ACTIVITY")

    if tags & {"indoor", "rain_safe", "mall"}:
        _append_unique(styles, "室内")
    if tags & {"child_friendly", "kid_safe", "family_time"}:
        _append_unique(scenes, "亲子")
        _append_unique(parent_categories, "FAMILY")
    if tags & {"quiet", "quiet_stay"}:
        _append_unique(styles, "安静")
        _append_unique(parent_categories, "QUIET_STAY")
    if tags & {"group_ok", "friend_group"}:
        _append_unique(scenes, "朋友")

    intensity = "unknown"
    if any(type_id in type_ids for type_id in ("ACTIVITY_FOOTBALL", "ACTIVITY_BASKETBALL", "ACTIVITY_CLIMBING")):
        intensity = "high"
    elif any(type_id in type_ids for type_id in ("ACTIVITY_BADMINTON", "ACTIVITY_TENNIS", "ACTIVITY_TABLE_TENNIS", "ACTIVITY_SWIMMING", "ACTIVITY_FITNESS")):
        intensity = "medium"
    elif type_ids or parent_categories:
        intensity = "low"
    physical_intensity = {"low": 0.2, "medium": 0.55, "high": 0.9}.get(intensity, 0.5)
    noise_level = _clamp(max(_float(risk.get("strong_social"), 0.35), 0.85 if tags & {"karaoke", "esports", "script_murder"} else 0.35))
    child_score = _clamp(
        (0.8 if tags & {"child_friendly", "kid_safe", "family_time", "amusement", "hands_on", "craft"} else 0.25)
        - (0.55 if tags & {"esports", "alcohol", "karaoke", "script_murder", "strong_social"} else 0.0)
        - (0.2 if intensity == "high" else 0.0)
    )
    elderly_score = _clamp(
        (0.75 if tags & {"lake", "park", "light_walk", "quiet_stay", "theater", "hands_on", "craft"} else 0.35)
        - (0.45 if intensity == "high" else 0.0)
        - (0.35 if tags & {"esports", "karaoke", "script_murder", "strong_social"} else 0.0)
    )
    return {
        "raw_activity_terms": raw_terms,
        "activity_type_ids": type_ids,
        "parent_categories": parent_categories,
        "facility_types": facilities,
        "genres": genres,
        "styles": styles,
        "scenes": scenes,
        "intensity": intensity,
        "physical_intensity": round(physical_intensity, 4),
        "indoor": bool(tags & {"indoor", "rain_safe", "mall"}),
        "booking_required": bool(category == "activity" and (type_ids or tags & {"amusement", "karaoke", "board_game", "sports"})),
        "child_activity_score": round(child_score, 4),
        "elderly_activity_score": round(elderly_score, 4),
        "noise_level": round(noise_level, 4),
        "quiet_score": round(_clamp(max(_float(experience.get("quiet_fit"), 0.45), 0.85 if tags & {"quiet", "quiet_stay", "lake", "park"} else 0.35)), 4),
    }


def _derived_addons(tags: set[str], menu: Dict[str, Any], family: Dict[str, Any], queue: Dict[str, Any]) -> list[str]:
    addons: list[str] = []
    if family.get("has_restroom"):
        _append_unique(addons, "厕所")
    if menu.get("has_child_friendly_food"):
        _append_unique(addons, "儿童可食")
    if menu.get("spicy_level", 0) >= 0.55:
        _append_unique(addons, "解辣饮品")
        _append_unique(addons, "湿巾")
    if queue.get("reservation_supported"):
        _append_unique(addons, "预约")
    if tags & {"photo_spot", "lake"}:
        _append_unique(addons, "拍照点")
    return addons


def _attach_structured_semantic_tags(feature: Dict[str, Any]) -> None:
    tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
    menu = feature.get("menu_features") if isinstance(feature.get("menu_features"), dict) else {}
    activity = feature.get("activity_features") if isinstance(feature.get("activity_features"), dict) else {}
    family = feature.get("family_features") if isinstance(feature.get("family_features"), dict) else {}
    queue = feature.get("queue_features") if isinstance(feature.get("queue_features"), dict) else {}
    child = feature.get("child_features") if isinstance(feature.get("child_features"), dict) else {}
    if menu.get("has_crayfish"):
        tags.update({"crayfish", "proper_dining", "dinner"})
    if menu.get("has_hotpot"):
        tags.update({"hotpot", "proper_dining", "dinner"})
    if menu.get("has_bbq"):
        tags.update({"bbq", "grill", "proper_dining", "dinner"})
    if menu.get("has_local_food"):
        tags.update({"local_food", "showcase_local", "proper_dining"})
    if menu.get("has_non_spicy"):
        tags.add("non_spicy_option")
    if menu.get("has_child_friendly_food"):
        tags.add("child_food")
    if _float(menu.get("healthy_option_score"), 0.0) >= 0.7:
        tags.update({"healthy_light", "light_food", "low_calorie"})
    if _float(family.get("family_friendly_score"), 0.0) >= 0.7 or _float(child.get("child_friendly_score"), 0.0) >= 0.7:
        tags.update({"family_friendly", "child_friendly", "kid_safe"})
    if _float(queue.get("queue_risk"), 0.5) <= 0.35:
        tags.add("low_queue")
    if _float(queue.get("queue_risk"), 0.5) >= 0.7:
        tags.update({"long_queue", "queue_risk"})
    activity_type_tags = {
        "ACTIVITY_AMUSEMENT": {"amusement", "child_friendly", "kid_safe"},
        "ACTIVITY_HANDS_ON": {"hands_on", "craft"},
        "ACTIVITY_BADMINTON": {"sports", "badminton"},
        "ACTIVITY_TENNIS": {"sports"},
        "ACTIVITY_FOOTBALL": {"sports"},
        "ACTIVITY_BASKETBALL": {"sports"},
        "ACTIVITY_TABLE_TENNIS": {"sports"},
        "ACTIVITY_BILLIARDS": {"sports"},
        "ACTIVITY_SWIMMING": {"sports", "swimming"},
        "ACTIVITY_FITNESS": {"sports", "fitness"},
        "ACTIVITY_YOGA": {"sports", "fitness", "quiet"},
        "ACTIVITY_CLIMBING": {"sports", "fitness"},
        "ACTIVITY_ESPORTS": {"esports", "low_fit_activity", "strong_social"},
        "ACTIVITY_SCRIPT_MURDER": {"script_murder", "board_game", "low_fit_activity", "strong_social"},
        "ACTIVITY_BOARD_GAME": {"board_game", "group_ok"},
        "ACTIVITY_KARAOKE": {"karaoke", "group_ok", "strong_social"},
        "ACTIVITY_THEATER": {"theater", "date_friendly"},
        "ACTIVITY_MOVIE": {"theater", "movie", "date_friendly"},
        "ACTIVITY_SCENIC": {"scenic", "photo_spot", "visitor_friendly"},
        "ACTIVITY_PARK_WALK": {"light_walk", "park"},
        "ACTIVITY_MALL_WALK": {"mall_walk", "mall", "rain_safe"},
    }
    for type_id in activity.get("activity_type_ids") or []:
        tags.update(activity_type_tags.get(str(type_id), set()))
    categories = set(str(item) for item in activity.get("parent_categories") or [])
    if "FAMILY" in categories or _float(activity.get("child_activity_score"), 0.0) >= 0.7:
        tags.update({"family_friendly", "child_friendly", "kid_safe"})
    if "QUIET_STAY" in categories or _float(activity.get("quiet_score"), 0.0) >= 0.75:
        tags.update({"quiet", "quiet_stay"})
    if _float(activity.get("noise_level"), 0.0) >= 0.72:
        tags.add("strong_social")
    feature["semantic_tags"] = sorted(tags)


def _haystack(item: Dict[str, Any], enrichment: Dict[str, Any]) -> str:
    values = [
        item.get("name"),
        item.get("sub_category"),
        item.get("address"),
        item.get("area"),
        " ".join(str(tag) for tag in item.get("tags") or []),
        " ".join(str(tag) for tag in item.get("suitable_scenarios") or []),
        enrichment.get("name"),
        enrichment.get("gaode_type"),
        enrichment.get("business_area"),
        enrichment.get("address"),
        enrichment.get("open_time"),
    ]
    values.extend(str(value) for value in (enrichment.get("biz_ext") or {}).values())
    return " ".join(str(value or "") for value in values)


def _matches(haystack: str, words: Iterable[str]) -> bool:
    return any(word and word in haystack for word in words)


def _looks_like_hands_on_experience(item: Dict[str, Any], haystack: str) -> bool:
    name = str(item.get("name") or "")
    category = str(item.get("category") or "")
    if any(word in name for word in HANDMADE_FOOD_FALSE_POSITIVE_WORDS):
        return False
    if category == "restaurant" and "DIY" not in name and "diy" not in name and "烘焙DIY" not in name:
        if any(word in name for word in ("粉", "面", "酸奶", "小吃", "馄饨", "水饺", "包子")):
            return False
    return _matches(haystack, HANDS_ON_WORDS)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
