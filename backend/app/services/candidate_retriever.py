import math
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from app.core.constants import TraceEventType
from app.core.data_paths import (
    GAODE_POI_ENRICHMENT_PATH,
    MOCK_POIS_PATH,
    MOCK_ROUTES_PATH,
    RECOMMENDATION_RANKER_WEIGHTS_PATH,
    RUNTIME_ACTIVITY_POIS_PATH,
)
from app.services.logging_service import LoggingService
from app.rules.recommendation_policy_engine import RecommendationPolicyEngine
from app.rules.poi_feature_store import POIFeatureStore
from app.rules.ranking_weights import default_ranker_weight_document, normalize_ranker_weights
from app.rules.recommendation_taxonomy import get_tag_keywords
from app.schemas.internal_intelligence import MachineIntent
from app.services.mock_api_service import MockAPIService


ALCOHOL_NAME_WORDS = get_tag_keywords("alcohol")
MUSIC_NAME_WORDS = get_tag_keywords("music")
HANDS_ON_NAME_WORDS = ("DIY", "diy", "手作", "手工坊", "陶艺", "拼豆", "油画", "烘焙DIY")
HANDMADE_FOOD_FALSE_POSITIVE_WORDS = ("手工粉", "手工面", "手擀面", "手工水饺", "手工饺", "手工馄饨", "手工米粉", "手作酸奶")
KARAOKE_NAME_WORDS = get_tag_keywords("karaoke")
BUFFET_NAME_WORDS = get_tag_keywords("buffet")
AMUSEMENT_NAME_WORDS = get_tag_keywords("amusement")
FAMILY_ACTIVITY_WORDS = ("亲子", "儿童", "童宇宙", "童", "乐园", "嘉年华", "手作", "手工", "手工坊", "DIY", "diy", "陶艺", "拼豆", "油画", "烘焙")
VISITOR_ACTIVITY_WORDS = ("金沙湖", "湖畔", "公园", "剧院", "影院", "茶空间", "手作", "手工", "陶艺", "艺术")
GENERIC_LOW_FIT_ACTIVITY_WORDS = ("棋牌", "麻将", "自助棋牌", "KTV", "电竞", "网咖", "台球", "健身", "游泳", "乒乓", "电玩", "PS5", "VR", "推理", "剧本杀", "桌游", "棋遇")
CASUAL_CHAIN_WORDS = ("米村", "拌饭", "麦当劳", "肯德基", "德克士", "老乡鸡", "老娘舅", "萨莉亚", "必胜客", "达美乐", "比萨", "披萨", "Pizza", "PIZZA", "新发现", "费大厨", "辣椒炒肉", "火锅", "烧烤", "烤肉", "麻辣", "牛肉", "羊肉炉", "鸡锅", "麻辣烫", "手擀面", "冷面", "砂锅", "瑞幸", "库迪", "蜜雪", "1点点", "CoCo", "霸王茶姬", "奶茶", "小吃", "快餐")
ANNIVERSARY_DINING_WORDS = ("湖畔", "临湖", "西餐", "料理", "日式", "会席", "茶空间", "小馆", "CANTEEN", "Cafe", "Modern", "希尔顿", "皇冠", "酒店", "格里餐厅", "彩丰楼", "四季轩", "御水月", "鮨", "融合料理", "沙滩餐厅")
ANNIVERSARY_ACTIVITY_WORDS = ("影院", "剧院", "湖", "公园", "Lounge", "LOUNGE", "茶空间", "艺术", "音乐", "民谣")
HOTPOT_NAME_WORDS = get_tag_keywords("hotpot")
CRAYFISH_NAME_WORDS = get_tag_keywords("crayfish")
JAPANESE_CUISINE_WORDS = get_tag_keywords("cuisine_japanese")
JAPANESE_QUALITY_WORDS = ("日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风料理", "会席")
JAPANESE_CASUAL_WORDS = ("日式咖喱", "蛋包饭", "回转寿司")
SUSHI_WORDS = get_tag_keywords("sushi")
IZAKAYA_WORDS = get_tag_keywords("izakaya")
BBQ_NAME_WORDS = get_tag_keywords("bbq")
WESTERN_CUISINE_WORDS = get_tag_keywords("western_cuisine")
STEAK_WORDS = get_tag_keywords("steak")
LAMB_NAME_WORDS = get_tag_keywords("lamb")
HEALTHY_LIGHT_WORDS = get_tag_keywords("healthy_light")
LIGHT_MEAL_NAME_WORDS = ("粥", "蒸", "汤", "面馆", "手擀面", "牛肉面", "日式", "料理", "寿司", "鱼", "椰子鸡", "顺德小馆", "小馆", "轻食", "沙拉", "健康", "素", "食堂")
BURGER_FOOD_WORDS = ("汉堡", "中国汉堡", "麦当劳", "肯德基", "德克士", "塔斯汀", "Burger", "BURGER", "burger")
DIETARY_DINING_TERMS = ("清淡", "低负担", "轻食", "低卡", "低脂", "减脂", "健康", "沙拉", "少油", "少辣", "不辣")
HEAVY_SPICY_NAME_WORDS = ("火锅", "毛肚", "麻辣", "烧烤", "烤肉", "干锅", "地锅", "鸡锅", "锅鸡", "美蛙", "酸辣", "酸菜鱼", "重庆", "烙锅", "串串", "烤鱼", "湖南菜")
NON_DINNER_NAME_WORDS = ("手工坊", "DIY", "diy", "烘焙", "蛋糕", "甜品", "咖啡", "茶姬", "奶茶", "酸奶", "面包", "美食街")
QUEUE_LIMITS = {"low": 10, "medium": 20, "high": 35}


