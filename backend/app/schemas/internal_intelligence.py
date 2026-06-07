from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    ConfigDict = None  # type: ignore[assignment]


PYDANTIC_V2 = ConfigDict is not None and hasattr(BaseModel, "model_validate")
ModelT = TypeVar("ModelT", bound="BaseInternalModel")


class InternalIntelligenceValidationError(ValueError):
    """Controlled validation failure for internal LLM-native contracts."""


class BaseInternalModel(BaseModel):
    if PYDANTIC_V2 and ConfigDict is not None:
        model_config = ConfigDict(populate_by_name=True, extra="forbid")
    else:  # pragma: no cover - exercised only under pydantic v1
        class Config:
            allow_population_by_field_name = True
            extra = "forbid"
            use_enum_values = True

    @classmethod
    def parse_payload(
        cls: Type[ModelT],
        payload: Any,
        *,
        fallback_on_error: bool = False,
        **fallback_kwargs: Any,
    ) -> ModelT:
        try:
            parsed_payload = cls._decode_payload(payload)
            return cls._parse_model(parsed_payload)
        except Exception as exc:
            if fallback_on_error:
                return cls.fallback(**fallback_kwargs)
            raise InternalIntelligenceValidationError(f"{cls.__name__} validation failed: {exc}") from exc

    @classmethod
    def validate_payload(cls: Type[ModelT], payload: Any) -> ModelT:
        return cls.parse_payload(payload)

    @classmethod
    def fallback(cls: Type[ModelT], **kwargs: Any) -> ModelT:
        payload = cls._fallback_payload()
        payload.update(kwargs)
        payload = cls._coerce_fallback_payload(payload)
        try:
            return cls._parse_model(payload)
        except Exception:
            try:
                return cls._parse_model(cls._coerce_fallback_payload(cls._fallback_payload()))
            except Exception as exc:  # pragma: no cover - defensive guard
                raise InternalIntelligenceValidationError(f"{cls.__name__} fallback failed: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        dump = getattr(self, "model_dump", None)
        if callable(dump):
            return dump(mode="json", by_alias=True)
        return self.dict(by_alias=True)  # pragma: no cover - pydantic v1 compatibility

    @classmethod
    def _decode_payload(cls, payload: Any) -> Any:
        if isinstance(payload, cls):
            return payload
        if isinstance(payload, str):
            return json.loads(payload)
        return payload

    @classmethod
    def _parse_model(cls: Type[ModelT], payload: Any) -> ModelT:
        if isinstance(payload, cls):
            return payload
        validate = getattr(cls, "model_validate", None)
        if callable(validate):
            return validate(payload)
        return cls.parse_obj(payload)  # pragma: no cover - pydantic v1 compatibility

    @classmethod
    def _fallback_payload(cls) -> Dict[str, Any]:
        return {}

    @classmethod
    def _coerce_fallback_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload


class CanonicalTag(str, Enum):
    SOLO = "SOLO"
    WITH_COUPLE = "WITH_COUPLE"
    WITH_CHILD = "WITH_CHILD"
    CHILD_AGE_PRESCHOOL = "CHILD_AGE_PRESCHOOL"
    CHILD_AGE_PRIMARY = "CHILD_AGE_PRIMARY"
    WITH_ELDERLY = "WITH_ELDERLY"
    WITH_FRIENDS = "WITH_FRIENDS"
    WITH_SIBLING = "WITH_SIBLING"
    FAMILY_OUTING = "FAMILY_OUTING"
    SHORT_DURATION = "SHORT_DURATION"
    HALF_DAY = "HALF_DAY"
    FULL_DAY = "FULL_DAY"
    TODAY = "TODAY"
    WEEKEND = "WEEKEND"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    RELAXED_PACE = "RELAXED_PACE"
    COMPACT_PACE = "COMPACT_PACE"
    NEARBY_REQUIRED = "NEARBY_REQUIRED"
    DESTINATION_FIRST = "DESTINATION_FIRST"
    LOW_TRANSFER_REQUIRED = "LOW_TRANSFER_REQUIRED"
    WALKING_FRIENDLY = "WALKING_FRIENDLY"
    DRIVING_FRIENDLY = "DRIVING_FRIENDLY"
    SUBWAY_FRIENDLY = "SUBWAY_FRIENDLY"
    AVOID_LONG_QUEUE = "AVOID_LONG_QUEUE"
    AVOID_CROWD = "AVOID_CROWD"
    AVOID_HIGH_WALKING_LOAD = "AVOID_HIGH_WALKING_LOAD"
    AVOID_NOISY_PLACE = "AVOID_NOISY_PLACE"
    WEATHER_ROBUST_REQUIRED = "WEATHER_ROBUST_REQUIRED"
    MEAL_REQUIRED = "MEAL_REQUIRED"
    DINNER_REQUIRED = "DINNER_REQUIRED"
    LUNCH_REQUIRED = "LUNCH_REQUIRED"
    FOOD_REQUIRED = "FOOD_REQUIRED"
    CRAYFISH_REQUIRED = "CRAYFISH_REQUIRED"
    BBQ_REQUIRED = "BBQ_REQUIRED"
    HOTPOT_REQUIRED = "HOTPOT_REQUIRED"
    LOCAL_FOOD_REQUIRED = "LOCAL_FOOD_REQUIRED"
    LIGHT_MEAL_REQUIRED = "LIGHT_MEAL_REQUIRED"
    DESSERT_REQUIRED = "DESSERT_REQUIRED"
    SNACK_REQUIRED = "SNACK_REQUIRED"
    DRINK_REQUIRED = "DRINK_REQUIRED"
    COFFEE_REQUIRED = "COFFEE_REQUIRED"
    MILK_TEA_REQUIRED = "MILK_TEA_REQUIRED"
    LOW_CALORIE_REQUIRED = "LOW_CALORIE_REQUIRED"
    NON_SPICY_REQUIRED = "NON_SPICY_REQUIRED"
    CHILD_FOOD_REQUIRED = "CHILD_FOOD_REQUIRED"
    COOL_DRINK_SUGGESTED = "COOL_DRINK_SUGGESTED"
    DRINK_SUGGESTED = "DRINK_SUGGESTED"
    ANNIVERSARY = "ANNIVERSARY"
    ROMANTIC = "ROMANTIC"
    CEREMONIAL = "CEREMONIAL"
    STRESS_RELIEF = "STRESS_RELIEF"
    HEALING = "HEALING"
    SCENIC = "SCENIC"
    PHOTO_SPOT_REQUIRED = "PHOTO_SPOT_REQUIRED"
    PREMIUM_EXPERIENCE = "PREMIUM_EXPERIENCE"
    CASUAL_EXPERIENCE = "CASUAL_EXPERIENCE"
    SPORTS = "SPORTS"
    FLOWER_SUGGESTED = "FLOWER_SUGGESTED"
    CAKE_SUGGESTED = "CAKE_SUGGESTED"
    RESTROOM_REQUIRED = "RESTROOM_REQUIRED"
    REST_AREA_REQUIRED = "REST_AREA_REQUIRED"
    PARKING_REQUIRED = "PARKING_REQUIRED"
    RESERVATION_SUGGESTED = "RESERVATION_SUGGESTED"
    WET_TISSUE_SUGGESTED = "WET_TISSUE_SUGGESTED"
    DRIVER_SERVICE_SUGGESTED = "DRIVER_SERVICE_SUGGESTED"


CANONICAL_TAG_VALUES = {tag.value for tag in CanonicalTag}

KnownDishId = Literal[
    "DISH_CRAYFISH",
    "DISH_HOTPOT",
    "DISH_BBQ",
    "DISH_LIGHT_MEAL",
    "DISH_COFFEE",
    "DISH_MILK_TEA",
    "DISH_DESSERT",
    "DISH_SNACK",
    "DISH_HANGZHOU_LOCAL",
    "DISH_JAPANESE",
    "DISH_STEAK",
    "DISH_LAMB",
    "DISH_NOODLES",
    "DISH_RICE",
    "DISH_SEAFOOD",
    "DISH_CHILD_FRIENDLY_FOOD",
    "DISH_OTHER",
]

ParentCategory = Literal[
    "CRAYFISH",
    "BBQ",
    "HOTPOT",
    "LOCAL_FOOD",
    "LIGHT_MEAL",
    "DRINK",
    "DESSERT",
    "SNACK",
    "WESTERN",
    "JAPANESE",
    "NOODLES",
    "RICE",
    "SEAFOOD",
    "LAMB",
    "CHILD_FRIENDLY",
    "LONG_TAIL_SNACK",
    "UNKNOWN_FOOD",
]

KNOWN_DISH_IDS = set(KnownDishId.__args__)
PARENT_CATEGORIES = set(ParentCategory.__args__)

ActivityTypeId = Literal[
    "ACTIVITY_AMUSEMENT",
    "ACTIVITY_HANDS_ON",
    "ACTIVITY_BADMINTON",
    "ACTIVITY_TENNIS",
    "ACTIVITY_FOOTBALL",
    "ACTIVITY_BASKETBALL",
    "ACTIVITY_TABLE_TENNIS",
    "ACTIVITY_BILLIARDS",
    "ACTIVITY_SWIMMING",
    "ACTIVITY_FITNESS",
    "ACTIVITY_YOGA",
    "ACTIVITY_CLIMBING",
    "ACTIVITY_ESPORTS",
    "ACTIVITY_SCRIPT_MURDER",
    "ACTIVITY_BOARD_GAME",
    "ACTIVITY_KARAOKE",
    "ACTIVITY_THEATER",
    "ACTIVITY_MOVIE",
    "ACTIVITY_LIVE_MUSIC",
    "ACTIVITY_SCENIC",
    "ACTIVITY_PARK_WALK",
    "ACTIVITY_MALL_WALK",
    "ACTIVITY_BOOKSTORE",
    "ACTIVITY_EXHIBITION",
    "ACTIVITY_DANCE",
    "ACTIVITY_OTHER",
]

ActivityParentCategory = Literal[
    "SPORTS",
    "GAME",
    "PERFORMANCE",
    "MOVIE_THEATER",
    "SCENIC",
    "HANDS_ON",
    "AMUSEMENT",
    "SOCIAL_ENTERTAINMENT",
    "QUIET_STAY",
    "WALK",
    "SHOPPING",
    "FAMILY",
    "UNKNOWN_ACTIVITY",
]

ACTIVITY_TYPE_IDS = set(ActivityTypeId.__args__)
ACTIVITY_PARENT_CATEGORIES = set(ActivityParentCategory.__args__)


def _dedupe_strings(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, Enum):
            text = str(value.value).strip()
        else:
            text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _filter_enum_values(values: Any, allowed: set[str]) -> List[str]:
    return [value for value in _dedupe_strings(values) if value in allowed]


def _float_map(values: Any) -> Dict[str, float]:
    if not isinstance(values, dict):
        return {}
    result: Dict[str, float] = {}
    for key, value in values.items():
        try:
            result[str(key)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue
    return result


def _string_map(values: Any) -> Dict[str, str]:
    if not isinstance(values, dict):
        return {}
    return {str(key): str(value) for key, value in values.items() if str(value).strip()}


class CanonicalTagSet(BaseInternalModel):
    canonical_tags: List[CanonicalTag] = Field(default_factory=list)
    source_tags: List[str] = Field(default_factory=list)
    inferred_tags: List[CanonicalTag] = Field(default_factory=list)
    confidence_by_tag: Dict[str, float] = Field(default_factory=dict)
    evidence_by_tag: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def _coerce_fallback_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "canonical_tags": _filter_enum_values(payload.get("canonical_tags"), CANONICAL_TAG_VALUES),
            "source_tags": _dedupe_strings(payload.get("source_tags")),
            "inferred_tags": _filter_enum_values(payload.get("inferred_tags"), CANONICAL_TAG_VALUES),
            "confidence_by_tag": _float_map(payload.get("confidence_by_tag")),
            "evidence_by_tag": _string_map(payload.get("evidence_by_tag")),
        }


class LatentIntent(BaseInternalModel):
    explicit_facts: List[str] = Field(default_factory=list)
    latent_goals: List[str] = Field(default_factory=list)
    hidden_constraints: List[str] = Field(default_factory=list)
    success_definition: List[str] = Field(default_factory=list)
    failure_cases: List[str] = Field(default_factory=list)
    canonical_tag_set: CanonicalTagSet = Field(default_factory=CanonicalTagSet)
    clarification_policy: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)


