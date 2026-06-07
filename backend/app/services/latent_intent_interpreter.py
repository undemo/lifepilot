from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.schemas.internal_intelligence import (
    CANONICAL_TAG_VALUES,
    CanonicalTag,
    CanonicalTagSet,
    InternalIntelligenceValidationError,
    LatentIntent,
)


TagEvidence = Tuple[CanonicalTag, str, float]


LEGACY_TAG_MAP: Dict[str, List[TagEvidence]] = {
    "family_parent_child": [
        (CanonicalTag.FAMILY_OUTING, "旧场景标签 family_parent_child", 0.9),
        (CanonicalTag.WITH_CHILD, "旧场景标签 family_parent_child", 0.9),
        (CanonicalTag.CHILD_FOOD_REQUIRED, "亲子场景需要儿童可食选项", 0.7),
        (CanonicalTag.RESTROOM_REQUIRED, "亲子场景需要厕所配套", 0.65),
        (CanonicalTag.REST_AREA_REQUIRED, "亲子场景需要休息点", 0.65),
    ],
    "anniversary_emotion": [
        (CanonicalTag.WITH_COUPLE, "旧场景标签 anniversary_emotion", 0.85),
        (CanonicalTag.ANNIVERSARY, "旧场景标签 anniversary_emotion", 0.9),
        (CanonicalTag.CEREMONIAL, "纪念日场景需要仪式感", 0.8),
        (CanonicalTag.ROMANTIC, "纪念日场景偏情侣体验", 0.75),
        (CanonicalTag.FLOWER_SUGGESTED, "纪念日场景建议鲜花配套", 0.65),
        (CanonicalTag.PHOTO_SPOT_REQUIRED, "纪念日场景适合拍照点", 0.65),
    ],
    "friend_group": [(CanonicalTag.WITH_FRIENDS, "旧场景标签 friend_group", 0.85)],
    "city_light_explore": [
        (CanonicalTag.SCENIC, "旧场景标签 city_light_explore", 0.75),
        (CanonicalTag.LOCAL_FOOD_REQUIRED, "城市体验场景需要本地美食", 0.65),
    ],
    "fallback_unknown": [],
    "child_friendly": [(CanonicalTag.WITH_CHILD, "旧标签 child_friendly", 0.75)],
    "family_time": [(CanonicalTag.FAMILY_OUTING, "旧标签 family_time", 0.75)],
    "kid_safe": [(CanonicalTag.WITH_CHILD, "旧标签 kid_safe", 0.7)],
    "low_queue": [
        (CanonicalTag.AVOID_LONG_QUEUE, "旧标签 low_queue", 0.8),
        (CanonicalTag.RESERVATION_SUGGESTED, "低排队偏好建议预约", 0.65),
    ],
    "nearby": [(CanonicalTag.NEARBY_REQUIRED, "旧标签 nearby", 0.8)],
    "route_simple": [(CanonicalTag.LOW_TRANSFER_REQUIRED, "旧标签 route_simple", 0.75)],
    "relaxed": [(CanonicalTag.RELAXED_PACE, "旧标签 relaxed", 0.75)],
    "low_pressure": [(CanonicalTag.RELAXED_PACE, "旧标签 low_pressure", 0.7)],
    "light_walk": [(CanonicalTag.WALKING_FRIENDLY, "旧标签 light_walk", 0.7)],
    "quiet": [(CanonicalTag.AVOID_NOISY_PLACE, "旧标签 quiet", 0.75)],
    "mood_relief": [
        (CanonicalTag.STRESS_RELIEF, "旧标签 mood_relief", 0.7),
        (CanonicalTag.HEALING, "旧标签 mood_relief", 0.7),
    ],
    "dinner": [
        (CanonicalTag.DINNER_REQUIRED, "旧标签 dinner", 0.85),
        (CanonicalTag.MEAL_REQUIRED, "晚餐需要餐饮 slot", 0.75),
    ],
    "proper_dining": [(CanonicalTag.MEAL_REQUIRED, "旧标签 proper_dining", 0.7)],
    "light_food": [(CanonicalTag.LIGHT_MEAL_REQUIRED, "旧标签 light_food", 0.8)],
    "light_meal": [
        (CanonicalTag.LIGHT_MEAL_REQUIRED, "旧标签 light_meal", 0.85),
        (CanonicalTag.LOW_CALORIE_REQUIRED, "轻食通常对应低负担餐饮", 0.65),
    ],
    "healthy_light": [(CanonicalTag.LOW_CALORIE_REQUIRED, "旧标签 healthy_light", 0.8)],
    "hotpot": [
        (CanonicalTag.HOTPOT_REQUIRED, "旧标签 hotpot", 0.9),
        (CanonicalTag.MEAL_REQUIRED, "火锅需要餐饮 slot", 0.75),
    ],
    "bbq": [
        (CanonicalTag.BBQ_REQUIRED, "旧标签 bbq", 0.9),
        (CanonicalTag.MEAL_REQUIRED, "烧烤需要餐饮 slot", 0.75),
    ],
    "grill": [
        (CanonicalTag.BBQ_REQUIRED, "旧标签 grill", 0.8),
        (CanonicalTag.MEAL_REQUIRED, "烤物需要餐饮 slot", 0.7),
    ],
    "coffee": [(CanonicalTag.COFFEE_REQUIRED, "旧标签 coffee", 0.85)],
    "dessert": [(CanonicalTag.DESSERT_REQUIRED, "旧标签 dessert", 0.8)],
    "date_friendly": [(CanonicalTag.WITH_COUPLE, "旧标签 date_friendly", 0.8)],
    "romantic": [(CanonicalTag.ROMANTIC, "旧标签 romantic", 0.8)],
    "photo_spot": [(CanonicalTag.PHOTO_SPOT_REQUIRED, "旧标签 photo_spot", 0.75)],
    "beautiful_dining": [(CanonicalTag.PREMIUM_EXPERIENCE, "旧标签 beautiful_dining", 0.65)],
    "quality_dining": [(CanonicalTag.PREMIUM_EXPERIENCE, "旧标签 quality_dining", 0.65)],
    "ambience_dining": [(CanonicalTag.CEREMONIAL, "旧标签 ambience_dining", 0.65)],
    "sibling": [(CanonicalTag.WITH_SIBLING, "旧标签 sibling", 0.85)],
    "visiting_family": [(CanonicalTag.WITH_SIBLING, "旧标签 visiting_family", 0.6)],
    "showcase_local": [
        (CanonicalTag.SCENIC, "旧标签 showcase_local", 0.75),
        (CanonicalTag.LOCAL_FOOD_REQUIRED, "展示城市体验时需要本地美食", 0.65),
    ],
    "amusement": [(CanonicalTag.FAMILY_OUTING, "旧标签 amusement", 0.65)],
}


