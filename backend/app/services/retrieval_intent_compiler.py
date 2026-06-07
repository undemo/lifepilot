from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.schemas.internal_intelligence import ActivityIntent, FoodIntent, LatentIntent, MachineIntent


class RetrievalIntentCompiler:
    """Compile normalized semantic intent into deterministic retrieval intent."""

    def compile(
        self,
        *,
        raw_user_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        latent_intent: Optional[LatentIntent | Dict[str, Any]] = None,
        food_intent: Optional[FoodIntent | Dict[str, Any]] = None,
        activity_intent: Optional[ActivityIntent | Dict[str, Any]] = None,
    ) -> MachineIntent:
        tags = self._canonical_values(latent_intent)
        food = self._food_intent(food_intent)
        activity = self._activity_intent(activity_intent)
        builder = _MachineIntentBuilder(tags)

        self._apply_global_constraints(builder, raw_user_text, constraints)
        self._apply_child_rules(builder, food)
        self._apply_queue_rules(builder)
        self._apply_nearby_rules(builder)
        self._apply_food_rules(builder, food)
        self._apply_anniversary_rules(builder)
        self._apply_stress_relief_rules(builder)
        self._apply_activity_rules(builder, activity)
        self._apply_sports_rules(builder, raw_user_text)
        self._apply_scenic_rules(builder)
        self._apply_legacy_slot_hints(builder, user_goal, constraints)
        return builder.build()

    def _canonical_values(self, latent_intent: Optional[LatentIntent | Dict[str, Any]]) -> set[str]:
        if latent_intent is None:
            return set()
        if isinstance(latent_intent, LatentIntent):
            return {tag.value for tag in latent_intent.canonical_tag_set.canonical_tags}
        payload = dict(latent_intent or {})
        tag_set = payload.get("canonical_tag_set") or {}
        values = tag_set.get("canonical_tags") if isinstance(tag_set, dict) else []
        return {str(tag) for tag in values or []}

    def _food_intent(self, food_intent: Optional[FoodIntent | Dict[str, Any]]) -> FoodIntent:
        if isinstance(food_intent, FoodIntent):
            return food_intent
        if isinstance(food_intent, dict):
            return FoodIntent.parse_payload(food_intent, fallback_on_error=True, **food_intent)
        return FoodIntent.fallback()

    def _activity_intent(self, activity_intent: Optional[ActivityIntent | Dict[str, Any]]) -> ActivityIntent:
        if isinstance(activity_intent, ActivityIntent):
            return activity_intent
        if isinstance(activity_intent, dict):
            return ActivityIntent.parse_payload(activity_intent, fallback_on_error=True, **activity_intent)
        return ActivityIntent.fallback()

    def _apply_global_constraints(self, builder: "_MachineIntentBuilder", raw_text: str, constraints: Dict[str, Any]) -> None:
        if builder.has("WITH_CHILD"):
            builder.global_constraints["with_child"] = True
        if builder.has("CHILD_AGE_PRESCHOOL"):
            builder.global_constraints["child_age_group"] = "preschool"
        elif builder.has("CHILD_AGE_PRIMARY"):
            builder.global_constraints["child_age_group"] = "primary"
        if builder.has("RELAXED_PACE"):
            builder.global_constraints["pace"] = "relaxed"
        if builder.has("COMPACT_PACE"):
            builder.global_constraints["pace"] = "compact"
        if builder.has("NEARBY_REQUIRED") or constraints.get("distance_preference") == "nearby":
            builder.global_constraints["max_single_leg_travel_minutes"] = 30
        if constraints.get("budget_max_per_person") is not None:
            builder.global_constraints["budget_max_per_person"] = constraints.get("budget_max_per_person")
        if "不想走太远" in raw_text or "别太远" in raw_text:
            builder.global_constraints.setdefault("max_single_leg_travel_minutes", 30)

    def _apply_child_rules(self, builder: "_MachineIntentBuilder", food: FoodIntent) -> None:
        if not (builder.has("WITH_CHILD") or builder.has("CHILD_AGE_PRESCHOOL") or builder.has("CHILD_AGE_PRIMARY")):
            return
        builder.add_hard_filter("child_age_compatible", "==", True, advisory=True, scope="all")
        builder.add_soft("child_friendly_score", 1.4, scope="activity")
        builder.add_soft("restroom_score", 0.6, scope="all")
        builder.add_soft("rest_area_score", 0.6, scope="all")
        builder.add_soft("low_walking_intensity", 0.8, scope="activity")
        builder.add_soft("family_friendly_score", 1.0, scope="all")
        builder.add_soft("child_food_score", 1.0, scope="meal")
        builder.add_penalty("high_noise_level", -0.5, scope="all")
        builder.add_penalty("high_walking_intensity", -0.8, scope="activity")
        builder.add_penalty("spicy_only_restaurant", -0.8, scope="meal")
        builder.add_verifier("verify_child_suitability")
        builder.add_verifier("verify_route")
        builder.add_hint("带孩子场景优先低强度、厕所/休息点和儿童可食选项。")
        if food.child_food_required:
            builder.add_soft("child_food_score", 1.0, scope="meal")
        if food.non_spicy_required or builder.has("NON_SPICY_REQUIRED"):
            builder.add_soft("non_spicy_option", 1.0, scope="meal")

    def _apply_queue_rules(self, builder: "_MachineIntentBuilder") -> None:
        if not builder.has("AVOID_LONG_QUEUE"):
            return
        builder.hard_filters.append(
            {
                "feature": "expected_queue_minutes",
                "operator": "<=",
                "value": 20,
                "alternative": {"feature": "queue_risk", "operator": "<=", "value": 0.65},
                "advisory": True,
                "reason": "avoid_long_queue",
            }
        )
        builder.add_soft("reservation_supported", 0.8, scope="all")
        builder.add_soft("low_queue_score", 1.2, scope="all")
        builder.add_penalty("high_queue_risk", -1.0, scope="all")
        builder.add_verifier("verify_queue")
        builder.add_hint("不排长队需求需要优先低排队风险或可预约候选。")

    def _apply_nearby_rules(self, builder: "_MachineIntentBuilder") -> None:
        if not builder.has("NEARBY_REQUIRED"):
            return
        builder.add_hard_filter("max_single_leg_travel_minutes", "<=", 30, advisory=True, scope="route")
        builder.add_soft("nearby_score", 1.2, scope="route")
        builder.add_soft("low_transfer_score", 1.0, scope="route")
        builder.add_penalty("long_transfer", -1.0, scope="route")
        builder.add_verifier("verify_route")
        builder.add_hint("附近/别太远需求需要控制单段路程和转场复杂度。")

    def _apply_food_rules(self, builder: "_MachineIntentBuilder", food: FoodIntent) -> None:
        wants_meal = bool(
            builder.has_any({"MEAL_REQUIRED", "DINNER_REQUIRED", "LUNCH_REQUIRED", "FOOD_REQUIRED"})
            or food.raw_terms
            or food.known_dish_ids
            or food.parent_categories
        )
        if not wants_meal:
            return
        meal_time = "dinner" if builder.has("DINNER_REQUIRED") else "lunch" if builder.has("LUNCH_REQUIRED") else "meal"
        builder.slot_requirements.append(
            {
                "slot_type": "meal",
                "required": bool(builder.has_any({"MEAL_REQUIRED", "DINNER_REQUIRED", "LUNCH_REQUIRED", "FOOD_REQUIRED"})),
                "preferred_time": meal_time,
                "food_match": {
                    "raw_terms": list(food.raw_terms),
                    "known_dish_ids": list(food.known_dish_ids),
                    "parent_categories": list(food.parent_categories),
                    "ingredients": list(food.ingredients),
                    "cooking_methods": list(food.cooking_methods),
                    "flavors": list(food.flavors),
                    "forms": list(food.forms),
                    "scenes": list(food.scenes),
                },
            }
        )
        builder.retrieval_plan["food_intent"] = food.to_dict()
        builder.retrieval_plan["food_match"] = {
            "raw_terms": list(food.raw_terms),
            "known_dish_ids": list(food.known_dish_ids),
            "parent_categories": list(food.parent_categories),
            "ingredients": list(food.ingredients),
            "cooking_methods": list(food.cooking_methods),
            "flavors": list(food.flavors),
            "forms": list(food.forms),
            "scenes": list(food.scenes),
            "retrieval_mode": food.retrieval_mode,
        }
        indexes = []
        if food.raw_terms:
            indexes.append("raw_term_index")
        if food.known_dish_ids:
            indexes.append("known_dish_index")
        if food.parent_categories:
            indexes.append("parent_category_index")
        if food.ingredients:
            indexes.append("ingredient_index")
        if food.cooking_methods:
            indexes.append("cooking_method_index")
        if food.flavors:
            indexes.append("flavor_index")
        if food.forms:
            indexes.append("form_index")
        if food.scenes:
            indexes.append("scene_index")
        builder.add_indexes(indexes)
        builder.add_soft("exact_raw_food_match", 1.5, scope="meal")
        builder.add_soft("known_dish_match", 1.3, scope="meal")
        builder.add_soft("attribute_combo_match", 1.0, scope="meal")
        builder.add_soft("parent_category_match", 0.6, scope="meal")
        builder.add_soft("scene_match", 0.4, scope="meal")
        builder.add_verifier("verify_restaurant_capacity")
        if food.child_food_required or builder.has("CHILD_FOOD_REQUIRED"):
            builder.add_soft("child_food_score", 1.0, scope="meal")
            builder.add_soft("non_spicy_option", 1.0, scope="meal")
            builder.add_soft("family_dining_score", 0.8, scope="meal")
        if food.low_calorie_required or builder.has("LOW_CALORIE_REQUIRED"):
            builder.add_soft("healthy_option_score", 1.2, scope="meal")
            builder.add_soft("light_meal_match", 1.0, scope="meal")
            builder.add_penalty("oiliness_level", -0.8, scope="meal")
        self._apply_explicit_food_tags(builder, food)

    def _apply_explicit_food_tags(self, builder: "_MachineIntentBuilder", food: FoodIntent) -> None:
        categories = set(food.parent_categories)
        if builder.has("CRAYFISH_REQUIRED") or "CRAYFISH" in categories:
            builder.add_hard_filter("has_crayfish", "==", True, advisory=True, scope="meal")
            builder.add_hint("小龙虾需求需要匹配菜品或原始食物词。")
        if builder.has("HOTPOT_REQUIRED") or "HOTPOT" in categories:
            builder.add_hard_filter("has_hotpot", "==", True, advisory=True, scope="meal")
            builder.add_hint("火锅需求需要匹配火锅品类，并关注不辣/清汤备选。")
        if builder.has("BBQ_REQUIRED") or "BBQ" in categories:
            builder.add_hard_filter("has_bbq", "==", True, advisory=True, scope="meal")
            builder.add_hint("烧烤/烤物需求需要匹配烤物或相关属性。")
        if builder.has("LOCAL_FOOD_REQUIRED") or "LOCAL_FOOD" in categories:
            builder.add_hard_filter("has_local_food", "==", True, advisory=True, scope="meal")
            builder.add_hint("本地美食需求需要优先城市特色餐饮。")

    def _apply_anniversary_rules(self, builder: "_MachineIntentBuilder") -> None:
        if not builder.has("ANNIVERSARY"):
            return
        builder.add_soft("ceremonial_score", 1.2, scope="all")
        builder.add_soft("romantic_score", 1.0, scope="all")
        builder.add_soft("photo_score", 0.6, scope="activity")
        builder.slot_requirements.append({"slot_type": "addon", "tag": "FLOWER_SUGGESTED", "required": False})
        builder.slot_requirements.append({"slot_type": "addon", "tag": "PHOTO_SPOT_REQUIRED", "required": False})
        builder.add_hint("纪念日需要轻量仪式感、拍照点和安静餐饮。")

    def _apply_stress_relief_rules(self, builder: "_MachineIntentBuilder") -> None:
        if not builder.has("STRESS_RELIEF"):
            return
        builder.add_soft("quiet_score", 1.2, scope="activity")
        builder.add_soft("relaxation_score", 1.2, scope="activity")
        builder.add_soft("low_crowd_score", 1.0, scope="activity")
        builder.add_penalty("noisy_place", -1.0, scope="activity")
        builder.add_penalty("compact_pace", -0.8, scope="plan")
        builder.add_hint("散心/压力释放需要低刺激、低人流和低决策成本。")

    def _apply_activity_rules(self, builder: "_MachineIntentBuilder", activity: ActivityIntent) -> None:
        has_activity_need = bool(
            activity.raw_terms
            or activity.activity_type_ids
            or activity.parent_categories
            or activity.facility_types
            or activity.genres
            or activity.styles
            or activity.scenes
        )
        if not has_activity_need:
            return
        activity_match = {
            "raw_terms": list(activity.raw_terms),
            "activity_type_ids": list(activity.activity_type_ids),
            "parent_categories": list(activity.parent_categories),
            "facility_types": list(activity.facility_types),
            "genres": list(activity.genres),
            "styles": list(activity.styles),
            "scenes": list(activity.scenes),
            "retrieval_mode": activity.retrieval_mode,
            "intensity": activity.intensity,
            "child_suitable_required": activity.child_suitable_required,
            "elderly_suitable_required": activity.elderly_suitable_required,
            "quiet_required": activity.quiet_required,
            "social_mode": activity.social_mode,
        }
        builder.slot_requirements.append(
            {
                "slot_type": "activity",
                "required": True,
                "activity_match": activity_match,
                "activity_category": "structured_activity",
                "raw_terms": list(activity.raw_terms),
            }
        )
        builder.retrieval_plan["activity_intent"] = activity.to_dict()
        builder.retrieval_plan["activity_match"] = activity_match
        indexes = []
        if activity.raw_terms:
            indexes.append("raw_activity_term_index")
        if activity.activity_type_ids:
            indexes.append("activity_type_index")
        if activity.parent_categories:
            indexes.append("activity_parent_category_index")
        if activity.facility_types:
            indexes.append("activity_facility_index")
        if activity.genres:
            indexes.append("activity_genre_index")
        if activity.styles:
            indexes.append("activity_style_index")
        if activity.scenes:
            indexes.append("activity_scene_index")
        builder.add_indexes(indexes)
        builder.add_soft("exact_raw_activity_match", 2.0, scope="activity")
        builder.add_soft("known_activity_match", 1.6, scope="activity")
        builder.add_soft("activity_attribute_match", 1.0, scope="activity")
        builder.add_soft("parent_activity_category_match", 0.7, scope="activity")
        builder.add_soft("activity_scene_match", 0.5, scope="activity")
        builder.add_soft("companion_activity_fit", 1.0, scope="activity")
        builder.add_verifier("verify_activity_availability")
        if activity.booking_required:
            builder.add_soft("reservation_supported", 0.5, scope="activity")
            builder.add_hint("活动场馆可能需要预约或确认场次。")
        if activity.child_suitable_required:
            builder.add_soft("child_activity_score", 1.2, scope="activity")
            builder.add_penalty("child_incompatible_activity", -1.8, scope="activity")
            builder.add_hint("带孩子场景需要规避网咖、强噪声、强对抗或年龄不合适活动。")
        if activity.elderly_suitable_required:
            builder.add_soft("low_physical_intensity", 1.2, scope="activity")
            builder.add_soft("rest_area_score", 0.4, scope="activity")
            builder.add_penalty("elderly_incompatible_activity", -1.5, scope="activity")
            builder.add_penalty("high_physical_intensity", -1.2, scope="activity")
            builder.add_hint("长辈场景需要低强度、可休息、少对抗。")
        if activity.quiet_required:
            builder.add_soft("quiet_score", 1.0, scope="activity")
            builder.add_penalty("noisy_place", -1.0, scope="activity")
        if "SPORTS" in set(activity.parent_categories):
            builder.slot_requirements.append({"slot_type": "addon", "tag": "DRINK_SUGGESTED", "required": False})
            builder.add_soft("sport_facility_score", 1.0, scope="activity")
            builder.add_soft("shower_or_rest_area", 0.4, scope="activity")
            builder.add_hint("运动场景需要合理场馆 slot 和运动后补水/餐饮配套。")
        if set(activity.parent_categories) & {"SCENIC", "WALK"}:
            builder.add_soft("scenic_score", 0.9, scope="activity")
            builder.add_soft("photo_score", 0.4, scope="activity")
            builder.add_hint("景点/逛逛需求需要优先可散步、可拍照、低转场的地点。")

    def _apply_sports_rules(self, builder: "_MachineIntentBuilder", raw_text: str) -> None:
        if not builder.has("SPORTS") or (builder.retrieval_plan or {}).get("activity_match"):
            return
        sport_terms = [term for term in ("羽毛球", "篮球", "足球", "乒乓球", "台球", "游泳", "健身", "攀岩", "网球") if term in raw_text]
        builder.slot_requirements.append({"slot_type": "activity", "activity_category": "sports", "raw_terms": sport_terms, "required": False})
        builder.slot_requirements.append({"slot_type": "addon", "tag": "DRINK_SUGGESTED", "required": False})
        builder.add_soft("sport_facility_score", 16.0, scope="activity")
        builder.add_soft("shower_or_rest_area", 0.4, scope="activity")
        builder.add_hint("运动场景需要合理场馆 slot 和运动后补水/餐饮配套。")

    def _apply_scenic_rules(self, builder: "_MachineIntentBuilder") -> None:
        if not builder.has("SCENIC"):
            return
        builder.add_soft("scenic_score", 1.0, scope="activity")
        builder.add_soft("photo_score", 0.6, scope="activity")
        builder.add_hint("城市名片/美景需求需要优先景观、拍照点和本地特色。")

    def _apply_legacy_slot_hints(self, builder: "_MachineIntentBuilder", user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> None:
        scenario = str(user_goal.get("scenario") or "")
        if scenario == "city_light_explore":
            builder.global_constraints.setdefault("destination_first", True)
        if "route_simple" in set(str(item) for item in constraints.get("must_have") or []):
            builder.global_constraints.setdefault("low_transfer_required", True)


class _MachineIntentBuilder:
    def __init__(self, tags: set[str]) -> None:
        self.tags = set(tags)
        self.global_constraints: Dict[str, Any] = {}
        self.slot_requirements: List[Dict[str, Any]] = []
        self.hard_filters: List[Dict[str, Any]] = []
        self.soft_preferences: List[Dict[str, Any]] = []
        self.penalties: List[Dict[str, Any]] = []
        self.retrieval_plan: Dict[str, Any] = {}
        self.verifier_expectations: List[str] = []
        self.explanation_hints: List[str] = []

    def has(self, tag: str) -> bool:
        return tag in self.tags

    def has_any(self, tags: Iterable[str]) -> bool:
        return bool(self.tags & set(tags))

    def add_hard_filter(self, feature: str, operator: str, value: Any, *, advisory: bool, scope: str) -> None:
        self.hard_filters.append(
            {
                "feature": feature,
                "operator": operator,
                "value": value,
                "advisory": advisory,
                "scope": scope,
            }
        )

    def add_soft(self, feature: str, weight: float, *, scope: str) -> None:
        self.soft_preferences.append({"feature": feature, "weight": float(weight), "scope": scope})

    def add_penalty(self, feature: str, weight: float, *, scope: str) -> None:
        self.penalties.append({"feature": feature, "weight": float(weight), "scope": scope})

    def add_verifier(self, expectation: str) -> None:
        self.verifier_expectations.append(expectation)

    def add_hint(self, hint: str) -> None:
        self.explanation_hints.append(hint)

    def add_indexes(self, indexes: Iterable[Any]) -> None:
        existing = list(self.retrieval_plan.get("indexes") or [])
        self.retrieval_plan["indexes"] = _dedupe([*existing, *list(indexes or [])])

    def build(self) -> MachineIntent:
        payload = {
            "canonical_tags": sorted(self.tags),
            "global_constraints": self.global_constraints,
            "slot_requirements": self.slot_requirements,
            "hard_filters": self.hard_filters,
            "soft_preferences": self.soft_preferences,
            "penalties": self.penalties,
            "retrieval_plan": self.retrieval_plan,
            "verifier_expectations": _dedupe(self.verifier_expectations),
            "explanation_hints": _dedupe(self.explanation_hints),
        }
        return MachineIntent.parse_payload(payload, fallback_on_error=True, **payload)


def _dedupe(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