class FoodIntent(BaseInternalModel):
    raw_terms: List[str] = Field(default_factory=list)
    known_dish_ids: List[KnownDishId] = Field(default_factory=list)
    parent_categories: List[ParentCategory] = Field(default_factory=list)
    ingredients: List[str] = Field(default_factory=list)
    cooking_methods: List[str] = Field(default_factory=list)
    flavors: List[str] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list)
    scenes: List[str] = Field(default_factory=list)
    specific_tags_from_existing_taxonomy: List[str] = Field(default_factory=list)
    fallback_query_text: str = ""
    retrieval_mode: Literal["known_dish", "long_tail_attribute", "mixed", "unknown"] = "unknown"
    child_food_required: bool = False
    non_spicy_required: bool = False
    low_calorie_required: bool = False

    @classmethod
    def _coerce_fallback_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = payload.get("retrieval_mode")
        if mode not in {"known_dish", "long_tail_attribute", "mixed", "unknown"}:
            mode = "unknown"
        return {
            "raw_terms": _dedupe_strings(payload.get("raw_terms")),
            "known_dish_ids": _filter_enum_values(payload.get("known_dish_ids"), KNOWN_DISH_IDS),
            "parent_categories": _filter_enum_values(payload.get("parent_categories"), PARENT_CATEGORIES),
            "ingredients": _dedupe_strings(payload.get("ingredients")),
            "cooking_methods": _dedupe_strings(payload.get("cooking_methods")),
            "flavors": _dedupe_strings(payload.get("flavors")),
            "forms": _dedupe_strings(payload.get("forms")),
            "scenes": _dedupe_strings(payload.get("scenes")),
            "specific_tags_from_existing_taxonomy": _dedupe_strings(payload.get("specific_tags_from_existing_taxonomy")),
            "fallback_query_text": str(payload.get("fallback_query_text") or ""),
            "retrieval_mode": mode,
            "child_food_required": bool(payload.get("child_food_required", False)),
            "non_spicy_required": bool(payload.get("non_spicy_required", False)),
            "low_calorie_required": bool(payload.get("low_calorie_required", False)),
        }