class LatentIntentInterpreter:
    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm_client = llm_client

    def interpret(
        self,
        *,
        raw_user_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        recommendation_profile: Optional[Dict[str, Any]] = None,
        dining_preference: Optional[Dict[str, Any]] = None,
    ) -> LatentIntent:
        recommendation_profile = recommendation_profile or constraints.get("recommendation_profile") or {}
        dining_preference = dining_preference or constraints.get("dining_preference") or {}
        source_tags = self._collect_source_tags(user_goal, constraints, recommendation_profile, dining_preference)
        tag_set, notes = self._rule_tag_set(raw_user_text, user_goal, constraints, recommendation_profile, dining_preference, source_tags)
        latent = self._fallback_latent_intent(raw_user_text, tag_set, notes)

        if self.llm_client is not None and self._should_call_llm(tag_set):
            latent = self._try_llm_supplement(raw_user_text, user_goal, constraints, tag_set, latent)
        return latent

    def _rule_tag_set(
        self,
        raw_user_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        recommendation_profile: Dict[str, Any],
        dining_preference: Dict[str, Any],
        source_tags: List[str],
    ) -> tuple[CanonicalTagSet, Dict[str, List[str]]]:
        collector = _TagCollector(source_tags)
        text = raw_user_text or ""
        scenario = str(user_goal.get("scenario") or "")
        if scenario:
            self._add_legacy_tags(collector, [scenario])
        self._add_legacy_tags(collector, source_tags)
        self._apply_text_rules(collector, text)
        self._apply_constraint_rules(collector, constraints)
        self._apply_dining_rules(collector, dining_preference)
        self._apply_derived_rules(collector)
        return collector.to_tag_set(), collector.notes

    def _add_legacy_tags(self, collector: "_TagCollector", tags: Iterable[str]) -> None:
        for raw_tag in tags:
            tag = str(raw_tag or "").strip()
            normalized = tag.lower().replace("-", "_").replace(" ", "_")
            for canonical_tag, evidence, confidence in LEGACY_TAG_MAP.get(normalized, []):
                collector.add(canonical_tag, evidence, confidence)

    def _apply_text_rules(self, collector: "_TagCollector", text: str) -> None:
        if not text:
            return
        if re.search(r"(孩子|小孩|儿童|亲子|宝宝)", text):
            collector.add(CanonicalTag.WITH_CHILD, "用户提到孩子/儿童", 0.92)
            collector.add(CanonicalTag.FAMILY_OUTING, "用户提到亲子出行", 0.85)
            collector.add(CanonicalTag.CHILD_FOOD_REQUIRED, "带孩子需要儿童可食选项", 0.75)
            collector.add(CanonicalTag.RESTROOM_REQUIRED, "带孩子需要厕所配套", 0.7)
            collector.add(CanonicalTag.REST_AREA_REQUIRED, "带孩子需要休息点", 0.7)
        if re.search(r"([0-6])\s*岁", text):
            collector.add(CanonicalTag.CHILD_AGE_PRESCHOOL, "用户提到学龄前儿童年龄", 0.95)
        if re.search(r"([7-9]|1[0-2])\s*岁", text):
            collector.add(CanonicalTag.CHILD_AGE_PRIMARY, "用户提到小学年龄段儿童", 0.8)
        if any(token in text for token in ("老婆", "女朋友", "对象", "约会", "情侣")):
            collector.add(CanonicalTag.WITH_COUPLE, "用户提到伴侣/约会对象", 0.85)
        if any(token in text for token in ("约会", "情侣", "女朋友")):
            collector.add(CanonicalTag.ROMANTIC, "用户表达约会场景", 0.7)
        if any(token in text for token in ("纪念日", "周年", "生日", "仪式感")):
            collector.add(CanonicalTag.ANNIVERSARY, "用户提到纪念日/周年", 0.92)
            collector.add(CanonicalTag.CEREMONIAL, "用户需要仪式感", 0.85)
            collector.add(CanonicalTag.FLOWER_SUGGESTED, "纪念日建议鲜花配套", 0.7)
            collector.add(CanonicalTag.PHOTO_SPOT_REQUIRED, "纪念日适合安排拍照点", 0.7)
        if any(token in text for token in ("减脂", "低卡", "少油", "清淡", "轻食")):
            collector.add(CanonicalTag.LOW_CALORIE_REQUIRED, "用户提到减脂/低卡/清淡", 0.9)
            collector.add(CanonicalTag.LIGHT_MEAL_REQUIRED, "用户需要低负担餐饮", 0.85)
        if any(token in text for token in ("压力很大", "压力大", "散散心", "散心", "放松", "治愈", "缓一缓")):
            collector.add(CanonicalTag.STRESS_RELIEF, "用户表达压力释放需求", 0.9)
            collector.add(CanonicalTag.HEALING, "用户需要治愈/放松体验", 0.82)
            collector.add(CanonicalTag.RELAXED_PACE, "压力释放场景应降低节奏压力", 0.75)
            collector.add(CanonicalTag.AVOID_CROWD, "散心场景应规避拥挤", 0.7)
        if any(token in text for token in ("别太远", "不远", "附近", "近点", "就近", "不想走太远")):
            collector.add(CanonicalTag.NEARBY_REQUIRED, "用户要求距离近", 0.9)
            collector.add(CanonicalTag.LOW_TRANSFER_REQUIRED, "近距离需求隐含少转场", 0.72)
        if any(token in text for token in ("不排队", "不排长队", "别排队", "别等太久", "少排队")):
            collector.add(CanonicalTag.AVOID_LONG_QUEUE, "用户明确不想排队", 0.92)
            collector.add(CanonicalTag.RESERVATION_SUGGESTED, "不排队需求建议预约", 0.75)
        if "今天" in text:
            collector.add(CanonicalTag.TODAY, "用户提到今天", 0.8)
        if "周末" in text or "这周末" in text:
            collector.add(CanonicalTag.WEEKEND, "用户提到周末", 0.8)
        if "下午" in text:
            collector.add(CanonicalTag.AFTERNOON, "用户提到下午", 0.85)
        if any(token in text for token in ("晚上", "晚饭", "晚餐")):
            collector.add(CanonicalTag.EVENING, "用户提到晚上", 0.75)
        if any(token in text for token in ("晚饭", "晚餐", "晚上吃")):
            collector.add(CanonicalTag.DINNER_REQUIRED, "用户提到晚饭/晚餐", 0.9)
            collector.add(CanonicalTag.MEAL_REQUIRED, "晚饭需要餐饮 slot", 0.8)
        if any(token in text for token in ("午饭", "午餐", "中午吃")):
            collector.add(CanonicalTag.LUNCH_REQUIRED, "用户提到午饭/午餐", 0.85)
            collector.add(CanonicalTag.MEAL_REQUIRED, "午饭需要餐饮 slot", 0.75)
        if any(token in text for token in ("几个小时", "1小时", "一小时", "两小时", "2小时", "三小时", "3小时")):
            collector.add(CanonicalTag.SHORT_DURATION, "用户表达几个小时内完成", 0.85)
        if any(token in text for token in ("半天", "半日")):
            collector.add(CanonicalTag.HALF_DAY, "用户表达半天安排", 0.75)
        if any(token in text for token in ("一天", "整天", "一整天")):
            collector.add(CanonicalTag.FULL_DAY, "用户表达全天安排", 0.75)
        if any(token in text for token in ("小龙虾", "龙虾", "麻小", "虾尾")):
            collector.add(CanonicalTag.CRAYFISH_REQUIRED, "用户提到小龙虾", 0.95)
            collector.add(CanonicalTag.MEAL_REQUIRED, "小龙虾需要餐饮 slot", 0.8)
        if any(token in text for token in ("火锅", "涮锅")):
            collector.add(CanonicalTag.HOTPOT_REQUIRED, "用户提到火锅", 0.95)
            collector.add(CanonicalTag.MEAL_REQUIRED, "火锅需要餐饮 slot", 0.8)
        if any(token in text for token in ("烧烤", "烤串", "烤肉", "炭烤", "碳烤")):
            collector.add(CanonicalTag.BBQ_REQUIRED, "用户提到烧烤/炭烤", 0.9)
            collector.add(CanonicalTag.MEAL_REQUIRED, "烧烤需要餐饮 slot", 0.75)
        if "杭帮菜" in text or "本地菜" in text or "特色菜" in text or "美食" in text:
            collector.add(CanonicalTag.LOCAL_FOOD_REQUIRED, "用户提到本地美食/特色", 0.72)
            collector.add(CanonicalTag.FOOD_REQUIRED, "用户有美食体验需求", 0.65)
        if "奶茶" in text:
            collector.add(CanonicalTag.MILK_TEA_REQUIRED, "用户提到奶茶", 0.88)
            collector.add(CanonicalTag.DRINK_REQUIRED, "奶茶属于饮品需求", 0.8)
        if "咖啡" in text:
            collector.add(CanonicalTag.COFFEE_REQUIRED, "用户提到咖啡", 0.88)
            collector.add(CanonicalTag.DRINK_REQUIRED, "咖啡属于饮品需求", 0.8)
        if any(token in text for token in ("饮品", "喝点", "喝杯")):
            collector.add(CanonicalTag.DRINK_REQUIRED, "用户提到饮品", 0.75)
        if any(token in text for token in ("甜品", "蛋糕", "糖葫芦", "巴斯克")):
            collector.add(CanonicalTag.DESSERT_REQUIRED, "用户提到甜品", 0.78)
            collector.add(CanonicalTag.SNACK_REQUIRED, "甜品/小吃需求", 0.6)
        if any(token in text for token in ("羽毛球", "网球", "足球", "篮球", "乒乓球", "台球", "游泳", "运动", "打球", "健身", "攀岩", "瑜伽")):
            collector.add(CanonicalTag.SPORTS, "用户提到运动/球类/健身", 0.9)
            collector.add(CanonicalTag.DRINK_SUGGESTED, "运动后建议补水", 0.65)
        if any(token in text for token in ("美景", "景点", "西湖", "名胜", "风景", "公园", "逛逛")):
            collector.add(CanonicalTag.SCENIC, "用户提到美景/景点", 0.85)
            collector.add(CanonicalTag.PHOTO_SPOT_REQUIRED, "景点体验适合拍照点", 0.65)
        if any(token in text for token in ("朋友", "室友", "同学", "同事")):
            collector.add(CanonicalTag.WITH_FRIENDS, "用户提到朋友", 0.88)
        if any(token in text for token in ("姐姐", "妹妹", "哥哥", "弟弟", "我姐", "我妹", "我哥", "我弟")):
            collector.add(CanonicalTag.WITH_SIBLING, "用户提到兄弟姐妹", 0.88)
        if any(token in text for token in ("爷爷", "奶奶", "外公", "外婆", "老人", "长辈")):
            collector.add(CanonicalTag.WITH_ELDERLY, "用户提到长辈/老人", 0.9)
            collector.add(CanonicalTag.RELAXED_PACE, "长辈场景需要舒缓节奏", 0.72)
            collector.add(CanonicalTag.REST_AREA_REQUIRED, "长辈场景需要休息点", 0.7)

    def _apply_constraint_rules(self, collector: "_TagCollector", constraints: Dict[str, Any]) -> None:
        if constraints.get("child_friendly_required") is True:
            collector.add(CanonicalTag.WITH_CHILD, "约束中 child_friendly_required=true", 0.9)
            collector.add(CanonicalTag.CHILD_FOOD_REQUIRED, "亲子约束需要儿童可食选项", 0.75)
        if constraints.get("queue_tolerance") == "low":
            collector.add(CanonicalTag.AVOID_LONG_QUEUE, "约束中 queue_tolerance=low", 0.8)
            collector.add(CanonicalTag.RESERVATION_SUGGESTED, "低排队约束建议预约", 0.65)
        if constraints.get("distance_preference") == "nearby":
            collector.add(CanonicalTag.NEARBY_REQUIRED, "约束中 distance_preference=nearby", 0.8)
        if constraints.get("walking_tolerance") == "low":
            collector.add(CanonicalTag.AVOID_HIGH_WALKING_LOAD, "约束中 walking_tolerance=low", 0.75)
        dietary = set(str(item) for item in constraints.get("dietary_preference") or [])
        if dietary & {"low_calorie", "light_food", "healthy_light"}:
            collector.add(CanonicalTag.LOW_CALORIE_REQUIRED, "饮食约束包含低卡/轻食", 0.8)
            collector.add(CanonicalTag.LIGHT_MEAL_REQUIRED, "饮食约束包含低负担餐饮", 0.75)

    def _apply_dining_rules(self, collector: "_TagCollector", dining_preference: Dict[str, Any]) -> None:
        tags = set(str(tag) for tag in (dining_preference or {}).get("specific_tags") or [])
        tags.update(str(tag) for tag in (dining_preference or {}).get("normalized_tags") or [])
        self._add_legacy_tags(collector, tags)
        raw_terms = " ".join(str(term) for term in (dining_preference or {}).get("raw_terms") or [])
        if raw_terms:
            self._apply_text_rules(collector, raw_terms)

    def _apply_derived_rules(self, collector: "_TagCollector") -> None:
        tags = collector.tags
        risky_food = {CanonicalTag.CRAYFISH_REQUIRED, CanonicalTag.HOTPOT_REQUIRED, CanonicalTag.BBQ_REQUIRED}
        if CanonicalTag.WITH_CHILD in tags and tags & risky_food:
            collector.add(CanonicalTag.CHILD_FOOD_REQUIRED, "带孩子且餐饮偏重口，需要儿童可食备选", 0.78)
            collector.add(CanonicalTag.NON_SPICY_REQUIRED, "带孩子且餐饮可能偏辣，需要不辣选项", 0.72)
            collector.add(CanonicalTag.WET_TISSUE_SUGGESTED, "亲子重口餐饮建议湿巾", 0.6)
            collector.add(CanonicalTag.COOL_DRINK_SUGGESTED, "亲子重口餐饮建议解辣饮品", 0.6)
        if CanonicalTag.SPORTS in tags:
            collector.add(CanonicalTag.DRINK_SUGGESTED, "运动后建议补水", 0.65)
        if CanonicalTag.LOW_CALORIE_REQUIRED in tags:
            collector.add(CanonicalTag.LIGHT_MEAL_REQUIRED, "低卡需求应映射到轻食/低负担餐饮", 0.75)

    def _collect_source_tags(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        recommendation_profile: Dict[str, Any],
        dining_preference: Dict[str, Any],
    ) -> List[str]:
        source: List[str] = []
        source.extend(str(tag) for tag in user_goal.get("intent_tags") or [])
        source.extend(str(tag) for tag in constraints.get("must_have") or [])
        source.extend(str(tag) for tag in recommendation_profile.get("normalized_tags") or [])
        source.extend(str(tag) for tag in dining_preference.get("normalized_tags") or [])
        source.extend(str(tag) for tag in dining_preference.get("specific_tags") or [])
        return _dedupe(source)

    def _fallback_latent_intent(self, raw_user_text: str, tag_set: CanonicalTagSet, notes: Dict[str, List[str]]) -> LatentIntent:
        tags = {tag.value for tag in tag_set.canonical_tags}
        explicit_facts: List[str] = []
        latent_goals: List[str] = []
        hidden_constraints: List[str] = []
        success_definition: List[str] = []
        failure_cases: List[str] = []

        if "WITH_CHILD" in tags:
            latent_goals.append("亲子出行需要低强度、低排队和儿童可食选项")
            hidden_constraints.extend(["优先选择有厕所和休息点的地点", "避免高噪声、重辣且没有儿童可食选项的餐厅"])
            success_definition.append("孩子能参与且不明显疲惫，餐饮有不辣或儿童可食备选")
            failure_cases.extend(["排队过久导致孩子烦躁", "餐厅只有重辣或重油选项"])
        if "ANNIVERSARY" in tags:
            latent_goals.append("纪念日需要轻量仪式感和可拍照记忆点")
            hidden_constraints.append("避免过于随便、嘈杂或缺少氛围的安排")
            success_definition.append("伴侣能感受到用心且路线不过度折腾")
            failure_cases.append("推荐过于日常或嘈杂，削弱纪念日体验")
        if "STRESS_RELIEF" in tags:
            latent_goals.append("压力释放场景需要低刺激和低决策成本")
            hidden_constraints.append("避免高人流、高噪声和紧凑赶场")
            success_definition.append("用户能放松下来，路线简单且选择负担低")
            failure_cases.append("安排太吵、太赶或转场过多")
        if "LOW_CALORIE_REQUIRED" in tags:
            latent_goals.append("减脂需求需要低油低负担餐饮和饭后轻松活动")
            hidden_constraints.append("避免只给重油重辣且无清淡备选的餐厅")
        if "AVOID_LONG_QUEUE" in tags:
            hidden_constraints.append("优先可预约或低排队风险候选")
            failure_cases.append("热门候选排队时间过长")
        if "NEARBY_REQUIRED" in tags:
            hidden_constraints.append("控制单段路程和转场复杂度")
            failure_cases.append("单段路程过远或转场太多")
        if "SPORTS" in tags:
            latent_goals.append("运动场景需要合理场馆 slot 和运动后补水/餐饮配套")
        if "SCENIC" in tags:
            latent_goals.append("城市体验场景需要体现景观和本地特色")

        missing_fields = []
        if "NEARBY_REQUIRED" not in tags and not re.search(r"(附近|别太远|不远|就近)", raw_user_text or ""):
            missing_fields.append("area_or_distance_preference")
        if "DINNER_REQUIRED" not in tags and "LUNCH_REQUIRED" not in tags and "MEAL_REQUIRED" in tags:
            missing_fields.append("meal_time")

        return LatentIntent.fallback(
            explicit_facts=_dedupe(notes.get("explicit_facts", [])),
            latent_goals=_dedupe(latent_goals),
            hidden_constraints=_dedupe(hidden_constraints),
            success_definition=_dedupe(success_definition),
            failure_cases=_dedupe(failure_cases),
            canonical_tag_set=tag_set,
            clarification_policy={"ask_only_if_blocking": True},
            missing_fields=missing_fields,
        )

    def _should_call_llm(self, tag_set: CanonicalTagSet) -> bool:
        return len(tag_set.canonical_tags) < 2

    def _try_llm_supplement(
        self,
        raw_user_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        tag_set: CanonicalTagSet,
        fallback: LatentIntent,
    ) -> LatentIntent:
        try:
            payload = self.llm_client.generate_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=self._llm_user_prompt(raw_user_text, user_goal, constraints, tag_set),
                temperature=0.1,
                max_tokens=900,
            )
            return self._merge_llm_payload(payload, tag_set, fallback)
        except Exception:
            return fallback

    def _merge_llm_payload(self, payload: Dict[str, Any], base_tag_set: CanonicalTagSet, fallback: LatentIntent) -> LatentIntent:
        inferred_tags = _dedupe(str(tag) for tag in payload.get("inferred_tags") or [])
        invalid_tags = [tag for tag in inferred_tags if tag not in CANONICAL_TAG_VALUES]
        if invalid_tags:
            raise InternalIntelligenceValidationError(f"unknown inferred canonical tags: {invalid_tags}")
        canonical_values = _dedupe([tag.value for tag in base_tag_set.canonical_tags] + inferred_tags)
        confidence = dict(base_tag_set.confidence_by_tag)
        evidence = dict(base_tag_set.evidence_by_tag)
        for tag, value in (payload.get("confidence_by_tag") or {}).items():
            try:
                confidence[str(tag)] = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                continue
        for tag, value in (payload.get("evidence_by_tag") or {}).items():
            if str(tag) in CANONICAL_TAG_VALUES and str(value).strip():
                evidence[str(tag)] = str(value).strip()
        merged_tag_set = CanonicalTagSet.parse_payload(
            {
                "canonical_tags": canonical_values,
                "source_tags": base_tag_set.source_tags,
                "inferred_tags": inferred_tags,
                "confidence_by_tag": confidence,
                "evidence_by_tag": evidence,
            }
        )
        return LatentIntent.parse_payload(
            {
                "explicit_facts": _dedupe(fallback.explicit_facts + _list_strings(payload.get("explicit_facts"))),
                "latent_goals": _dedupe(fallback.latent_goals + _list_strings(payload.get("latent_goals"))),
                "hidden_constraints": _dedupe(fallback.hidden_constraints + _list_strings(payload.get("hidden_constraints"))),
                "success_definition": _dedupe(fallback.success_definition + _list_strings(payload.get("success_definition"))),
                "failure_cases": _dedupe(fallback.failure_cases + _list_strings(payload.get("failure_cases"))),
                "canonical_tag_set": merged_tag_set.to_dict(),
                "clarification_policy": payload.get("clarification_policy") if isinstance(payload.get("clarification_policy"), dict) else fallback.clarification_policy,
                "missing_fields": _dedupe(fallback.missing_fields + _list_strings(payload.get("missing_fields"))),
            }
        )

    def _llm_user_prompt(
        self,
        raw_user_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        tag_set: CanonicalTagSet,
    ) -> str:
        return (
            "用户原文：\n"
            f"{raw_user_text}\n\n"
            "已有规则解析摘要：\n"
            f"scenario={user_goal.get('scenario')}\n"
            f"intent_tags={user_goal.get('intent_tags')}\n"
            f"must_have={constraints.get('must_have')}\n"
            f"canonical_tags={[tag.value for tag in tag_set.canonical_tags]}\n\n"
            "只补充规则没有覆盖的隐性需求。输出 JSON object，字段只能包含："
            "explicit_facts, latent_goals, hidden_constraints, success_definition, failure_cases, "
            "inferred_tags, confidence_by_tag, evidence_by_tag, clarification_policy, missing_fields。"
        )


