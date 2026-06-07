from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from app.core.data_paths import RECOMMENDATION_POLICY_PATH
from app.rules.recommendation_taxonomy import get_tag_keywords


HANDMADE_FOOD_FALSE_POSITIVE_WORDS = ("手工粉", "手工面", "手擀面", "手工水饺", "手工饺", "手工馄饨", "手工米粉", "手作酸奶")


DEFAULT_RECOMMENDATION_POLICY: Dict[str, Any] = {
    "version": "2026-05-23",
    "story": "LifePilot recommendation policy: controlled semantic lexicon, scenario fit, hard constraints, route fit and ranking score components.",
    "lexicon": {
        "alcohol": list(get_tag_keywords("alcohol")),
        "light_drink": list(get_tag_keywords("light_drink")),
        "music": list(get_tag_keywords("music")),
        "hands_on": ["DIY", "diy", "手作", "手工", "陶艺", "拼豆", "油画", "烘焙DIY"],
        "craft": ["DIY", "diy", "手作", "手工", "陶艺", "拼豆", "油画", "烘焙DIY"],
        "karaoke": list(get_tag_keywords("karaoke")),
        "buffet": list(get_tag_keywords("buffet")),
        "hotpot": list(get_tag_keywords("hotpot")),
        "cuisine_japanese": list(get_tag_keywords("cuisine_japanese")),
        "sushi": list(get_tag_keywords("sushi")),
        "izakaya": list(get_tag_keywords("izakaya")),
        "bbq": ["烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉"],
        "grill": ["烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉"],
        "western_cuisine": list(get_tag_keywords("western_cuisine")),
        "steak": list(get_tag_keywords("steak")),
        "lamb": list(get_tag_keywords("lamb")),
        "healthy_light": list(get_tag_keywords("healthy_light")),
        "light_meal": ["粥", "蒸", "汤", "面馆", "手擀面", "牛肉面", "日式", "料理", "寿司", "鱼", "椰子鸡", "轻食", "沙拉", "健康"],
        "quality_dining": ["湖畔", "临湖", "西餐", "料理", "日式", "会席", "茶空间", "小馆", "CANTEEN", "Modern", "希尔顿", "皇冠", "鮨", "融合料理"],
        "ambience_dining": ["湖畔", "临湖", "西餐", "料理", "日式", "会席", "茶空间", "小馆", "CANTEEN", "Modern", "希尔顿", "皇冠", "鮨", "融合料理"],
        "proper_dining": ["餐厅", "料理", "火锅", "烤肉", "烧肉", "烧烤", "小馆", "CANTEEN", "饭店", "酒楼"],
        "child_friendly": list(get_tag_keywords("child_friendly")),
        "kid_safe": list(get_tag_keywords("kid_safe")),
        "low_fit_activity": list(get_tag_keywords("low_fit_activity")),
        "low_end_chain": list(get_tag_keywords("low_end_chain")),
        "coffee": ["咖啡", "Coffee", "COFFEE", "M Stand", "Manner", "星巴克", "瑞幸", "库迪"],
        "dessert": ["甜品", "蛋糕", "面包", "泡芙", "酸奶", "奶吧", "鲜奶", "牛奶", "奶茶"],
        "lake": ["湖畔", "金沙湖", "公园", "茶空间", "沙滩"],
        "showcase_local": ["金沙湖", "湖畔", "公园", "剧院", "茶空间", "下沙"],
    },
    "tag_implications": {
        "cuisine_japanese": ["proper_dining", "slow_dining", "dinner", "date_friendly"],
        "sushi": ["cuisine_japanese", "proper_dining", "slow_dining", "dinner"],
        "izakaya": ["cuisine_japanese", "proper_dining", "slow_dining", "dinner"],
        "buffet": ["proper_dining", "slow_dining", "dinner"],
        "bbq": ["grill", "proper_dining", "slow_dining", "dinner"],
        "grill": ["bbq", "proper_dining", "slow_dining", "dinner"],
        "western_cuisine": ["proper_dining", "slow_dining", "dinner", "date_friendly"],
        "steak": ["western_cuisine", "proper_dining", "slow_dining", "dinner"],
        "lamb": ["proper_dining", "dinner"],
        "healthy_light": ["light_meal", "light_food"],
        "hotpot": ["proper_dining", "slow_dining", "dinner"],
        "hands_on": ["craft", "date_friendly", "visitor_friendly", "indoor"],
        "craft": ["hands_on", "date_friendly", "visitor_friendly", "indoor"],
        "karaoke": ["group_ok", "indoor", "rain_safe"],
        "quality_dining": ["proper_dining", "slow_dining"],
        "ambience_dining": ["proper_dining", "slow_dining"],
        "child_friendly": ["kid_safe", "family_time"],
        "kid_safe": ["child_friendly", "family_time"],
    },
    "explicit_dining_anchors": {
        "buffet": {
            "required_any": ["buffet"],
            "boost_tags": ["buffet", "proper_dining", "dinner"],
            "budget_pp": 240,
            "note": "用户明说自助餐，餐厅槽位必须命中自助餐/放题语义。",
        },
        "hotpot": {
            "required_any": ["hotpot"],
            "boost_tags": ["hotpot", "proper_dining", "dinner"],
            "budget_pp": 160,
            "note": "用户明说火锅，餐厅槽位必须命中火锅语义。",
        },
        "cuisine_japanese": {
            "required_any": ["cuisine_japanese", "sushi", "izakaya"],
            "boost_tags": ["cuisine_japanese", "sushi", "izakaya", "proper_dining", "dinner"],
            "budget_pp": 220,
            "note": "用户明说日料/日本料理，餐厅槽位必须命中日料语义。",
        },
        "sushi": {
            "required_any": ["cuisine_japanese", "sushi"],
            "boost_tags": ["cuisine_japanese", "sushi", "proper_dining", "dinner"],
            "budget_pp": 220,
            "note": "用户明说寿司，餐厅槽位必须命中日料或寿司语义。",
        },
        "izakaya": {
            "required_any": ["cuisine_japanese", "izakaya"],
            "boost_tags": ["cuisine_japanese", "izakaya", "proper_dining", "dinner"],
            "budget_pp": 220,
            "note": "用户明说居酒屋/烧鸟，餐厅槽位必须命中日料小馆语义。",
        },
        "bbq": {
            "required_any": ["bbq", "grill"],
            "boost_tags": ["bbq", "grill", "proper_dining", "dinner"],
            "budget_pp": 180,
            "note": "用户明说烤肉/烧烤，餐厅槽位必须命中烤肉语义。",
        },
        "grill": {
            "required_any": ["bbq", "grill"],
            "boost_tags": ["bbq", "grill", "proper_dining", "dinner"],
            "budget_pp": 180,
            "note": "用户明说烤肉/烧烤，餐厅槽位必须命中烤肉语义。",
        },
    },
    "scenario_profiles": {
        "anniversary_emotion": {
            "desired_tags": ["date_friendly", "low_key", "thoughtful", "quiet_dining", "route_simple", "ambience_dining"],
            "avoid_tags": ["low_fit_activity", "fast_food", "low_end_chain"],
            "role_positive": {
                "activity": ["hands_on", "craft", "date_friendly", "quiet_stay", "lake", "theater"],
                "restaurant": ["proper_dining", "quality_dining", "ambience_dining", "buffet", "hotpot", "cuisine_japanese", "sushi", "izakaya", "bbq", "grill", "western_cuisine", "steak", "lamb", "light_meal", "healthy_light"],
                "tail": ["coffee", "dessert", "lake", "quiet_stay"],
            },
        },
        "family_parent_child": {
            "desired_tags": ["child_friendly", "kid_safe", "family_time", "low_queue", "light_meal"],
            "avoid_tags": ["low_fit_activity", "alcohol", "light_drink", "spicy_heavy"],
            "role_positive": {
                "activity": ["child_friendly", "kid_safe", "hands_on", "craft", "amusement"],
                "restaurant": ["buffet", "light_meal", "light_food", "family_friendly"],
                "tail": ["child_friendly", "kid_safe", "lake", "park", "quiet_stay"],
            },
        },
        "friend_group": {
            "desired_tags": ["friend_group", "group_ok", "budget_sensitive", "relaxed", "low_queue"],
            "avoid_tags": ["high_pressure", "long_queue"],
            "role_positive": {
                "activity": ["karaoke", "board_game", "group_ok", "indoor", "mall_walk"],
                "restaurant": ["buffet", "bbq", "grill", "proper_dining"],
                "tail": ["coffee", "dessert", "quiet_stay"],
            },
        },
        "city_light_explore": {
            "desired_tags": ["visitor_friendly", "host_guest", "showcase_local", "conversation", "route_simple", "quality_dining"],
            "avoid_tags": ["low_fit_activity", "low_end_chain", "fast_food"],
            "role_positive": {
                "activity": ["visitor_friendly", "showcase_local", "lake", "theater", "hands_on", "craft"],
                "restaurant": ["quality_dining", "proper_dining", "ambience_dining", "lake"],
                "tail": ["lake", "park", "coffee", "dessert", "quiet_stay"],
            },
        },
        "fallback_unknown": {
            "desired_tags": ["alone", "mood_relief", "quiet", "low_pressure", "light_walk", "nearby"],
            "avoid_tags": ["low_fit_activity", "strong_social", "high_pressure"],
            "role_positive": {
                "activity": ["quiet_stay", "lake", "park", "music", "acoustic_music"],
                "restaurant": ["alcohol", "light_drink", "coffee", "quiet_stay"],
                "tail": ["lake", "park", "quiet_stay", "music"],
            },
        },
    },
}