class ActivityIntent(BaseInternalModel):
    raw_terms: List[str] = Field(default_factory=list)
    activity_type_ids: List[ActivityTypeId] = Field(default_factory=list)
    parent_categories: List[ActivityParentCategory] = Field(default_factory=list)
    facility_types: List[str] = Field(default_factory=list)
    genres: List[str] = Field(default_factory=list)
    styles: List[str] = Field(default_factory=list)
    scenes: List[str] = Field(default_factory=list)
    fallback_query_text: str = ""
    retrieval_mode: Literal["known_activity", "attribute", "mixed", "unknown"] = "unknown"
    intensity: Literal["low", "medium", "high", "unknown"] = "unknown"
    indoor_preferred: bool = False
    outdoor_acceptable: bool = True
    booking_required: bool = False
    child_suitable_required: bool = False
    elderly_suitable_required: bool = False
    quiet_required: bool = False
    social_mode: Literal["solo", "couple", "family", "friends", "sibling", "elderly", "unknown"] = "unknown"

    @classmethod
    def _coerce_fallback_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = payload.get("retrieval_mode")
        if mode not in {"known_activity", "attribute", "mixed", "unknown"}:
            mode = "unknown"
        intensity = payload.get("intensity")
        if intensity not in {"low", "medium", "high", "unknown"}:
            intensity = "unknown"
        social_mode = payload.get("social_mode")
        if social_mode not in {"solo", "couple", "family", "friends", "sibling", "elderly", "unknown"}:
            social_mode = "unknown"
        return {
            "raw_terms": _dedupe_strings(payload.get("raw_terms")),
            "activity_type_ids": _filter_enum_values(payload.get("activity_type_ids"), ACTIVITY_TYPE_IDS),
            "parent_categories": _filter_enum_values(payload.get("parent_categories"), ACTIVITY_PARENT_CATEGORIES),
            "facility_types": _dedupe_strings(payload.get("facility_types")),
            "genres": _dedupe_strings(payload.get("genres")),
            "styles": _dedupe_strings(payload.get("styles")),
            "scenes": _dedupe_strings(payload.get("scenes")),
            "fallback_query_text": str(payload.get("fallback_query_text") or ""),
            "retrieval_mode": mode,
            "intensity": intensity,
            "indoor_preferred": bool(payload.get("indoor_preferred", False)),
            "outdoor_acceptable": bool(payload.get("outdoor_acceptable", True)),
            "booking_required": bool(payload.get("booking_required", False)),
            "child_suitable_required": bool(payload.get("child_suitable_required", False)),
            "elderly_suitable_required": bool(payload.get("elderly_suitable_required", False)),
            "quiet_required": bool(payload.get("quiet_required", False)),
            "social_mode": social_mode,
        }


