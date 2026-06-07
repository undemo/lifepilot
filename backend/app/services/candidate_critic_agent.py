from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.schemas.internal_intelligence import CandidateCriticReport, FoodIntent, LatentIntent, MachineIntent


class CandidateCriticAgent:
    """Top-N semantic critic for already retrieved candidates.

    This agent never loads all POIs and never changes factual status. It only
    inspects candidate objects it receives and returns score deltas.
    """

    def __init__(self, poi_feature_store: Optional[Any] = None, llm_client: Optional[Any] = None, top_n: int = 10) -> None:
        self.poi_feature_store = poi_feature_store
        self.llm_client = llm_client
        self.top_n = max(1, int(top_n or 10))

    def review(
        self,
        *,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        latent_intent: Optional[Any] = None,
        food_intent: Optional[Any] = None,
        machine_intent: Optional[Any] = None,
        top_candidates: Optional[Iterable[Dict[str, Any]]] = None,
        backup_candidates: Optional[Iterable[Dict[str, Any]]] = None,
        top_n: Optional[int] = None,
    ) -> List[CandidateCriticReport]:
        limit = max(1, int(top_n or self.top_n))
        candidates = self._candidate_items(top_candidates or [], backup_candidates or [], limit)
        if not candidates:
            return []
        canonical_tags = self._canonical_tags(latent_intent, machine_intent, user_goal, constraints)
        food_payload = self._food_payload(food_intent, machine_intent)
        deterministic = self._deterministic_reports(candidates, canonical_tags, food_payload)
        llm_reports = self._try_llm_review(candidates, user_goal, constraints, canonical_tags, food_payload, machine_intent)
        if not llm_reports:
            return deterministic
        return self._merge_reports(deterministic, llm_reports)

    def _candidate_items(
        self,
        top_candidates: Iterable[Dict[str, Any]],
        backup_candidates: Iterable[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add(item: Any) -> None:
            if not isinstance(item, dict):
                return
            poi = item.get("poi") if isinstance(item.get("poi"), dict) else item
            poi_id = str(poi.get("poi_id") or "")
            if not poi_id or poi_id in seen or len(items) >= limit:
                return
            seen.add(poi_id)
            items.append(poi)

        for candidate in top_candidates:
            add(candidate)
        for candidate in sorted(
            [item for item in backup_candidates if isinstance(item, dict)],
            key=lambda item: -float(item.get("score") or 0.0),
        ):
            add(candidate)
        return items

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
                tag_set = (latent_intent.get("canonical_tag_set") or {})
                tags.update(str(tag) for tag in tag_set.get("canonical_tags") or [])
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
            tags.update({"WITH_CHILD", "CHILD_FOOD_REQUIRED"})
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
                    payload.update(((machine_intent.get("retrieval_plan") or {}).get("food_match") or {}))
            except Exception:
                pass
        return payload

    def _deterministic_reports(
        self,
        candidates: List[Dict[str, Any]],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
    ) -> List[CandidateCriticReport]:
        reports: List[CandidateCriticReport] = []
        for item in candidates:
            delta, reason_codes, risk_notes = self._deterministic_delta(item, canonical_tags, food_payload)
            decision = self._decision(delta)
            reason = self._user_reason(item, reason_codes, risk_notes)
            payload = {
                "poi_id": str(item.get("poi_id") or "unknown_poi"),
                "decision": decision,
                "score_delta": round(delta, 2),
                "reason_codes": reason_codes,
                "user_facing_reason": reason,
                "risk_notes": risk_notes,
            }
            reports.append(CandidateCriticReport.parse_payload(payload, fallback_on_error=True, **payload))
        return reports

    def _deterministic_delta(
        self,
        item: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
    ) -> tuple[float, List[str], List[str]]:
        delta = 0.0
        reason_codes: List[str] = []
        risk_notes: List[str] = []
        category = str(item.get("category") or "")
        feature = self._feature(item)
        menu = self._group(feature, "menu_features")
        family = self._group(feature, "family_features")
        queue = self._group(feature, "queue_features")
        physical = self._group(feature, "physical_features")
        experience = self._group(feature, "experience_features")
        child = self._group(feature, "child_features")
        text = self._text(item, feature)

        with_child = bool(canonical_tags & {"WITH_CHILD", "CHILD_AGE_PRESCHOOL", "FAMILY_OUTING", "CHILD_FOOD_REQUIRED"})
        if with_child:
            if category == "restaurant":
                child_food_score = max(self._num(family.get("child_food_score"), 0.5), 0.8 if menu.get("has_child_friendly_food") else 0.0)
                if child_food_score < 0.45:
                    delta -= 18
                    reason_codes.append("CHILD_FOOD_MISSING")
                    risk_notes.append("儿童可食选项偏弱")
                if self._num(menu.get("spicy_level"), 0.3) >= 0.7 and not bool(menu.get("has_non_spicy")):
                    delta -= 16
                    reason_codes.append("SPICY_CHILD_RISK")
                    risk_notes.append("偏辣且缺少明确不辣备选")
                if self._num(family.get("noise_level"), 0.5) >= 0.75:
                    delta -= 12
                    reason_codes.append("CHILD_NOISE_RISK")
                    risk_notes.append("噪声水平偏高")
            elif category == "activity":
                if self._num(child.get("child_friendly_score"), self._num(experience.get("family_friendly_score"), 0.5)) < 0.4:
                    delta -= 18
                    reason_codes.append("CHILD_ACTIVITY_LOW_FIT")
                    risk_notes.append("亲子适配度偏低")
                if self._num(physical.get("walking_intensity"), 0.45) >= 0.75:
                    delta -= 12
                    reason_codes.append("HIGH_WALKING_LOAD")
                    risk_notes.append("体力消耗偏高")

        if "AVOID_LONG_QUEUE" in canonical_tags:
            queue_risk = self._num(queue.get("queue_risk"), 0.5)
            peak_wait = self._num(queue.get("avg_wait_minutes_peak"), 16.0)
            if queue_risk >= 0.75 or peak_wait > 25:
                delta -= 22
                reason_codes.append("HIGH_QUEUE_RISK")
                risk_notes.append("排队风险偏高")
            elif queue_risk >= 0.6 or peak_wait > 20:
                delta -= 10
                reason_codes.append("MEDIUM_QUEUE_RISK")
                risk_notes.append("高峰等待时间略长")

        if "LOW_CALORIE_REQUIRED" in canonical_tags and category == "restaurant":
            healthy = self._num(menu.get("healthy_option_score"), 0.45)
            oiliness = self._num(menu.get("oiliness_level"), 0.45)
            spicy = self._num(menu.get("spicy_level"), 0.3)
            if oiliness >= 0.68 and healthy < 0.5:
                delta -= 18
                reason_codes.append("LOW_CALORIE_MISMATCH")
                risk_notes.append("低脂/少油备选偏弱")
            if spicy >= 0.72 and healthy < 0.55:
                delta -= 8
                reason_codes.append("HEAVY_FLAVOR_RISK")

        if canonical_tags & {"ANNIVERSARY", "CEREMONIAL", "ROMANTIC"}:
            premium = self._num(experience.get("premium_score"), 0.45)
            photo = self._num(experience.get("photo_score"), 0.45)
            noise = self._num(family.get("noise_level"), 0.5)
            if category == "restaurant" and premium < 0.4 and noise >= 0.65:
                delta -= 14
                reason_codes.append("ANNIVERSARY_LOW_CEREMONY")
                risk_notes.append("纪念日仪式感偏弱")
            if category == "activity" and max(photo, premium) < 0.4:
                delta -= 8
                reason_codes.append("ANNIVERSARY_LOW_PHOTO_FIT")

        if canonical_tags & {"STRESS_RELIEF", "HEALING", "AVOID_CROWD", "AVOID_NOISY_PLACE"}:
            noise = max(self._num(family.get("noise_level"), 0.45), 0.85 if "KTV" in text or "电玩城" in text else 0.0)
            relaxation = self._num(experience.get("relaxation_score"), 0.5)
            if noise >= 0.7:
                delta -= 18
                reason_codes.append("NOISY_FOR_HEALING")
                risk_notes.append("散心场景下噪声/刺激偏高")
            if self._num(queue.get("queue_risk"), 0.45) >= 0.65:
                delta -= 10
                reason_codes.append("CROWD_RISK")
            if relaxation < 0.35:
                delta -= 12
                reason_codes.append("LOW_RELAXATION_FIT")

        if category == "restaurant" and self._has_food_need(food_payload):
            food_score = self._food_match_score(menu, text, food_payload)
            if food_score < 0.15:
                delta -= 18 if food_payload.get("retrieval_mode") == "long_tail_attribute" else 12
                reason_codes.append("FOOD_INTENT_MISMATCH")
                risk_notes.append("和用户餐饮表达匹配弱")

        return max(-45.0, min(0.0, delta)), _dedupe(reason_codes), _dedupe(risk_notes)

    def _try_llm_review(
        self,
        candidates: List[Dict[str, Any]],
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        canonical_tags: set[str],
        food_payload: Dict[str, Any],
        machine_intent: Optional[Any],
    ) -> List[CandidateCriticReport]:
        if not self._llm_enabled():
            return []
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是LifePilot候选审稿器。只根据给定候选字段、FeatureStore摘要、MachineIntent和FoodIntent判断。"
                    "不得编造POI状态、菜单、路线、余位，不得读取未给出的POI。只输出JSON。"
                    "reports[].decision只能是keep/demote/backup_only/reject；第一版reject会被系统当作大幅降权。"
                    "不要输出推理链、prompt、debug信息或任何密钥。"
                ),
                user_prompt=(
                    "输出格式：{\"reports\":[{\"poi_id\":\"...\",\"decision\":\"keep|demote|backup_only|reject\","
                    "\"score_delta\":0到-35之间的数字,\"reason_codes\":[\"...\"],"
                    "\"user_facing_reason\":\"一句中文原因\",\"risk_notes\":[\"...\"]}]}。"
                    f"用户目标摘要：{user_goal.get('goal_summary')}。"
                    f"约束摘要：party_size={constraints.get('party_size')}, queue={constraints.get('queue_tolerance')}, "
                    f"walking={constraints.get('walking_tolerance')}。"
                    f"canonical_tags={sorted(canonical_tags)}。"
                    f"food_intent={self._compact_food(food_payload)}。"
                    f"machine_intent={self._compact_machine(machine_intent)}。"
                    f"candidates={self._candidate_summaries(candidates)}。"
                ),
                temperature=0.1,
                max_tokens=1000,
            )
            raw_reports = data.get("reports") if isinstance(data, dict) else []
            reports: List[CandidateCriticReport] = []
            allowed_ids = {str(item.get("poi_id")) for item in candidates}
            for payload in raw_reports or []:
                if not isinstance(payload, dict) or str(payload.get("poi_id")) not in allowed_ids:
                    continue
                normalized = self._normalize_llm_report(payload)
                reports.append(CandidateCriticReport.parse_payload(normalized))
            return reports
        except Exception:
            return []

    def _normalize_llm_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        report = dict(payload)
        decision = str(report.get("decision") or "keep")
        score_delta = self._num(report.get("score_delta"), 0.0)
        if decision == "reject":
            decision = "backup_only"
            score_delta = min(score_delta, -35.0)
        if decision not in {"keep", "demote", "backup_only"}:
            decision = "keep"
        report["decision"] = decision
        report["score_delta"] = max(-35.0, min(5.0, score_delta))
        report["reason_codes"] = [str(item)[:64] for item in report.get("reason_codes") or [] if str(item).strip()][:6]
        report["risk_notes"] = [str(item)[:120] for item in report.get("risk_notes") or [] if str(item).strip()][:6]
        report["user_facing_reason"] = str(report.get("user_facing_reason") or "")[:120]
        return report

    def _merge_reports(
        self,
        deterministic: List[CandidateCriticReport],
        llm_reports: List[CandidateCriticReport],
    ) -> List[CandidateCriticReport]:
        by_id = {report.poi_id: report for report in deterministic}
        for llm_report in llm_reports:
            base = by_id.get(llm_report.poi_id)
            if base is None:
                by_id[llm_report.poi_id] = llm_report
                continue
            if llm_report.score_delta < base.score_delta:
                payload = base.to_dict()
                payload["score_delta"] = llm_report.score_delta
                payload["decision"] = self._decision(llm_report.score_delta)
                payload["reason_codes"] = _dedupe(list(base.reason_codes) + list(llm_report.reason_codes))
                payload["risk_notes"] = _dedupe(list(base.risk_notes) + list(llm_report.risk_notes))
                payload["user_facing_reason"] = llm_report.user_facing_reason or base.user_facing_reason
                by_id[llm_report.poi_id] = CandidateCriticReport.parse_payload(payload, fallback_on_error=True, **payload)
        return list(by_id.values())

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

    def _feature(self, item: Dict[str, Any]) -> Dict[str, Any]:
        feature: Dict[str, Any] = {}
        if self.poi_feature_store is not None:
            try:
                feature = self.poi_feature_store.for_item(item) or {}
            except Exception:
                feature = {}
        merged = dict(feature) if isinstance(feature, dict) else {}
        for key in ("menu_features", "family_features", "queue_features", "physical_features", "experience_features", "child_features"):
            if isinstance(item.get(key), dict):
                existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
                merged[key] = {**existing, **item[key]}
        return merged

    def _group(self, feature: Dict[str, Any], key: str) -> Dict[str, Any]:
        value = feature.get(key) if isinstance(feature, dict) else {}
        return value if isinstance(value, dict) else {}

    def _text(self, item: Dict[str, Any], feature: Dict[str, Any]) -> str:
        parts = [str(item.get("name") or ""), str(item.get("category") or "")]
        parts.extend(str(tag) for tag in item.get("tags") or [])
        parts.extend(str(tag) for tag in feature.get("semantic_tags") or [])
        menu = self._group(feature, "menu_features")
        for key in ("signature_dishes", "raw_food_terms", "ingredients", "cooking_methods", "flavors", "forms", "scenes", "dish_ids", "parent_categories"):
            parts.extend(str(value) for value in menu.get(key) or [])
        return " ".join(part for part in parts if part)

    def _has_food_need(self, food_payload: Dict[str, Any]) -> bool:
        if not isinstance(food_payload, dict) or food_payload.get("retrieval_mode") == "unknown":
            return False
        keys = ("raw_terms", "known_dish_ids", "parent_categories", "ingredients", "cooking_methods", "flavors", "forms")
        return any(food_payload.get(key) for key in keys)

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
        return max(raw * 1.0, dish * 0.9, category * 0.45, (sum(attributes) / max(1, len(attributes))) * 0.75, scene * 0.3)

    def _overlap(self, wanted: Any, existing: Any, text: str) -> float:
        wanted_values = [str(value) for value in wanted or [] if str(value).strip()]
        if not wanted_values:
            return 0.0
        existing_values = set(str(value) for value in existing or [] if str(value).strip())
        hits = 0
        for value in wanted_values:
            if value in existing_values or value in text:
                hits += 1
        return hits / max(1, len(wanted_values))

    def _candidate_summaries(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for item in candidates:
            feature = self._feature(item)
            summaries.append(
                {
                    "poi_id": item.get("poi_id"),
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "semantic_tags": list(feature.get("semantic_tags") or [])[:12],
                    "menu_features": self._compact_group(self._group(feature, "menu_features")),
                    "family_features": self._compact_group(self._group(feature, "family_features")),
                    "queue_features": self._compact_group(self._group(feature, "queue_features")),
                    "experience_features": self._compact_group(self._group(feature, "experience_features")),
                }
            )
        return summaries

    def _compact_group(self, values: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for key, value in values.items():
            if isinstance(value, list):
                compact[key] = value[:6]
            elif isinstance(value, (str, int, float, bool)):
                compact[key] = value
        return compact

    def _compact_food(self, food_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in food_payload.items() if key in {"raw_terms", "known_dish_ids", "parent_categories", "ingredients", "cooking_methods", "flavors", "forms", "scenes", "retrieval_mode"}}

    def _compact_machine(self, machine_intent: Optional[Any]) -> Dict[str, Any]:
        try:
            payload = machine_intent.to_dict() if isinstance(machine_intent, MachineIntent) else dict(machine_intent or {})
        except Exception:
            return {}
        return {
            "soft_preferences": payload.get("soft_preferences", [])[:8],
            "penalties": payload.get("penalties", [])[:8],
            "verifier_expectations": payload.get("verifier_expectations", [])[:8],
        }

    def _decision(self, delta: float) -> str:
        if delta <= -32:
            return "backup_only"
        if delta <= -8:
            return "demote"
        return "keep"

    def _user_reason(self, item: Dict[str, Any], reason_codes: List[str], risk_notes: List[str]) -> str:
        if not reason_codes:
            return "候选与当前约束未发现明显语义冲突。"
        name = str(item.get("name") or "该候选")
        return f"{name}存在{risk_notes[0] if risk_notes else '适配风险'}，建议降权。"

    def _num(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def _dedupe(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