@dataclass(frozen=True)
class RecommendationScore:
    score: float
    veto: bool
    semantic_tags: set[str]
    components: Dict[str, float]
    reasons: list[str]


class RecommendationPolicyEngine:
    """Internal, swappable scoring layer for POI recommendation.

    The policy is deliberately stored outside code in recommendation_policy.json when available.
    This lets rules be added or removed without changing PlanContract or public APIs.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self._policy: Optional[Dict[str, Any]] = None

    @property
    def policy(self) -> Dict[str, Any]:
        if self._policy is None:
            loaded = self.store.read(RECOMMENDATION_POLICY_PATH, DEFAULT_RECOMMENDATION_POLICY)
            self._policy = self._with_defaults(loaded)
        return self._policy

    def semantic_tags(self, item: Dict[str, Any]) -> set[str]:
        tags = {str(tag) for tag in item.get("tags", [])}
        tags.update(str(tag) for tag in item.get("suitable_scenarios", []))
        haystack = " ".join(
            str(value or "")
            for value in (
                item.get("name"),
                item.get("sub_category"),
                item.get("address"),
                item.get("area"),
            )
        )
        name_haystack = " ".join(str(value or "") for value in (item.get("name"), item.get("sub_category")))
        for tag, patterns in (self.policy.get("lexicon") or {}).items():
            target_haystack = name_haystack if tag in {"music", "karaoke"} else haystack
            if tag in {"hands_on", "craft"} and self._looks_like_handmade_food(item):
                continue
            if self._matches_any(target_haystack, patterns):
                tags.add(str(tag))
        self._apply_implications(tags)
        return tags

    def explicit_dining_anchor(self, constraints: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        markers = set(str(item) for item in constraints.get("must_have") or [])
        anchors = self.policy.get("explicit_dining_anchors") or {}
        for marker, anchor in anchors.items():
            if str(marker) in markers:
                return anchor
        return None

    def explicit_dining_required_tags(self, constraints: Dict[str, Any]) -> set[str]:
        anchor = self.explicit_dining_anchor(constraints)
        return set(str(tag) for tag in (anchor or {}).get("required_any") or [])

    def score_item(
        self,
        item: Optional[Dict[str, Any]],
        role: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> RecommendationScore:
        if not item:
            return RecommendationScore(-9999, True, set(), {}, ["missing_item"])

        tags = self.semantic_tags(item)
        scenario = str(user_goal.get("scenario") or "fallback_unknown")
        profile = (self.policy.get("scenario_profiles") or {}).get(scenario, {})
        desired = set(str(tag) for tag in profile.get("desired_tags") or [])
        desired.update(str(tag) for tag in user_goal.get("intent_tags") or [])
        desired.update(str(tag) for tag in (constraints.get("recommendation_profile") or {}).get("normalized_tags") or [])
        desired.update(str(tag) for tag in constraints.get("activity_preference") or [])

        avoid = set(str(tag) for tag in profile.get("avoid_tags") or [])
        avoid.update(str(tag) for tag in constraints.get("must_not_have") or [])
        anchor = self.explicit_dining_anchor(constraints)
        required = set(str(tag) for tag in (anchor or {}).get("required_any") or [])
        anchor_boost_tags = set(str(tag) for tag in (anchor or {}).get("boost_tags") or [])

        components: Dict[str, float] = {
            "semantic_match": float(len(tags & desired) * 7),
            "constraint_penalty": -float(len(tags & avoid) * 18),
            "role_affinity": 0.0,
            "explicit_anchor": 0.0,
            "rating_prior": float(item.get("rating") or 4.2) * 1.2,
        }
        reasons: list[str] = []
        role_positive = ((profile.get("role_positive") or {}).get(role) or [])
        role_hits = tags & set(str(tag) for tag in role_positive)
        components["role_affinity"] = float(len(role_hits) * 16)
        if role_hits:
            reasons.append("role_affinity")

        if role == "restaurant" and required:
            if not tags & required:
                return RecommendationScore(-9999, True, tags, components, ["explicit_dining_anchor_miss"])
            components["explicit_anchor"] = 95.0 + float(len(tags & anchor_boost_tags) * 10)
            reasons.append(str((anchor or {}).get("note") or "explicit_dining_anchor"))

        total = sum(components.values())
        return RecommendationScore(total, False, tags, components, reasons)

    def chain_score(
        self,
        activity: Optional[Dict[str, Any]],
        restaurant: Optional[Dict[str, Any]],
        tail: Optional[Dict[str, Any]],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        planning_order: str,
    ) -> float:
        score = 0.0
        selected = [item for item in (activity, restaurant, tail) if item]
        ids = [str(item.get("poi_id")) for item in selected]
        if len(ids) != len(set(ids)):
            score -= 500

        scenario = str(user_goal.get("scenario") or "")
        restaurant_tags = self.semantic_tags(restaurant or {}) if restaurant else set()
        activity_tags = self.semantic_tags(activity or {}) if activity else set()
        tail_tags = self.semantic_tags(tail or {}) if tail else set()
        if self.explicit_dining_anchor(constraints) and planning_order == "dinner_last" and restaurant_tags:
            score += 32
        if scenario == "anniversary_emotion":
            if activity_tags & {"hands_on", "craft", "theater", "lake"} and restaurant_tags & {"proper_dining", "quality_dining", "ambience_dining", "hotpot", "cuisine_japanese", "sushi", "izakaya", "bbq", "grill", "western_cuisine", "steak", "lamb", "light_meal", "healthy_light"}:
                score += 26
            if tail_tags & {"coffee", "dessert", "lake", "quiet_stay"}:
                score += 10
        if scenario == "family_parent_child" and activity_tags & {"child_friendly", "kid_safe"} and restaurant_tags & {"light_meal", "light_food", "family_friendly"}:
            score += 26
        return score

    def _apply_implications(self, tags: set[str]) -> None:
        changed = True
        implications = self.policy.get("tag_implications") or {}
        while changed:
            changed = False
            for tag, implied in implications.items():
                if tag not in tags:
                    continue
                for value in implied or []:
                    value = str(value)
                    if value not in tags:
                        tags.add(value)
                        changed = True

    def _with_defaults(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        policy = dict(DEFAULT_RECOMMENDATION_POLICY)
        for key, value in (loaded or {}).items():
            if isinstance(value, dict) and isinstance(policy.get(key), dict):
                merged = dict(policy[key])
                merged.update(value)
                policy[key] = merged
            else:
                policy[key] = value
        return policy

    def _matches_any(self, haystack: str, patterns: Iterable[Any]) -> bool:
        return any(str(pattern) and str(pattern) in haystack for pattern in patterns or [])

    def _looks_like_handmade_food(self, item: Dict[str, Any]) -> bool:
        name = str(item.get("name") or "")
        category = str(item.get("category") or "")
        if any(word in name for word in HANDMADE_FOOD_FALSE_POSITIVE_WORDS):
            return True
        return category == "restaurant" and "DIY" not in name and "diy" not in name and any(
            word in name for word in ("粉", "面", "酸奶", "小吃", "馄饨", "水饺", "包子")
        )