class MachineIntent(BaseInternalModel):
    canonical_tags: List[CanonicalTag] = Field(default_factory=list)
    global_constraints: Dict[str, Any] = Field(default_factory=dict)
    slot_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    hard_filters: List[Dict[str, Any]] = Field(default_factory=list)
    soft_preferences: List[Dict[str, Any]] = Field(default_factory=list)
    penalties: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_plan: Dict[str, Any] = Field(default_factory=dict)
    verifier_expectations: List[str] = Field(default_factory=list)
    explanation_hints: List[str] = Field(default_factory=list)

    @classmethod
    def _coerce_fallback_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(payload)
        result["canonical_tags"] = _filter_enum_values(payload.get("canonical_tags"), CANONICAL_TAG_VALUES)
        return result


class CandidateCriticReport(BaseInternalModel):
    poi_id: str = "unknown_poi"
    decision: Literal["keep", "demote", "backup_only", "reject"] = "keep"
    score_delta: float = 0.0
    reason_codes: List[str] = Field(default_factory=list)
    user_facing_reason: str = ""
    risk_notes: List[str] = Field(default_factory=list)


class PlanCriticReport(BaseInternalModel):
    pass_: bool = Field(default=True, alias="pass")
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    repair_instructions: List[Dict[str, Any]] = Field(default_factory=list)
    severity: Literal["none", "low", "medium", "high"] = "none"
    verifier_related_notes: List[str] = Field(default_factory=list)


class PlanRepairPatch(BaseInternalModel):
    patch_type: Literal["replace_slot", "reorder_slots", "add_addon", "adjust_time", "fail"] = "fail"
    target_slot: Optional[str] = None
    replacement_candidate_ids: List[str] = Field(default_factory=list)
    reason: str = ""
    must_reverify: bool = True


class RecommendationExplanation(BaseInternalModel):
    why_this_plan: List[str] = Field(default_factory=list)
    why_selected: List[Dict[str, Any]] = Field(default_factory=list)
    why_not_selected: List[Dict[str, Any]] = Field(default_factory=list)
    risk_reminders: List[str] = Field(default_factory=list)
    addon_suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    assumption_notes: List[str] = Field(default_factory=list)
