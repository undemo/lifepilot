from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.core.data_paths import ACTIVITY_SEMANTICS_PATH, DATA_DIR
from app.schemas.internal_intelligence import (
    ACTIVITY_PARENT_CATEGORIES,
    ACTIVITY_TYPE_IDS,
    ActivityIntent,
    CanonicalTag,
)


class ActivitySemanticAgent:
    """Parse activity and entertainment needs into a controlled internal intent.

    The agent is query-side only: it never scans POIs and never recommends
    venues. Retrieval/ranking consume the structured ActivityIntent later.
    """

    def __init__(self, data_dir: Optional[Path] = None, llm_client: Optional[Any] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self.llm_client = llm_client
        self.semantics = self._load_semantics()

    def analyze(
        self,
        *,
        raw_user_text: str,
        constraints: Optional[Dict[str, Any]] = None,
        recommendation_profile: Optional[Dict[str, Any]] = None,
        canonical_tags: Optional[Iterable[Any]] = None,
    ) -> ActivityIntent:
        constraints = constraints or {}
        recommendation_profile = recommendation_profile or constraints.get("recommendation_profile") or {}
        canonical_values = self._canonical_values(canonical_tags)
        deterministic = self._rule_activity_intent(raw_user_text or "", constraints, recommendation_profile, canonical_values)

        if self.llm_client is not None and deterministic.retrieval_mode == "unknown":
            return self._try_llm_supplement(raw_user_text or "", constraints, recommendation_profile, canonical_values, deterministic)
        return deterministic

    def _rule_activity_intent(
        self,
        raw_text: str,
        constraints: Dict[str, Any],
        recommendation_profile: Dict[str, Any],
        canonical_tags: set[str],
    ) -> ActivityIntent:
        if self._is_food_or_drink_only(raw_text):
            return ActivityIntent.fallback()

        raw_terms = self._extract_raw_terms(raw_text, constraints, recommendation_profile)
        search_text = " ".join([raw_text, *raw_terms])
        type_ids: List[str] = []
        parent_categories: List[str] = []
        facility_types: List[str] = []
        genres: List[str] = []
        styles: List[str] = []
        scenes: List[str] = []
        intensities: List[str] = []
        indoor_preferred = False
        outdoor_acceptable = True
        booking_required = False

        for keyword, config in self._known_activity_keywords().items():
            if keyword not in search_text:
                continue
            type_id = str(config.get("activity_type_id") or "")
            if type_id in ACTIVITY_TYPE_IDS:
                type_ids.append(type_id)
            for category in config.get("parent_categories") or []:
                if category in ACTIVITY_PARENT_CATEGORIES:
                    parent_categories.append(category)
            facility_types.extend(str(value) for value in config.get("facility_types") or [])
            genres.extend(str(value) for value in config.get("genres") or [])
            styles.extend(str(value) for value in config.get("styles") or [])
            scenes.extend(str(value) for value in config.get("scenes") or [])
            if str(config.get("intensity") or "") in {"low", "medium", "high"}:
                intensities.append(str(config.get("intensity")))
            indoor_preferred = indoor_preferred or bool(config.get("indoor_preferred"))
            outdoor_acceptable = outdoor_acceptable and bool(config.get("outdoor_acceptable", True))
            booking_required = booking_required or bool(config.get("booking_required"))

        facility_types.extend(self._keyword_hits(search_text, "facility_keywords"))
        genres.extend(self._keyword_hits(search_text, "genre_keywords"))
        styles.extend(self._keyword_hits(search_text, "style_keywords"))
        scenes.extend(self._keyword_hits(search_text, "scene_keywords"))
        self._derive_companion_scene(canonical_tags, scenes)
        self._derive_parent_category(type_ids, parent_categories, raw_terms, genres, styles)

        child_required = bool(canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "CHILD_AGE_PRIMARY", "FAMILY_OUTING"})
        elderly_required = bool(canonical_tags & {"WITH_ELDERLY"})
        quiet_required = bool(canonical_tags & {"STRESS_RELIEF", "HEALING", "AVOID_CROWD", "AVOID_NOISY_PLACE"})
        if child_required:
            scenes.append("亲子")
        if elderly_required:
            scenes.append("长辈")
            styles.append("低强度")
        social_or_high_stimulation = bool(set(parent_categories) & {"GAME", "SOCIAL_ENTERTAINMENT"} or set(type_ids) & {"ACTIVITY_ESPORTS", "ACTIVITY_SCRIPT_MURDER", "ACTIVITY_BOARD_GAME", "ACTIVITY_KARAOKE"})
        if quiet_required and not social_or_high_stimulation:
            styles.extend(["安静", "低刺激"])
            scenes.append("散心")

        intensity = self._resolve_intensity(_dedupe_strings(intensities), styles, elderly_required)
        payload = {
            "raw_terms": _dedupe_strings(raw_terms),
            "activity_type_ids": [item for item in _dedupe_strings(type_ids) if item in ACTIVITY_TYPE_IDS],
            "parent_categories": [item for item in _dedupe_strings(parent_categories) if item in ACTIVITY_PARENT_CATEGORIES],
            "facility_types": _dedupe_strings(facility_types),
            "genres": _dedupe_strings(genres),
            "styles": _dedupe_strings(styles),
            "scenes": _dedupe_strings(scenes),
            "fallback_query_text": self._fallback_query_text(raw_terms, facility_types, genres, styles, scenes),
            "retrieval_mode": self._retrieval_mode(type_ids, raw_terms, facility_types, genres, styles, scenes),
            "intensity": intensity,
            "indoor_preferred": indoor_preferred or "WEATHER_ROBUST_REQUIRED" in canonical_tags,
            "outdoor_acceptable": outdoor_acceptable and "WEATHER_ROBUST_REQUIRED" not in canonical_tags,
            "booking_required": booking_required or "RESERVATION_SUGGESTED" in canonical_tags,
            "child_suitable_required": child_required,
            "elderly_suitable_required": elderly_required,
            "quiet_required": quiet_required and not social_or_high_stimulation,
            "social_mode": self._social_mode(canonical_tags, raw_text),
        }
        return ActivityIntent.parse_payload(payload, fallback_on_error=True, **payload)

    def _load_semantics(self) -> Dict[str, Any]:
        path = self.data_dir / "activity_semantics.json"
        if not path.exists():
            path = ACTIVITY_SEMANTICS_PATH
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _known_activity_keywords(self) -> Dict[str, Dict[str, Any]]:
        value = self.semantics.get("known_activity_keywords") or {}
        return value if isinstance(value, dict) else {}

    def _extract_raw_terms(self, raw_text: str, constraints: Dict[str, Any], recommendation_profile: Dict[str, Any]) -> List[str]:
        terms: List[str] = []
        for keyword in self._known_activity_keywords().keys():
            if keyword in raw_text:
                terms.append(keyword)
        for phrase in self._activity_phrases(raw_text):
            if self._has_activity_signal(phrase):
                terms.append(phrase)
        explicit_terms = bool(terms)
        for tag in (recommendation_profile.get("normalized_tags") or []) + (constraints.get("must_have") or []):
            text = str(tag or "")
            if text in {"hands_on", "craft"}:
                terms.append("手工")
            elif text in {"karaoke"}:
                terms.append("KTV")
            elif text in {"board_game"}:
                terms.append("桌游")
            elif text in {"light_walk"} and not explicit_terms:
                terms.append("散步")
            elif text in {"amusement"}:
                terms.append("游乐园")
        return _dedupe_strings(terms)

    def _activity_phrases(self, raw_text: str) -> List[str]:
        phrases: List[str] = []
        patterns = (
            r"(?:想|要|准备)?(?:和[^，。,.!?；;]{1,8})?(?:去)?(?:打|玩|看|逛|唱|做|体验)([^，。,.!?；;]+)",
            r"(?:去|找个地方)([^，。,.!?；;]*(?:景点|公园|展览|电影|剧本杀|电竞|手工|球|KTV|唱歌|散步|逛逛)[^，。,.!?；;]*)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, raw_text or ""):
                phrase = self._clean_phrase(match.group(1))
                if phrase:
                    phrases.append(phrase)
        return _dedupe_strings(phrases)

    def _clean_phrase(self, phrase: str) -> str:
        text = str(phrase or "").strip()
        text = re.split(r"(?:然后|再|顺便|但|不过|晚饭|晚餐|午饭|吃|喝|安排)", text)[0].strip()
        text = re.sub(r"^(个|一场|一下|会儿|点)", "", text)
        text = re.sub(r"(一下|会儿|然后你安排)$", "", text).strip()
        return text if 1 <= len(text) <= 18 else ""

    def _has_activity_signal(self, text: str) -> bool:
        if not text or self._is_food_or_drink_only(text):
            return False
        return any(keyword in text for keyword in self._known_activity_keywords().keys()) or any(
            token in text for token in ("球", "电竞", "网咖", "剧本", "电影", "影院", "景点", "公园", "手工", "手作", "逛", "散步", "唱歌", "KTV")
        )

    def _is_food_or_drink_only(self, text: str) -> bool:
        normalized = re.sub(r"^(今天|下午|晚上|想|要|喝|吃|点|杯|一杯|附近|顺便|再)", "", text or "").strip()
        food_tokens = ("奶茶", "咖啡", "火锅", "小龙虾", "烧烤", "烤串", "轻食", "清淡", "甜品", "糖葫芦", "拌面", "巴斯克", "菠萝")
        activity_tokens = tuple(self._known_activity_keywords().keys()) + ("逛", "散步", "景点", "公园", "球", "电竞", "电影", "手工")
        return bool(normalized and any(token in text for token in food_tokens) and not any(token in text for token in activity_tokens))

    def _keyword_hits(self, text: str, key: str) -> List[str]:
        mapping = self.semantics.get(key) or {}
        if not isinstance(mapping, dict):
            return []
        return _dedupe_strings(str(value) for keyword, value in mapping.items() if keyword and keyword in text)

    def _derive_companion_scene(self, canonical_tags: set[str], scenes: List[str]) -> None:
        if "WITH_CHILD" in canonical_tags or "FAMILY_OUTING" in canonical_tags:
            scenes.append("亲子")
        if "WITH_FRIENDS" in canonical_tags:
            scenes.append("朋友")
        if "WITH_SIBLING" in canonical_tags:
            scenes.append("亲友")
        if "WITH_COUPLE" in canonical_tags:
            scenes.append("约会")
        if "WITH_ELDERLY" in canonical_tags:
            scenes.append("长辈")

    def _derive_parent_category(
        self,
        type_ids: List[str],
        parent_categories: List[str],
        raw_terms: List[str],
        genres: List[str],
        styles: List[str],
    ) -> None:
        joined = " ".join(raw_terms)
        if any(type_id in type_ids for type_id in ("ACTIVITY_BADMINTON", "ACTIVITY_TENNIS", "ACTIVITY_FOOTBALL", "ACTIVITY_BASKETBALL", "ACTIVITY_TABLE_TENNIS", "ACTIVITY_BILLIARDS", "ACTIVITY_SWIMMING", "ACTIVITY_FITNESS", "ACTIVITY_YOGA", "ACTIVITY_CLIMBING")):
            parent_categories.append("SPORTS")
        if any(type_id in type_ids for type_id in ("ACTIVITY_ESPORTS", "ACTIVITY_SCRIPT_MURDER", "ACTIVITY_BOARD_GAME")):
            parent_categories.extend(["GAME", "SOCIAL_ENTERTAINMENT"])
        if any(type_id in type_ids for type_id in ("ACTIVITY_MOVIE", "ACTIVITY_THEATER", "ACTIVITY_LIVE_MUSIC")):
            parent_categories.append("MOVIE_THEATER" if "ACTIVITY_MOVIE" in type_ids else "PERFORMANCE")
        if "逛" in joined or "散步" in joined:
            parent_categories.append("WALK")
            styles.append("低强度")
        if "景点" in joined or "美景" in joined or "风景" in joined:
            parent_categories.append("SCENIC")
        if not parent_categories and (raw_terms or genres or styles):
            parent_categories.append("UNKNOWN_ACTIVITY")

    def _resolve_intensity(self, intensities: List[str], styles: List[str], elderly_required: bool) -> str:
        if elderly_required:
            return "low"
        if "high" in intensities:
            return "high"
        if "medium" in intensities:
            return "medium"
        if "low" in intensities or "低强度" in styles:
            return "low"
        return "unknown"

    def _retrieval_mode(
        self,
        type_ids: List[str],
        raw_terms: List[str],
        facility_types: List[str],
        genres: List[str],
        styles: List[str],
        scenes: List[str],
    ) -> str:
        has_known = bool(type_ids)
        has_attributes = bool(facility_types or genres or styles or scenes)
        if has_known and has_attributes and len(_dedupe_strings(raw_terms)) > 1:
            return "mixed"
        if has_known:
            return "known_activity"
        if raw_terms or has_attributes:
            return "attribute"
        return "unknown"

    def _fallback_query_text(
        self,
        raw_terms: List[str],
        facility_types: List[str],
        genres: List[str],
        styles: List[str],
        scenes: List[str],
    ) -> str:
        return " ".join(_dedupe_strings([*raw_terms, *facility_types, *genres, *styles, *scenes]))

    def _social_mode(self, canonical_tags: set[str], raw_text: str) -> str:
        if "WITH_CHILD" in canonical_tags or "FAMILY_OUTING" in canonical_tags:
            return "family"
        if "WITH_ELDERLY" in canonical_tags:
            return "elderly"
        if "WITH_SIBLING" in canonical_tags:
            return "sibling"
        if "WITH_FRIENDS" in canonical_tags or "室友" in raw_text:
            return "friends"
        if "WITH_COUPLE" in canonical_tags:
            return "couple"
        if "SOLO" in canonical_tags:
            return "solo"
        return "unknown"

    def _canonical_values(self, canonical_tags: Optional[Iterable[Any]]) -> set[str]:
        values: set[str] = set()
        for tag in canonical_tags or []:
            if isinstance(tag, CanonicalTag):
                values.add(tag.value)
            elif isinstance(tag, str):
                values.add(tag)
            elif hasattr(tag, "value"):
                values.add(str(tag.value))
        return values

    def _try_llm_supplement(
        self,
        raw_text: str,
        constraints: Dict[str, Any],
        recommendation_profile: Dict[str, Any],
        canonical_tags: set[str],
        deterministic: ActivityIntent,
    ) -> ActivityIntent:
        try:
            payload = self.llm_client.generate_json(
                system_prompt=_ACTIVITY_SYSTEM_PROMPT,
                user_prompt=self._llm_user_prompt(raw_text, constraints, recommendation_profile, canonical_tags, deterministic),
                temperature=0.1,
                max_tokens=700,
            )
            parsed = ActivityIntent.parse_payload(payload)
            return self._merge_activity_intents(deterministic, parsed)
        except Exception:
            return deterministic

    def _merge_activity_intents(self, base: ActivityIntent, supplement: ActivityIntent) -> ActivityIntent:
        payload = base.to_dict()
        supplement_payload = supplement.to_dict()
        for key in ("raw_terms", "activity_type_ids", "parent_categories", "facility_types", "genres", "styles", "scenes"):
            payload[key] = _dedupe_strings(list(payload.get(key) or []) + list(supplement_payload.get(key) or []))
        payload["fallback_query_text"] = self._fallback_query_text(
            payload["raw_terms"],
            payload["facility_types"],
            payload["genres"],
            payload["styles"],
            payload["scenes"],
        )
        payload["retrieval_mode"] = self._retrieval_mode(
            payload["activity_type_ids"],
            payload["raw_terms"],
            payload["facility_types"],
            payload["genres"],
            payload["styles"],
            payload["scenes"],
        )
        payload["child_suitable_required"] = bool(base.child_suitable_required or supplement.child_suitable_required)
        payload["elderly_suitable_required"] = bool(base.elderly_suitable_required or supplement.elderly_suitable_required)
        payload["quiet_required"] = bool(base.quiet_required or supplement.quiet_required)
        payload["booking_required"] = bool(base.booking_required or supplement.booking_required)
        if payload.get("intensity") == "unknown":
            payload["intensity"] = supplement_payload.get("intensity") or "unknown"
        if payload.get("social_mode") == "unknown":
            payload["social_mode"] = supplement_payload.get("social_mode") or "unknown"
        return ActivityIntent.parse_payload(payload, fallback_on_error=True, **base.to_dict())

    def _llm_user_prompt(
        self,
        raw_text: str,
        constraints: Dict[str, Any],
        recommendation_profile: Dict[str, Any],
        canonical_tags: set[str],
        deterministic: ActivityIntent,
    ) -> str:
        return (
            "只解析活动/娱乐场所语义，不推荐 POI，不扫描 POI，不编造 activity_type_id。\n"
            f"用户原文：{raw_text}\n"
            f"constraints 摘要：{constraints}\n"
            f"recommendation_profile 摘要：{recommendation_profile}\n"
            f"canonical_tags：{sorted(canonical_tags)}\n"
            f"规则结果：{deterministic.to_dict()}\n"
            f"activity_type_ids 只能从 {sorted(ACTIVITY_TYPE_IDS)} 选择；parent_categories 只能从 {sorted(ACTIVITY_PARENT_CATEGORIES)} 选择。"
        )


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


_ACTIVITY_SYSTEM_PROMPT = (
    "你是 LifePilot 的 ActivitySemanticAgent。你只负责把用户活动/娱乐场所表达解析成 ActivityIntent JSON，"
    "不得推荐场馆，不得读取或扫描 POI，不得输出推理链。raw_terms 必须保留用户原始活动词；"
    "未知活动不要编造专属 activity_type_id，只输出 facility_types/genres/styles/scenes。"
)
