from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.core.data_paths import MOCK_POIS_PATH
from app.schemas.internal_intelligence import FoodIntent, LatentIntent, MachineIntent, PlanCriticReport


class PlanCriticAgent:
    """Semantic critic for verified PlanContract objects."""

    def __init__(self, poi_feature_store: Optional[Any] = None, llm_client: Optional[Any] = None) -> None:
        self.poi_feature_store = poi_feature_store
        self.llm_client = llm_client
        self._poi_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def review(
        self,
        *,
        plan_contract: Dict[str, Any],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        latent_intent: Optional[Any] = None,
        food_intent: Optional[Any] = None,
        machine_intent: Optional[Any] = None,
        verifier_result: Optional[Dict[str, Any]] = None,
    ) -> PlanCriticReport:
        canonical_tags = self._canonical_tags(latent_intent, machine_intent, user_goal, constraints)
        food_payload = self._food_payload(food_intent, machine_intent)
        issues = self._deterministic_issues(plan_contract, canonical_tags, food_payload)
        verifier_notes = self._verifier_notes(verifier_result or plan_contract.get("verifier_result") or {})
        severity = self._severity(issues, verifier_notes)
        payload = {
            "pass": not issues and severity in {"none", "low"},
            "issues": issues,
            "repair_instructions": self._repair_instructions(issues),
            "severity": severity,
            "verifier_related_notes": verifier_notes,
        }
        return PlanCriticReport.parse_payload(payload, fallback_on_error=True, **payload)

    def _deterministic_issues(
        self,
        plan: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        timeline = plan.get("timeline") or []
        transport_count = len([step for step in timeline if step.get("type") == "transport"])
        visit_steps = [step for step in timeline if step.get("poi_id") and step.get("type") != "transport"]

        if "SHORT_DURATION" in canonical_tags and len(visit_steps) >= 4:
            issues.append(self._issue("TOO_MANY_STOPS_FOR_SHORT_DURATION", "medium", None, None, "短时段内停留点偏多，决策和转场成本偏高。", "reorder_slots"))
        if "SHORT_DURATION" in canonical_tags and transport_count > 2:
            issues.append(self._issue("TOO_MANY_TRANSFERS", "medium", None, None, "短时段内转场偏多。", "reorder_slots"))

        has_food_need = self._has_food_need(food_payload)
        restaurant_checked = False
        for step in visit_steps:
            feature = self._feature_for_step(step)
            menu = self._group(feature, "menu_features")
            family = self._group(feature, "family_features")
            child = self._group(feature, "child_features")
            queue = self._group(feature, "queue_features")
            physical = self._group(feature, "physical_features")
            experience = self._group(feature, "experience_features")
            step_type = str(step.get("type") or "")
            poi_id = str(step.get("poi_id") or "")

            if canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "FAMILY_OUTING", "CHILD_FOOD_REQUIRED"}:
                if step_type == "restaurant":
                    child_food_score = max(self._num(family.get("child_food_score"), 0.5), 0.8 if menu.get("has_child_friendly_food") else 0.0)
                    if child_food_score < 0.45:
                        issues.append(self._issue("CHILD_FOOD_MISSING", "high", step.get("step_id"), poi_id, "餐饮节点缺少明确儿童可食选项。", "replace_slot"))
                    if self._num(menu.get("spicy_level"), 0.3) >= 0.72 and not bool(menu.get("has_non_spicy")):
                        issues.append(self._issue("NON_SPICY_OPTION_MISSING", "high", step.get("step_id"), poi_id, "带孩子场景下缺少不辣备选。", "replace_slot"))
                elif step_type == "activity":
                    child_score = self._num(child.get("child_friendly_score"), self._num(experience.get("family_friendly_score"), 0.5))
                    if child_score < 0.35:
                        issues.append(self._issue("CHILD_ACTIVITY_LOW_FIT", "medium", step.get("step_id"), poi_id, "活动节点亲子适配度偏低。", "replace_slot"))
                    if self._num(physical.get("walking_intensity"), 0.45) >= 0.78:
                        issues.append(self._issue("HIGH_WALKING_LOAD", "medium", step.get("step_id"), poi_id, "活动体力消耗偏高。", "replace_slot"))

            if "AVOID_LONG_QUEUE" in canonical_tags:
                if self._num(queue.get("queue_risk"), 0.45) >= 0.78 or self._num(queue.get("avg_wait_minutes_peak"), 15) > 28:
                    issues.append(self._issue("QUEUE_RISK_TOO_HIGH", "high", step.get("step_id"), poi_id, "节点排队风险高，和“不排队”目标冲突。", "replace_slot"))

            if "LOW_CALORIE_REQUIRED" in canonical_tags and step_type == "restaurant":
                if self._num(menu.get("oiliness_level"), 0.45) >= 0.72 and self._num(menu.get("healthy_option_score"), 0.45) < 0.5:
                    issues.append(self._issue("LOW_CALORIE_MISMATCH", "high", step.get("step_id"), poi_id, "餐饮节点偏重油，低脂/清淡备选不足。", "replace_slot"))

            if canonical_tags & {"STRESS_RELIEF", "HEALING", "AVOID_CROWD", "AVOID_NOISY_PLACE"}:
                noise = self._num(family.get("noise_level"), 0.45)
                relaxation = self._num(experience.get("relaxation_score"), 0.5)
                if noise >= 0.72:
                    issues.append(self._issue("NOISY_FOR_HEALING", "medium", step.get("step_id"), poi_id, "散心场景下节点噪声/刺激偏高。", "replace_slot"))
                if relaxation < 0.32:
                    issues.append(self._issue("LOW_RELAXATION_FIT", "medium", step.get("step_id"), poi_id, "节点放松感偏弱。", "replace_slot"))

            if canonical_tags & {"ANNIVERSARY", "CEREMONIAL", "ROMANTIC"}:
                premium = self._num(experience.get("premium_score"), 0.45)
                photo = self._num(experience.get("photo_score"), 0.45)
                if step_type == "restaurant" and premium < 0.35:
                    issues.append(self._issue("ANNIVERSARY_RESTAURANT_LOW_CEREMONY", "medium", step.get("step_id"), poi_id, "纪念日餐饮仪式感偏弱。", "replace_slot"))
                if step_type in {"activity", "walk"} and max(photo, premium) < 0.35:
                    issues.append(self._issue("ANNIVERSARY_ADDON_OR_PHOTO_MISSING", "low", step.get("step_id"), poi_id, "纪念日缺少拍照/仪式感补充。", "add_addon"))

            if step_type == "restaurant":
                restaurant_checked = True
                if has_food_need and self._food_match_score(menu, self._text(step, feature), food_payload) < 0.15:
                    issues.append(self._issue("FOOD_INTENT_IGNORED", "high", step.get("step_id"), poi_id, "餐饮节点没有满足用户食物表达。", "replace_slot"))

        if has_food_need and not restaurant_checked:
            issues.append(self._issue("MEAL_SLOT_MISSING", "high", None, None, "用户有餐饮需求，但计划中缺少餐饮节点。", "add_addon"))
        return issues[:12]

    def _verifier_notes(self, verifier_result: Dict[str, Any]) -> List[str]:
        notes: List[str] = []
        status = verifier_result.get("status")
        if status == "fail":
            notes.append("Verifier 已判定当前计划不可执行。")
        for check in verifier_result.get("failed_checks") or []:
            notes.append(f"失败检查：{check}")
        for warning in verifier_result.get("warnings") or []:
            notes.append(f"风险提示：{warning}")
        return notes[:8]

    def _repair_instructions(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        instructions: List[Dict[str, Any]] = []
        for issue in issues:
            instructions.append(
                {
                    "issue_code": issue.get("code"),
                    "target_slot": issue.get("step_id"),
                    "preferred_patch_type": issue.get("repair_hint") or "fail",
                    "reason": issue.get("message") or "",
                    "must_reverify": True,
                }
            )
        return instructions

    def _issue(self, code: str, severity: str, step_id: Optional[str], poi_id: Optional[str], message: str, repair_hint: str) -> Dict[str, Any]:
        return {
            "code": code,
            "severity": severity,
            "step_id": step_id,
            "poi_id": poi_id,
            "message": message,
            "repair_hint": repair_hint,
        }

    def _severity(self, issues: List[Dict[str, Any]], verifier_notes: List[str]) -> str:
        if any(issue.get("severity") == "high" for issue in issues):
            return "high"
        if any(issue.get("severity") == "medium" for issue in issues) or verifier_notes:
            return "medium"
        if issues:
            return "low"
        return "none"

    def _canonical_tags(
        self,
        latent_intent: Optional[Any],
        machine_intent: Optional[Any],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> set[str]:
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

    def _feature_for_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        poi_id = str(step.get("poi_id") or "")
        item = self._poi_index().get(poi_id) or {"poi_id": poi_id, "name": step.get("title"), "category": step.get("type")}
        if self.poi_feature_store is None:
            return {}
        try:
            return self.poi_feature_store.for_item(item) or {}
        except Exception:
            try:
                return self.poi_feature_store.get(poi_id) or {}
            except Exception:
                return {}

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

    def _text(self, step: Dict[str, Any], feature: Dict[str, Any]) -> str:
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
        attributes = [
            self._overlap(food_payload.get("ingredients"), menu.get("ingredients"), text),
            self._overlap(food_payload.get("cooking_methods"), menu.get("cooking_methods"), text),
            self._overlap(food_payload.get("flavors"), menu.get("flavors"), text),
            self._overlap(food_payload.get("forms"), menu.get("forms"), text),
        ]
        scene = self._overlap(food_payload.get("scenes"), menu.get("scenes"), text)
        return max(raw, dish * 0.9, category * 0.45, (sum(attributes) / max(1, len(attributes))) * 0.75, scene * 0.3)

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