class _TagCollector:
    def __init__(self, source_tags: List[str]) -> None:
        self.source_tags = source_tags
        self.tags: set[CanonicalTag] = set()
        self.confidence_by_tag: Dict[str, float] = {}
        self.evidence_by_tag: Dict[str, str] = {}
        self.notes: Dict[str, List[str]] = {"explicit_facts": []}

    def add(self, tag: CanonicalTag, evidence: str, confidence: float) -> None:
        self.tags.add(tag)
        key = tag.value
        previous = self.confidence_by_tag.get(key, 0.0)
        if confidence >= previous:
            self.confidence_by_tag[key] = max(0.0, min(1.0, confidence))
            self.evidence_by_tag[key] = evidence
        if confidence >= 0.85:
            self.notes.setdefault("explicit_facts", []).append(evidence)

    def to_tag_set(self) -> CanonicalTagSet:
        ordered = sorted(self.tags, key=lambda tag: tag.value)
        return CanonicalTagSet.parse_payload(
            {
                "canonical_tags": [tag.value for tag in ordered],
                "source_tags": self.source_tags,
                "inferred_tags": [],
                "confidence_by_tag": self.confidence_by_tag,
                "evidence_by_tag": self.evidence_by_tag,
            }
        )


def _dedupe(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _list_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return _dedupe(value)


_SYSTEM_PROMPT = (
    "你是 LifePilot 的 LatentIntentInterpreter。你只能基于给定用户原文和已有规则解析做语义补充，"
    "不得推荐 POI，不得编造事实，不得输出推理链。inferred_tags 只能从固定 CanonicalTag 枚举中选择："
    f"{sorted(CANONICAL_TAG_VALUES)}。只输出 JSON object。"
)
