from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.core.data_paths import DATA_DIR, FOOD_SEMANTICS_PATH
from app.rules.recommendation_taxonomy import extract_dining_preference
from app.schemas.internal_intelligence import (
    KNOWN_DISH_IDS,
    PARENT_CATEGORIES,
    CanonicalTag,
    FoodIntent,
)


class FoodSemanticAgent:
    def __init__(self, data_dir: Optional[Path] = None, llm_client: Optional[Any] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self.llm_client = llm_client
        self.semantics = self._load_semantics()

    def analyze(
        self,
        *,
        raw_user_text: str,
        constraints: Optional[Dict[str, Any]] = None,
        dining_preference: Optional[Dict[str, Any]] = None,
        recommendation_profile: Optional[Dict[str, Any]] = None,
        canonical_tags: Optional[Iterable[Any]] = None,
    ) -> FoodIntent:
        constraints = constraints or {}
        recommendation_profile = recommendation_profile or constraints.get("recommendation_profile") or {}
        existing_dining = dining_preference or constraints.get("dining_preference") or {}
        extracted_dining = extract_dining_preference(
            raw_user_text or "",
            (recommendation_profile.get("normalized_tags") or []) + (existing_dining.get("normalized_tags") or []),
        )
        merged_dining = self._merge_dining_preference(existing_dining, extracted_dining)
        canonical_values = self._canonical_values(canonical_tags)
        deterministic = self._rule_food_intent(raw_user_text or "", merged_dining, canonical_values)

        if self.llm_client is not None and deterministic.retrieval_mode == "unknown":
            return self._try_llm_supplement(raw_user_text or "", merged_dining, canonical_values, deterministic)
        return deterministic

    def _rule_food_intent(self, raw_text: str, dining_preference: Dict[str, Any], canonical_tags: set[str]) -> FoodIntent:
        raw_terms = self._extract_raw_terms(raw_text, dining_preference)
        search_text = " ".join([raw_text, *raw_terms])
        known_dish_ids: List[str] = []
        parent_categories: List[str] = []

        for keyword, config in self._keyword_config().items():
            if keyword not in search_text:
                continue
            for category in config.get("parent_categories") or []:
                if category in PARENT_CATEGORIES:
                    parent_categories.append(category)
            if self._should_add_known_dish(keyword, config, raw_terms):
                dish_id = str(config.get("dish_id") or "")
                if dish_id in KNOWN_DISH_IDS:
                    known_dish_ids.append(dish_id)

        ingredients = self._keyword_hits(search_text, "ingredient_keywords")
        cooking_methods = self._keyword_hits(search_text, "cooking_method_keywords")
        flavors = self._keyword_hits(search_text, "flavor_keywords")
        forms = self._keyword_hits(search_text, "form_keywords")
        scenes = self._keyword_hits(search_text, "scene_keywords")

        if "炭烤" in cooking_methods and "烧烤" not in cooking_methods:
            cooking_methods.append("烧烤")
        self._derive_long_tail_attributes(raw_terms, parent_categories, ingredients, cooking_methods, flavors, forms, scenes)
        self._derive_parent_categories(parent_categories, cooking_methods, forms, flavors, raw_terms)

        specific_tags = _dedupe_strings(
            list(dining_preference.get("specific_tags") or []) + list(dining_preference.get("normalized_tags") or [])
        )
        child_food_required = self._needs_child_food(raw_text, canonical_tags, parent_categories, flavors)
        non_spicy_required = self._needs_non_spicy(raw_text, canonical_tags, child_food_required, parent_categories, flavors)
        low_calorie_required = "LOW_CALORIE_REQUIRED" in canonical_tags or any(token in raw_text for token in ("减脂", "低卡", "低脂", "少油", "清淡"))

        payload = {
            "raw_terms": raw_terms,
            "known_dish_ids": _dedupe_strings(known_dish_ids),
            "parent_categories": [category for category in _dedupe_strings(parent_categories) if category in PARENT_CATEGORIES],
            "ingredients": _dedupe_strings(ingredients),
            "cooking_methods": _dedupe_strings(cooking_methods),
            "flavors": _dedupe_strings(flavors),
            "forms": _dedupe_strings(forms),
            "scenes": _dedupe_strings(scenes),
            "specific_tags_from_existing_taxonomy": specific_tags,
            "fallback_query_text": self._fallback_query_text(raw_terms, ingredients, cooking_methods, flavors, forms, scenes),
            "retrieval_mode": self._retrieval_mode(known_dish_ids, raw_terms, ingredients, cooking_methods, flavors, forms, scenes),
            "child_food_required": child_food_required,
            "non_spicy_required": non_spicy_required,
            "low_calorie_required": low_calorie_required,
        }
        return FoodIntent.parse_payload(payload, fallback_on_error=True, **payload)

    def _load_semantics(self) -> Dict[str, Any]:
        path = self.data_dir / "food_semantics.json"
        if not path.exists():
            path = FOOD_SEMANTICS_PATH
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _keyword_config(self) -> Dict[str, Dict[str, Any]]:
        value = self.semantics.get("known_dish_keywords") or {}
        return value if isinstance(value, dict) else {}

    def _merge_dining_preference(self, base: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(extracted or {})
        for key, value in (base or {}).items():
            if isinstance(value, list):
                merged[key] = _dedupe_strings(list(merged.get(key) or []) + value)
            elif value not in (None, "", False):
                merged[key] = value
        merged["raw_terms"] = _dedupe_strings(list((base or {}).get("raw_terms") or []) + list((extracted or {}).get("raw_terms") or []))
        merged["positive_terms"] = _dedupe_strings(list((base or {}).get("positive_terms") or []) + list((extracted or {}).get("positive_terms") or []))
        merged["normalized_tags"] = _dedupe_strings(list((base or {}).get("normalized_tags") or []) + list((extracted or {}).get("normalized_tags") or []))
        merged["specific_tags"] = _dedupe_strings(list((base or {}).get("specific_tags") or []) + list((extracted or {}).get("specific_tags") or []))
        return merged

    def _extract_raw_terms(self, raw_text: str, dining_preference: Dict[str, Any]) -> List[str]:
        raw_terms = _dedupe_strings(dining_preference.get("raw_terms") or [])
        for phrase in self._eat_phrases(raw_text):
            if phrase and phrase not in raw_terms:
                raw_terms.append(phrase)
        if not raw_terms:
            compact = self._compact_food_text(raw_text)
            if compact and self._has_food_signal(compact):
                raw_terms.append(compact)
        for keyword, config in self._keyword_config().items():
            if keyword in raw_text and not config.get("generic_method") and not config.get("generic_ingredient"):
                if not any(keyword in term for term in raw_terms):
                    raw_terms.append(keyword)
        return _dedupe_strings(raw_terms)

    def _eat_phrases(self, raw_text: str) -> List[str]:
        phrases: List[str] = []
        patterns = (
            r"(?:晚上|晚饭|晚餐|中午|午饭|午餐)?\s*(?:想吃点|想吃|想喝|吃点|喝点|要吃|要喝|晚上吃|中午吃)([^，。,.!?；;]+)",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, raw_text or ""):
                phrase = self._clean_phrase(match.group(1))
                if phrase:
                    phrases.append(phrase)
        return _dedupe_strings(phrases)

    def _clean_phrase(self, phrase: str) -> str:
        text = str(phrase or "").strip()
        text = re.split(r"(?:然后|再|顺便|但|不过|附近|别|不想|找个地方|安排)", text)[0].strip()
        text = re.sub(r"^(点|些|个|一顿|一份)", "", text)
        text = re.sub(r"(的|一点|一些|一顿|一份)$", "", text).strip()
        return text

    def _compact_food_text(self, raw_text: str) -> str:
        text = re.sub(r"[，。,.!?；;].*$", "", raw_text or "").strip()
        text = re.sub(r"^(晚上|今天|这周末|周末|想吃|想喝|吃点|喝点)", "", text).strip()
        return text if 2 <= len(text) <= 18 else ""

    def _has_food_signal(self, text: str) -> bool:
        for key in ("known_dish_keywords", "ingredient_keywords", "cooking_method_keywords", "flavor_keywords", "form_keywords"):
            values = self.semantics.get(key) or {}
            if any(self._keyword_allowed_for_attribute(key, keyword) and keyword in text for keyword in values.keys()):
                return True
        return False

    def _keyword_hits(self, text: str, key: str) -> List[str]:
        mapping = self.semantics.get(key) or {}
        if not isinstance(mapping, dict):
            return []
        hits: List[str] = []
        for keyword, normalized in mapping.items():
            if not self._keyword_allowed_for_attribute(key, keyword):
                continue
            if keyword in text:
                hits.append(str(normalized))
        return _dedupe_strings(hits)

    def _keyword_allowed_for_attribute(self, key: str, keyword: str) -> bool:
        if len(str(keyword)) > 1:
            return True
        return key == "flavor_keywords"

    def _should_add_known_dish(self, keyword: str, config: Dict[str, Any], raw_terms: List[str]) -> bool:
        if config.get("generic_method") or config.get("generic_form") or config.get("generic_ingredient"):
            return keyword in raw_terms
        if keyword in raw_terms:
            return True
        for term in raw_terms:
            if keyword in term and term != keyword:
                return not (self._looks_like_long_tail(term) and self._has_specific_ingredient_or_flavor(term))
        return not raw_terms

    def _looks_like_long_tail(self, term: str) -> bool:
        signal_groups = 0
        for key in ("ingredient_keywords", "cooking_method_keywords", "flavor_keywords", "form_keywords"):
            mapping = self.semantics.get(key) or {}
            if any(keyword in term for keyword in mapping.keys()):
                signal_groups += 1
        return len(term) >= 4 and signal_groups >= 2

    def _has_specific_ingredient_or_flavor(self, term: str) -> bool:
        ingredients = self.semantics.get("ingredient_keywords") or {}
        flavors = self.semantics.get("flavor_keywords") or {}
        return any(keyword in term for keyword in ingredients.keys()) or any(keyword in term for keyword in flavors.keys())

    def _derive_long_tail_attributes(
        self,
        raw_terms: List[str],
        parent_categories: List[str],
        ingredients: List[str],
        cooking_methods: List[str],
        flavors: List[str],
        forms: List[str],
        scenes: List[str],
    ) -> None:
        joined = " ".join(raw_terms)
        if "糖葫芦" in joined:
            parent_categories.extend(["DESSERT", "SNACK", "LONG_TAIL_SNACK"])
            forms.extend(["糖葫芦", "小吃"])
            scenes.append("网红小吃")
            flavors.append("甜")
        if "奶皮子" in joined:
            ingredients.append("奶皮子")
            flavors.append("奶香")
            parent_categories.extend(["DESSERT", "SNACK"])
        if "巴斯克" in joined:
            parent_categories.append("DESSERT")
            forms.extend(["甜品", "蛋糕", "巴斯克"])
        if "拌面" in joined or "面" in joined:
            parent_categories.append("NOODLES")
            forms.extend(["面", "主食"])
        if "藤椒" in joined:
            flavors.extend(["藤椒", "麻"])
        if "碳烤" in joined or "炭烤" in joined:
            parent_categories.append("BBQ")
            cooking_methods.extend(["炭烤", "烧烤"])
            forms.append("烤物")

    def _derive_parent_categories(
        self,
        parent_categories: List[str],
        cooking_methods: List[str],
        forms: List[str],
        flavors: List[str],
        raw_terms: List[str],
    ) -> None:
        if {"烧烤", "炭烤"} & set(cooking_methods):
            parent_categories.append("BBQ")
        if {"甜品", "蛋糕", "巴斯克"} & set(forms):
            parent_categories.append("DESSERT")
        if {"小吃", "糖葫芦"} & set(forms):
            parent_categories.append("SNACK")
        if {"面", "主食"} & set(forms):
            parent_categories.append("NOODLES")
        if {"清淡", "低脂", "低卡"} & set(flavors) or any(term in {"清淡", "轻食", "低卡", "低脂"} for term in raw_terms):
            parent_categories.append("LIGHT_MEAL")
        if not parent_categories and raw_terms:
            parent_categories.append("UNKNOWN_FOOD")

    def _needs_child_food(self, raw_text: str, canonical_tags: set[str], parent_categories: List[str], flavors: List[str]) -> bool:
        with_child = bool(canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "CHILD_AGE_PRIMARY", "FAMILY_OUTING"})
        heavy_food = bool(set(parent_categories) & {"CRAYFISH", "HOTPOT", "BBQ", "LAMB", "SEAFOOD"})
        spicy = bool(set(flavors) & {"辣", "麻辣", "藤椒", "麻", "重口"}) or "辣" in raw_text
        return with_child and (heavy_food or spicy)

    def _needs_non_spicy(self, raw_text: str, canonical_tags: set[str], child_food_required: bool, parent_categories: List[str], flavors: List[str]) -> bool:
        explicit = any(token in raw_text for token in ("不能吃辣", "不要辣", "不吃辣", "不辣", "别辣"))
        spicy_or_heavy = bool(set(parent_categories) & {"CRAYFISH", "HOTPOT", "BBQ"}) or bool(set(flavors) & {"辣", "麻辣", "藤椒", "麻", "重口"})
        return explicit or "NON_SPICY_REQUIRED" in canonical_tags or (child_food_required and spicy_or_heavy)

    def _retrieval_mode(
        self,
        known_dish_ids: List[str],
        raw_terms: List[str],
        ingredients: List[str],
        cooking_methods: List[str],
        flavors: List[str],
        forms: List[str],
        scenes: List[str],
    ) -> str:
        has_known = bool(known_dish_ids)
        has_attributes = bool(ingredients or cooking_methods or flavors or forms)
        has_long_tail = any(self._looks_like_long_tail(term) for term in raw_terms)
        if has_known and has_long_tail:
            return "mixed"
        if has_known:
            return "known_dish"
        if raw_terms or has_attributes:
            return "long_tail_attribute"
        return "unknown"

    def _fallback_query_text(
        self,
        raw_terms: List[str],
        ingredients: List[str],
        cooking_methods: List[str],
        flavors: List[str],
        forms: List[str],
        scenes: List[str],
    ) -> str:
        return " ".join(_dedupe_strings([*raw_terms, *ingredients, *cooking_methods, *flavors, *forms, *scenes]))

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
        dining_preference: Dict[str, Any],
        canonical_tags: set[str],
        deterministic: FoodIntent,
    ) -> FoodIntent:
        try:
            payload = self.llm_client.generate_json(
                system_prompt=_FOOD_SYSTEM_PROMPT,
                user_prompt=self._llm_user_prompt(raw_text, dining_preference, canonical_tags, deterministic),
                temperature=0.1,
                max_tokens=700,
            )
            parsed = FoodIntent.parse_payload(payload)
            return self._merge_food_intents(deterministic, parsed)
        except Exception:
            return deterministic

    def _merge_food_intents(self, base: FoodIntent, supplement: FoodIntent) -> FoodIntent:
        payload = base.to_dict()
        supplement_payload = supplement.to_dict()
        for key in (
            "raw_terms",
            "known_dish_ids",
            "parent_categories",
            "ingredients",
            "cooking_methods",
            "flavors",
            "forms",
            "scenes",
            "specific_tags_from_existing_taxonomy",
        ):
            payload[key] = _dedupe_strings(list(payload.get(key) or []) + list(supplement_payload.get(key) or []))
        payload["fallback_query_text"] = self._fallback_query_text(
            payload["raw_terms"],
            payload["ingredients"],
            payload["cooking_methods"],
            payload["flavors"],
            payload["forms"],
            payload["scenes"],
        )
        payload["retrieval_mode"] = self._retrieval_mode(
            payload["known_dish_ids"],
            payload["raw_terms"],
            payload["ingredients"],
            payload["cooking_methods"],
            payload["flavors"],
            payload["forms"],
            payload["scenes"],
        )
        payload["child_food_required"] = bool(base.child_food_required or supplement.child_food_required)
        payload["non_spicy_required"] = bool(base.non_spicy_required or supplement.non_spicy_required)
        payload["low_calorie_required"] = bool(base.low_calorie_required or supplement.low_calorie_required)
        return FoodIntent.parse_payload(payload, fallback_on_error=True, **base.to_dict())

    def _llm_user_prompt(
        self,
        raw_text: str,
        dining_preference: Dict[str, Any],
        canonical_tags: set[str],
        deterministic: FoodIntent,
    ) -> str:
        return (
            "只解析食物语义，不推荐餐厅，不扫描 POI，不编造 dish_id。\n"
            f"用户原文：{raw_text}\n"
            f"已有 dining_preference：{dining_preference}\n"
            f"canonical_tags：{sorted(canonical_tags)}\n"
            f"规则结果：{deterministic.to_dict()}\n"
            f"known_dish_ids 只能从 {sorted(KNOWN_DISH_IDS)} 选择；未知长尾菜品只输出 attributes 并保留 raw_terms。"
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


_FOOD_SYSTEM_PROMPT = (
    "你是 LifePilot 的 FoodSemanticAgent。你只负责把用户食物表达解析成 FoodIntent JSON，"
    "不得推荐餐厅，不得读取或扫描 POI，不得输出推理链。raw_terms 必须保留用户原始食物词；"
    "长尾食物不要编造专属 dish_id，只输出 ingredients/cooking_methods/flavors/forms/scenes。"
)
