from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.core.data_paths import MOCK_POIS_PATH
from app.rules.recommendation_taxonomy import TAG_DEFINITIONS
from app.schemas.internal_intelligence import FoodIntent, LatentIntent, MachineIntent, RecommendationExplanation


SENSITIVE_API_KEY_LABEL = "API" + " Key"
SENSITIVE_API_KEY_LOWER = "api" + " key"


class ExplanationAgent:
    """Generate optional user-visible recommendation explanations.

    The agent only uses structured inputs already produced by deterministic
    services. It never exposes prompts, raw LLM output, or debug payloads.
    """

    def __init__(self, poi_feature_store: Optional[Any] = None, llm_client: Optional[Any] = None) -> None:
        self.poi_feature_store = poi_feature_store
        self.llm_client = llm_client
        self._poi_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def explain(
        self,
        *,
        final_plan_contract: Dict[str, Any],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        latent_intent: Optional[Any] = None,
        food_intent: Optional[Any] = None,
        machine_intent: Optional[Any] = None,
        selected_candidates: Optional[Dict[str, Any]] = None,
        critic_reports: Optional[Iterable[Any]] = None,
        verifier_notes: Optional[Iterable[Any]] = None,
        plan_critic_notes: Optional[Iterable[Any]] = None,
    ) -> RecommendationExplanation:
        canonical_tags = self._canonical_tags(latent_intent, machine_intent, user_goal, constraints)
        food_payload = self._food_payload(food_intent, machine_intent)
        deterministic = self._fallback_explanation(
            final_plan_contract,
            canonical_tags,
            food_payload,
            selected_candidates or {},
            list(critic_reports or []),
            list(verifier_notes or []),
            list(plan_critic_notes or []),
        )
        llm_explanation = self._try_llm_explanation(
            deterministic,
            final_plan_contract,
            canonical_tags,
            food_payload,
            selected_candidates or {},
            list(critic_reports or []),
        )
        return llm_explanation or deterministic

    def _fallback_explanation(
        self,
        plan: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
        selected_candidates: Dict[str, Any],
        critic_reports: List[Any],
        verifier_notes: List[Any],
        plan_critic_notes: List[Any],
    ) -> RecommendationExplanation:
        why_this = self._why_this_plan(plan, canonical_tags, food_payload)
        why_selected = self._why_selected(plan, canonical_tags, food_payload, selected_candidates)
        why_not = self._why_not_selected(critic_reports)
        risks = self._risk_reminders(plan, canonical_tags, verifier_notes, plan_critic_notes)
        addons = self._addon_suggestions(canonical_tags, food_payload)
        assumptions = self._assumptions(plan, canonical_tags, food_payload)
        payload = {
            "why_this_plan": why_this[:5],
            "why_selected": why_selected[:8],
            "why_not_selected": why_not[:6],
            "risk_reminders": risks[:6],
            "addon_suggestions": addons[:8],
            "assumption_notes": assumptions[:5],
        }
        return RecommendationExplanation.parse_payload(payload, fallback_on_error=True, **payload)

    def _why_this_plan(self, plan: Dict[str, Any], canonical_tags: set[str], food_payload: Dict[str, Any]) -> List[str]:
        reasons: List[str] = []
        if canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "FAMILY_OUTING"}:
            reasons.append("按亲子出行处理，优先少排队、低强度、厕所和休息点。")
        if "AVOID_LONG_QUEUE" in canonical_tags:
            reasons.append("已把排队风险作为核心取舍，优先可预约或等待更短的节点。")
        if "NEARBY_REQUIRED" in canonical_tags:
            reasons.append("路线按就近和少转场处理，避免把时间花在路上。")
        if "SHORT_DURATION" in canonical_tags:
            reasons.append("时间窗口较短，已压缩为少节点、少转场的安排。")
        if canonical_tags & {"ANNIVERSARY", "CEREMONIAL", "ROMANTIC"}:
            reasons.append("纪念日场景补了拍照、仪式感和相对安静的体验。")
        if canonical_tags & {"LOW_CALORIE_REQUIRED", "LIGHT_MEAL_REQUIRED"}:
            reasons.append("餐饮按低油、清淡和饭后轻松走走来取舍。")
        if canonical_tags & {"STRESS_RELIEF", "HEALING"}:
            reasons.append("散心场景优先低刺激、低人流和低决策成本。")
        if "SPORTS" in canonical_tags:
            reasons.append("运动节点后预留补水和轻餐饮配套。")
        food_reason = self._food_reason(food_payload)
        if food_reason:
            reasons.append(food_reason)
        if not reasons:
            reasons.append("整体按时间窗口、预算、路线和当前模拟状态做了可执行性取舍。")
        return _dedupe(reasons)

    def _food_reason(self, food_payload: Dict[str, Any]) -> str:
        raw_terms = [str(term) for term in food_payload.get("raw_terms") or []]
        categories = set(str(item) for item in food_payload.get("parent_categories") or [])
        dishes = set(str(item) for item in food_payload.get("known_dish_ids") or [])
        ingredients = [str(item) for item in food_payload.get("ingredients") or []]
        methods = [str(item) for item in food_payload.get("cooking_methods") or []]
        flavors = [str(item) for item in food_payload.get("flavors") or []]
        forms = [str(item) for item in food_payload.get("forms") or []]
        if food_payload.get("retrieval_mode") == "long_tail_attribute":
            if raw_terms:
                return f"把“{raw_terms[0]}”按“{self._join_attrs(ingredients + methods + forms + flavors)}”做长尾属性匹配。"
            return f"餐饮按“{self._join_attrs(ingredients + methods + forms + flavors)}”做长尾属性匹配。"
        if "DISH_CRAYFISH" in dishes or "CRAYFISH" in categories:
            return "餐饮识别为小龙虾需求，同时保留不辣菜和解辣饮品选项。"
        if "DISH_HOTPOT" in dishes or "HOTPOT" in categories:
            return "餐饮识别为火锅需求，带孩子时优先清汤、不辣和可预约选项。"
        if "DISH_BBQ" in dishes or "BBQ" in categories:
            return "餐饮识别为烧烤/烤物需求，优先匹配创意烤物和排队风险较低的店。"
        if "LIGHT_MEAL" in categories or "DISH_LIGHT_MEAL" in dishes:
            return "餐饮识别为清淡/轻食需求，优先低油和健康选项。"
        if "DESSERT" in categories or "SNACK" in categories:
            return "餐饮识别为甜品/小吃需求，优先短停留、顺路和低负担搭配。"
        return ""

    def _why_selected(
        self,
        plan: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
        selected_candidates: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        selected_pois = selected_candidates.get("selected_pois") if isinstance(selected_candidates, dict) else {}
        for step in plan.get("timeline") or []:
            if step.get("type") == "transport" or not step.get("poi_id"):
                continue
            poi = (selected_pois or {}).get(step.get("type")) or self._poi_index().get(str(step.get("poi_id"))) or {}
            feature = self._feature(poi or step)
            reason = self._selected_reason(step, feature, canonical_tags, food_payload)
            selected.append(
                {
                    "poi_id": step.get("poi_id"),
                    "title": step.get("title"),
                    "slot": step.get("type"),
                    "reason": reason,
                }
            )
        return selected

    def _selected_reason(self, step: Dict[str, Any], feature: Dict[str, Any], canonical_tags: set[str], food_payload: Dict[str, Any]) -> str:
        step_type = str(step.get("type") or "")
        menu = self._group(feature, "menu_features")
        family = self._group(feature, "family_features")
        queue = self._group(feature, "queue_features")
        experience = self._group(feature, "experience_features")
        parts: List[str] = []
        if step_type == "restaurant" and self._has_food_need(food_payload):
            score = self._food_match_score(menu, self._feature_text(step, feature), food_payload)
            if score >= 0.5:
                parts.append("餐饮语义匹配度高")
            elif score >= 0.2:
                parts.append("餐饮类别和部分属性匹配")
        if canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL"}:
            if self._num(family.get("child_food_score"), 0.5) >= 0.6 or menu.get("has_child_friendly_food"):
                parts.append("有儿童可食或家庭友好选项")
            if menu.get("has_non_spicy"):
                parts.append("有不辣备选")
        if "AVOID_LONG_QUEUE" in canonical_tags and self._num(queue.get("queue_risk"), 0.5) <= 0.55:
            parts.append("排队风险相对可控")
        if canonical_tags & {"STRESS_RELIEF", "HEALING"} and self._num(experience.get("relaxation_score"), 0.5) >= 0.6:
            parts.append("更适合低刺激放松")
        if canonical_tags & {"ANNIVERSARY", "CEREMONIAL"} and max(self._num(experience.get("photo_score"), 0.45), self._num(experience.get("premium_score"), 0.45)) >= 0.6:
            parts.append("适合拍照或有仪式感")
        if not parts:
            parts.append("符合当前时间、预算和路线可执行性")
        return "，".join(_dedupe(parts)) + "。"

    def _why_not_selected(self, critic_reports: List[Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for report in critic_reports:
            payload = report.to_dict() if hasattr(report, "to_dict") else report if isinstance(report, dict) else {}
            if float(payload.get("score_delta") or 0) >= 0:
                continue
            items.append(
                {
                    "poi_id": payload.get("poi_id"),
                    "decision": payload.get("decision"),
                    "reason": self._safe_text(payload.get("user_facing_reason") or "该候选存在适配风险，因此降为备选。"),
                    "reason_codes": [str(code) for code in payload.get("reason_codes") or []][:5],
                }
            )
        return items

    def _risk_reminders(
        self,
        plan: Dict[str, Any],
        canonical_tags: set[str],
        verifier_notes: List[Any],
        plan_critic_notes: List[Any],
    ) -> List[str]:
        reminders: List[str] = []
        for risk in plan.get("risks") or []:
            message = risk.get("message") or risk.get("description") or risk.get("mitigation")
            if message:
                reminders.append(self._safe_text(message))
        for note in verifier_notes:
            if isinstance(note, str):
                reminders.append(self._safe_text(note))
        for note in plan_critic_notes:
            if isinstance(note, str):
                reminders.append(self._safe_text(note))
            elif isinstance(note, dict) and note.get("message"):
                reminders.append(self._safe_text(note.get("message")))
        if "AVOID_LONG_QUEUE" in canonical_tags:
            reminders.append("热门时段仍建议提前预约或先刷新模拟排队状态。")
        if canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL"}:
            reminders.append("带孩子出门建议现场确认厕所、休息点和不辣菜。")
        if "SHORT_DURATION" in canonical_tags:
            reminders.append("短时行程不建议强塞多个地点，优先保留一个可执行节点。")
        return _dedupe([item for item in reminders if item])[:6]

    def _addon_suggestions(self, canonical_tags: set[str], food_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []

        def add(kind: str, label: str, reason: str) -> None:
            if kind not in {item.get("type") for item in suggestions}:
                suggestions.append({"type": kind, "label": label, "reason": reason})

        if "AVOID_LONG_QUEUE" in canonical_tags:
            add("reservation", "提前预约", "降低排队和等位风险")
        if canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL"}:
            add("wet_tissue", "湿巾", "小龙虾、火锅、烧烤或亲子场景更方便")
            add("child_non_spicy_food", "儿童不辣菜", "避免孩子只能吃重辣或重油菜")
            add("rest_area", "休息点", "减少孩子疲劳和临时决策")
        if food_payload.get("child_food_required") or food_payload.get("non_spicy_required"):
            add("non_spicy_option", "不辣备选", "餐饮节点优先确认清汤、蒜蓉或清淡菜")
        if food_payload.get("low_calorie_required") or "LOW_CALORIE_REQUIRED" in canonical_tags:
            add("low_calorie_option", "低脂少油备选", "兼顾减脂和正餐体验")
        if canonical_tags & {"ANNIVERSARY", "CEREMONIAL"}:
            add("flower", "花束", "补足纪念日仪式感")
            add("photo_spot", "拍照点", "保留可记录的节点")
        if canonical_tags & {"SPORTS"}:
            add("hydration", "补水饮品", "运动后降低疲劳感")
        if "DISH_CRAYFISH" in set(food_payload.get("known_dish_ids") or []) or "CRAYFISH" in set(food_payload.get("parent_categories") or []):
            add("cool_drink", "解辣饮品", "搭配小龙虾更稳妥")
            add("wet_tissue", "湿巾", "吃小龙虾更方便")
        if "DISH_HOTPOT" in set(food_payload.get("known_dish_ids") or []) or "HOTPOT" in set(food_payload.get("parent_categories") or []):
            add("clear_soup", "清汤锅", "带孩子或不能吃辣时优先确认")
        return suggestions

    def _assumptions(self, plan: Dict[str, Any], canonical_tags: set[str], food_payload: Dict[str, Any]) -> List[str]:
        notes = ["余位、排队、路线和天气均以当前 Mock 数字孪生状态为准。"]
        if food_payload.get("retrieval_mode") == "long_tail_attribute":
            notes.append("长尾食物按原词和属性组合检索，不强行编造专属菜品 ID。")
        if "NEARBY_REQUIRED" in canonical_tags:
            notes.append("就近偏好按当前区域和单段转场时间近似处理。")
        if plan.get("verifier_result", {}).get("status") == "warning":
            notes.append("可执行性检查提示风险时，方案仍可展示但建议保留备选。")
        return notes

    def _try_llm_explanation(
        self,
        fallback: RecommendationExplanation,
        plan: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
        selected_candidates: Dict[str, Any],
        critic_reports: List[Any],
    ) -> Optional[RecommendationExplanation]:
        if not self._llm_enabled():
            return None
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是LifePilot中文解释模块。只能基于给定结构化字段生成用户可见解释。"
                    "不得编造POI信息、菜单、路线、余位、天气。不得输出prompt、raw output、debug、chain-of-thought或密钥。"
                    "只输出符合RecommendationExplanation字段的JSON对象。"
                ),
                user_prompt=(
                    "字段：why_this_plan(list[str]), why_selected(list[object]), why_not_selected(list[object]), "
                    "risk_reminders(list[str]), addon_suggestions(list[object]), assumption_notes(list[str])。"
                    "每条中文不超过45字。"
                    f"plan_summary={self._plan_summary(plan)}。"
                    f"canonical_tags={sorted(canonical_tags)}。"
                    f"food_intent={self._compact_food(food_payload)}。"
                    f"selected_candidates={self._selected_summary(selected_candidates)}。"
                    f"critic_reports={self._compact_critic(critic_reports)}。"
                    f"fallback={fallback.to_dict()}。"
                ),
                temperature=0.2,
                max_tokens=1200,
            )
            explanation = RecommendationExplanation.parse_payload(data)
            if not explanation.why_this_plan:
                return fallback
            return self._sanitize_explanation(explanation)
        except Exception:
            return None

    def _sanitize_explanation(self, explanation: RecommendationExplanation) -> RecommendationExplanation:
        payload = explanation.to_dict()
        for key in ("why_this_plan", "risk_reminders", "assumption_notes"):
            payload[key] = [self._safe_text(item) for item in payload.get(key) or [] if self._safe_text(item)]
        for key in ("why_selected", "why_not_selected", "addon_suggestions"):
            cleaned = []
            for item in payload.get(key) or []:
                if isinstance(item, dict):
                    cleaned.append({str(k): self._safe_text(v) if isinstance(v, str) else v for k, v in item.items()})
            payload[key] = cleaned
        return RecommendationExplanation.parse_payload(payload, fallback_on_error=True, **payload)

    def _llm_enabled(self) -> bool:
        if self.llm_client is None or not hasattr(self.llm_client, "generate_json"):
            return False
        snapshot = getattr(self.llm_client, "snapshot", None)
        if callable(snapshot):
            try:
                return bool(snapshot().get("enabled"))
            except Exception:
                return False
        return True

    def _canonical_tags(self, latent_intent: Optional[Any], machine_intent: Optional[Any], user_goal: Dict[str, Any], constraints: Dict[str, Any]) -> set[str]:
        tags: set[str] = set()
        try:
            if isinstance(latent_intent, LatentIntent):
                tags.update(tag.value for tag in latent_intent.canonical_tag_set.canonical_tags)
            elif isinstance(latent_intent, dict):
                tags.update(str(tag) for tag in (latent_intent.get("canonical_tag_set") or {}).get("canonical_tags") or [])
        except Exception:
            pass
        try:
            if isinstance(machine_intent, MachineIntent):
                tags.update(tag.value for tag in machine_intent.canonical_tags)
            elif isinstance(machine_intent, dict):
                tags.update(str(tag) for tag in machine_intent.get("canonical_tags") or [])
        except Exception:
            pass
        tags.update(str(tag) for tag in user_goal.get("intent_tags") or [])
        tags.update(str(tag) for tag in constraints.get("must_have") or [])
        if constraints.get("child_friendly_required"):
            tags.add("WITH_CHILD")
        if constraints.get("queue_tolerance") == "low":
            tags.add("AVOID_LONG_QUEUE")
        return tags

    def _food_payload(self, food_intent: Optional[Any], machine_intent: Optional[Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        try:
            if isinstance(food_intent, FoodIntent):
                payload.update(food_intent.to_dict())
            elif isinstance(food_intent, dict):
                payload.update(FoodIntent.parse_payload(food_intent, fallback_on_error=True, **food_intent).to_dict())
        except Exception:
            pass
        if not payload:
            try:
                if isinstance(machine_intent, MachineIntent):
                    payload.update((machine_intent.retrieval_plan or {}).get("food_match") or {})
                elif isinstance(machine_intent, dict):
                    payload.update((machine_intent.get("retrieval_plan") or {}).get("food_match") or {})
            except Exception:
                pass
        return payload

    def _feature(self, item: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if self.poi_feature_store is None:
            merged = {}
        else:
            try:
                merged = self.poi_feature_store.for_item(item) or {}
            except Exception:
                merged = {}
        for key in ("menu_features", "family_features", "queue_features", "physical_features", "experience_features", "child_features"):
            if isinstance(item.get(key), dict):
                existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
                merged[key] = {**existing, **item[key]}
        if item.get("tags") and not merged.get("semantic_tags"):
            merged["semantic_tags"] = list(item.get("tags") or [])
        return merged

    def _poi_index(self) -> Dict[str, Dict[str, Any]]:
        if self._poi_cache is not None:
            return self._poi_cache
        self._poi_cache = {}
        store = getattr(self.poi_feature_store, "store", None)
        if store is None:
            return self._poi_cache
        try:
            pois = store.read(MOCK_POIS_PATH, {"pois": []}).get("pois", [])
        except Exception:
            pois = []
        self._poi_cache = {str(item.get("poi_id")): item for item in pois if isinstance(item, dict) and item.get("poi_id")}
        return self._poi_cache

    def _group(self, feature: Dict[str, Any], key: str) -> Dict[str, Any]:
        value = feature.get(key) if isinstance(feature, dict) else {}
        return value if isinstance(value, dict) else {}

    def _feature_text(self, step: Dict[str, Any], feature: Dict[str, Any]) -> str:
        parts = [str(step.get("title") or ""), str(step.get("type") or "")]
        parts.extend(str(tag) for tag in feature.get("semantic_tags") or [])
        menu = self._group(feature, "menu_features")
        for key in ("signature_dishes", "raw_food_terms", "ingredients", "cooking_methods", "flavors", "forms", "scenes", "dish_ids", "parent_categories"):
            parts.extend(str(value) for value in menu.get(key) or [])
        return " ".join(part for part in parts if part)

    def _has_food_need(self, food_payload: Dict[str, Any]) -> bool:
        if not isinstance(food_payload, dict) or food_payload.get("retrieval_mode") == "unknown":
            return False
        food_keys = ("raw_terms", "known_dish_ids", "parent_categories", "ingredients", "cooking_methods", "flavors", "forms")
        return any(food_payload.get(key) for key in food_keys)

    def _food_match_score(self, menu: Dict[str, Any], text: str, food_payload: Dict[str, Any]) -> float:
        raw = self._overlap(food_payload.get("raw_terms"), menu.get("raw_food_terms"), text)
        dish = self._overlap(food_payload.get("known_dish_ids"), menu.get("dish_ids"), text)
        category = self._overlap(food_payload.get("parent_categories"), menu.get("parent_categories"), text)
        attrs = [
            self._overlap(food_payload.get("ingredients"), menu.get("ingredients"), text),
            self._overlap(food_payload.get("cooking_methods"), menu.get("cooking_methods"), text),
            self._overlap(food_payload.get("flavors"), menu.get("flavors"), text),
            self._overlap(food_payload.get("forms"), menu.get("forms"), text),
        ]
        return max(raw, dish * 0.9, category * 0.45, (sum(attrs) / max(1, len(attrs))) * 0.75)

    def _overlap(self, wanted: Any, existing: Any, text: str) -> float:
        values = [str(value) for value in wanted or [] if str(value).strip()]
        if not values:
            return 0.0
        existing_values = set(str(value) for value in existing or [] if str(value).strip())
        hits = sum(1 for value in values if value in existing_values or value in text)
        return hits / max(1, len(values))

    def _num(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _join_attrs(self, values: List[str]) -> str:
        clean = _dedupe([str(value) for value in values if str(value).strip()])
        return " + ".join(clean[:5]) if clean else "原词 + 食物属性"

    def _plan_summary(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "plan_id": plan.get("plan_id"),
            "status": plan.get("status"),
            "verifier_status": (plan.get("verifier_result") or {}).get("status"),
            "timeline": [
                {"type": step.get("type"), "title": step.get("title"), "poi_id": step.get("poi_id")}
                for step in (plan.get("timeline") or [])
                if step.get("type") != "transport"
            ],
            "risks": [
                {"type": risk.get("type"), "message": risk.get("message") or risk.get("description")}
                for risk in (plan.get("risks") or [])[:5]
            ],
        }

    def _selected_summary(self, selected_candidates: Dict[str, Any]) -> List[Dict[str, Any]]:
        selected = selected_candidates.get("selected_pois") if isinstance(selected_candidates, dict) else {}
        return [
            {"role": role, "poi_id": poi.get("poi_id"), "name": poi.get("name"), "category": poi.get("category")}
            for role, poi in (selected or {}).items()
            if isinstance(poi, dict)
        ]

    def _compact_food(self, food_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in food_payload.items() if key in {"raw_terms", "known_dish_ids", "parent_categories", "ingredients", "cooking_methods", "flavors", "forms", "scenes", "retrieval_mode", "child_food_required", "non_spicy_required", "low_calorie_required"}}

    def _compact_critic(self, critic_reports: List[Any]) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for report in critic_reports:
            payload = report.to_dict() if hasattr(report, "to_dict") else report if isinstance(report, dict) else {}
            compact.append(
                {
                    "poi_id": payload.get("poi_id"),
                    "decision": payload.get("decision"),
                    "score_delta": payload.get("score_delta"),
                    "reason_codes": payload.get("reason_codes", [])[:5],
                }
            )
        return compact[:8]

    def _safe_text(self, value: Any) -> str:
        text = str(value or "")
        blocked = ("prompt", "raw output", "chain-of-thought", SENSITIVE_API_KEY_LOWER, SENSITIVE_API_KEY_LABEL, "debug", "completion")
        for token in blocked:
            text = text.replace(token, "")
        replacements = {
            "MockAPI": "模拟状态",
            "mock_api": "模拟状态",
            "Verifier": "可执行性检查",
            "PlanB": "备选方案",
            "debug payload": "",
            "chain of thought": "",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        for key, definition in sorted(TAG_DEFINITIONS.items(), key=lambda item: len(item[0]), reverse=True):
            if definition.user_visible and key in text:
                text = text.replace(key, definition.display_label)
        return text.strip()


def _dedupe(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