class CandidateRetriever:
    def __init__(
        self,
        mock_api_service: MockAPIService,
        logging_service: LoggingService,
        policy_engine: Optional[RecommendationPolicyEngine] = None,
        poi_feature_store: Optional[POIFeatureStore] = None,
        activity_candidate_provider: Optional[Any] = None,
    ) -> None:
        self.mock_api_service = mock_api_service
        self.logging_service = logging_service
        self.policy_engine = policy_engine
        self.poi_feature_store = poi_feature_store
        self.activity_candidate_provider = activity_candidate_provider
        self._enrichment_cache: Optional[Dict[str, Any]] = None
        self._ranker_weights: Optional[Dict[str, float]] = None
        self._weather_score_cache: Dict[tuple[str, str, str, str], Any] = {}
        self._chain_status_cache: Dict[tuple[str, str, int], float] = {}
        self._activity_status_cache: Dict[tuple[str, str, int], bool] = {}

    def retrieve(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
        machine_intent: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self._weather_score_cache = {}
        self._chain_status_cache = {}
        self._activity_status_cache = {}
        machine = self._normalize_machine_intent(machine_intent)
        scenario = user_goal["scenario"]
        search_scenario = None if scenario in {"fallback_unknown", "city_light_explore"} else scenario
        activity_items = self._search(trace_id, search_scenario, "activity", constraints)
        activity_items = self._merge_machine_activity_candidates(trace_id, search_scenario, constraints, activity_items, machine)
        restaurant_items = self._restaurants(trace_id, search_scenario, constraints)
        restaurant_items = self._merge_machine_food_candidates(trace_id, search_scenario, constraints, restaurant_items, machine)
        tail_items = self._tail_items(trace_id, search_scenario, constraints)
        if scenario in {"anniversary_emotion", "city_light_explore"}:
            activity_items = self._merge_unique(
                activity_items,
                self.mock_api_service.search_pois(trace_id, scenario=None, category="activity", limit=200).get("items", []),
            )
            restaurant_items = self._merge_unique(
                restaurant_items,
                self.mock_api_service.search_restaurants(
                    trace_id,
                    scenario=None,
                    budget_max_per_person=constraints.get("budget_max_per_person"),
                    limit=200,
                ).get("items", []),
            )
            service_items = self._search(trace_id, search_scenario, "service", constraints)
            if service_items:
                tail_items = service_items + tail_items

        selected = self._select_chain(activity_items, restaurant_items, tail_items, constraints, user_goal, machine)
        restaurant_first = self._restaurant_first(constraints)
        dinner_last = self._dinner_last(constraints)
        planning_order = "restaurant_first" if restaurant_first else "dinner_last" if dinner_last else "activity_first"
        extra_pois = self._select_extra_pois(activity_items, restaurant_items, tail_items, selected, constraints, user_goal, machine)
        backup_candidates = self._select_backup_candidates(
            trace_id,
            activity_items,
            restaurant_items,
            tail_items,
            selected,
            constraints,
            user_goal,
            machine,
        )
        itinerary_nodes = self._itinerary_nodes(selected, extra_pois, planning_order, constraints, user_goal)
        status_snapshots = self._status_snapshots(trace_id, selected, constraints, time_window)
        routes = self._route_snapshots(trace_id, selected, time_window, planning_order=planning_order, itinerary_nodes=itinerary_nodes)
        weather = self._weather(trace_id, selected, time_window)
        candidate_set = {
            "selected_pois": selected,
            "extra_pois": extra_pois,
            "backup_candidates": backup_candidates,
            "itinerary_nodes": itinerary_nodes,
            "routes": routes,
            "status_snapshots": status_snapshots,
            "weather": weather,
            "candidate_counts": {
                "activity": len(activity_items),
                "restaurant": len(restaurant_items),
                "tail": len(tail_items),
            },
            "planning_order": planning_order,
        }
        self.logging_service.log(
            trace_id,
            TraceEventType.POI_LOG,
            "CandidateRetriever",
            {
                "user_visible_message": "已从Mock数字孪生区域筛选活动、餐厅和收尾节点。",
                "selected_poi_ids": [poi["poi_id"] for poi in selected.values() if poi],
                "route_count": len(routes),
                "candidate_counts": candidate_set["candidate_counts"],
                "itinerary_stop_count": len(itinerary_nodes) if itinerary_nodes else len([poi for poi in selected.values() if poi]),
                "backup_count": len(backup_candidates),
            },
        )
        return candidate_set

    def _all_pois(self) -> list[Dict[str, Any]]:
        pois = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        runtime = self.mock_api_service.store.read(RUNTIME_ACTIVITY_POIS_PATH, {"pois": []}).get("pois", [])
        return self._merge_unique(runtime if isinstance(runtime, list) else [], pois if isinstance(pois, list) else [])

    def _normalize_machine_intent(self, machine_intent: Optional[Any]) -> Optional[Dict[str, Any]]:
        if machine_intent is None:
            return None
        try:
            if isinstance(machine_intent, MachineIntent):
                payload = machine_intent.to_dict()
            elif isinstance(machine_intent, dict):
                payload = MachineIntent.parse_payload(machine_intent, fallback_on_error=True, **machine_intent).to_dict()
            else:
                return None
        except Exception:
            return None
        if not any(payload.get(key) for key in ("soft_preferences", "penalties", "hard_filters", "retrieval_plan", "slot_requirements")):
            return None
        return payload

    def _merge_machine_food_candidates(
        self,
        trace_id: str,
        scenario: Optional[str],
        constraints: Dict[str, Any],
        items: list[Dict[str, Any]],
        machine_intent: Optional[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        if not machine_intent or not (machine_intent.get("retrieval_plan") or {}).get("food_match"):
            return items
        try:
            source_items = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        except Exception:
            return items
        preferred_area = self._preferred_area(constraints)
        budget_pp = constraints.get("budget_max_per_person")
        matches: list[Dict[str, Any]] = []
        for item in source_items:
            if item.get("category") != "restaurant":
                continue
            if scenario and scenario not in item.get("suitable_scenarios", []):
                continue
            if preferred_area and item.get("area") != preferred_area and item.get("location", {}).get("area") != preferred_area:
                continue
            if budget_pp is not None and float(item.get("price_per_person") or 0) > float(budget_pp) + self._budget_slack({"scenario": scenario}):
                continue
            score = self._food_match_score(item, (machine_intent.get("retrieval_plan") or {}).get("food_match") or {})
            if score > 0:
                enriched = dict(item)
                enriched["_machine_food_match_score"] = score
                matches.append(enriched)
        matches = sorted(matches, key=lambda item: -float(item.get("_machine_food_match_score") or 0))[:40]
        return self._merge_unique(matches, items)

    def _merge_machine_activity_candidates(
        self,
        trace_id: str,
        scenario: Optional[str],
        constraints: Dict[str, Any],
        items: list[Dict[str, Any]],
        machine_intent: Optional[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        if not machine_intent:
            return items
        activity_match = ((machine_intent.get("retrieval_plan") or {}).get("activity_match") or {})
        if activity_match:
            try:
                source_items = self._all_pois()
            except Exception:
                return items
            preferred_area = self._preferred_area(constraints)
            preferred_matches: list[Dict[str, Any]] = []
            fallback_matches: list[Dict[str, Any]] = []
            for item in source_items:
                if item.get("category") not in {"activity", "walk_spot"}:
                    continue
                score = self._activity_match_score(item, activity_match)
                if score <= 0.0:
                    continue
                if score < 0.35 and scenario and scenario not in item.get("suitable_scenarios", []):
                    continue
                enriched = dict(item)
                enriched["_machine_activity_match_score"] = score
                if preferred_area and item.get("area") != preferred_area and item.get("location", {}).get("area") != preferred_area:
                    fallback_matches.append(enriched)
                else:
                    preferred_matches.append(enriched)
            matches = preferred_matches or fallback_matches
            activity_categories = set(str(item) for item in activity_match.get("parent_categories") or [])
            min_local_matches = 1 if activity_categories & {"SCENIC", "WALK", "SHOPPING", "QUIET_STAY"} else 3
            if len(matches) < min_local_matches and self.activity_candidate_provider is not None:
                try:
                    supplements = self.activity_candidate_provider.supplement(
                        trace_id=trace_id,
                        activity_match=activity_match,
                        constraints=constraints,
                        scenario=scenario,
                        existing_ids={str(item.get("poi_id")) for item in self._merge_unique(matches, items)},
                        limit=12,
                    )
                except Exception:
                    supplements = []
                for item in supplements or []:
                    score = self._activity_match_score(item, activity_match)
                    if score > 0:
                        enriched = dict(item)
                        enriched["_machine_activity_match_score"] = score
                        matches.append(enriched)
            matches = sorted(matches, key=lambda item: -float(item.get("_machine_activity_match_score") or 0.0))[:40]
            legacy_items = [item for item in items if item.get("category") in {"activity", "walk_spot"}]
            return self._merge_unique(matches, legacy_items)
        slot_requirements = machine_intent.get("slot_requirements") or []
        canonical_tags = set(str(tag) for tag in machine_intent.get("canonical_tags") or [])
        wants_sports = "SPORTS" in canonical_tags or any(
            isinstance(requirement, dict)
            and requirement.get("slot_type") == "activity"
            and requirement.get("activity_category") == "sports"
            for requirement in slot_requirements
        )
        if not wants_sports:
            return items
        activity_terms: list[str] = []
        for requirement in slot_requirements:
            if not isinstance(requirement, dict):
                continue
            if requirement.get("slot_type") == "activity" and requirement.get("activity_category") == "sports":
                activity_terms.extend(str(term) for term in requirement.get("raw_terms") or [] if str(term).strip())
        try:
            source_items = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        except Exception:
            return items
        preferred_area = self._preferred_area(constraints)
        preferred_matches: list[Dict[str, Any]] = []
        fallback_matches: list[Dict[str, Any]] = []
        for item in source_items:
            if item.get("category") != "activity":
                continue
            if scenario and scenario not in item.get("suitable_scenarios", []) and "friend_group" not in item.get("suitable_scenarios", []):
                continue
            tags = self._semantic_tags(item)
            name_text = " ".join(
                str(value)
                for value in (
                    item.get("name"),
                    item.get("sub_category"),
                    " ".join(str(tag) for tag in item.get("tags") or []),
                )
                if value
            )
            if activity_terms:
                matched = any(term in name_text for term in activity_terms)
                if "羽毛球" in activity_terms:
                    matched = matched or "badminton" in tags
            else:
                matched = bool(tags & {"sports", "fitness", "badminton"}) or any(token in name_text for token in ("球馆", "健身", "运动"))
            if matched:
                enriched = dict(item)
                enriched["_machine_activity_match_score"] = 1.0 if any(term in name_text for term in activity_terms) or ("羽毛球" in activity_terms and "badminton" in tags) else 0.75
                if preferred_area and item.get("area") != preferred_area and item.get("location", {}).get("area") != preferred_area:
                    fallback_matches.append(enriched)
                else:
                    preferred_matches.append(enriched)
        matches = preferred_matches or fallback_matches
        matches = sorted(matches, key=lambda item: -float(item.get("_machine_activity_match_score") or 0.0))
        return self._merge_unique(matches[:20], items)

    def _apply_machine_intent_score(
        self,
        item: Optional[Dict[str, Any]],
        role: str,
        base_score: float,
        machine_intent: Optional[Dict[str, Any]],
    ) -> float:
        if not item or not machine_intent or base_score <= -9000:
            return base_score
        score = float(base_score)
        for preference in machine_intent.get("soft_preferences") or []:
            if not self._machine_scope_matches(str(preference.get("scope") or "all"), role):
                continue
            feature = str(preference.get("feature") or "")
            value = self._machine_feature_value(item, feature, role, machine_intent)
            score += value * float(preference.get("weight") or 0.0) * 24.0
        for penalty in machine_intent.get("penalties") or []:
            if not self._machine_scope_matches(str(penalty.get("scope") or "all"), role):
                continue
            feature = str(penalty.get("feature") or "")
            value = self._machine_feature_value(item, feature, role, machine_intent)
            score += value * float(penalty.get("weight") or 0.0) * 24.0
        for hard_filter in machine_intent.get("hard_filters") or []:
            if not hard_filter.get("advisory", True):
                continue
            if not self._machine_scope_matches(str(hard_filter.get("scope") or "all"), role):
                continue
            known, value = self._machine_filter_value(item, str(hard_filter.get("feature") or ""), role, machine_intent)
            if known and not self._passes_machine_filter(value, str(hard_filter.get("operator") or "=="), hard_filter.get("value")):
                alternative = hard_filter.get("alternative") if isinstance(hard_filter.get("alternative"), dict) else None
                alternative_passed = False
                if alternative:
                    alt_known, alt_value = self._machine_filter_value(item, str(alternative.get("feature") or ""), role, machine_intent)
                    alternative_passed = alt_known and self._passes_machine_filter(alt_value, str(alternative.get("operator") or "=="), alternative.get("value"))
                if not alternative_passed:
                    score -= 12.0
        activity_match = ((machine_intent or {}).get("retrieval_plan") or {}).get("activity_match") or {}
        if role == "activity" and activity_match:
            activity_score = self._activity_match_score(item, activity_match)
            child_conflict = bool(activity_match.get("child_suitable_required")) and self._child_incompatible_activity_value(item, activity_match) >= 0.8
            elderly_conflict = bool(activity_match.get("elderly_suitable_required")) and self._elderly_incompatible_activity_value(item, activity_match) >= 0.8
            safety_override = bool(activity_match.get("child_suitable_required") or activity_match.get("elderly_suitable_required"))
            has_primary_match_need = self._activity_match_has_primary_constraints(activity_match)
            if activity_score <= 0 and has_primary_match_need and not safety_override:
                return -9999.0
            elif not child_conflict and not elderly_conflict:
                score += min(activity_score, 6.0) * 90.0
                if "WALK" in set(str(item) for item in activity_match.get("parent_categories") or []) and item.get("category") == "walk_spot":
                    score += 700.0
        return score

    def _machine_scope_matches(self, scope: str, role: str) -> bool:
        if scope in {"", "all", "plan"}:
            return True
        if scope == "meal":
            return role == "restaurant"
        if scope == "activity":
            return role == "activity"
        if scope == "route":
            return role in {"activity", "restaurant", "tail"}
        return scope == role

    def _machine_feature_value(
        self,
        item: Dict[str, Any],
        feature_key: str,
        role: str = "activity",
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> float:
        direct = self._machine_direct_features(item)
        if feature_key in direct:
            return self._clamp01(direct.get(feature_key))
        food_match = ((machine_intent or {}).get("retrieval_plan") or {}).get("food_match") or {}
        if feature_key in {"exact_raw_food_match", "known_dish_match", "attribute_combo_match", "parent_category_match", "scene_match"}:
            return self._food_match_component(item, food_match, feature_key)
        activity_match = ((machine_intent or {}).get("retrieval_plan") or {}).get("activity_match") or {}
        if feature_key in {"exact_raw_activity_match", "known_activity_match", "activity_attribute_match", "parent_activity_category_match", "activity_scene_match"}:
            return self._activity_match_component(item, activity_match, feature_key)
        if feature_key == "companion_activity_fit":
            return self._companion_activity_fit_value(item, activity_match)
        if feature_key == "child_activity_score":
            return max(self._family_fit_value(item), self._tag_presence(item, {"child_friendly", "kid_safe", "family_time", "amusement", "hands_on", "craft"}))
        if feature_key == "child_incompatible_activity":
            return self._child_incompatible_activity_value(item, activity_match)
        if feature_key == "elderly_incompatible_activity":
            return self._elderly_incompatible_activity_value(item, activity_match)
        if feature_key == "low_physical_intensity":
            return self._clamp01(1.0 - self._physical_intensity_value(item))
        if feature_key in {"high_physical_intensity", "high_walking_intensity"}:
            return max(self._physical_intensity_value(item), self._feature_score(item, "risk_scores", "route_fragility", 0.35) if feature_key == "high_walking_intensity" else 0.0)
        if feature_key in {"low_queue_score", "high_queue_risk", "reservation_supported"}:
            queue_risk = self._queue_risk_value(item)
            if feature_key == "low_queue_score":
                return self._clamp01(1.0 - queue_risk)
            if feature_key == "high_queue_risk":
                return self._clamp01(queue_risk)
            return self._reservation_supported_value(item)
        if feature_key in {"nearby_score", "low_transfer_score", "long_transfer"}:
            route_anchor = self._feature_score(item, "scores", "route_anchor", 0.5)
            route_fragility = self._feature_score(item, "risk_scores", "route_fragility", 0.5)
            if feature_key == "nearby_score":
                return self._clamp01(max(route_anchor, 1.0 - route_fragility))
            if feature_key == "low_transfer_score":
                return self._clamp01(1.0 - route_fragility)
            return self._clamp01(route_fragility)
        if feature_key in {"child_friendly_score", "family_friendly_score", "family_dining_score"}:
            return self._family_fit_value(item)
        if feature_key == "child_food_score":
            return self._child_food_value(item)
        if feature_key == "non_spicy_option":
            return 1.0 if "spicy_heavy" not in self._semantic_tags(item) else 0.25
        if feature_key == "restroom_score":
            return self._direct_or_tag_value(item, ("has_restroom",), {"mall", "amusement", "child_friendly", "family_time"}, 0.5)
        if feature_key in {"rest_area_score", "shower_or_rest_area"}:
            return max(self._feature_score(item, "experience_scores", "stay_duration_fit", 0.4), self._direct_or_tag_value(item, ("has_rest_area",), {"mall", "lake", "park", "quiet_stay"}, 0.4))
        if feature_key == "low_walking_intensity":
            return self._clamp01(1.0 - self._feature_score(item, "risk_scores", "route_fragility", 0.35))
        if feature_key == "high_noise_level":
            return self._noise_value(item)
        if feature_key in {"spicy_only_restaurant", "oiliness_level"}:
            return self._heavy_food_value(item)
        if feature_key in {"healthy_option_score", "light_meal_match"}:
            return self._light_meal_value(item)
        if feature_key == "ceremonial_score":
            return max(self._feature_score(item, "experience_scores", "ritual_fit", 0.0), self._tag_presence(item, {"quality_dining", "ambience_dining", "date_friendly"}))
        if feature_key == "romantic_score":
            return max(self._feature_score(item, "scores", "date_fit", 0.0), self._tag_presence(item, {"date_friendly", "romantic", "ambience_dining"}))
        if feature_key == "photo_score":
            return self._tag_presence(item, {"photo_spot", "lake", "showcase_local"})
        if feature_key in {"quiet_score", "relaxation_score"}:
            return max(self._feature_score(item, "experience_scores", "quiet_fit", 0.0), self._tag_presence(item, {"quiet", "quiet_stay", "lake", "park", "light_walk"}))
        if feature_key in {"low_crowd_score", "noisy_place"}:
            if feature_key == "low_crowd_score":
                return self._clamp01(1.0 - max(self._queue_risk_value(item), self._noise_value(item)))
            return self._noise_value(item)
        if feature_key == "compact_pace":
            return self._feature_score(item, "risk_scores", "route_fragility", 0.25)
        if feature_key == "sport_facility_score":
            activity_match = ((machine_intent or {}).get("retrieval_plan") or {}).get("activity_match") or {}
            if activity_match:
                categories = set(str(item) for item in activity_match.get("parent_categories") or [])
                types = set(str(item) for item in activity_match.get("activity_type_ids") or [])
                if "SPORTS" in categories or any(type_id in types for type_id in ("ACTIVITY_BADMINTON", "ACTIVITY_TENNIS", "ACTIVITY_FOOTBALL", "ACTIVITY_BASKETBALL", "ACTIVITY_TABLE_TENNIS", "ACTIVITY_BILLIARDS", "ACTIVITY_SWIMMING", "ACTIVITY_FITNESS", "ACTIVITY_YOGA", "ACTIVITY_CLIMBING")):
                    return max(self._activity_match_score(item, activity_match), self._tag_presence(item, {"sports", "fitness", "badminton"}))
            activity_terms: list[str] = []
            for requirement in ((machine_intent or {}).get("slot_requirements") or []):
                if not isinstance(requirement, dict):
                    continue
                if requirement.get("slot_type") == "activity" and requirement.get("activity_category") == "sports":
                    activity_terms.extend(str(term) for term in requirement.get("raw_terms") or [] if str(term).strip())
            if activity_terms:
                tags = self._semantic_tags(item)
                name_text = " ".join(
                    str(value)
                    for value in (
                        item.get("name"),
                        item.get("sub_category"),
                        " ".join(str(tag) for tag in item.get("tags") or []),
                    )
                    if value
                )
                matched = any(term in name_text for term in activity_terms)
                if "羽毛球" in activity_terms:
                    matched = matched or "badminton" in tags
                return 1.0 if matched else 0.0
            direct_score = item.get("_machine_activity_match_score")
            if direct_score is not None:
                return self._clamp01(direct_score)
            tags = self._semantic_tags(item)
            text = self._poi_text(item)
            if "badminton" in tags or "羽毛球" in text:
                return 1.0
            return self._tag_presence(item, {"sports", "fitness", "badminton"})
        if feature_key == "scenic_score":
            return self._tag_presence(item, {"lake", "park", "showcase_local", "photo_spot", "scenic"})
        return 0.5

    def _machine_filter_value(
        self,
        item: Dict[str, Any],
        feature_key: str,
        role: str,
        machine_intent: Optional[Dict[str, Any]],
    ) -> tuple[bool, Any]:
        direct = self._machine_direct_features(item)
        if feature_key in direct:
            return True, direct.get(feature_key)
        if feature_key == "child_age_compatible":
            tags = self._semantic_tags(item)
            if tags & {"child_friendly", "kid_safe", "family_time", "amusement"}:
                return True, True
            return False, None
        if feature_key in {"has_crayfish", "has_hotpot", "has_bbq", "has_local_food"}:
            return True, self._machine_bool_feature(item, feature_key)
        if feature_key == "queue_risk":
            return True, self._queue_risk_value(item)
        if feature_key == "expected_queue_minutes":
            queue_minutes = self._queue_minutes_value(item)
            return (queue_minutes is not None), queue_minutes
        if feature_key == "max_single_leg_travel_minutes":
            if "max_single_leg_travel_minutes" in direct:
                return True, direct["max_single_leg_travel_minutes"]
            return False, None
        return False, None

    def _passes_machine_filter(self, actual: Any, operator: str, expected: Any) -> bool:
        try:
            if operator == "==":
                return actual == expected
            actual_number = float(actual)
            expected_number = float(expected)
            if operator == "<=":
                return actual_number <= expected_number
            if operator == "<":
                return actual_number < expected_number
            if operator == ">=":
                return actual_number >= expected_number
            if operator == ">":
                return actual_number > expected_number
        except (TypeError, ValueError):
            return True
        return True

    def _food_match_score(self, item: Dict[str, Any], food_match: Dict[str, Any]) -> float:
        if not food_match:
            return 0.0
        return (
            self._food_match_component(item, food_match, "exact_raw_food_match") * 1.5
            + self._food_match_component(item, food_match, "known_dish_match") * 1.3
            + self._food_match_component(item, food_match, "attribute_combo_match") * 1.0
            + self._food_match_component(item, food_match, "parent_category_match") * 0.6
            + self._food_match_component(item, food_match, "scene_match") * 0.4
        )

    def _food_match_component(self, item: Dict[str, Any], food_match: Dict[str, Any], component: str) -> float:
        if not food_match:
            return 0.0
        text = self._machine_food_text(item)
        menu = self._menu_features(item)
        tags = self._semantic_tags(item)
        if component == "exact_raw_food_match":
            raw_terms = [str(term) for term in food_match.get("raw_terms") or [] if str(term).strip()]
            if not raw_terms:
                return 0.0
            return 1.0 if any(term in text for term in raw_terms) else 0.0
        if component == "known_dish_match":
            dish_ids = set(str(item) for item in food_match.get("known_dish_ids") or [])
            if not dish_ids:
                return 0.0
            item_dishes = set(str(item) for item in menu.get("dish_ids") or [])
            if dish_ids & item_dishes:
                return 1.0
            return 1.0 if self._dish_ids_match_tags(dish_ids, tags, item, text) else 0.0
        if component == "parent_category_match":
            categories = set(str(item) for item in food_match.get("parent_categories") or [])
            if not categories:
                return 0.0
            item_categories = set(str(item) for item in menu.get("parent_categories") or [])
            if categories & item_categories:
                return 1.0
            return 1.0 if self._parent_categories_match_tags(categories, tags, item, text) else 0.0
        if component == "attribute_combo_match":
            groups = [
                ("ingredients", menu.get("ingredients") or []),
                ("cooking_methods", menu.get("cooking_methods") or []),
                ("flavors", menu.get("flavors") or []),
                ("forms", menu.get("forms") or []),
            ]
            available = 0
            matched = 0
            for key, item_values in groups:
                desired = [str(value) for value in food_match.get(key) or [] if str(value).strip()]
                if not desired:
                    continue
                available += 1
                item_set = set(str(value) for value in item_values)
                if any(value in item_set or value in text for value in desired):
                    matched += 1
            return 0.0 if available == 0 else matched / available
        if component == "scene_match":
            scenes = [str(scene) for scene in food_match.get("scenes") or [] if str(scene).strip()]
            if not scenes:
                return 0.0
            item_scenes = set(str(scene) for scene in menu.get("scenes") or [])
            return 1.0 if any(scene in item_scenes or scene in text for scene in scenes) else 0.0
        return 0.0

    def _activity_match_score(self, item: Dict[str, Any], activity_match: Dict[str, Any]) -> float:
        if not activity_match:
            return 0.0
        raw_score = self._activity_match_component(item, activity_match, "exact_raw_activity_match")
        known_score = self._activity_match_component(item, activity_match, "known_activity_match")
        attribute_score = self._activity_match_component(item, activity_match, "activity_attribute_match")
        parent_score = self._activity_match_component(item, activity_match, "parent_activity_category_match")
        if activity_match.get("activity_type_ids") and raw_score <= 0 and known_score <= 0:
            return 0.0
        primary_score = raw_score * 2.0 + known_score * 1.6 + attribute_score * 1.0 + parent_score * 0.7
        if primary_score <= 0:
            return 0.0
        return (
            primary_score
            + self._activity_match_component(item, activity_match, "activity_scene_match") * 0.5
        )

    def _activity_match_has_primary_constraints(self, activity_match: Dict[str, Any]) -> bool:
        if any(activity_match.get(key) for key in ("raw_terms", "activity_type_ids", "facility_types", "genres")):
            return True
        parent_categories = {
            str(item)
            for item in activity_match.get("parent_categories") or []
            if str(item) not in {"", "UNKNOWN_ACTIVITY", "UNKNOWN"}
        }
        return bool(parent_categories)

    def _activity_match_component(self, item: Dict[str, Any], activity_match: Dict[str, Any], component: str) -> float:
        if not activity_match:
            return 0.0
        text = self._machine_activity_text(item)
        activity = self._activity_features(item)
        tags = self._semantic_tags(item)
        if component == "exact_raw_activity_match":
            raw_terms = [str(term) for term in activity_match.get("raw_terms") or [] if str(term).strip()]
            if not raw_terms:
                return 0.0
            return 1.0 if any(term in text for term in raw_terms) else 0.0
        if component == "known_activity_match":
            desired = set(str(item) for item in activity_match.get("activity_type_ids") or [])
            if not desired:
                return 0.0
            item_types = set(str(item) for item in activity.get("activity_type_ids") or [])
            if desired & item_types:
                return 1.0
            return 1.0 if self._activity_type_ids_match_tags(desired, tags, text) else 0.0
        if component == "parent_activity_category_match":
            desired = set(str(item) for item in activity_match.get("parent_categories") or [])
            if not desired:
                return 0.0
            item_categories = set(str(item) for item in activity.get("parent_categories") or [])
            if desired & item_categories:
                return 1.0
            return 1.0 if self._activity_parent_categories_match_tags(desired, tags, text) else 0.0
        if component == "activity_attribute_match":
            groups = [
                ("facility_types", activity.get("facility_types") or []),
                ("genres", activity.get("genres") or []),
                ("styles", activity.get("styles") or []),
            ]
            available = 0
            matched = 0
            for key, item_values in groups:
                desired = [str(value) for value in activity_match.get(key) or [] if str(value).strip()]
                if not desired:
                    continue
                available += 1
                item_set = set(str(value) for value in item_values)
                if any(value in item_set or value in text for value in desired):
                    matched += 1
            return 0.0 if available == 0 else matched / available
        if component == "activity_scene_match":
            scenes = [str(scene) for scene in activity_match.get("scenes") or [] if str(scene).strip()]
            if not scenes:
                return 0.0
            item_scenes = set(str(scene) for scene in activity.get("scenes") or [])
            return 1.0 if any(scene in item_scenes or scene in text for scene in scenes) else 0.0
        return 0.0

    def _machine_activity_text(self, item: Dict[str, Any]) -> str:
        activity = self._activity_features(item)
        values = [self._poi_text(item)]
        for key in ("activity_type_ids", "parent_categories", "facility_types", "genres", "styles", "scenes"):
            value = activity.get(key)
            if isinstance(value, list):
                values.append(" ".join(str(item) for item in value))
            elif value:
                values.append(str(value))
        return " ".join(values)

    def _activity_type_ids_match_tags(self, type_ids: set[str], tags: set[str], text: str) -> bool:
        mapping = {
            "ACTIVITY_AMUSEMENT": {"amusement"},
            "ACTIVITY_HANDS_ON": {"hands_on", "craft"},
            "ACTIVITY_BADMINTON": {"badminton"},
            "ACTIVITY_TENNIS": set(),
            "ACTIVITY_FOOTBALL": set(),
            "ACTIVITY_BASKETBALL": set(),
            "ACTIVITY_TABLE_TENNIS": set(),
            "ACTIVITY_BILLIARDS": set(),
            "ACTIVITY_SWIMMING": {"swimming"},
            "ACTIVITY_FITNESS": {"fitness"},
            "ACTIVITY_YOGA": {"fitness", "quiet"},
            "ACTIVITY_CLIMBING": set(),
            "ACTIVITY_ESPORTS": {"esports"},
            "ACTIVITY_SCRIPT_MURDER": {"script_murder", "board_game"},
            "ACTIVITY_BOARD_GAME": {"board_game"},
            "ACTIVITY_KARAOKE": {"karaoke"},
            "ACTIVITY_THEATER": {"theater"},
            "ACTIVITY_MOVIE": {"theater", "private_cinema", "movie"},
            "ACTIVITY_LIVE_MUSIC": {"music", "acoustic_music"},
            "ACTIVITY_SCENIC": {"lake", "park", "showcase_local", "photo_spot", "scenic"},
            "ACTIVITY_PARK_WALK": {"lake", "park", "light_walk"},
            "ACTIVITY_MALL_WALK": {"mall", "mall_walk"},
            "ACTIVITY_BOOKSTORE": {"quiet_stay"},
            "ACTIVITY_EXHIBITION": {"theater", "quiet_stay"},
        }
        text_mapping = {
            "ACTIVITY_BADMINTON": ("羽毛球",),
            "ACTIVITY_TENNIS": ("网球",),
            "ACTIVITY_FOOTBALL": ("足球",),
            "ACTIVITY_BASKETBALL": ("篮球",),
            "ACTIVITY_TABLE_TENNIS": ("乒乓",),
            "ACTIVITY_BILLIARDS": ("台球",),
            "ACTIVITY_ESPORTS": ("电竞", "网咖", "网吧"),
            "ACTIVITY_SCRIPT_MURDER": ("剧本杀", "推理", "密室"),
            "ACTIVITY_KARAOKE": ("KTV", "唱K", "唱歌"),
            "ACTIVITY_MOVIE": ("影院", "电影"),
            "ACTIVITY_THEATER": ("剧院", "音乐剧", "话剧", "演出"),
            "ACTIVITY_HANDS_ON": ("手工", "手作", "DIY", "陶艺"),
            "ACTIVITY_AMUSEMENT": ("游乐园", "儿童乐园", "乐园"),
            "ACTIVITY_SCENIC": ("景点", "美景", "西湖", "金沙湖"),
            "ACTIVITY_PARK_WALK": ("公园", "散步", "逛逛", "湖畔"),
        }
        return any(tags & mapping.get(type_id, set()) or any(word in text for word in text_mapping.get(type_id, ())) for type_id in type_ids)

    def _activity_parent_categories_match_tags(self, categories: set[str], tags: set[str], text: str) -> bool:
        mapping = {
            "SPORTS": {"sports", "fitness", "badminton", "swimming"},
            "GAME": {"esports", "script_murder", "board_game"},
            "PERFORMANCE": {"theater", "music", "acoustic_music"},
            "MOVIE_THEATER": {"theater", "private_cinema", "movie"},
            "SCENIC": {"lake", "park", "showcase_local", "photo_spot", "scenic"},
            "HANDS_ON": {"hands_on", "craft"},
            "AMUSEMENT": {"amusement"},
            "SOCIAL_ENTERTAINMENT": {"karaoke", "board_game", "group_ok", "strong_social"},
            "QUIET_STAY": {"quiet", "quiet_stay", "coffee", "dessert"},
            "WALK": {"lake", "park", "light_walk", "mall_walk"},
            "SHOPPING": {"mall", "shopping"},
            "FAMILY": {"child_friendly", "kid_safe", "family_time"},
        }
        text_mapping = {
            "SPORTS": ("羽毛球", "网球", "足球", "篮球", "乒乓", "台球", "运动", "球馆"),
            "GAME": ("电竞", "网咖", "剧本杀", "密室", "桌游"),
            "PERFORMANCE": ("剧院", "音乐", "演出", "音乐剧", "话剧"),
            "MOVIE_THEATER": ("电影", "影院"),
            "SCENIC": ("景点", "公园", "湖", "西湖", "美景"),
            "HANDS_ON": ("手工", "手作", "DIY", "陶艺"),
            "AMUSEMENT": ("游乐园", "乐园", "游艺"),
            "WALK": ("散步", "逛逛", "公园", "湖畔"),
        }
        return any(tags & mapping.get(category, set()) or any(word in text for word in text_mapping.get(category, ())) for category in categories)

    def _machine_direct_features(self, item: Dict[str, Any]) -> Dict[str, Any]:
        direct: Dict[str, Any] = {}
        payload = self._feature_store_payload(item)
        for key in (
            "child_features",
            "queue_features",
            "physical_features",
            "experience_features",
            "family_features",
            "menu_features",
            "activity_features",
        ):
            value = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(value, dict):
                direct.update(value)
        for key in (
            "_machine_features",
            "machine_features",
            "child_features",
            "queue_features",
            "physical_features",
            "experience_features",
            "family_features",
            "menu_features",
            "activity_features",
        ):
            value = item.get(key)
            if isinstance(value, dict):
                direct.update(value)
        return direct

    def _menu_features(self, item: Dict[str, Any]) -> Dict[str, Any]:
        menu = item.get("menu_features")
        if isinstance(menu, dict):
            return menu
        feature = self.poi_feature_store.for_item(item) if self.poi_feature_store else {}
        menu = feature.get("menu_features") if isinstance(feature, dict) else {}
        return menu if isinstance(menu, dict) else {}

    def _activity_features(self, item: Dict[str, Any]) -> Dict[str, Any]:
        activity = item.get("activity_features")
        if isinstance(activity, dict):
            return activity
        feature = self.poi_feature_store.for_item(item) if self.poi_feature_store else {}
        activity = feature.get("activity_features") if isinstance(feature, dict) else {}
        return activity if isinstance(activity, dict) else {}

    def _feature_store_payload(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if not self.poi_feature_store:
            return {}
        try:
            return self.poi_feature_store.for_item(item) or {}
        except Exception:
            return {}

    def _feature_score(self, item: Dict[str, Any], group: str, key: str, default: float) -> float:
        direct = self._machine_direct_features(item)
        if key in direct:
            return self._clamp01(direct.get(key))
        payload = self._feature_store_payload(item)
        values = payload.get(group) if isinstance(payload, dict) else {}
        if isinstance(values, dict) and key in values:
            return self._clamp01(values.get(key))
        return self._clamp01(default)

    def _queue_risk_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        for key in ("queue_risk", "queue_pressure"):
            if key in direct:
                return self._clamp01(direct.get(key))
        return self._feature_score(item, "risk_scores", "queue_pressure", 0.5)

    def _queue_minutes_value(self, item: Dict[str, Any]) -> Optional[float]:
        direct = self._machine_direct_features(item)
        for key in ("expected_queue_minutes", "avg_wait_minutes_peak", "avg_wait_minutes_offpeak"):
            if key in direct:
                try:
                    return float(direct.get(key))
                except (TypeError, ValueError):
                    return None
        return None

    def _reservation_supported_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        if "reservation_supported" in direct:
            return 1.0 if bool(direct.get("reservation_supported")) else 0.0
        tags = self._semantic_tags(item)
        if "low_queue" in tags:
            return 0.65
        return 0.5

    def _family_fit_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        for key in ("family_friendly_score", "family_fit", "child_friendly_score"):
            if key in direct:
                return self._clamp01(direct.get(key))
        return max(self._feature_score(item, "scores", "family_fit", 0.0), self._tag_presence(item, {"child_friendly", "kid_safe", "family_time", "family_friendly"}))

    def _child_food_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        for key in ("child_food_score", "has_child_friendly_food"):
            if key in direct:
                value = direct.get(key)
                return self._clamp01(value) if isinstance(value, (int, float)) else 1.0 if value else 0.0
        return max(self._feature_score(item, "experience_scores", "kid_safety", 0.0), self._tag_presence(item, {"child_friendly", "light_meal", "light_food", "child_food"}))

    def _noise_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        if "noise_level" in direct:
            return self._clamp01(direct.get("noise_level"))
        return max(self._feature_score(item, "risk_scores", "strong_social", 0.0), self._tag_presence(item, {"karaoke", "board_game", "strong_social", "low_fit_activity"}))

    def _heavy_food_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        for key in ("oiliness_level", "spicy_level"):
            if key in direct:
                return self._clamp01(direct.get(key))
        return max(self._feature_score(item, "risk_scores", "heavy_meal", 0.0), self._tag_presence(item, {"spicy_heavy", "hotpot", "bbq", "grill"}))

    def _light_meal_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        if "healthy_option_score" in direct:
            return self._clamp01(direct.get("healthy_option_score"))
        return max(self._feature_score(item, "scores", "light_meal_fit", 0.0), self._tag_presence(item, {"light_meal", "light_food", "healthy_light", "low_calorie"}))

    def _direct_or_tag_value(self, item: Dict[str, Any], keys: tuple[str, ...], tags: set[str], default: float) -> float:
        direct = self._machine_direct_features(item)
        for key in keys:
            if key in direct:
                value = direct.get(key)
                return self._clamp01(value) if isinstance(value, (int, float)) else 1.0 if value else 0.0
        return max(default, self._tag_presence(item, tags))

    def _companion_activity_fit_value(self, item: Dict[str, Any], activity_match: Dict[str, Any]) -> float:
        mode = str((activity_match or {}).get("social_mode") or "unknown")
        tags = self._semantic_tags(item)
        if mode == "family":
            return self._tag_presence(item, {"child_friendly", "kid_safe", "family_time", "amusement", "hands_on", "craft", "park", "lake"})
        if mode == "elderly":
            return self._clamp01(1.0 - self._elderly_incompatible_activity_value(item, activity_match))
        if mode in {"friends", "sibling"}:
            return self._tag_presence(item, {"group_ok", "friend_group", "sports", "board_game", "karaoke", "esports", "theater", "lake", "park", "hands_on", "craft"})
        if mode == "couple":
            return self._tag_presence(item, {"date_friendly", "quiet_stay", "theater", "hands_on", "craft", "lake", "photo_spot"})
        return 0.5

    def _child_incompatible_activity_value(self, item: Dict[str, Any], activity_match: Dict[str, Any]) -> float:
        tags = self._semantic_tags(item)
        text = self._machine_activity_text(item)
        if tags & {"child_friendly", "kid_safe", "family_time", "amusement", "hands_on", "craft"}:
            return 0.0
        if any(word in text for word in ("电竞", "网咖", "网吧", "酒吧", "KTV", "剧本杀", "密室")):
            return 2.4
        if tags & {"esports", "alcohol", "light_drink", "karaoke", "script_murder", "strong_social", "low_fit_activity"}:
            return 1.8
        if self._physical_intensity_value(item) >= 0.78:
            return 1.2
        return 0.2

    def _elderly_incompatible_activity_value(self, item: Dict[str, Any], activity_match: Dict[str, Any]) -> float:
        tags = self._semantic_tags(item)
        text = self._machine_activity_text(item)
        if any(word in text for word in ("足球", "篮球", "攀岩", "健身", "电竞", "网咖", "KTV", "剧本杀", "密室")):
            return 2.4
        if tags & {"fitness", "sports", "strong_social", "low_fit_activity"}:
            return 1.6
        if tags & {"lake", "park", "light_walk", "quiet_stay", "theater", "hands_on", "craft"}:
            return 0.0
        return self._physical_intensity_value(item) * 0.8

    def _physical_intensity_value(self, item: Dict[str, Any]) -> float:
        direct = self._machine_direct_features(item)
        value = direct.get("physical_intensity") or direct.get("activity_intensity")
        if isinstance(value, (int, float)):
            return self._clamp01(value)
        if isinstance(value, str):
            return {"low": 0.2, "medium": 0.55, "high": 0.9}.get(value, 0.5)
        tags = self._semantic_tags(item)
        text = self._machine_activity_text(item)
        if any(word in text for word in ("足球", "篮球", "攀岩")):
            return 0.9
        if any(word in text for word in ("羽毛球", "网球", "乒乓球", "游泳", "健身")) or tags & {"sports", "fitness", "swimming"}:
            return 0.65
        if tags & {"lake", "park", "light_walk", "quiet_stay", "theater", "hands_on", "craft", "board_game", "karaoke", "esports"}:
            return 0.25
        return 0.5

    def _tag_presence(self, item: Dict[str, Any], tags: set[str]) -> float:
        return 1.0 if self._semantic_tags(item) & tags else 0.0

    def _machine_bool_feature(self, item: Dict[str, Any], feature_key: str) -> bool:
        direct = self._machine_direct_features(item)
        if feature_key in direct:
            return bool(direct.get(feature_key))
        text = self._machine_food_text(item)
        tags = self._semantic_tags(item)
        if feature_key == "has_crayfish":
            return "小龙虾" in text or "crayfish" in tags
        if feature_key == "has_hotpot":
            return "hotpot" in tags or "火锅" in text
        if feature_key == "has_bbq":
            return bool(tags & {"bbq", "grill"} or any(word in text for word in BBQ_NAME_WORDS))
        if feature_key == "has_local_food":
            return bool(tags & {"showcase_local", "local_food"} or any(word in text for word in ("杭帮菜", "本地菜", "特色菜")))
        return False

    def _machine_food_text(self, item: Dict[str, Any]) -> str:
        menu = self._menu_features(item)
        values = [self._poi_text(item)]
        for key in ("signature_dishes", "raw_food_terms", "ingredients", "cooking_methods", "flavors", "forms", "scenes", "dish_ids", "parent_categories"):
            value = menu.get(key)
            if isinstance(value, list):
                values.append(" ".join(str(item) for item in value))
            elif value:
                values.append(str(value))
        return " ".join(values)

    def _dish_ids_match_tags(self, dish_ids: set[str], tags: set[str], item: Dict[str, Any], text: str) -> bool:
        mapping = {
            "DISH_CRAYFISH": {"crayfish"},
            "DISH_HOTPOT": {"hotpot"},
            "DISH_BBQ": {"bbq", "grill"},
            "DISH_LIGHT_MEAL": {"light_meal", "light_food", "healthy_light", "low_calorie"},
            "DISH_COFFEE": {"coffee"},
            "DISH_MILK_TEA": {"milk_tea"},
            "DISH_DESSERT": {"dessert"},
            "DISH_SNACK": {"snack_meal", "dessert"},
            "DISH_HANGZHOU_LOCAL": {"showcase_local", "local_food"},
            "DISH_JAPANESE": {"cuisine_japanese", "sushi", "izakaya"},
            "DISH_STEAK": {"western_cuisine", "steak"},
            "DISH_LAMB": {"lamb"},
            "DISH_NOODLES": {"snack_meal"},
            "DISH_SEAFOOD": {"seafood"},
            "DISH_CHILD_FRIENDLY_FOOD": {"child_food", "family_friendly"},
        }
        text_mapping = {
            "DISH_CRAYFISH": ("小龙虾", "龙虾", "虾尾"),
            "DISH_HOTPOT": HOTPOT_NAME_WORDS,
            "DISH_BBQ": BBQ_NAME_WORDS,
            "DISH_LIGHT_MEAL": HEALTHY_LIGHT_WORDS + LIGHT_MEAL_NAME_WORDS,
            "DISH_COFFEE": ("咖啡",),
            "DISH_MILK_TEA": ("奶茶", "茶姬"),
            "DISH_DESSERT": ("甜品", "蛋糕", "巴斯克", "糖葫芦"),
            "DISH_SNACK": ("小吃", "糖葫芦", "面馆", "拌面"),
            "DISH_HANGZHOU_LOCAL": ("杭帮菜", "本地菜", "特色菜"),
            "DISH_NOODLES": ("面", "拌面", "汤面", "拉面"),
            "DISH_SEAFOOD": ("海鲜", "鱼", "虾", "蟹"),
            "DISH_CHILD_FRIENDLY_FOOD": BURGER_FOOD_WORDS,
        }
        return any(tags & mapping.get(dish_id, set()) or any(word in text for word in text_mapping.get(dish_id, ())) for dish_id in dish_ids)

    def _parent_categories_match_tags(self, categories: set[str], tags: set[str], item: Dict[str, Any], text: str) -> bool:
        category_to_dish = {
            "CRAYFISH": {"DISH_CRAYFISH"},
            "HOTPOT": {"DISH_HOTPOT"},
            "BBQ": {"DISH_BBQ"},
            "LIGHT_MEAL": {"DISH_LIGHT_MEAL"},
            "DRINK": {"DISH_COFFEE", "DISH_MILK_TEA"},
            "DESSERT": {"DISH_DESSERT"},
            "SNACK": {"DISH_SNACK"},
            "LOCAL_FOOD": {"DISH_HANGZHOU_LOCAL"},
            "JAPANESE": {"DISH_JAPANESE"},
            "NOODLES": {"DISH_NOODLES"},
            "SEAFOOD": {"DISH_SEAFOOD"},
            "LAMB": {"DISH_LAMB"},
            "CHILD_FRIENDLY": {"DISH_CHILD_FRIENDLY_FOOD"},
        }
        return any(self._dish_ids_match_tags(category_to_dish.get(category, set()), tags, item, text) for category in categories)

    def _clamp01(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    def _merge_machine_retrieval_terms(self, machine_intent: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not machine_intent:
            return {}
        return ((machine_intent.get("retrieval_plan") or {}).get("food_match") or {}).copy()

    def _machine_has_food_need(self, machine_intent: Optional[Dict[str, Any]]) -> bool:
        food_match = self._merge_machine_retrieval_terms(machine_intent)
        return any(
            food_match.get(key)
            for key in (
                "raw_terms",
                "known_dish_ids",
                "parent_categories",
                "ingredients",
                "cooking_methods",
                "flavors",
                "forms",
            )
        )

    def _machine_activity_match(self, machine_intent: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not machine_intent:
            return {}
        return ((machine_intent.get("retrieval_plan") or {}).get("activity_match") or {}).copy()

    def _machine_has_activity_need(self, machine_intent: Optional[Dict[str, Any]]) -> bool:
        activity_match = self._machine_activity_match(machine_intent)
        return any(
            activity_match.get(key)
            for key in (
                "raw_terms",
                "activity_type_ids",
                "parent_categories",
                "facility_types",
                "genres",
                "styles",
                "scenes",
            )
        )

    def _machine_activity_match_score(self, item: Dict[str, Any], machine_intent: Optional[Dict[str, Any]]) -> float:
        return self._activity_match_score(item, self._machine_activity_match(machine_intent))

    def apply_critic_reports(self, candidate_set: Dict[str, Any], critic_reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        reports: Dict[str, Dict[str, Any]] = {}
        for report in critic_reports or []:
            if hasattr(report, "to_dict"):
                payload = report.to_dict()
            elif isinstance(report, dict):
                payload = report
            else:
                continue
            poi_id = str(payload.get("poi_id") or "")
            if not poi_id:
                continue
            if payload.get("decision") == "reject":
                payload = dict(payload)
                payload["decision"] = "backup_only"
                payload["score_delta"] = min(float(payload.get("score_delta") or 0.0), -35.0)
            reports[poi_id] = payload
        if not reports:
            return candidate_set
        candidate_set.setdefault("_internal_intelligence", {})["candidate_critic_reports"] = list(reports.values())
        for poi in (candidate_set.get("selected_pois") or {}).values():
            if isinstance(poi, dict) and str(poi.get("poi_id")) in reports:
                report = reports[str(poi.get("poi_id"))]
                poi["_critic_score_delta"] = float(report.get("score_delta") or 0.0)
                poi["_critic_decision"] = str(report.get("decision") or "")
        for poi in candidate_set.get("extra_pois") or []:
            if isinstance(poi, dict) and str(poi.get("poi_id")) in reports:
                report = reports[str(poi.get("poi_id"))]
                poi["_critic_score_delta"] = float(report.get("score_delta") or 0.0)
                poi["_critic_decision"] = str(report.get("decision") or "")
        for backup in candidate_set.get("backup_candidates") or []:
            poi = backup.get("poi") if isinstance(backup, dict) else None
            if isinstance(poi, dict) and str(poi.get("poi_id")) in reports:
                report = reports[str(poi.get("poi_id"))]
                delta = float(report.get("score_delta") or 0.0)
                backup["score"] = round(float(backup.get("score") or 0.0) + delta, 2)
                backup["_critic_score_delta"] = delta
                backup["_critic_decision"] = str(report.get("decision") or "")
        candidate_set["backup_candidates"] = sorted(
            candidate_set.get("backup_candidates") or [],
            key=lambda item: -float(item.get("score") or 0.0) if isinstance(item, dict) else 0.0,
        )
        return candidate_set

    def _search(self, trace_id: str, scenario: str, category: str, constraints: Dict[str, Any]) -> list[Dict[str, Any]]:
        tags = None
        if category == "activity" and constraints.get("child_friendly_required"):
            tags = "family_parent_child"
        area = self._preferred_area(constraints)
        data = self.mock_api_service.search_pois(trace_id, scenario=scenario, area=area, category=category, tags=tags, limit=100)
        items = data.get("items", [])
        if not items and tags:
            items = self.mock_api_service.search_pois(trace_id, scenario=scenario, area=area, category=category, limit=100).get("items", [])
        if not items and area:
            items = self.mock_api_service.search_pois(trace_id, scenario=scenario, category=category, tags=tags, limit=100).get("items", [])
        markers = set(str(item) for item in constraints.get("must_have") or [])
        intent_markers = markers | set(self._profile_tags(constraints))
        if category == "activity" and intent_markers & {"alcohol", "music", "acoustic_music", "hands_on", "craft", "coffee", "conversation", "mall_walk", "board_game", "karaoke", "esports", "light_walk", "nearby", "quiet"}:
            source_items = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
            preferred_area = self._preferred_area(constraints)
            semantic_categories = {"activity", "restaurant"}
            if intent_markers & {"light_walk", "nearby"}:
                semantic_categories.add("walk_spot")
            all_items = [
                item
                for item in source_items
                if item.get("category") in semantic_categories
                and (not scenario or scenario in item.get("suitable_scenarios", []))
                and (not preferred_area or item.get("area") == preferred_area or item.get("location", {}).get("area") == preferred_area)
            ]
            if "karaoke" in intent_markers:
                wanted = {"karaoke"}
            elif "esports" in intent_markers:
                wanted = {"esports"}
            elif intent_markers & {"hands_on", "craft"}:
                wanted = {"hands_on", "craft"}
            elif "board_game" in intent_markers:
                wanted = {"board_game"}
            elif intent_markers & {"music", "acoustic_music"}:
                wanted = {"music", "acoustic_music"}
            elif "alcohol" in intent_markers:
                wanted = {"alcohol", "light_drink", "quiet_stay", "lake", "park"}
            elif "mall_walk" in intent_markers:
                wanted = {"mall", "mall_walk", "rain_safe"}
            elif intent_markers & {"light_walk", "nearby"}:
                if "light_walk" in intent_markers and not intent_markers & {"coffee", "conversation"}:
                    wanted = {"lake", "park", "light_walk", "quiet"}
                else:
                    wanted = {"lake", "park", "light_walk", "quiet_stay", "coffee"}
            else:
                wanted = {"coffee", "conversation", "quiet_stay"}
            semantic_matches = [item for item in all_items if self._semantic_tags(item) & wanted]
            items = self._merge_unique(semantic_matches, items)
        return items

    def _restaurants(self, trace_id: str, scenario: str, constraints: Dict[str, Any]) -> list[Dict[str, Any]]:
        dietary = ",".join(constraints.get("dietary_preference") or [])
        area = self._preferred_area(constraints)
        required_tags = self._required_restaurant_tags(constraints)
        items = self.mock_api_service.search_restaurants(
            trace_id,
            scenario=scenario,
            area=area,
            dietary_preference=dietary or None,
            budget_max_per_person=constraints.get("budget_max_per_person"),
            tags=required_tags,
            limit=100,
        ).get("items", [])
        if not items:
            items = self.mock_api_service.search_restaurants(
                trace_id,
                scenario=scenario,
                area=area,
                budget_max_per_person=constraints.get("budget_max_per_person"),
                limit=100,
            ).get("items", [])
        if not items and area:
            items = self.mock_api_service.search_restaurants(
                trace_id,
                scenario=scenario,
                dietary_preference=dietary or None,
                budget_max_per_person=constraints.get("budget_max_per_person"),
                limit=100,
            ).get("items", [])
        if required_tags:
            source_items = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
            preferred_area = self._preferred_area(constraints)
            budget_pp = constraints.get("budget_max_per_person")
            alcohol_activity_items = [
                item
                for item in source_items
                if item.get("category") == "activity"
                and (not scenario or scenario in item.get("suitable_scenarios", []))
                and (not preferred_area or item.get("area") == preferred_area or item.get("location", {}).get("area") == preferred_area)
            ]
            semantic_activity_matches = [
                item
                for item in alcohol_activity_items
                if required_tags in self._semantic_tags(item)
                and (
                    budget_pp is None
                    or float(item.get("price_per_person") or 0) <= float(budget_pp or 0) + 20
                )
            ]
            all_items = [
                item
                for item in source_items
                if item.get("category") == "restaurant"
                and (not scenario or scenario in item.get("suitable_scenarios", []))
                and (not preferred_area or item.get("area") == preferred_area or item.get("location", {}).get("area") == preferred_area)
                and (budget_pp is None or float(item.get("price_per_person") or 0) <= float(budget_pp or 0) + 20)
            ]
            semantic_matches = [item for item in all_items if required_tags in self._semantic_tags(item)]
            if not semantic_matches and preferred_area:
                all_area_items = [
                    item
                    for item in source_items
                    if item.get("category") == "restaurant"
                    and (not scenario or scenario in item.get("suitable_scenarios", []))
                    and (budget_pp is None or float(item.get("price_per_person") or 0) <= float(budget_pp or 0) + 20)
                ]
                semantic_matches = [item for item in all_area_items if required_tags in self._semantic_tags(item)]
            items = self._merge_unique([*semantic_matches, *semantic_activity_matches], items)
        open_matches = self._open_dining_restaurant_candidates(scenario, constraints)
        dining_preference = self._dining_preference(constraints)
        if dining_preference.get("explicit"):
            dining_preference["match_available"] = bool(open_matches)
            dining_preference["raw_match_available"] = any(
                self._matches_explicit_dining_raw_term(item, constraints) for item in open_matches
            )
            constraints["dining_preference"] = dining_preference
        if open_matches:
            items = self._merge_unique(open_matches, items)
        return items

    def _tail_items(self, trace_id: str, scenario: str, constraints: Dict[str, Any]) -> list[Dict[str, Any]]:
        if self._friend_activity_without_meal({"scenario": scenario}, constraints, None) and int(constraints.get("target_stop_count") or 0) <= 1:
            return []
        if self._friend_activity_without_meal({"scenario": scenario}, constraints, None):
            markers = set(str(item) for item in constraints.get("must_have") or [])
            items = self._search(trace_id, scenario, "activity", constraints)
            if "esports" in markers:
                items = [item for item in items if "esports" in self._semantic_tags(item)]
            elif "karaoke" in markers:
                items = [item for item in items if "karaoke" in self._semantic_tags(item)]
            elif "board_game" in markers:
                items = [item for item in items if "board_game" in self._semantic_tags(item)]
            return items[:30]
        items = self._search(trace_id, scenario, "walk_spot", constraints)
        if items:
            return items
        area = self._preferred_area(constraints)
        profile_tags = set(self._profile_tags(constraints))
        fallback_tags = {"coffee", "dessert", "quiet_stay", "lake", "park", "mall", "rain_safe", "photo_spot", "date_friendly"}
        alcohol_tail = bool(profile_tags & {"alcohol", "light_drink"})
        family_tail = constraints.get("child_friendly_required") is True
        if alcohol_tail:
            fallback_tags = {"alcohol", "light_drink", "music", "acoustic_music", "lake", "park", "theater", "quiet_stay"}
        elif family_tail:
            fallback_tags = {"child_friendly", "kid_safe", "family_time", "not_tiring", "lake", "park", "quiet_stay", "dessert", "coffee"}
        elif profile_tags & {"music", "acoustic_music"}:
            fallback_tags.update({"music", "acoustic_music", "date_friendly", "lake"})
        pois = self.mock_api_service.search_pois(trace_id, scenario=scenario, area=area, limit=100).get("items", [])
        if not pois and area:
            pois = self.mock_api_service.search_pois(trace_id, scenario=scenario, limit=100).get("items", [])
        result = []
        for poi in pois:
            semantic_tags = self._semantic_tags(poi)
            if poi.get("category") not in {"restaurant", "activity"}:
                continue
            if family_tail and self._is_family_unsafe_activity(poi, semantic_tags):
                continue
            if (
                family_tail
                and poi.get("category") == "restaurant"
                and semantic_tags & {"food", "restaurant", "proper_dining", "slow_dining"}
                and not semantic_tags & {"coffee", "dessert", "quiet_stay"}
            ):
                continue
            if family_tail and poi.get("category") == "activity" and not semantic_tags & {"child_friendly", "kid_safe", "family_time", "hands_on", "craft", "amusement", "lake", "park"}:
                continue
            if not (semantic_tags & fallback_tags or (not alcohol_tail and self._name_matches_tail(poi))):
                continue
            if (
                scenario in {"anniversary_emotion", "city_light_explore"}
                and poi.get("category") == "restaurant"
                and semantic_tags & {"food", "restaurant", "proper_dining", "slow_dining"}
                and not semantic_tags & {"coffee", "dessert", "quiet_stay"}
            ):
                continue
            result.append(poi)
        return result[:30]

    def _select_chain(
        self,
        activity_items: list[Dict[str, Any]],
        restaurant_items: list[Dict[str, Any]],
        tail_items: list[Dict[str, Any]],
        constraints: Dict[str, Any],
        user_goal: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        budget_pp = constraints.get("budget_max_per_person")
        desired_tags = self._desired_tags(user_goal, constraints)
        avoid_tags = self._avoid_tags(user_goal, constraints)
        preferred_area = self._preferred_area(constraints)
        score_cache: Dict[tuple[str, str], float] = {}
        optional_restaurant = self._optional_restaurant_allowed(user_goal, constraints, machine_intent)

        def score_item(item: Optional[Dict[str, Any]], role: str) -> float:
            if not item:
                return -9999
            key = (str(item.get("poi_id")), role)
            if key not in score_cache:
                base_score = self._item_score(item, role, user_goal, constraints, desired_tags, avoid_tags, preferred_area, machine_intent)
                score_cache[key] = self._apply_machine_intent_score(item, role, base_score, machine_intent)
            return score_cache[key]

        activity_ranked = [
            item
            for item in sorted(activity_items, key=lambda item: -score_item(item, "activity"))
            if score_item(item, "activity") > -9000
        ][:35]
        restaurant_ranked = [
            item
            for item in sorted(restaurant_items, key=lambda item: -score_item(item, "restaurant"))
            if score_item(item, "restaurant") > -9000
        ][:45]
        if "alcohol" not in set(str(item) for item in constraints.get("must_have") or []):
            non_alcohol = [item for item in restaurant_ranked if "alcohol" not in self._semantic_tags(item)]
            if non_alcohol:
                restaurant_ranked = non_alcohol
        tail_ranked = [
            item
            for item in sorted(tail_items, key=lambda item: -score_item(item, "tail"))
            if score_item(item, "tail") > -9000
        ][:35]
        if self._meal_only_plan(user_goal, constraints, machine_intent) and restaurant_ranked:
            return self._decorate_selected(
                {
                    "activity": None,
                    "restaurant": restaurant_ranked[0],
                    "tail": None,
                },
                user_goal.get("scenario"),
            )
        best: Optional[tuple[float, Dict[str, Optional[Dict[str, Any]]]]] = None
        solo_optional_restaurant = self._solo_optional_restaurant(user_goal, constraints)
        activity_without_meal = self._friend_activity_without_meal(user_goal, constraints, machine_intent)

        def consider(activity: Optional[Dict[str, Any]], restaurant: Optional[Dict[str, Any]], tail: Optional[Dict[str, Any]], order: str) -> None:
            nonlocal best
            if not activity or (not restaurant and not optional_restaurant):
                return
            if restaurant and str(activity.get("poi_id")) == str(restaurant.get("poi_id")):
                return
            chain_price = self._chain_price(activity, restaurant, tail)
            if budget_pp is not None and chain_price > float(budget_pp) + self._budget_slack(user_goal, constraints):
                return
            if order == "restaurant_first":
                route_pois = (restaurant, activity, tail)
            elif order == "dinner_last":
                route_pois = (activity, tail, restaurant)
            else:
                route_pois = (activity, restaurant, tail)
            route_score = self._chain_route_score(route_pois)
            policy_chain_score = self._policy_chain_score(activity, restaurant, tail, user_goal, constraints, order)
            status_adjustment = 0.0
            if self._is_service_poi(tail) or user_goal.get("scenario") in {"anniversary_emotion", "city_light_explore"}:
                status_adjustment = self._chain_restaurant_status_adjustment(activity, restaurant, tail, order, constraints)
                if status_adjustment <= -9000:
                    return
            if tail and tail.get("category") == "activity":
                tail_arrival = self._chain_tail_arrival_time(activity, restaurant, tail, order, constraints)
                if not self._activity_available_at(tail, tail_arrival, constraints):
                    return
            item_score = (
                score_item(activity, "activity")
                + (score_item(restaurant, "restaurant") if restaurant else 0)
                + (score_item(tail, "tail") if tail else 0)
            )
            budget_penalty = self._budget_penalty(chain_price, budget_pp, user_goal, constraints)
            route_penalty = self._chain_route_penalty(route_pois, user_goal, constraints)
            tail_penalty = self._tail_inclusion_penalty(activity, restaurant, tail, route_pois, user_goal, constraints, score_item(tail, "tail") if tail else 0.0)
            solo_adjustment = self._solo_optional_restaurant_adjustment(activity, restaurant, tail, user_goal, constraints)
            total = item_score + route_score + policy_chain_score + status_adjustment + solo_adjustment - budget_penalty - route_penalty - tail_penalty
            if best is None or total > best[0]:
                best = (total, {"activity": activity, "restaurant": restaurant, "tail": tail})

        if self._restaurant_first(constraints):
            for restaurant in restaurant_ranked:
                for activity in activity_ranked:
                    excluded = {str(activity.get("poi_id")), str(restaurant.get("poi_id"))}
                    consider(activity, restaurant, self._best_tail(activity, tail_ranked, excluded, score_item=score_item), "restaurant_first")
                    consider(activity, restaurant, None, "restaurant_first")
        elif self._dinner_last(constraints):
            for activity in activity_ranked:
                for restaurant in restaurant_ranked:
                    excluded = {str(activity.get("poi_id")), str(restaurant.get("poi_id"))}
                    consider(activity, restaurant, self._best_tail(activity, tail_ranked, excluded, destination=restaurant, score_item=score_item), "dinner_last")
                    consider(activity, restaurant, None, "dinner_last")
        else:
            for activity in activity_ranked:
                if not activity_without_meal:
                    for restaurant in restaurant_ranked:
                        excluded = {str(activity.get("poi_id")), str(restaurant.get("poi_id"))}
                        consider(activity, restaurant, self._best_tail(restaurant, tail_ranked, excluded, score_item=score_item), "activity_first")
                        consider(activity, restaurant, None, "activity_first")
                if solo_optional_restaurant:
                    excluded = {str(activity.get("poi_id"))}
                    consider(activity, None, self._best_tail(activity, tail_ranked, excluded, score_item=score_item), "activity_first")
                    consider(activity, None, None, "activity_first")
                elif optional_restaurant:
                    excluded = {str(activity.get("poi_id"))}
                    if int(constraints.get("target_stop_count") or 0) > 1:
                        consider(activity, None, self._best_tail(activity, tail_ranked, excluded, score_item=score_item), "activity_first")
                        if tail_ranked:
                            continue
                    consider(activity, None, None, "activity_first")
        if best:
            return self._decorate_selected(best[1], user_goal.get("scenario"))
        fallback_tail = tail_ranked[0] if tail_ranked and (not optional_restaurant or int(constraints.get("target_stop_count") or 0) > 1) else None
        return self._decorate_selected({
            "activity": activity_ranked[0] if activity_ranked else None,
            "restaurant": None if optional_restaurant else restaurant_ranked[0] if restaurant_ranked else None,
            "tail": fallback_tail,
        }, user_goal.get("scenario"))

    def _select_extra_pois(
        self,
        activity_items: list[Dict[str, Any]],
        restaurant_items: list[Dict[str, Any]],
        tail_items: list[Dict[str, Any]],
        selected: Dict[str, Optional[Dict[str, Any]]],
        constraints: Dict[str, Any],
        user_goal: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> list[Dict[str, Any]]:
        target = int(constraints.get("target_stop_count") or 0)
        target_source = str(constraints.get("target_stop_count_source") or "")
        if target < 2 or (target < 4 and target_source != "explicit"):
            return []
        selected_ids = {str(poi.get("poi_id")) for poi in selected.values() if poi}
        base_count = len(selected_ids)
        needed = max(0, target - base_count)
        if needed <= 0:
            return []
        desired_tags = self._desired_tags(user_goal, constraints)
        avoid_tags = self._avoid_tags(user_goal, constraints)
        preferred_area = self._preferred_area(constraints)
        current_area = str(constraints.get("current_area") or "")
        party_size = max(1, int(constraints.get("party_size") or 1))
        budget_total = self._budget_total_limit(constraints, party_size)
        spent_total = self._selected_budget_amount(selected, party_size)
        markers = set(str(item) for item in constraints.get("must_have") or [])
        cap_hands_on_extras = user_goal.get("scenario") in {"anniversary_emotion", "city_light_explore"} and not markers & {"hands_on", "craft"}
        skip_service_extras = user_goal.get("scenario") in {"anniversary_emotion", "city_light_explore"} and target >= 4
        diversify_solo_mood = user_goal.get("scenario") == "fallback_unknown" and party_size == 1 and target >= 3
        pool: list[tuple[float, str, Dict[str, Any]]] = []

        def solo_mood_group(item: Optional[Dict[str, Any]]) -> str:
            if not item:
                return ""
            semantic = self._semantic_tags(item)
            name = str(item.get("name") or "")
            if semantic & {"private_cinema", "theater", "movie"} or "影院" in name:
                return "cinema"
            if semantic & {"hands_on", "craft"} or any(token in name for token in ("手作", "手工", "香薰", "陶艺")):
                return "craft"
            if any(token in name for token in ("茶咖", "咖啡", "茶空间")) or semantic & {"coffee", "quiet_stay"}:
                return "quiet_cafe"
            if semantic & {"lake", "park", "light_walk"} or any(token in name for token in ("步道", "公园", "湖畔", "慢行")):
                return "walk"
            return ""

        def add_pool(items: list[Dict[str, Any]], role: str) -> None:
            for item in items:
                poi_id = str(item.get("poi_id"))
                if poi_id in selected_ids:
                    continue
                if skip_service_extras and self._is_service_poi(item):
                    continue
                base_score = self._item_score(item, role, user_goal, constraints, desired_tags, avoid_tags, preferred_area, machine_intent)
                score = self._apply_machine_intent_score(item, role, base_score, machine_intent)
                if score <= -9000:
                    continue
                semantic = self._semantic_tags(item)
                if role != "restaurant" and semantic & {"spicy_heavy", "low_end_chain", "casual_chain"}:
                    score -= 80
                cost = self._candidate_budget_amount(item, role, party_size)
                if budget_total is not None:
                    score -= max(0.0, cost - max(0.0, budget_total - spent_total) / max(1, needed)) * 0.45
                if diversify_solo_mood:
                    item_area = str(item.get("area") or item.get("location", {}).get("area") or "")
                    if current_area and item_area == current_area:
                        score += 180
                    elif current_area:
                        score -= 80
                    anchors = [poi for poi in selected.values() if poi and not self._is_service_poi(poi)]
                    if anchors:
                        score += max(self._route_affinity(anchor, item) for anchor in anchors) * 4.0
                    if role == "tail" and semantic & {"lake", "park", "light_walk"}:
                        score += 180
                pool.append((score, role, item))

        add_pool(activity_items, "activity")
        add_pool(tail_items, "tail")
        if needed > 2:
            # Coffee/dessert restaurants can be a gentle final stop, but avoid adding a second proper dinner.
            for item in restaurant_items:
                semantic = self._semantic_tags(item)
                if semantic & {"coffee", "dessert", "quiet_stay"} and not semantic & {"proper_dining", "slow_dining"}:
                    add_pool([item], "tail")

        extras: list[Dict[str, Any]] = []
        used = set(selected_ids)
        used_solo_mood_groups = {
            solo_mood_group(poi)
            for poi in selected.values()
            if poi
        }
        used_solo_mood_groups.discard("")
        extra_spend = 0.0
        hands_on_extra_count = 0
        soft_tail_extra_count = 0
        for _, role, item in sorted(pool, key=lambda value: -value[0]):
            poi_id = str(item.get("poi_id"))
            if poi_id in used:
                continue
            semantic = self._semantic_tags(item)
            solo_group = solo_mood_group(item)
            if diversify_solo_mood and solo_group and solo_group in used_solo_mood_groups:
                continue
            if skip_service_extras and role == "tail" and semantic & {"coffee", "dessert", "quiet_stay"} and soft_tail_extra_count >= 1:
                continue
            if cap_hands_on_extras and semantic & {"hands_on", "craft"} and hands_on_extra_count >= 1:
                continue
            item_cost = self._candidate_budget_amount(item, role, party_size)
            if budget_total is not None and spent_total + extra_spend + item_cost > budget_total:
                continue
            decorated = self._decorate_selected({role: item}, user_goal.get("scenario")).get(role)
            if decorated:
                enriched = dict(decorated)
                enriched["_itinerary_role"] = role
                extras.append(enriched)
                used.add(poi_id)
                extra_spend += item_cost
                if semantic & {"hands_on", "craft"}:
                    hands_on_extra_count += 1
                if role == "tail" and semantic & {"coffee", "dessert", "quiet_stay"}:
                    soft_tail_extra_count += 1
                if solo_group:
                    used_solo_mood_groups.add(solo_group)
            if len(extras) >= needed:
                break
        return extras

    def _budget_total_limit(self, constraints: Dict[str, Any], party_size: int) -> Optional[float]:
        if constraints.get("budget_max") is not None:
            return float(constraints["budget_max"])
        if constraints.get("budget_max_per_person") is not None:
            return float(constraints["budget_max_per_person"]) * party_size
        return None

    def _selected_budget_amount(self, selected: Dict[str, Optional[Dict[str, Any]]], party_size: int) -> float:
        total = 0.0
        for role, item in selected.items():
            if item:
                total += self._candidate_budget_amount(item, role, party_size)
        return total

    def _candidate_budget_amount(self, item: Dict[str, Any], role: str, party_size: int) -> float:
        price = float(item.get("price_per_person") or 0)
        category = str(item.get("category") or "")
        if role in {"activity", "restaurant"} or category == "activity":
            return price * party_size
        if category == "restaurant":
            return price if role == "tail" else price * party_size
        if category == "service":
            return price
        return 0.0

    def _select_backup_candidates(
        self,
        trace_id: str,
        activity_items: list[Dict[str, Any]],
        restaurant_items: list[Dict[str, Any]],
        tail_items: list[Dict[str, Any]],
        selected: Dict[str, Optional[Dict[str, Any]]],
        constraints: Dict[str, Any],
        user_goal: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> list[Dict[str, Any]]:
        desired_tags = self._desired_tags(user_goal, constraints)
        avoid_tags = self._avoid_tags(user_goal, constraints)
        preferred_area = self._preferred_area(constraints)
        selected_ids = {str(poi.get("poi_id")) for poi in selected.values() if poi}
        specs = [
            ("restaurant", restaurant_items, "restaurant_capacity"),
            ("activity", activity_items, "activity_ticket"),
        ]
        if selected.get("tail"):
            tail_trigger = "service_order" if self._is_service_poi(selected.get("tail")) else "route_delay"
            specs.append(("tail", tail_items, tail_trigger))
        backups: list[Dict[str, Any]] = []
        budget_pp = constraints.get("budget_max_per_person")
        current_chain_price = self._chain_price(selected.get("activity"), selected.get("restaurant"), selected.get("tail"))
        budget_limit = None if budget_pp is None else float(budget_pp) + self._budget_slack(user_goal, constraints)
        for role, items, trigger in specs:
            source = selected.get(role)
            if not source:
                continue
            ranked: list[tuple[float, Dict[str, Any]]] = []
            for item in items:
                poi_id = str(item.get("poi_id"))
                if not poi_id or poi_id in selected_ids:
                    continue
                if role == "restaurant" and item.get("category") != "restaurant":
                    continue
                if role == "activity" and item.get("category") != "activity":
                    continue
                if role == "tail" and self._is_service_poi(source) != self._is_service_poi(item):
                    continue
                base_score = self._item_score(item, role, user_goal, constraints, desired_tags, avoid_tags, preferred_area, machine_intent)
                score = self._apply_machine_intent_score(item, role, base_score, machine_intent)
                if score <= -9000:
                    continue
                candidate_chain_price = current_chain_price - float(source.get("price_per_person") or 0) + float(item.get("price_per_person") or 0)
                if budget_limit is not None and candidate_chain_price > budget_limit:
                    continue
                ranked.append((score, item))
            for score, candidate in sorted(ranked, key=lambda value: -value[0])[:12]:
                status = self._backup_status(trace_id, role, candidate, constraints)
                if not status.get("backup_available"):
                    continue
                if role == "restaurant" and str(constraints.get("queue_tolerance") or "") == "low" and not status.get("backup_matches_queue_preference", True):
                    continue
                backups.append(
                    {
                        "role": role,
                        "trigger": trigger,
                        "original_poi_id": source["poi_id"],
                        "poi": self._decorate_selected({role: candidate}, user_goal.get("scenario")).get(role) or candidate,
                        "status": status,
                        "score": round(score, 2),
                        "price_delta": round(float(candidate.get("price_per_person") or 0) - float(source.get("price_per_person") or 0), 2),
                        "route_extra_minutes": self._approx_route_extra_minutes(source, candidate),
                    }
                )
                break
        return backups

    def _backup_status(self, trace_id: str, role: str, item: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
        party_size = int(constraints.get("party_size") or 1)
        if role == "restaurant":
            when = self._planning_arrival_time_for_role("restaurant", constraints)
            status = self.mock_api_service.restaurant_status(trace_id, item["poi_id"], arrival_time=when, party_size=party_size)
            queue_limit = QUEUE_LIMITS.get(str(constraints.get("queue_tolerance") or "medium"), QUEUE_LIMITS["medium"])
            fallback_limit = max(queue_limit, QUEUE_LIMITS["high"])
            queue_minutes = int(status.get("queue_minutes") or 0)
            status["backup_matches_queue_preference"] = queue_minutes <= queue_limit
            status["backup_available"] = bool(
                int(status.get("available_tables") or 0) > 0
                and status.get("reservation_available")
                and queue_minutes <= fallback_limit
            )
            return status
        when = self._planning_arrival_time_for_role(role, constraints)
        status = self.mock_api_service.poi_status(trace_id, item["poi_id"], party_size=party_size, when=when)
        if item.get("category") == "activity":
            status["backup_available"] = bool(status.get("booking_available", True) and status.get("ticket_available", True))
        else:
            status["backup_available"] = bool(status.get("available", True))
        return status

    def _approx_route_extra_minutes(self, source: Dict[str, Any], candidate: Dict[str, Any]) -> int:
        distance = self._distance_km(source, candidate)
        if distance is None:
            return 0
        return max(0, int(round(distance * 8)) - 4)

    def _chain_restaurant_status_adjustment(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Optional[Dict[str, Any]],
        tail: Optional[Dict[str, Any]],
        order: str,
        constraints: Dict[str, Any],
    ) -> float:
        if not restaurant:
            return 0.0
        arrival_time = self._chain_restaurant_arrival_time(activity, restaurant, tail, order, constraints)
        party_size = int(constraints.get("party_size") or 1)
        status_time = self._bucket_time(arrival_time)
        cache_key = (str(restaurant.get("poi_id") or ""), status_time or "", party_size)
        if cache_key in self._chain_status_cache:
            return self._chain_status_cache[cache_key]
        logger = self.mock_api_service.logger
        try:
            self.mock_api_service.logger = None
            status = self.mock_api_service.restaurant_status(
                "trace_internal_chain_status",
                restaurant["poi_id"],
                arrival_time=status_time,
                party_size=party_size,
            )
        except Exception:
            return -9000.0
        finally:
            self.mock_api_service.logger = logger
        if not status.get("available") or not status.get("reservation_available") or int(status.get("available_tables") or 0) <= 0:
            self._chain_status_cache[cache_key] = -9000.0
            return -9000.0
        queue_minutes = int(status.get("queue_minutes") or 0)
        queue_limit = QUEUE_LIMITS.get(str(constraints.get("queue_tolerance") or "medium"), QUEUE_LIMITS["medium"])
        if queue_minutes <= queue_limit:
            self._chain_status_cache[cache_key] = 0.0
            return 0.0
        adjustment = -min(260.0, float(queue_minutes - queue_limit) * 8.0)
        self._chain_status_cache[cache_key] = adjustment
        return adjustment

    def _chain_restaurant_arrival_time(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Dict[str, Any],
        tail: Optional[Dict[str, Any]],
        order: str,
        constraints: Dict[str, Any],
    ) -> Optional[str]:
        start_value = constraints.get("planning_start_time")
        try:
            current = datetime.fromisoformat(str(start_value)) if start_value else None
        except (TypeError, ValueError):
            return self._planning_arrival_time_for_role("restaurant", constraints)
        if current is None:
            return self._planning_arrival_time_for_role("restaurant", constraints)
        if order == "restaurant_first":
            sequence = [("restaurant", restaurant)]
        elif order == "dinner_last":
            sequence = [("activity", activity), ("tail", tail), ("restaurant", restaurant)]
        else:
            sequence = [("activity", activity), ("restaurant", restaurant)]
        previous_physical: Optional[Dict[str, Any]] = None
        for role, poi in sequence:
            if not poi:
                continue
            if role == "restaurant":
                if previous_physical:
                    current += timedelta(minutes=self._route_minutes_between(previous_physical, poi))
                return current.replace(microsecond=0).isoformat()
            is_service = self._is_service_poi(poi)
            if previous_physical and not is_service:
                current += timedelta(minutes=self._route_minutes_between(previous_physical, poi))
            current += timedelta(minutes=self._candidate_stop_duration(role, poi))
            if not is_service:
                previous_physical = poi
        return self._planning_arrival_time_for_role("restaurant", constraints)

    def _chain_tail_arrival_time(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Optional[Dict[str, Any]],
        tail: Dict[str, Any],
        order: str,
        constraints: Dict[str, Any],
    ) -> Optional[str]:
        start_value = constraints.get("planning_start_time")
        try:
            current = datetime.fromisoformat(str(start_value)) if start_value else None
        except (TypeError, ValueError):
            return self._planning_arrival_time_for_role("tail", constraints)
        if current is None:
            return self._planning_arrival_time_for_role("tail", constraints)
        if order == "restaurant_first":
            sequence = [("restaurant", restaurant), ("activity", activity), ("tail", tail)]
        elif order == "dinner_last":
            sequence = [("activity", activity), ("tail", tail), ("restaurant", restaurant)]
        else:
            sequence = [("activity", activity), ("restaurant", restaurant), ("tail", tail)]
        previous_physical: Optional[Dict[str, Any]] = None
        for role, poi in sequence:
            if not poi:
                continue
            is_service = self._is_service_poi(poi)
            if previous_physical and not is_service:
                current += timedelta(minutes=self._route_minutes_between(previous_physical, poi))
            if role == "tail":
                return current.replace(microsecond=0).isoformat()
            current += timedelta(minutes=self._candidate_stop_duration(role, poi))
            if not is_service:
                previous_physical = poi
        return self._planning_arrival_time_for_role("tail", constraints)

    def _activity_available_at(self, item: Dict[str, Any], when: Optional[str], constraints: Dict[str, Any]) -> bool:
        status_time = self._bucket_time(when) or ""
        party_size = int(constraints.get("party_size") or 1)
        cache_key = (str(item.get("poi_id") or ""), status_time, party_size)
        if cache_key in self._activity_status_cache:
            return self._activity_status_cache[cache_key]
        logger = self.mock_api_service.logger
        try:
            self.mock_api_service.logger = None
            status = self.mock_api_service.poi_status(
                "trace_internal_chain_status",
                item["poi_id"],
                party_size=party_size,
                when=status_time,
            )
        except Exception:
            self._activity_status_cache[cache_key] = False
            return False
        finally:
            self.mock_api_service.logger = logger
        remaining_tickets = status.get("remaining_tickets")
        enough_tickets = remaining_tickets is None or int(remaining_tickets) >= party_size
        available = bool(status.get("available")) and status.get("ticket_available") is not False and status.get("booking_available") is not False and enough_tickets
        self._activity_status_cache[cache_key] = available
        return available

    def _route_minutes_between(self, origin: Dict[str, Any], destination: Dict[str, Any]) -> int:
        distance = self._distance_km(origin, destination)
        if distance is None:
            return 12
        return max(2, int(round(distance * 14)))

    def _candidate_stop_duration(self, role: str, poi: Dict[str, Any]) -> int:
        if self._is_service_poi(poi):
            return 20
        if role == "tail":
            return 45
        return 70

    def _bucket_time(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return value
        minute = (parsed.minute // 15) * 15
        return parsed.replace(minute=minute, second=0, microsecond=0).isoformat()

    def _itinerary_nodes(
        self,
        selected: Dict[str, Optional[Dict[str, Any]]],
        extra_pois: list[Dict[str, Any]],
        planning_order: str,
        constraints: Dict[str, Any],
        user_goal: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        target = int(constraints.get("target_stop_count") or 0)
        target_source = str(constraints.get("target_stop_count_source") or "")
        if target < 2 or (target < 4 and target_source != "explicit"):
            return []
        activity = selected.get("activity")
        restaurant = selected.get("restaurant")
        tail = selected.get("tail")
        extras = [poi for poi in extra_pois if poi]
        nodes: list[Dict[str, Any]] = []

        def node(role: str, poi: Optional[Dict[str, Any]]) -> None:
            if poi:
                nodes.append({"role": role, "poi": poi})

        service_tail = self._is_service_poi(tail)
        if planning_order == "restaurant_first":
            if service_tail and restaurant:
                node("tail", tail)
            node("restaurant", restaurant)
            node("activity", activity)
            for extra in extras:
                node(str(extra.get("_itinerary_role") or "activity"), extra)
            if not service_tail:
                node("tail", tail)
        elif planning_order == "dinner_last":
            node("activity", activity)
            for extra in extras:
                node(str(extra.get("_itinerary_role") or "activity"), extra)
            node("tail", tail)
            node("restaurant", restaurant)
        elif user_goal.get("scenario") == "anniversary_emotion" and restaurant:
            node("activity", activity)
            pre_dinner_extra_count = max(0, target - 3)
            for extra in extras[:pre_dinner_extra_count]:
                node(str(extra.get("_itinerary_role") or "activity"), extra)
            if service_tail:
                node("tail", tail)
            node("restaurant", restaurant)
            if not service_tail:
                node("tail", tail)
            for extra in extras[pre_dinner_extra_count:]:
                node(str(extra.get("_itinerary_role") or "tail"), extra)
        else:
            node("activity", activity)
            for extra in extras[:1]:
                node(str(extra.get("_itinerary_role") or "activity"), extra)
            if service_tail and restaurant:
                node("tail", tail)
            node("restaurant", restaurant)
            for extra in extras[1:]:
                node(str(extra.get("_itinerary_role") or "tail"), extra)
            if not service_tail:
                node("tail", tail)

        seen: set[str] = set()
        deduped = []
        for item in nodes:
            poi_id = str((item.get("poi") or {}).get("poi_id") or "")
            if not poi_id or poi_id in seen:
                continue
            seen.add(poi_id)
            deduped.append(item)
        return deduped[: max(target, 0)]

    def _desired_tags(self, user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> set[str]:
        tags = set(user_goal.get("intent_tags") or [])
        tags.update(self._profile_tags(constraints))
        tags.update(constraints.get("activity_preference") or [])
        scenario = user_goal.get("scenario")
        if scenario == "family_parent_child":
            tags.update({"family_parent_child", "child_friendly", "kid_safe", "family_time", "pet_friendly", "rain_safe", "low_queue"})
        elif scenario == "friend_group":
            tags.update({"friend_group", "budget_sensitive", "mood_relief", "rain_safe"})
        elif scenario == "anniversary_emotion":
            tags.update({"date_friendly", "quiet", "quiet_dining", "low_key", "thoughtful", "rain_safe", "visitor_friendly", "route_simple", "quality_dining", "ambience_dining"})
        elif scenario == "city_light_explore":
            tags.update({"visitor_friendly", "host_guest", "showcase_local", "conversation", "relaxed", "route_simple", "quality_dining", "photo_spot", "lake"})
        elif (
            scenario == "fallback_unknown"
            and int(constraints.get("party_size") or 1) == 1
            and not self._meal_only_plan(user_goal, constraints)
        ):
            tags.update({"quiet_alone", "mood_relief", "quiet", "alone", "light_walk", "nearby", "low_pressure", "rain_safe", "low_queue"})
            if "alcohol" in constraints.get("must_have", []):
                tags.update({"alcohol", "light_drink"})
            if "music" in constraints.get("must_have", []) or "acoustic_music" in constraints.get("must_have", []):
                tags.update({"music", "acoustic_music"})
        return {str(tag) for tag in tags}

    def _avoid_tags(self, user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> set[str]:
        tags = set(str(tag) for tag in constraints.get("must_not_have") or [])
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if "alcohol" not in markers:
            tags.update({"alcohol", "light_drink"})
        if "hotpot" not in markers and markers & {"light_meal", "light_food"}:
            tags.update({"hotpot", "spicy_heavy"})
        if user_goal.get("scenario") == "family_parent_child":
            tags.update({"low_fit_activity", "strong_social", "long_queue", "spicy_heavy"})
        if user_goal.get("scenario") == "fallback_unknown" and int(constraints.get("party_size") or 1) == 1:
            tags.update({"family_parent_child", "friend_group", "interactive", "high_budget", "party", "strong_social"})
        if user_goal.get("scenario") in {"anniversary_emotion", "city_light_explore"}:
            tags.update({"fast_food", "low_end_chain", "canteen_style"})
        if user_goal.get("scenario") == "city_light_explore" and "alcohol" not in markers:
            tags.update({"alcohol", "light_drink"})
        if markers & {"bbq", "grill"}:
            tags.discard("low_end_chain")
        if markers & {"cuisine_japanese", "sushi", "izakaya"}:
            tags.discard("low_end_chain")
        return tags

    def _profile_tags(self, constraints: Dict[str, Any]) -> list[str]:
        profile = constraints.get("recommendation_profile") or {}
        if not isinstance(profile, dict):
            return []
        return [str(tag) for tag in profile.get("normalized_tags") or []]

    def _dining_preference(self, constraints: Dict[str, Any]) -> Dict[str, Any]:
        value = constraints.get("dining_preference") or {}
        return value if isinstance(value, dict) else {}

    def _explicit_dining_raw_terms(self, constraints: Dict[str, Any]) -> list[str]:
        dining_preference = self._dining_preference(constraints)
        terms: list[str] = []
        for term in dining_preference.get("raw_terms") or []:
            text = str(term or "").strip()
            if len(text) < 2 or text in DIETARY_DINING_TERMS:
                continue
            if text not in terms:
                terms.append(text)
        return terms

    def _matches_explicit_dining_raw_term(self, item: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
        terms = self._explicit_dining_raw_terms(constraints)
        if not terms:
            return False
        haystack = self._machine_food_text(item)
        return any(term in haystack for term in terms)

    def _open_dining_restaurant_candidates(self, scenario: Optional[str], constraints: Dict[str, Any]) -> list[Dict[str, Any]]:
        dining_preference = self._dining_preference(constraints)
        if not dining_preference.get("explicit"):
            return []
        source_items = self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        preferred_area = self._preferred_area(constraints)
        budget_pp = constraints.get("budget_max_per_person")
        candidates = []
        for item in source_items:
            if item.get("category") != "restaurant":
                continue
            if scenario and scenario not in item.get("suitable_scenarios", []):
                continue
            if preferred_area and item.get("area") != preferred_area and item.get("location", {}).get("area") != preferred_area:
                continue
            if budget_pp is not None and float(item.get("price_per_person") or 0) > float(budget_pp) + self._budget_slack({"scenario": scenario}):
                continue
            match_score = self._open_dining_match_score(item, constraints)
            if match_score > 0:
                enriched = dict(item)
                enriched["_open_dining_match_score"] = match_score
                candidates.append(enriched)
        return sorted(candidates, key=lambda item: -float(item.get("_open_dining_match_score") or 0))[:40]

    def _open_dining_match_score(self, item: Dict[str, Any], constraints: Dict[str, Any]) -> float:
        dining_preference = self._dining_preference(constraints)
        if not dining_preference.get("explicit"):
            return 0.0
        haystack = self._poi_text(item)
        semantic_tags = self._semantic_tags(item)
        target_tags = set(str(tag) for tag in dining_preference.get("specific_tags") or [])
        target_tags -= {"dinner", "explicit_dining", "proper_dining", "quality_dining", "ambience_dining", "beautiful_dining"}
        score = 0.0
        for term in dining_preference.get("positive_terms") or []:
            term = str(term).strip()
            if len(term) >= 2 and term in haystack:
                score += min(36.0, 8.0 + len(term) * 3.0)
        tag_hits = semantic_tags & target_tags
        score += float(len(tag_hits) * 28)
        if {"lamb", "bbq"} <= target_tags or {"lamb", "grill"} <= target_tags:
            if "lamb" in semantic_tags and semantic_tags & {"bbq", "grill"}:
                score += 70
            elif "lamb" in semantic_tags or semantic_tags & {"bbq", "grill"}:
                score += 24
        if target_tags & {"light_meal", "light_food", "healthy_light"} and semantic_tags & {"light_meal", "light_food", "healthy_light", "low_calorie"}:
            score += 60
        if target_tags & {"western_cuisine", "steak"} and semantic_tags & {"western_cuisine", "steak"}:
            score += 65
        for raw_term in dining_preference.get("raw_terms") or []:
            raw_term = str(raw_term).strip()
            if len(raw_term) >= 2 and raw_term in haystack:
                score += 150 if raw_term not in DIETARY_DINING_TERMS else 80
        return score

    def _matches_open_dining(self, item: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
        return self._open_dining_match_score(item, constraints) > 0

    def _rank_items(
        self,
        items: list[Dict[str, Any]],
        role: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        desired_tags: set[str],
        avoid_tags: set[str],
        preferred_area: Optional[str],
    ) -> list[Dict[str, Any]]:
        return sorted(
            items,
            key=lambda item: -self._item_score(item, role, user_goal, constraints, desired_tags, avoid_tags, preferred_area),
        )

    def _item_score(
        self,
        item: Optional[Dict[str, Any]],
        role: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        desired_tags: set[str],
        avoid_tags: set[str],
        preferred_area: Optional[str],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> float:
        if not item:
            return -9999
        scenario = user_goal.get("scenario")
        profile = constraints.get("recommendation_profile") or {}
        weights = profile.get("weights") if isinstance(profile, dict) else {}
        if not isinstance(weights, dict):
            weights = {}
        semantic_tags = self._semantic_tags(item)
        name = str(item.get("name") or "")
        raw_tags = set(str(tag) for tag in item.get("tags") or [])
        markers = set(str(item) for item in constraints.get("must_have") or [])
        hard_avoid_tags = set(str(item) for item in constraints.get("must_not_have") or [])
        explicit_activity_fit = role in {"activity", "tail"} and self._machine_activity_match_score(item, machine_intent) >= 0.55
        policy_score = self._policy_item_score(item, role, user_goal, constraints)
        if policy_score.get("veto"):
            return -9999
        if scenario == "family_parent_child" and role == "activity" and item.get("category") != "activity":
            return -9999
        if "coffee" in hard_avoid_tags and "coffee" in semantic_tags:
            return -9999
        if hard_avoid_tags & {"alcohol", "light_drink"} and semantic_tags & {"alcohol", "light_drink"}:
            return -9999
        explicit_dining_tags = self._explicit_dining_required_tags(constraints)
        dining_preference = self._dining_preference(constraints)
        if (
            role == "restaurant"
            and dining_preference.get("explicit")
            and dining_preference.get("match_available")
            and not self._matches_open_dining(item, constraints)
        ):
            return -9999
        explicit_raw_match = self._matches_explicit_dining_raw_term(item, constraints)
        if (
            role == "restaurant"
            and dining_preference.get("explicit")
            and dining_preference.get("raw_match_available")
            and not explicit_raw_match
        ):
            return -9999
        if role == "restaurant" and explicit_dining_tags and not semantic_tags & explicit_dining_tags:
            return -9999
        if role == "restaurant" and "alcohol" in markers and "alcohol" not in semantic_tags:
            return -9999
        if role == "restaurant" and "buffet" in markers and "buffet" not in semantic_tags:
            return -9999
        if role == "restaurant" and "hotpot" in markers and "hotpot" not in semantic_tags:
            return -9999
        if role == "restaurant" and markers & {"bbq", "grill"} and not semantic_tags & {"bbq", "grill"}:
            return -9999
        if role == "restaurant" and markers & {"light_meal", "light_food"} and "hotpot" not in markers:
            if semantic_tags & {"spicy_heavy", "hotpot"}:
                return -9999
            if self._is_non_dinner_place(item):
                return -9999
            if dining_preference.get("match_available") and not semantic_tags & {"light_meal", "light_food", "healthy_light", "low_calorie"} and not explicit_raw_match:
                return -9999
        if role == "tail" and self._is_redundant_meal_tail(item, user_goal, constraints):
            return -9999
        if role == "restaurant" and item.get("category") != "restaurant":
            if not (scenario == "fallback_unknown" and "alcohol" in markers and semantic_tags & {"alcohol", "light_drink"}):
                return -9999
        if role == "restaurant" and scenario in {"anniversary_emotion", "city_light_explore"}:
            non_meal_tags = {"coffee", "dessert", "quiet_stay"}
            proper_meal_tags = {
                "proper_dining",
                "slow_dining",
                "light_meal",
                "light_food",
                "cuisine_japanese",
                "western_cuisine",
                "bbq",
                "grill",
                "hotpot",
                "buffet",
                "lamb",
                "steak",
            }
            if semantic_tags & non_meal_tags and not semantic_tags & proper_meal_tags:
                return -9999
            if self._is_non_dinner_place(item) and not markers & {"coffee", "dessert"}:
                return -9999
        if (
            self._solo_optional_restaurant(user_goal, constraints)
            and not self._machine_has_food_need(machine_intent)
            and not self._machine_has_activity_need(machine_intent)
        ):
            if role == "restaurant":
                return -9999
            if role == "activity":
                if semantic_tags & {"low_fit_activity", "script_murder", "board_game", "sports", "fitness"}:
                    return -9999
                if semantic_tags & {"food", "restaurant", "proper_dining", "casual_chain", "snack_meal", "spicy_heavy", "hotpot", "bbq", "grill"} and not semantic_tags & {"coffee", "dessert", "quiet_stay"}:
                    return -9999
                if item.get("category") == "restaurant" and semantic_tags & {"food", "restaurant", "proper_dining", "casual_chain", "snack_meal"} and not semantic_tags & {"coffee", "dessert", "quiet_stay", "lake", "park"}:
                    return -9999
                if not semantic_tags & {"lake", "park", "light_walk", "quiet_stay", "coffee", "music", "acoustic_music", "theater", "private_cinema"}:
                    return -9999
            if role == "restaurant":
                if semantic_tags & {"proper_dining", "casual_chain", "low_end_chain", "snack_meal", "spicy_heavy", "hotpot", "bbq", "grill"} and not semantic_tags & {"coffee", "dessert", "quiet_stay", "alcohol", "light_drink", "lake", "park"}:
                    return -9999
        if self._solo_optional_restaurant(user_goal, constraints) and role == "activity" and "coffee" not in markers:
            snack_shop_words = ("奶吧", "奶茶", "甜品", "蛋糕", "蜜雪", "茶姬", "瑞幸", "库迪")
            if any(word in name for word in snack_shop_words):
                return -9999
        if self._solo_optional_restaurant(user_goal, constraints) and role == "activity":
            raw_text = str(user_goal.get("raw_text") or "")
            solo_quiet_request = any(token in raw_text for token in ("散心", "安静", "放松", "低压力", "走走", "逛逛"))
            if solo_quiet_request:
                calm_tags = {"lake", "park", "light_walk", "quiet", "quiet_stay", "coffee", "theater", "private_cinema", "hands_on", "craft"}
                calm_words = ("茶咖", "咖啡", "茶空间", "步道", "公园", "湖畔", "慢行", "影院", "手作", "手工", "香薰", "陶艺")
                noisy_or_high_stimulus_words = (
                    "格斗",
                    "射击",
                    "酒馆",
                    "跳海",
                    "电玩",
                    "VR",
                    "XR",
                    "训练",
                    "健身",
                    "台球",
                    "KTV",
                    "密室",
                    "剧本杀",
                    "网咖",
                    "电竞",
                    "潮玩运动",
                )
                if any(word in name for word in noisy_or_high_stimulus_words):
                    return -9999
                if "alcohol" not in markers and semantic_tags & {"alcohol", "light_drink"}:
                    return -9999
                if not raw_tags & calm_tags and not any(word in name for word in calm_words):
                    return -9999
        if (
            role == "activity"
            and scenario in {"anniversary_emotion", "city_light_explore"}
            and dining_preference.get("explicit")
            and item.get("category") == "restaurant"
            and not semantic_tags & {"theater", "private_cinema", "hands_on", "craft", "music", "acoustic_music"}
        ):
            return -9999
        if role == "activity" and markers & {"music", "acoustic_music"}:
            if semantic_tags & {"fitness", "sports"}:
                return -9999
            if semantic_tags & {"low_fit_activity"} and not semantic_tags & {"alcohol", "light_drink"}:
                return -9999
        if scenario == "anniversary_emotion" and role == "activity" and "alcohol" not in markers and semantic_tags & {"alcohol", "light_drink"}:
            return -9999
        if role == "activity" and markers & {"hands_on", "craft"} and not semantic_tags & {"hands_on", "craft"}:
            return -9999
        if role == "activity" and "board_game" in markers and "board_game" not in semantic_tags:
            return -9999
        if role == "activity" and "karaoke" in markers and "karaoke" not in semantic_tags:
            return -9999
        if role == "activity" and "esports" in markers and "esports" not in semantic_tags and not explicit_activity_fit:
            return -9999
        if role == "activity" and markers & {"music", "acoustic_music"} and not semantic_tags & {"music", "acoustic_music"}:
            return -9999
        if role == "activity" and "coffee" in markers and not semantic_tags & {"coffee", "quiet", "quiet_stay"}:
            return -9999
        if role == "activity" and "light_walk" in markers:
            if semantic_tags & {"theater", "private_cinema", "movie"}:
                return -9999
            if not semantic_tags & {"lake", "park", "light_walk", "quiet", "quiet_stay"}:
                return -9999
            if not markers & {"coffee", "conversation", "post_meal_conversation"} and not semantic_tags & {"lake", "park", "light_walk"}:
                return -9999
        if (
            scenario == "friend_group"
            and role == "activity"
            and item.get("category") == "restaurant"
            and markers & {"buffet", "bbq", "grill", "dinner"}
            and semantic_tags & {"food", "restaurant", "proper_dining", "slow_dining"}
            and not semantic_tags & {"coffee", "dessert", "quiet_stay", "alcohol", "light_drink", "music", "acoustic_music"}
        ):
            return -9999
        if scenario == "friend_group" and role == "activity" and "post_meal_conversation" in markers:
            post_meal_activity_tags = {"coffee", "dessert", "quiet_stay", "lake", "park"}
            if semantic_tags & {"theater", "private_cinema", "movie"}:
                return -9999
            if not semantic_tags & post_meal_activity_tags:
                return -9999
            if semantic_tags & {"proper_dining", "slow_dining", "bbq", "grill", "hotpot", "alcohol", "light_drink"} and not semantic_tags & {"coffee", "dessert", "quiet_stay"}:
                return -9999
        if scenario == "anniversary_emotion" and role == "activity" and semantic_tags & {"low_fit_activity", "sports", "fitness"} and not explicit_activity_fit:
            return -9999
        if scenario == "anniversary_emotion" and role == "tail" and semantic_tags & {"low_fit_activity", "sports", "fitness", "script_murder", "board_game"} and not explicit_activity_fit:
            return -9999
        if scenario == "city_light_explore" and role in {"activity", "tail"} and semantic_tags & {"low_fit_activity", "sports", "fitness", "script_murder", "board_game"} and not explicit_activity_fit:
            return -9999
        if scenario == "city_light_explore" and role in {"activity", "tail"} and "alcohol" not in markers and semantic_tags & {"alcohol", "light_drink"}:
            return -9999
        if scenario == "family_parent_child" and role in {"activity", "tail"} and self._is_family_unsafe_activity(item, semantic_tags):
            return -9999
        if scenario == "family_parent_child" and role == "activity":
            if "amusement" in markers and "amusement" not in semantic_tags:
                return -9999
            if not semantic_tags & {"child_friendly", "kid_safe", "family_time", "hands_on", "craft", "amusement"}:
                return -9999
            if semantic_tags & {"shopping"} and not semantic_tags & {"child_friendly", "kid_safe", "family_time", "hands_on", "craft", "amusement", "movie", "theater"}:
                return -9999
        quality_restaurant_tags = {"quality_dining", "proper_dining", "slow_dining", "ambience_dining"}
        lake_quality_fit = "lake" in semantic_tags and float(item.get("price_per_person") or 0) >= 120
        if role == "restaurant" and markers & {"beautiful_dining", "quality_dining"} and not (semantic_tags & quality_restaurant_tags or lake_quality_fit):
            return -9999
        if scenario == "fallback_unknown" and "alcohol" in markers and role == "activity" and not semantic_tags & {"alcohol", "light_drink", "music", "acoustic_music", "lake", "park", "quiet_stay", "theater"}:
            return -9999
        weather_score = self._weather_context_score(item, role, constraints, semantic_tags)
        if weather_score <= -9000:
            return -9999
        status_score = self._status_score(item, role, constraints)
        if (role in {"restaurant", "activity"} or (role == "tail" and item.get("category") == "activity")) and status_score <= -20:
            return -9999
        score = float(weights.get("intent_match", 42)) * self._tag_score(item, desired_tags)
        score -= 36 * self._tag_penalty(item, avoid_tags)
        score -= 18 * self._area_penalty(item, preferred_area)
        score += float(item.get("rating") or 4.2) * float(weights.get("rating", 8))
        score += status_score * float(weights.get("status", 18))
        score -= self._price_penalty(item, role, constraints)
        score += self._role_bonus(item, role, scenario, constraints)
        score += self._feature_rank_score(item, role, scenario, constraints, desired_tags, avoid_tags)
        score += weather_score
        score -= self._poi_quality_penalty(item, role, scenario, constraints, machine_intent)
        if role == "restaurant":
            score += self._open_dining_match_score(item, constraints) * 2.4
        score += float(policy_score.get("score") or 0)
        return score

    def _feature_rank_score(
        self,
        item: Dict[str, Any],
        role: str,
        scenario: str,
        constraints: Dict[str, Any],
        desired_tags: set[str],
        avoid_tags: set[str],
    ) -> float:
        if not self.poi_feature_store:
            return 0.0
        feature = self.poi_feature_store.for_item(item)
        if not feature:
            return 0.0
        scores = {
            str(key): float(value)
            for key, value in (feature.get("scores") or {}).items()
            if isinstance(value, (int, float))
        }
        experience = {
            str(key): float(value)
            for key, value in (feature.get("experience_scores") or {}).items()
            if isinstance(value, (int, float))
        }
        risk = {
            str(key): float(value)
            for key, value in (feature.get("risk_scores") or {}).items()
            if isinstance(value, (int, float))
        }
        tags = set(str(tag) for tag in feature.get("semantic_tags") or [])
        markers = set(str(item) for item in constraints.get("must_have") or [])
        value = scores.get("quality", 0.0) * self._rank_weight("base.quality")
        value += len(tags & desired_tags) * self._rank_weight("tag.desired")
        value += len(tags & avoid_tags) * self._rank_weight("tag.avoid")
        if role == "activity":
            if scenario == "family_parent_child":
                value += scores.get("family_fit", 0.0) * self._rank_weight("activity.family_fit")
                value += scores.get("amusement_fit", 0.0) * self._rank_weight("activity.amusement_fit.required" if "amusement" in markers else "activity.amusement_fit.default")
            elif scenario == "anniversary_emotion":
                value += scores.get("date_fit", 0.0) * self._rank_weight("activity.date_fit")
            elif scenario == "city_light_explore":
                value += scores.get("visitor_fit", 0.0) * self._rank_weight("activity.visitor_fit")
            elif scenario == "friend_group":
                value += scores.get("friend_fit", 0.0) * self._rank_weight("activity.friend_fit")
                value += max(experience.get("conversation_fit", 0.0), experience.get("stay_duration_fit", 0.0)) * self._rank_weight("activity.experience_fit")
            else:
                value += scores.get("solo_fit", 0.0) * self._rank_weight("activity.solo_fit")
                value += max(experience.get("quiet_fit", 0.0), experience.get("walkability", 0.0)) * self._rank_weight("activity.experience_fit")
            if scenario == "family_parent_child":
                value += experience.get("kid_safety", 0.0) * self._rank_weight("activity.experience_fit")
            elif scenario == "anniversary_emotion":
                value += experience.get("ritual_fit", 0.0) * self._rank_weight("activity.experience_fit")
            elif scenario == "city_light_explore":
                value += max(experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0)) * self._rank_weight("activity.experience_fit")
            if not ("karaoke" in markers and "karaoke" in tags):
                value += scores.get("low_fit_penalty", 0.0) * self._rank_weight("activity.low_fit_penalty")
            if "mall_walk" not in markers:
                value += risk.get("mall_dependency", 0.0) * self._rank_weight("activity.mall_dependency_risk")
            if "light_walk" in markers or avoid_tags & {"movie", "theater", "private_cinema"}:
                value += risk.get("movie_dependency", 0.0) * self._rank_weight("activity.movie_dependency_risk")
        elif role == "restaurant":
            explicit_tags = self._explicit_dining_required_tags(constraints)
            value += scores.get("proper_dining", 0.0) * self._rank_weight("restaurant.proper_dining")
            value += scores.get("casual_penalty", 0.0) * self._rank_weight("restaurant.casual_penalty")
            value += max(experience.get("dining_substance", 0.0), experience.get("ritual_fit", 0.0)) * self._rank_weight("restaurant.experience_fit")
            value += max(risk.get("snack_substitution", 0.0), risk.get("dinner_substitution", 0.0)) * self._rank_weight("restaurant.snack_substitution_risk")
            if scenario == "family_parent_child":
                value += scores.get("family_fit", 0.0) * self._rank_weight("restaurant.family_fit")
                value += experience.get("kid_safety", 0.0) * self._rank_weight("restaurant.experience_fit")
            elif scenario == "anniversary_emotion":
                value += scores.get("date_fit", 0.0) * self._rank_weight("restaurant.date_fit")
                value += experience.get("ritual_fit", 0.0) * self._rank_weight("restaurant.experience_fit")
            elif scenario == "city_light_explore":
                value += scores.get("visitor_fit", 0.0) * self._rank_weight("restaurant.visitor_fit")
                value += experience.get("conversation_fit", 0.0) * self._rank_weight("restaurant.experience_fit")
            elif scenario == "friend_group":
                value += scores.get("friend_fit", 0.0) * self._rank_weight("restaurant.friend_fit")
            if "buffet" in explicit_tags or "buffet" in markers:
                value += scores.get("buffet_fit", 0.0) * self._rank_weight("restaurant.buffet_fit.required")
            if markers & {"light_meal", "light_food", "healthy_light"}:
                value += scores.get("light_meal_fit", 0.0) * self._rank_weight("restaurant.light_meal_fit.required")
                value += risk.get("heavy_meal", 0.0) * self._rank_weight("restaurant.heavy_meal_risk")
            if markers & {"beautiful_dining", "quality_dining"}:
                value += scores.get("quality", 0.0) * self._rank_weight("restaurant.quality.required")
                value += scores.get("proper_dining", 0.0) * self._rank_weight("restaurant.proper_dining.required")
        else:
            if scenario == "family_parent_child":
                value += scores.get("family_fit", 0.0) * self._rank_weight("tail.family_fit")
                value += experience.get("kid_safety", 0.0) * self._rank_weight("tail.experience_fit")
            elif scenario == "anniversary_emotion":
                value += scores.get("date_fit", 0.0) * self._rank_weight("tail.date_fit")
                value += experience.get("ritual_fit", 0.0) * self._rank_weight("tail.experience_fit")
            elif scenario == "city_light_explore":
                value += scores.get("visitor_fit", 0.0) * self._rank_weight("tail.visitor_fit")
                value += max(experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0)) * self._rank_weight("tail.experience_fit")
            else:
                value += scores.get("solo_fit", 0.0) * self._rank_weight("tail.solo_fit")
                value += max(experience.get("quiet_fit", 0.0), experience.get("conversation_fit", 0.0), experience.get("walkability", 0.0)) * self._rank_weight("tail.experience_fit")
            value += scores.get("route_anchor", 0.0) * self._rank_weight("tail.route_anchor")
            value += scores.get("low_fit_penalty", 0.0) * self._rank_weight("tail.low_fit_penalty")
        if markers & {"nearby", "route_simple", "area_jinshahu", "area_xiasha", "area_gaojiao"}:
            value += scores.get("route_anchor", 0.0) * self._rank_weight("context.route_anchor.required")
            value += risk.get("route_fragility", 0.0) * self._rank_weight("risk.route_fragility")
        if role in {"activity", "tail"}:
            value += risk.get("weather_exposure", 0.0) * self._rank_weight("risk.weather_exposure")
        if str(constraints.get("queue_tolerance") or "") == "low" or markers & {"low_queue", "queue"}:
            value += self._queue_pressure_for_role(feature, role, constraints, risk) * self._rank_weight("risk.queue_pressure")
        value += risk.get("intent_mismatch", 0.0) * self._rank_weight("risk.intent_mismatch")
        if "alcohol" not in markers and role != "restaurant":
            value += risk.get("alcohol_risk", 0.0) * self._rank_weight("risk.alcohol")
        return value

    def _weather_context_score(self, item: Dict[str, Any], role: str, constraints: Dict[str, Any], semantic_tags: set[str]) -> float:
        if role not in {"activity", "tail"} or constraints.get("weather_sensitive") is False:
            return 0.0
        window = self._weather_window_for_role(role, constraints)
        area = item.get("area") or (item.get("location") or {}).get("area")
        if not window or not area:
            return 0.0
        weather = self._weather_for_candidate(str(area), window[0], window[1])
        if not weather:
            return 0.0
        rain_probability = float(weather.get("rain_probability") or 0)
        outdoor_risk_level = str(weather.get("outdoor_risk_level") or "")
        high_risk = rain_probability >= 0.6 or outdoor_risk_level in {"high", "blocking"}
        medium_risk = rain_probability >= 0.4 or outdoor_risk_level == "medium"
        if not high_risk and not medium_risk:
            return 0.0

        weather_exposed = self._is_weather_exposed_item(item, semantic_tags)
        if weather_exposed and high_risk:
            return -10000.0
        if weather_exposed and medium_risk:
            return -420.0

        if semantic_tags & {"rain_safe", "indoor", "mall", "quiet_stay", "coffee", "dessert"}:
            feature = self.poi_feature_store.for_item(item) if self.poi_feature_store else {}
            rain_comfort = float((feature.get("experience_scores") or {}).get("rain_comfort") or 0.0)
            return (54.0 if high_risk else 28.0) + rain_comfort * 38.0
        return 0.0

    def _weather_window_for_role(self, role: str, constraints: Dict[str, Any]) -> Optional[tuple[str, str]]:
        start_time = constraints.get("planning_start_time")
        if not start_time:
            return None
        try:
            start = datetime.fromisoformat(str(start_time))
        except (TypeError, ValueError):
            return None
        offset_minutes = 0 if role == "activity" else 150
        duration_minutes = 90 if role == "activity" else 60
        window_start = start + timedelta(minutes=offset_minutes)
        window_end = window_start + timedelta(minutes=duration_minutes)
        return window_start.replace(microsecond=0).isoformat(), window_end.replace(microsecond=0).isoformat()

    def _weather_for_candidate(self, area: str, start_time: str, end_time: str) -> Optional[Dict[str, Any]]:
        key = (area, start_time, end_time, "weather_context")
        if key in self._weather_score_cache:
            cached = self._weather_score_cache[key]
            return cached if isinstance(cached, dict) else None
        logger = self.mock_api_service.logger
        try:
            self.mock_api_service.logger = None
            weather = self.mock_api_service.weather(
                "trace_internal_recommendation",
                area=area,
                start_time=start_time,
                end_time=end_time,
            )
            self._weather_score_cache[key] = weather
            return weather
        except Exception:
            self._weather_score_cache[key] = {}
            return None
        finally:
            self.mock_api_service.logger = logger

    def _is_weather_exposed_item(self, item: Dict[str, Any], semantic_tags: set[str]) -> bool:
        name = str(item.get("name") or "")
        sub_category = str(item.get("sub_category") or "")
        text = f"{name} {sub_category}"
        if any(token in text for token in ("室内", "地下", "连通", "雨天", "温室", "雨歇", "避雨")):
            return False
        if semantic_tags & {"indoor", "rain_safe", "mall"}:
            return False
        if item.get("category") == "walk_spot":
            return True
        return bool(semantic_tags & {"outdoor", "outdoor_shade", "lake", "park", "light_walk"})

    def _rank_weight(self, key: str) -> float:
        if self._ranker_weights is None:
            document = self.mock_api_service.store.read(RECOMMENDATION_RANKER_WEIGHTS_PATH, default_ranker_weight_document())
            self._ranker_weights = normalize_ranker_weights(document)
        return self._ranker_weights[key]

    def _status_score(self, item: Dict[str, Any], role: str, constraints: Dict[str, Any]) -> float:
        when = self._planning_arrival_time_for_role(role, constraints)
        markers = set(str(item) for item in constraints.get("must_have") or [])
        party_size = int(constraints.get("party_size") or 1)
        logger = self.mock_api_service.logger
        try:
            self.mock_api_service.logger = None
            if role == "restaurant" and item.get("category") != "restaurant" and "alcohol" in markers:
                status = self.mock_api_service.poi_status("trace_internal_recommendation", item["poi_id"], party_size=party_size, when=when)
                if not status.get("available"):
                    return -30.0
                queue = float(status.get("queue_minutes") or 0)
                return 1.8 - min(queue, 35) / 20
            if role == "restaurant" or item.get("category") == "restaurant":
                status = self.mock_api_service.restaurant_status("trace_internal_recommendation", item["poi_id"], arrival_time=when, party_size=party_size)
                if not status.get("available") or not status.get("reservation_available"):
                    return -30.0
                queue = float(status.get("queue_minutes") or 0)
                available_tables = float(status.get("available_tables") or 0)
                score = 2.4 + min(available_tables, 4) * 0.35 - min(queue, 45) / 12
                if status.get("risk_level") in {"medium", "high"}:
                    score -= 1.2
                if str(constraints.get("queue_tolerance") or "") == "low" and queue > 10:
                    score -= min(2.8, (queue - 10) / 8)
                return score
            status = self.mock_api_service.poi_status("trace_internal_recommendation", item["poi_id"], party_size=party_size, when=when)
            if not status.get("available"):
                return -30.0
            remaining_tickets = status.get("remaining_tickets")
            if status.get("ticket_available") is False or status.get("booking_available") is False:
                return -30.0
            if remaining_tickets is not None and float(remaining_tickets) < party_size:
                return -30.0
            queue = float(status.get("queue_minutes") or 0)
            tickets = float(remaining_tickets or party_size)
            return 1.5 + min(tickets, 20) / 20 - min(queue, 35) / 25
        except Exception:
            return -10.0
        finally:
            self.mock_api_service.logger = logger

    def _queue_pressure_for_role(
        self,
        feature: Dict[str, Any],
        role: str,
        constraints: Dict[str, Any],
        risk: Optional[Dict[str, float]] = None,
    ) -> float:
        status_signals = feature.get("status_signals") if isinstance(feature, dict) else {}
        profile = (status_signals or {}).get("queue_profile") if isinstance(status_signals, dict) else {}
        segment = self._queue_segment_for_time(self._planning_arrival_time_for_role(role, constraints))
        if segment and isinstance(profile, dict) and isinstance(profile.get(segment), dict):
            value = profile[segment].get("queue_pressure")
            if isinstance(value, (int, float)):
                return float(value)
        if isinstance(status_signals, dict) and isinstance(status_signals.get("queue_pressure"), (int, float)):
            return float(status_signals.get("queue_pressure") or 0.0)
        return float((risk or {}).get("queue_pressure", 0.0))

    def _planning_arrival_time_for_role(self, role: str, constraints: Dict[str, Any]) -> Optional[str]:
        when = constraints.get("planning_start_time")
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if role == "restaurant" and self._dinner_last(constraints):
            when = self._dinner_anchor_time(constraints)
        elif role == "restaurant" and not (markers & {"alcohol", "post_meal_conversation", "restaurant_first_request"}):
            when = self._offset_time(when, 90)
        elif role == "tail":
            when = self._offset_time(when, 180)
        return when

    def _dinner_anchor_time(self, constraints: Dict[str, Any]) -> Optional[str]:
        start_value = constraints.get("planning_start_time")
        end_value = constraints.get("planning_end_time")
        if not start_value or not end_value:
            return self._offset_time(start_value, 90)
        try:
            start = datetime.fromisoformat(str(start_value))
            end = datetime.fromisoformat(str(end_value))
        except (TypeError, ValueError):
            return self._offset_time(str(start_value), 90)
        anchor = start.replace(hour=17, minute=30, second=0, microsecond=0)
        if anchor < start:
            anchor = start
        latest = end - timedelta(minutes=70)
        if anchor > latest:
            anchor = max(start, latest)
        return anchor.replace(microsecond=0).isoformat()

    def _queue_segment_for_time(self, value: Optional[str]) -> str:
        if not value:
            return ""
        try:
            hour = datetime.fromisoformat(str(value)).hour
        except (TypeError, ValueError):
            return ""
        if hour < 16:
            return "afternoon"
        if hour < 19:
            return "dinner"
        return "evening"

    def _offset_time(self, value: Optional[str], minutes: int) -> Optional[str]:
        if not value:
            return value
        try:
            return (datetime.fromisoformat(value) + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()
        except (TypeError, ValueError):
            return value

    def _role_bonus(self, item: Dict[str, Any], role: str, scenario: str, constraints: Dict[str, Any]) -> float:
        tags = self._semantic_tags(item)
        name = str(item.get("name") or "")
        markers = set(str(item) for item in constraints.get("must_have") or [])
        explicitly_wants_hands_on = bool(markers & {"hands_on", "craft"})
        bonus = 0.0
        if scenario == "anniversary_emotion":
            if role == "activity":
                if tags & {"date_friendly", "quiet_stay", "lake", "park", "indoor", "has_photo", "private_cinema", "theater", "lounge"}:
                    bonus += 44
                if any(token in name for token in ANNIVERSARY_ACTIVITY_WORDS) and (explicitly_wants_hands_on or not tags & {"hands_on", "craft"}):
                    bonus += 36
                if tags & {"hands_on", "craft"} and explicitly_wants_hands_on:
                    bonus += 88
            if role == "restaurant":
                if "hotpot" in constraints.get("must_have", []) and tags & {"hotpot"}:
                    bonus += 118
                if "buffet" in markers and "buffet" in tags:
                    bonus += 118
                if markers & {"cuisine_japanese", "sushi", "izakaya"} and tags & {"cuisine_japanese", "sushi", "izakaya"}:
                    bonus += 118
                    if any(token in name for token in JAPANESE_QUALITY_WORDS):
                        bonus += 72
                if markers & {"bbq", "grill"} and tags & {"bbq", "grill"}:
                    bonus += 118
                if markers & {"western_cuisine", "steak"} and tags & {"western_cuisine", "steak"}:
                    bonus += 118
                if "lamb" in markers and "lamb" in tags:
                    bonus += 96
                    if tags & {"bbq", "grill"}:
                        bonus += 42
                if markers & {"light_meal", "light_food", "healthy_light"} and tags & {"light_meal", "light_food", "healthy_light", "low_calorie"}:
                    bonus += 96
                if tags & {"food", "restaurant", "lake", "proper_dining", "slow_dining", "quality_dining", "ambience_dining"}:
                    bonus += 34
                if any(token in name for token in ANNIVERSARY_DINING_WORDS):
                    bonus += 34
                if tags & {"quality_dining", "ambience_dining"}:
                    bonus += 58
            if role == "tail" and (tags & {"dessert", "coffee", "lake", "park"} or self._name_matches_tail(item)):
                bonus += 26
        elif scenario == "family_parent_child":
            if role == "activity" and tags & {"child_friendly", "kid_safe", "family_time", "amusement", "hands_on", "craft"}:
                bonus += 72
            if role == "activity" and "amusement" in markers and "amusement" in tags:
                bonus += 120
            if role == "activity" and any(token in name for token in FAMILY_ACTIVITY_WORDS):
                bonus += 46
            if role == "activity" and tags & {"movie", "theater"}:
                bonus += 18
            if role == "restaurant" and tags & {"light_food", "light_meal", "low_calorie", "family_friendly"}:
                bonus += 68
            if role == "restaurant" and "buffet" in markers and "buffet" in tags:
                bonus += 118
            if role == "restaurant" and any(token in name for token in LIGHT_MEAL_NAME_WORDS):
                bonus += 34
            if role == "tail" and tags & {"lake", "park", "quiet_stay", "child_friendly", "kid_safe"}:
                bonus += 24
        elif scenario == "friend_group":
            if tags & {"group_ok", "board_game", "mall", "indoor"}:
                bonus += 28
            if role == "activity" and "esports" in markers and "esports" in tags:
                bonus += 132
            if role == "activity" and "karaoke" in markers and "karaoke" in tags:
                bonus += 132
            if role == "activity" and "post_meal_conversation" in markers and tags & {"coffee", "dessert", "quiet_stay", "lake", "park"}:
                bonus += 72
            if role == "activity" and "restaurant_first_request" in markers and tags & {"karaoke", "coffee", "dessert", "quiet_stay", "lake", "park", "light_walk"}:
                bonus += 58
            if role == "restaurant" and float(item.get("price_per_person") or 0) <= float(constraints.get("budget_max_per_person") or 999):
                bonus += 18
        elif scenario == "city_light_explore":
            if role == "activity":
                if tags & {"visitor_friendly", "lake", "park", "theater", "private_cinema", "quiet_stay"}:
                    bonus += 48
                if explicitly_wants_hands_on and tags & {"hands_on", "craft"}:
                    bonus += 42
                if any(token in name for token in VISITOR_ACTIVITY_WORDS) and (explicitly_wants_hands_on or not tags & {"hands_on", "craft"}):
                    bonus += 36
            if role == "restaurant":
                if tags & {"quality_dining", "proper_dining", "slow_dining", "lake", "ambience_dining"}:
                    bonus += 44
                if any(token in name for token in ANNIVERSARY_DINING_WORDS):
                    bonus += 26
            if role == "tail" and tags & {"lake", "park", "coffee", "dessert", "quiet_stay"}:
                bonus += 24
        elif scenario == "fallback_unknown":
            if tags & {"quiet_stay", "coffee", "lake", "park", "date_friendly"}:
                bonus += 24
            if "alcohol" in constraints.get("must_have", []) and tags & {"alcohol", "light_drink"}:
                bonus += 82
            if ("music" in constraints.get("must_have", []) or "acoustic_music" in constraints.get("must_have", [])) and ("音乐" in name or tags & {"music"}):
                bonus += 46
        return bonus

    def _poi_quality_penalty(
        self,
        item: Dict[str, Any],
        role: str,
        scenario: str,
        constraints: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> float:
        tags = self._semantic_tags(item)
        name = str(item.get("name") or "")
        penalty = 0.0
        explicit_activity_fit = role in {"activity", "tail"} and self._machine_activity_match_score(item, machine_intent) >= 0.55
        profile_tags = set(self._profile_tags(constraints))
        wants_quality_meal = bool(profile_tags & {"beautiful_dining", "quality_dining", "ambience_dining"})
        wants_buffet = "buffet" in set(str(item) for item in constraints.get("must_have") or [])
        wants_hotpot = "hotpot" in set(str(item) for item in constraints.get("must_have") or [])
        wants_bbq = bool(set(str(item) for item in constraints.get("must_have") or []) & {"bbq", "grill"})
        wants_japanese = bool(set(str(item) for item in constraints.get("must_have") or []) & {"cuisine_japanese", "sushi", "izakaya"})
        wants_light_meal = bool(set(str(item) for item in constraints.get("must_have") or []) & {"light_meal", "light_food", "healthy_light"})
        wants_open_dining = bool((constraints.get("dining_preference") or {}).get("explicit"))
        explicit_raw_food_match = self._matches_explicit_dining_raw_term(item, constraints)
        explicitly_wants_hands_on = bool(set(str(item) for item in constraints.get("must_have") or []) & {"hands_on", "craft"})
        retail_words = ("DJI", "大疆", "眼镜", "美甲", "美睫", "授权", "服务中心", "手机", "数码")
        tea_words = ("蜜雪", "1点点", "霸王茶姬", "瑞幸", "库迪", "奶茶")
        if role == "activity" and (tags <= {"gaode_poi", "mall", "shopping", "rain_safe", "has_photo", "has_tel"} or any(word in name for word in retail_words)):
            penalty += 95
        if scenario == "anniversary_emotion" and role == "activity" and any(word in name for word in GENERIC_LOW_FIT_ACTIVITY_WORDS) and not explicit_activity_fit:
            penalty += 170
        if scenario == "anniversary_emotion" and role == "activity" and tags & {"script_murder", "board_game"} and not explicit_activity_fit:
            penalty += 170
        if scenario == "anniversary_emotion" and role == "activity" and wants_open_dining and not explicitly_wants_hands_on and tags & {"hands_on", "craft"}:
            penalty += 180
        if scenario == "anniversary_emotion" and role in {"activity", "tail"} and not explicitly_wants_hands_on and tags & {"hands_on", "craft"}:
            penalty += 95
        if scenario == "anniversary_emotion" and role == "activity" and wants_open_dining and tags & {"food", "restaurant", "proper_dining", "slow_dining", "bbq", "grill", "hotpot", "western_cuisine", "steak", "lamb", "alcohol", "light_drink"}:
            penalty += 220
        if scenario == "anniversary_emotion" and role == "activity" and any(word in name for word in ("奶吧", "咖啡", "蛋糕", "甜品", "奶茶", "茶姬", "瑞幸", "库迪")):
            penalty += 80
        if role == "restaurant" and scenario == "anniversary_emotion" and any(word in name for word in tea_words):
            penalty += 65
        if role == "restaurant" and scenario == "anniversary_emotion" and any(word in name for word in ("甜点", "蛋糕", "咖啡", "酸奶", "奶茶", "面包")):
            penalty += 42
        if role == "restaurant" and wants_japanese and not wants_bbq and tags & {"bbq", "grill"}:
            penalty += 260
        if role == "restaurant" and scenario == "anniversary_emotion" and wants_japanese and any(word in name for word in JAPANESE_CASUAL_WORDS):
            penalty += 420
        if role == "restaurant" and wants_quality_meal and (tags & {"coffee", "dessert", "quiet_stay"} or any(word in name for word in ("咖啡", "甜点", "蛋糕", "酸奶", "奶茶", "茶姬", "M Stand", "星巴克"))) and not tags & {"proper_dining", "slow_dining"}:
            penalty += 150
        if role == "restaurant" and scenario == "anniversary_emotion" and any(word in name for word in CASUAL_CHAIN_WORDS) and not ((wants_buffet and "buffet" in tags) or (wants_hotpot and "hotpot" in tags) or (wants_bbq and tags & {"bbq", "grill"}) or (wants_japanese and tags & {"cuisine_japanese", "sushi", "izakaya"})):
            penalty += 145
        if role == "restaurant" and wants_quality_meal and any(word in name for word in CASUAL_CHAIN_WORDS) and not ((wants_buffet and "buffet" in tags) or (wants_hotpot and "hotpot" in tags) or (wants_bbq and tags & {"bbq", "grill"}) or (wants_japanese and tags & {"cuisine_japanese", "sushi", "izakaya"})):
            penalty += 180
        if role == "restaurant" and wants_quality_meal and not tags & {"quality_dining", "proper_dining", "slow_dining", "lake", "ambience_dining"}:
            penalty += 220
        if role == "restaurant" and wants_quality_meal and float(item.get("price_per_person") or 0) < 80 and not tags & {"quality_dining", "ambience_dining", "lake"}:
            penalty += 110
        if role == "restaurant" and scenario == "anniversary_emotion" and float(item.get("price_per_person") or 0) < 60 and not tags & {"proper_dining", "slow_dining", "lake"}:
            penalty += 80
        if role == "restaurant" and scenario == "anniversary_emotion" and not tags & {"proper_dining", "slow_dining", "lake", "quiet_stay"}:
            penalty += 140
        if scenario == "city_light_explore" and role == "activity" and tags & {"low_fit_activity", "script_murder", "board_game"} and not explicit_activity_fit:
            penalty += 140
        if scenario == "city_light_explore" and role in {"activity", "tail"} and not explicitly_wants_hands_on and tags & {"hands_on", "craft"}:
            penalty += 110
        if scenario == "friend_group" and role in {"activity", "tail"} and not explicitly_wants_hands_on and tags & {"hands_on", "craft"}:
            penalty += 85
        if scenario == "city_light_explore" and role == "activity" and any(word in name for word in ("健身", "KTV", "电竞", "棋牌", "桌游", "密室", "剧本杀", "足球", "篮球", "运动", "Parking")) and not explicit_activity_fit:
            penalty += 150
        if scenario == "city_light_explore" and role == "activity" and tags & {"sports", "fitness"} and not explicit_activity_fit:
            penalty += 180
        if scenario == "city_light_explore" and role == "activity" and tags & {"alcohol", "light_drink"} and "alcohol" not in set(str(item) for item in constraints.get("must_have") or []):
            penalty += 160
        if scenario == "city_light_explore" and role == "restaurant" and any(word in name for word in ("麦当劳", "肯德基", "德克士", "麻辣烫", "拌饭", "老娘舅", "萨莉亚", "瑞幸", "蜜雪", "奶茶", "古茗", "茶百道", "霸王茶姬", "饮品")):
            penalty += 130
        if scenario == "city_light_explore" and role == "restaurant" and any(word in name for word in ("甜品", "甜点", "蛋糕", "酸奶", "咖啡", "斯利美", "面包", "茶姬")):
            penalty += 85
        if scenario == "city_light_explore" and role == "restaurant" and not tags & {"quality_dining", "proper_dining", "slow_dining", "lake", "ambience_dining"}:
            penalty += 65
        if scenario == "city_light_explore" and role == "restaurant" and float(item.get("price_per_person") or 0) < 45 and not tags & {"lake", "proper_dining", "quality_dining"}:
            penalty += 70
        if scenario == "city_light_explore" and role == "tail" and tags & {"food", "restaurant", "proper_dining", "slow_dining"} and not tags & {"coffee", "dessert", "quiet_stay", "park"}:
            penalty += 700
        if scenario == "family_parent_child" and role in {"activity", "tail"}:
            if self._is_family_unsafe_activity(item, tags):
                penalty += 900
            if tags & {"shopping"} and not tags & {"child_friendly", "kid_safe", "family_time", "hands_on", "craft", "amusement", "movie", "theater"}:
                penalty += 320
        if scenario == "family_parent_child" and role == "restaurant":
            if wants_light_meal and tags & {"spicy_heavy", "hotpot"} and not wants_hotpot:
                penalty += 900
            if wants_light_meal and self._is_non_dinner_place(item):
                penalty += 520
            if any(word in name for word in ("麦当劳", "肯德基", "德克士", "萨莉亚", "蜜雪", "古茗", "茶百道", "霸王茶姬", "奶茶", "酸辣粉")) and not explicit_raw_food_match:
                penalty += 160
        if scenario == "anniversary_emotion" and role == "tail" and tags & {"casual_chain"}:
            penalty += 170
        if scenario == "anniversary_emotion" and role == "tail" and tags & {"low_fit_activity", "script_murder", "board_game"}:
            penalty += 900
        if scenario == "anniversary_emotion" and role == "tail" and tags & {"food", "restaurant"} and not tags & {"coffee", "dessert", "quiet_stay"}:
            penalty += 700
        if scenario == "anniversary_emotion" and role == "activity" and tags & {"shopping"} and not tags & {"theater", "private_cinema", "park", "lounge"}:
            penalty += 350
        if scenario == "anniversary_emotion" and role == "activity" and any(word in name for word in ("美食街", "广场", "商场", "购物中心")):
            penalty += 180
        if scenario == "fallback_unknown" and int(constraints.get("party_size") or 1) == 1 and role in {"activity", "tail"}:
            if tags & {"low_fit_activity", "script_murder", "board_game"}:
                penalty += 150
            if self._solo_optional_restaurant({"scenario": scenario}, constraints):
                calm_tags = {"lake", "park", "light_walk", "quiet", "quiet_stay", "coffee", "theater", "private_cinema", "hands_on", "craft"}
                noisy_or_high_stimulus_words = (
                    "格斗",
                    "射击",
                    "酒馆",
                    "跳海",
                    "电玩",
                    "VR",
                    "XR",
                    "训练",
                    "健身",
                    "台球",
                    "KTV",
                    "密室",
                    "剧本杀",
                    "网咖",
                    "电竞",
                    "潮玩运动",
                )
                snack_shop_words = ("奶吧", "奶茶", "甜品", "蛋糕", "蜜雪", "茶姬", "瑞幸", "库迪")
                if any(word in name for word in noisy_or_high_stimulus_words) and not tags & {"theater", "private_cinema"}:
                    penalty += 300
                if any(word in name for word in snack_shop_words) and not tags & {"quiet_stay", "coffee"}:
                    penalty += 320
                if role == "activity" and not tags & calm_tags:
                    penalty += 180
            if role == "tail" and tags & {"casual_chain"}:
                penalty += 95
            if "alcohol" in constraints.get("must_have", []) and not tags & {"alcohol", "light_drink", "music", "acoustic_music", "lake", "park", "quiet_stay", "theater"}:
                penalty += 110
            if self._solo_optional_restaurant({"scenario": scenario}, constraints):
                if tags & {"food", "restaurant", "proper_dining", "casual_chain", "snack_meal"} and not tags & {"coffee", "dessert", "quiet_stay", "lake", "park"}:
                    penalty += 260
        if scenario == "fallback_unknown" and int(constraints.get("party_size") or 1) == 1 and role == "restaurant" and self._solo_optional_restaurant({"scenario": scenario}, constraints):
            if tags & {"proper_dining", "casual_chain", "low_end_chain", "snack_meal", "spicy_heavy"} and not tags & {"coffee", "dessert", "quiet_stay", "alcohol", "light_drink", "lake", "park"}:
                penalty += 520
        if role == "restaurant" and "quiet_dining" in self._profile_tags(constraints) and tags & {"dessert", "quiet_stay"} and not (tags & {"food", "restaurant"}):
            penalty += 18
        if "暂停营业" in name:
            penalty += 120
        if float(item.get("price_per_person") or 0) == 0 and role in {"activity", "restaurant"} and scenario != "family_parent_child":
            penalty += 20
        return penalty

    def _price_penalty(self, item: Dict[str, Any], role: str, constraints: Dict[str, Any]) -> float:
        price = float(item.get("price_per_person") or 0)
        budget_pp = constraints.get("budget_max_per_person")
        if budget_pp is None:
            return max(0.0, price - 220) / 2
        target = float(budget_pp)
        if role == "restaurant":
            return max(0.0, price - target) * 3 + max(0.0, target * 0.18 - price) * 0.25
        return max(0.0, price - target * 0.55) * 1.2

    def _budget_penalty(
        self,
        chain_price: float,
        budget_pp: Optional[float],
        user_goal: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> float:
        if budget_pp is None:
            return 0
        budget = float(budget_pp) + self._budget_slack(user_goal or {}, constraints)
        if chain_price <= budget:
            return max(0.0, budget * 0.2 - chain_price) * 0.2
        return (chain_price - budget) * 5

    def _budget_slack(self, user_goal: Dict[str, Any], constraints: Optional[Dict[str, Any]] = None) -> float:
        constraints = constraints or {}
        dining_preference = constraints.get("dining_preference") if isinstance(constraints, dict) else {}
        if constraints.get("budget_is_strict"):
            return 0
        if user_goal.get("scenario") == "family_parent_child" and isinstance(dining_preference, dict) and dining_preference.get("explicit"):
            return 120
        if user_goal.get("scenario") == "family_parent_child":
            return 0
        if user_goal.get("scenario") == "anniversary_emotion":
            return 45
        if user_goal.get("scenario") == "city_light_explore":
            return 85
        return 10

    def _solo_optional_restaurant(self, user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
        if user_goal.get("scenario") != "fallback_unknown" or int(constraints.get("party_size") or 1) != 1:
            return False
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if markers & {"dinner", "proper_dining", "explicit_dining", "alcohol", "light_drink", "coffee", "buffet", "hotpot", "crayfish", "bbq", "grill", "cuisine_japanese", "sushi", "izakaya"}:
            return False
        dining_preference = self._dining_preference(constraints)
        return not bool(dining_preference.get("explicit"))

    def _optional_restaurant_allowed(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self._solo_optional_restaurant(user_goal, constraints) or self._friend_activity_without_meal(user_goal, constraints, machine_intent)

    def _friend_activity_without_meal(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if user_goal.get("scenario") != "friend_group":
            return False
        if self._meal_required(user_goal, constraints, machine_intent):
            return False
        markers = set(str(item) for item in constraints.get("must_have") or [])
        explicit_activity_markers = {"esports", "karaoke", "board_game", "hands_on", "craft", "light_walk", "mall_walk"}
        return bool(markers & explicit_activity_markers or self._machine_has_activity_need(machine_intent))

    def _meal_only_plan(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self._meal_required(user_goal, constraints, machine_intent):
            return False
        if self._machine_has_activity_need(machine_intent):
            return False
        markers = set(str(item) for item in constraints.get("must_have") or [])
        profile_tags = set(self._profile_tags(constraints))
        activity_markers = {
            "esports",
            "karaoke",
            "board_game",
            "hands_on",
            "craft",
            "mall_walk",
            "lake_walk",
            "coffee",
            "conversation",
            "post_meal_conversation",
            "restaurant_first_request",
        }
        if markers & activity_markers or profile_tags & activity_markers:
            return False
        raw_text = str(user_goal.get("raw_text") or "")
        explicit_activity_terms = (
            "打游戏",
            "游戏",
            "电竞",
            "网咖",
            "网吧",
            "电玩",
            "KTV",
            "唱歌",
            "桌游",
            "剧本杀",
            "密室",
            "台球",
            "羽毛球",
            "电影",
            "看电影",
            "出去玩",
            "玩几个小时",
            "几个小时",
            "游乐园",
            "手工",
            "手作",
            "逛逛",
            "散步",
            "转转",
            "溜一圈",
            "饭后",
            "餐后",
            "吃完",
        )
        return not any(term in raw_text for term in explicit_activity_terms)

    def _meal_required(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        machine_intent: Optional[Dict[str, Any]] = None,
    ) -> bool:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        profile_tags = set(self._profile_tags(constraints))
        meal_markers = {
            "dinner",
            "lunch",
            "proper_dining",
            "explicit_dining",
            "buffet",
            "hotpot",
            "crayfish",
            "bbq",
            "grill",
            "cuisine_japanese",
            "sushi",
            "izakaya",
            "western_cuisine",
            "steak",
            "lamb",
            "light_meal",
            "light_food",
            "healthy_light",
            "restaurant_first_request",
            "post_meal_conversation",
        }
        if markers & meal_markers or profile_tags & meal_markers:
            return True
        dining_preference = self._dining_preference(constraints)
        if isinstance(dining_preference, dict) and dining_preference.get("explicit"):
            return True
        if self._machine_has_food_need(machine_intent):
            return True
        raw_text = str(user_goal.get("raw_text") or "")
        return any(token in raw_text for token in ("吃饭", "吃个饭", "吃点", "吃人均", "饭", "餐", "午饭", "午餐", "晚饭", "晚餐", "正餐", "人均"))

    def _solo_optional_restaurant_adjustment(
        self,
        activity: Dict[str, Any],
        restaurant: Optional[Dict[str, Any]],
        tail: Optional[Dict[str, Any]],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> float:
        if not self._solo_optional_restaurant(user_goal, constraints):
            return 0.0
        if not restaurant:
            bonus = 260.0
            if tail and self._is_foodish_stop(activity) and self._is_foodish_stop(tail):
                bonus -= 420.0
            return bonus
        penalty = -1200.0
        restaurant_tags = self._semantic_tags(restaurant)
        if restaurant_tags & {"proper_dining", "casual_chain", "low_end_chain", "snack_meal", "spicy_heavy"} and not restaurant_tags & {"coffee", "dessert", "quiet_stay", "lake", "park"}:
            penalty -= 360.0
        foodish_count = 0
        for item in (activity, restaurant, tail):
            if not item:
                continue
            tags = self._semantic_tags(item)
            if tags & {"coffee", "dessert", "food", "restaurant", "proper_dining", "snack_meal"}:
                foodish_count += 1
        if foodish_count >= 2:
            penalty -= 120.0
        return penalty

    def _is_foodish_stop(self, item: Optional[Dict[str, Any]]) -> bool:
        if not item:
            return False
        return bool(self._semantic_tags(item) & {"coffee", "dessert", "food", "restaurant", "proper_dining", "snack_meal"})

    def _chain_route_score(self, pois: tuple[Optional[Dict[str, Any]], ...]) -> float:
        score = 0.0
        cleaned = [poi for poi in pois if poi]
        for origin, destination in zip(cleaned, cleaned[1:]):
            distance = self._distance_km(origin, destination)
            if distance is None:
                score -= 20
            else:
                score += 30 - distance * 22
        return score

    def _chain_route_penalty(
        self,
        pois: tuple[Optional[Dict[str, Any]], ...],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> float:
        total_distance = self._chain_total_distance(pois)
        if total_distance is None:
            return 0.0
        markers = set(str(item) for item in constraints.get("must_have") or [])
        profile_tags = set(self._profile_tags(constraints))
        scenario = user_goal.get("scenario")
        route_sensitive = bool(markers & {"nearby", "route_simple", "area_jinshahu", "area_xiasha", "area_gaojiao"} or profile_tags & {"nearby", "route_simple"})
        if scenario in {"anniversary_emotion", "city_light_explore", "family_parent_child"}:
            route_sensitive = True
        limit = 3.2 if route_sensitive else 4.8
        if scenario == "friend_group" and "post_meal_conversation" in markers:
            limit = 1.8 if route_sensitive else 2.4
        elif scenario == "friend_group":
            limit = 4.2
        if total_distance <= limit:
            return 0.0
        weight = 125.0 if scenario == "friend_group" and "post_meal_conversation" in markers else 62.0 if route_sensitive else 34.0
        return (total_distance - limit) * weight

    def _chain_total_distance(self, pois: tuple[Optional[Dict[str, Any]], ...]) -> Optional[float]:
        total = 0.0
        cleaned = [poi for poi in pois if poi]
        for origin, destination in zip(cleaned, cleaned[1:]):
            distance = self._distance_km(origin, destination)
            if distance is None:
                return None
            total += distance
        return total

    def _tail_inclusion_penalty(
        self,
        activity: Dict[str, Any],
        restaurant: Dict[str, Any],
        tail: Optional[Dict[str, Any]],
        route_pois: tuple[Optional[Dict[str, Any]], ...],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        tail_score: float,
    ) -> float:
        if not tail:
            return 0.0
        scenario = user_goal.get("scenario")
        markers = set(str(item) for item in constraints.get("must_have") or [])
        profile_tags = set(self._profile_tags(constraints))
        route_sensitive = bool(markers & {"nearby", "route_simple", "area_jinshahu", "area_xiasha", "area_gaojiao"} or profile_tags & {"nearby", "route_simple"})
        total_distance = self._chain_total_distance(route_pois)
        penalty = 0.0
        if scenario == "family_parent_child":
            activity_tags = self._semantic_tags(activity)
            tail_tags = self._semantic_tags(tail)
            duplicate_core = bool(activity_tags & tail_tags & {"hands_on", "craft", "amusement"})
            if duplicate_core:
                penalty += max(160.0, max(tail_score, 0.0) * 0.75)
            if route_sensitive and total_distance is not None and total_distance > 3.2:
                penalty += max(130.0, max(tail_score, 0.0) * 0.9)
        elif "post_meal_conversation" in markers:
            activity_tags = self._semantic_tags(activity)
            tail_tags = self._semantic_tags(tail)
            chat_stop_tags = {"coffee", "dessert", "quiet_stay", "lake", "park"}
            if not tail_tags & chat_stop_tags:
                penalty += max(1800.0, max(tail_score, 0.0) + 900.0)
            if tail_tags & {"food", "restaurant", "proper_dining", "slow_dining", "light_meal", "snack_meal"} and not tail_tags & {"coffee", "dessert", "quiet_stay"}:
                penalty += 1400.0
            if activity_tags & chat_stop_tags and tail_tags & chat_stop_tags:
                penalty += max(420.0, max(tail_score, 0.0) + 180.0)
            if total_distance is not None and total_distance > 3.2:
                penalty += max(120.0, max(tail_score, 0.0) * 0.65)
        elif "restaurant_first_request" in markers:
            tail_tags = self._semantic_tags(tail)
            if markers & {"karaoke", "light_walk"}:
                penalty += max(900.0, max(tail_score, 0.0) + 450.0)
            if tail_tags & {"theater", "private_cinema", "movie"}:
                penalty += max(1200.0, max(tail_score, 0.0) + 600.0)
            if tail_tags & {"food", "restaurant", "proper_dining", "slow_dining", "light_meal", "snack_meal"} and not tail_tags & {"coffee", "dessert", "quiet_stay"}:
                penalty += max(900.0, max(tail_score, 0.0) + 450.0)
            if route_sensitive and total_distance is not None and total_distance > 3.2:
                penalty += max(120.0, max(tail_score, 0.0) * 0.65)
        elif (
            scenario == "friend_group"
            and int(constraints.get("target_stop_count") or 0) <= 2
            and markers & {"dinner"}
            and (markers & {"esports", "board_game", "karaoke"} or self._dining_preference(constraints).get("explicit"))
        ):
            penalty += max(900.0, max(tail_score, 0.0) + 450.0)
        elif route_sensitive and total_distance is not None and total_distance > 3.0:
            penalty += max(900.0, max(tail_score, 0.0) + 450.0)
        return penalty

    def _is_redundant_meal_tail(self, item: Dict[str, Any], user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
        if self._is_service_poi(item) or item.get("category") != "restaurant":
            return False
        if not self._meal_required(user_goal, constraints):
            return False
        tags = self._semantic_tags(item)
        meal_tags = {"food", "restaurant", "proper_dining", "slow_dining", "light_meal", "light_food", "healthy_light", "snack_meal"}
        if tags & {"coffee", "dessert"} and not tags & meal_tags:
            return False
        return bool(tags & meal_tags)

    def _best_tail(
        self,
        anchor: Dict[str, Any],
        tail_ranked: list[Dict[str, Any]],
        excluded_ids: Optional[set[str]] = None,
        destination: Optional[Dict[str, Any]] = None,
        score_item: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        if not tail_ranked:
            return None
        excluded = excluded_ids or {str(anchor.get("poi_id"))}
        candidates = [tail for tail in tail_ranked[:60] if str(tail.get("poi_id")) not in excluded]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda tail: (
                self._route_affinity(anchor, tail)
                + (self._route_affinity(tail, destination) if destination else 0)
                + (float(score_item(tail, "tail")) * 0.12 if score_item else 0.0)
            ),
        )

    def _route_affinity(self, origin: Dict[str, Any], destination: Dict[str, Any]) -> float:
        distance = self._distance_km(origin, destination)
        if distance is None:
            return -10
        return 20 - distance * 12

    def _name_matches_tail(self, item: Dict[str, Any]) -> bool:
        name = str(item.get("name") or "")
        return any(token in name for token in ("咖啡", "蛋糕", "甜品", "茶", "湖", "公园", "Manner", "星巴克"))

    def _restaurant_first(self, constraints: Dict[str, Any]) -> bool:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        return bool(markers & {"alcohol", "post_meal_conversation", "restaurant_first_request"})

    def _dinner_last(self, constraints: Dict[str, Any]) -> bool:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        return "dinner" in markers and not (markers & {"post_meal_conversation", "restaurant_first_request"})

    def _required_restaurant_tags(self, constraints: Dict[str, Any]) -> Optional[str]:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        explicit_tags = self._explicit_dining_required_tags(constraints)
        if "buffet" in explicit_tags:
            return "buffet"
        if "sushi" in markers and "sushi" in explicit_tags:
            return "sushi"
        if "izakaya" in markers and "izakaya" in explicit_tags:
            return "izakaya"
        if "cuisine_japanese" in explicit_tags:
            return "cuisine_japanese"
        if "crayfish" in markers:
            return "crayfish"
        if "hotpot" in markers:
            return "hotpot"
        if "buffet" in markers:
            return "buffet"
        if markers & {"bbq", "grill"}:
            return "bbq"
        if markers & {"light_meal", "light_food"}:
            return "light_meal"
        if "alcohol" in markers:
            return "alcohol"
        return None

    def _explicit_dining_required_tags(self, constraints: Dict[str, Any]) -> set[str]:
        if self.policy_engine:
            return self.policy_engine.explicit_dining_required_tags(constraints)
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if "buffet" in markers:
            return {"buffet"}
        if "hotpot" in markers:
            return {"hotpot"}
        if "crayfish" in markers:
            return {"crayfish"}
        if "sushi" in markers:
            return {"cuisine_japanese", "sushi"}
        if "izakaya" in markers:
            return {"cuisine_japanese", "izakaya"}
        if "cuisine_japanese" in markers:
            return {"cuisine_japanese", "sushi", "izakaya"}
        if markers & {"bbq", "grill"}:
            return {"bbq", "grill"}
        return set()

    def _preferred_area(self, constraints: Dict[str, Any]) -> Optional[str]:
        if constraints.get("preferred_area"):
            return str(constraints["preferred_area"])
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if "area_jinshahu" in markers:
            return "金沙湖"
        if "area_gaojiao" in markers:
            return "高教园区"
        if "area_xiasha" in markers:
            return "下沙"
        return None

    def _area_penalty(self, item: Dict[str, Any], preferred_area: Optional[str]) -> int:
        if not preferred_area:
            return 0
        area = item.get("area") or item.get("location", {}).get("area")
        penalty = 0 if area == preferred_area else 3
        name = str(item.get("name") or "")
        other_areas = {"金沙湖", "高教园区", "高教园", "下沙"} - {preferred_area}
        if preferred_area not in name and any(area_name in name for area_name in other_areas):
            penalty += 2
        return penalty

    def _tag_score(self, item: Dict[str, Any], desired_tags: set[str]) -> int:
        return len(self._semantic_tags(item) & desired_tags)

    def _tag_penalty(self, item: Dict[str, Any], avoid_tags: set[str]) -> int:
        return len(self._semantic_tags(item) & avoid_tags)

    def _poi_text(self, item: Dict[str, Any]) -> str:
        values: list[str] = [
            str(item.get("name") or ""),
            str(item.get("sub_category") or ""),
            str(item.get("address") or ""),
            str(item.get("area") or ""),
            " ".join(str(tag) for tag in item.get("tags", [])),
            " ".join(str(tag) for tag in item.get("suitable_scenarios", [])),
        ]
        enrichment = self._poi_enrichment(str(item.get("poi_id") or ""))
        if enrichment:
            values.extend(
                str(enrichment.get(key) or "")
                for key in ("name", "gaode_type", "business_area", "address", "open_time")
            )
            values.append(" ".join(str(value) for value in (enrichment.get("biz_ext") or {}).values()))
        return " ".join(values)

    def _semantic_tags(self, item: Dict[str, Any]) -> set[str]:
        tags = {str(tag) for tag in item.get("tags", [])}
        tags.update(str(tag) for tag in item.get("suitable_scenarios", []))
        if self.poi_feature_store:
            tags.update(self.poi_feature_store.semantic_tags(item))
        if self.policy_engine:
            tags.update(self.policy_engine.semantic_tags(item))
        name = str(item.get("name") or "")
        category = str(item.get("category") or "")
        if any(word in name for word in ALCOHOL_NAME_WORDS):
            tags.update({"alcohol", "light_drink"})
        if any(word in name for word in ("咖啡", "Coffee", "COFFEE", "M Stand", "Manner", "星巴克", "瑞幸", "库迪")):
            tags.update({"coffee", "quiet_stay"})
        if any(word in name for word in ("甜品", "蛋糕", "面包", "泡芙", "酸奶", "奶吧", "鲜奶", "牛奶")):
            tags.update({"dessert", "quiet_stay"})
        if any(word in name for word in MUSIC_NAME_WORDS):
            tags.update({"music", "acoustic_music"})
        if any(word in name for word in ("桌游", "棋牌", "麻将", "狼人杀", "剧本杀")):
            tags.update({"board_game", "group_ok"})
        if any(word in name for word in KARAOKE_NAME_WORDS):
            tags.update({"karaoke", "group_ok", "indoor", "rain_safe"})
        if self._looks_like_hands_on_experience(item):
            tags.update({"hands_on", "craft", "date_friendly", "visitor_friendly", "indoor"})
            if category == "activity":
                tags.update({"child_friendly", "kid_safe", "family_time"})
        if (category == "activity" and any(word in name for word in FAMILY_ACTIVITY_WORDS)) or "amusement" in tags:
            tags.update({"child_friendly", "kid_safe", "family_time", "not_tiring"})
        if category == "activity" and any(word in name for word in AMUSEMENT_NAME_WORDS):
            tags.update({"amusement", "child_friendly", "kid_safe", "family_time"})
        if "影院" in name or "剧院" in name:
            tags.update({"theater", "date_friendly"})
        if "私人影院" in name or "点播影院" in name:
            tags.update({"private_cinema", "date_friendly", "quiet"})
        if "Lounge" in name or "LOUNGE" in name:
            tags.update({"lounge", "date_friendly", "low_key"})
        if any(word in name for word in ANNIVERSARY_DINING_WORDS):
            tags.update({"proper_dining", "slow_dining", "quality_dining", "ambience_dining", "date_friendly"})
        if category == "restaurant" and any(word in name for word in BUFFET_NAME_WORDS):
            tags.update({"buffet", "proper_dining", "slow_dining"})
        if any(word in name for word in HOTPOT_NAME_WORDS):
            tags.update({"hotpot", "proper_dining", "slow_dining"})
        if any(word in name for word in CRAYFISH_NAME_WORDS):
            tags.update({"crayfish", "proper_dining", "slow_dining"})
        if any(word in name for word in JAPANESE_CUISINE_WORDS):
            tags.update({"cuisine_japanese", "proper_dining", "slow_dining", "date_friendly"})
        if any(word in name for word in SUSHI_WORDS):
            tags.update({"sushi", "cuisine_japanese", "proper_dining", "slow_dining"})
        if any(word in name for word in IZAKAYA_WORDS):
            tags.update({"izakaya", "cuisine_japanese", "proper_dining", "slow_dining"})
        if any(word in name for word in BBQ_NAME_WORDS):
            tags.update({"bbq", "grill", "proper_dining", "slow_dining"})
        if any(word in name for word in WESTERN_CUISINE_WORDS):
            tags.update({"western_cuisine", "proper_dining", "slow_dining", "date_friendly"})
        if any(word in name for word in STEAK_WORDS):
            tags.update({"steak", "western_cuisine", "proper_dining", "slow_dining"})
        if any(word in name for word in LAMB_NAME_WORDS):
            tags.update({"lamb", "proper_dining"})
            if any(word in name for word in ("烤", "炭", "烧烤", "烤全羊", "羊肉串")):
                tags.update({"bbq", "grill", "slow_dining"})
        if any(word in name for word in HEALTHY_LIGHT_WORDS):
            tags.update({"healthy_light", "light_meal", "light_food", "low_calorie"})
        if any(word in name for word in LIGHT_MEAL_NAME_WORDS):
            tags.update({"light_meal", "light_food", "family_friendly"})
        if category == "restaurant" and any(word in name for word in BURGER_FOOD_WORDS):
            tags.update({"proper_dining", "family_friendly", "child_food"})
        if any(word in name for word in HEAVY_SPICY_NAME_WORDS):
            tags.add("spicy_heavy")
        if any(word in name for word in ("湖畔", "金沙湖", "公园", "茶空间", "沙滩")):
            tags.update({"lake", "visitor_friendly", "showcase_local"})
        if any(word in name for word in CASUAL_CHAIN_WORDS) and not tags & {"hotpot", "bbq", "grill"}:
            tags.update({"casual_chain", "low_end_chain"})
        if any(word in name for word in GENERIC_LOW_FIT_ACTIVITY_WORDS) or tags & {"esports", "fitness", "sports", "swimming"}:
            tags.add("low_fit_activity")
        return tags

    def _poi_enrichment(self, poi_id: str) -> Dict[str, Any]:
        if self._enrichment_cache is None:
            self._enrichment_cache = self.mock_api_service.store.read(GAODE_POI_ENRICHMENT_PATH, {"enrichments": {}}).get("enrichments", {})
        value = self._enrichment_cache.get(poi_id) if isinstance(self._enrichment_cache, dict) else None
        return value if isinstance(value, dict) else {}

    def _policy_item_score(
        self,
        item: Dict[str, Any],
        role: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.policy_engine:
            return {"score": 0.0, "veto": False}
        score = self.policy_engine.score_item(item, role, user_goal, constraints)
        return {"score": score.score, "veto": score.veto}

    def _policy_chain_score(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Optional[Dict[str, Any]],
        tail: Optional[Dict[str, Any]],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        planning_order: str,
    ) -> float:
        if not self.policy_engine:
            return 0.0
        return self.policy_engine.chain_score(activity, restaurant, tail, user_goal, constraints, planning_order)

    def _is_family_unsafe_activity(self, item: Dict[str, Any], semantic_tags: Optional[set[str]] = None) -> bool:
        tags = semantic_tags or self._semantic_tags(item)
        name = str(item.get("name") or "")
        if item.get("category") != "activity":
            return False
        if tags & {"low_fit_activity", "alcohol", "light_drink"}:
            return True
        return any(word in name for word in ("棋牌", "KTV", "电竞", "网咖", "台球", "健身", "游泳", "PS5", "VR", "剧本杀", "桌游", "酒馆", "酒吧", "精酿"))

    def _is_non_dinner_place(self, item: Dict[str, Any]) -> bool:
        name = str(item.get("name") or "")
        tags = self._semantic_tags(item)
        return any(word in name for word in NON_DINNER_NAME_WORDS) or bool(tags & {"coffee", "dessert", "quiet_stay"} and not tags & {"proper_dining", "slow_dining", "light_meal"})

    def _looks_like_hands_on_experience(self, item: Dict[str, Any]) -> bool:
        name = str(item.get("name") or "")
        category = str(item.get("category") or "")
        if any(word in name for word in HANDMADE_FOOD_FALSE_POSITIVE_WORDS):
            return False
        if category == "restaurant" and "DIY" not in name and "diy" not in name and "烘焙DIY" not in name:
            if any(word in name for word in ("粉", "面", "酸奶", "小吃", "馄饨", "水饺", "包子")):
                return False
        return any(word in name for word in HANDS_ON_NAME_WORDS)

    def _decorate_selected(self, selected: Dict[str, Optional[Dict[str, Any]]], scenario: Optional[str] = None) -> Dict[str, Optional[Dict[str, Any]]]:
        decorated: Dict[str, Optional[Dict[str, Any]]] = {}
        priority = [
            "alcohol",
            "light_drink",
            "music",
            "acoustic_music",
            "esports",
            "karaoke",
            "board_game",
            "group_ok",
            "indoor",
            "buffet",
            "hotpot",
            "crayfish",
            "cuisine_japanese",
            "sushi",
            "izakaya",
            "bbq",
            "grill",
            "western_cuisine",
            "steak",
            "lamb",
            "healthy_light",
            "light_meal",
            "light_food",
            "hands_on",
            "craft",
            "coffee",
            "dessert",
            "date_friendly",
            "quality_dining",
            "ambience_dining",
            "proper_dining",
            "visitor_friendly",
            "showcase_local",
            "private_cinema",
            "theater",
            "lounge",
        ]
        family_tags = {"child_friendly", "kid_safe", "family_time", "family_friendly", "family_parent_child"}
        hidden_display_tags = {"gaode_poi", "has_photo", "has_tel", "leisure", "movie"}
        if scenario == "family_parent_child":
            priority.extend(["child_friendly", "kid_safe", "family_time"])
        for role, poi in selected.items():
            if not poi:
                decorated[role] = None
                continue
            enriched = dict(poi)
            existing = [str(tag) for tag in poi.get("tags", []) if str(tag) not in hidden_display_tags]
            semantic = self._semantic_tags(poi)
            if scenario != "family_parent_child":
                semantic -= family_tags
                existing = [tag for tag in existing if tag not in family_tags]
            if scenario != "friend_group":
                semantic -= {"group_ok"}
                existing = [tag for tag in existing if tag != "group_ok"]
            if scenario in {"friend_group", "fallback_unknown"}:
                semantic -= {"visitor_friendly", "showcase_local", "date_friendly"}
                existing = [tag for tag in existing if tag not in {"visitor_friendly", "showcase_local", "date_friendly"}]
            front = [tag for tag in priority if tag in semantic and tag not in existing]
            enriched["tags"] = [*front, *existing]
            decorated[role] = enriched
        return decorated

    def _merge_unique(self, primary: list[Dict[str, Any]], secondary: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        seen = set()
        merged = []
        for item in [*primary, *secondary]:
            poi_id = item.get("poi_id")
            if poi_id in seen:
                continue
            seen.add(poi_id)
            merged.append(item)
        return merged

    def _chain_price(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Optional[Dict[str, Any]],
        tail: Optional[Dict[str, Any]] = None,
    ) -> float:
        return (
            float((activity or {}).get("price_per_person") or 0)
            + float((restaurant or {}).get("price_per_person") or 0)
            + float((tail or {}).get("price_per_person") or 0)
        )

    def _status_snapshots(
        self,
        trace_id: str,
        selected: Dict[str, Optional[Dict[str, Any]]],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        snapshots = {}
        party_size = int(constraints.get("party_size") or 1)
        for role, poi in selected.items():
            if not poi:
                continue
            if poi.get("category") == "restaurant":
                snapshots[role] = self.mock_api_service.restaurant_status(
                    trace_id,
                    poi["poi_id"],
                    arrival_time=time_window["start_time"],
                    party_size=party_size,
                )
            else:
                snapshots[role] = self.mock_api_service.poi_status(trace_id, poi["poi_id"], party_size=party_size)
        return snapshots

    def _route_snapshots(
        self,
        trace_id: str,
        selected: Dict[str, Optional[Dict[str, Any]]],
        time_window: Dict[str, Any],
        planning_order: str = "activity_first",
        itinerary_nodes: Optional[list[Dict[str, Any]]] = None,
    ) -> list[Dict[str, Any]]:
        tail = selected.get("tail")
        restaurant = selected.get("restaurant")
        service_tail = self._is_service_poi(tail)
        if itinerary_nodes:
            itinerary_pois = [node.get("poi") for node in itinerary_nodes if node.get("poi") and not self._is_service_poi(node.get("poi"))]
            pairs = list(zip(itinerary_pois, itinerary_pois[1:]))
        elif planning_order == "restaurant_first":
            pairs = [
                (restaurant, selected.get("activity")),
            ]
            if not service_tail:
                pairs.append((selected.get("activity"), tail))
        elif planning_order == "dinner_last":
            if service_tail and restaurant:
                pairs = [(selected.get("activity"), restaurant)]
            else:
                pairs = [
                    (selected.get("activity"), tail or restaurant),
                    (tail, restaurant),
                ]
        else:
            if restaurant:
                pairs = [
                    (selected.get("activity"), restaurant),
                ]
                if not service_tail:
                    pairs.append((restaurant, tail))
            else:
                pairs = [] if service_tail else [(selected.get("activity"), tail)]
        routes = []
        for origin, destination in pairs:
            route = self._estimate_first_available_route(trace_id, origin, destination, time_window["start_time"])
            if route:
                routes.append(route)
        return routes

    def _is_service_poi(self, poi: Optional[Dict[str, Any]]) -> bool:
        return bool(poi and poi.get("category") == "service")

    def _estimate_first_available_route(
        self,
        trace_id: str,
        origin: Optional[Dict[str, Any]],
        destination: Optional[Dict[str, Any]],
        departure_time: str,
    ) -> Optional[Dict[str, Any]]:
        if not origin or not destination:
            return None
        for mode in ("walk", "taxi", "bike", "drive", "mixed", "subway"):
            if not self._has_route(self._route_rows(), origin["poi_id"], destination["poi_id"], mode):
                continue
            return self.mock_api_service.estimate_route(
                trace_id,
                origin_poi_id=origin["poi_id"],
                destination_poi_id=destination["poi_id"],
                transport_mode=mode,
                departure_time=departure_time,
            )
        return None

    def _weather(
        self,
        trace_id: str,
        selected: Dict[str, Optional[Dict[str, Any]]],
        time_window: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        tail = selected.get("tail")
        area = tail.get("area") if tail else None
        if not area:
            return None
        return self.mock_api_service.weather(
            trace_id,
            area=area,
            start_time=time_window["start_time"],
            end_time=time_window["end_time"],
        )

    def _route_rows(self) -> list[Dict[str, Any]]:
        return self.mock_api_service.store.read(MOCK_ROUTES_PATH, {"routes": []}).get("routes", [])

    def _has_route(self, rows: Iterable[Dict[str, Any]], origin: str, destination: str, mode: Optional[str] = None) -> bool:
        if any(
            row.get("origin_poi_id") == origin
            and row.get("destination_poi_id") == destination
            and (mode is None or row.get("transport_mode") == mode)
            for row in rows
        ):
            return True
        origin_poi = self._poi_by_id(origin)
        destination_poi = self._poi_by_id(destination)
        return self._distance_km(origin_poi, destination_poi) is not None

    def _poi_by_id(self, poi_id: str) -> Optional[Dict[str, Any]]:
        return next((poi for poi in self.mock_api_service.store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", []) if poi.get("poi_id") == poi_id), None)

    def _distance_km(self, origin: Optional[Dict[str, Any]], destination: Optional[Dict[str, Any]]) -> Optional[float]:
        if not origin or not destination:
            return None
        origin_loc = origin.get("location") or {}
        destination_loc = destination.get("location") or {}
        try:
            lat1 = math.radians(float(origin_loc["lat"]))
            lng1 = math.radians(float(origin_loc["lng"]))
            lat2 = math.radians(float(destination_loc["lat"]))
            lng2 = math.radians(float(destination_loc["lng"]))
        except (KeyError, TypeError, ValueError):
            return None
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
