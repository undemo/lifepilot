from __future__ import annotations

import re
from copy import deepcopy
from datetime import timedelta
from typing import Any, Dict, Iterable, Optional

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import MEMORIES_STORE_PATH
from app.core.errors import AppError, bad_request, not_found
from app.core.ids import new_id
from app.core.time import iso_now, now_shanghai
from app.rules.recommendation_taxonomy import area_from_text, normalize_intent_profile
from app.services.logging_service import LoggingService
from app.storage.json_store import JsonFileStore


LOW_SENSITIVITY_TTL_DAYS = 180
MEDIUM_SENSITIVITY_TTL_DAYS = 90
SHORT_TERM_TTL_DAYS = 7

ROUTE_TAGS = {"nearby", "route_simple", "light_walk"}
QUEUE_TAGS = {"low_queue"}
DIET_TAGS = {"light_food", "light_meal", "light_dinner", "healthy_light", "low_calorie"}
ACTIVITY_TAGS = {
    "quiet",
    "quiet_stay",
    "coffee",
    "conversation",
    "mall_walk",
    "board_game",
    "karaoke",
    "esports",
    "hands_on",
    "craft",
    "amusement",
    "photo_spot",
    "rain_safe",
    "indoor",
    "date_friendly",
    "quality_dining",
    "ambience_dining",
    "beautiful_dining",
    "alcohol",
    "light_drink",
    "music",
    "acoustic_music",
}
DINING_TAGS = {
    "hotpot",
    "buffet",
    "bbq",
    "grill",
    "cuisine_japanese",
    "sushi",
    "izakaya",
    "western_cuisine",
    "steak",
    "lamb",
    "proper_dining",
    "quality_dining",
    "ambience_dining",
    "beautiful_dining",
}
NEGATED_MEMORY_TAGS = {
    "coffee": ("不要咖啡", "不喝咖啡", "别安排咖啡"),
    "alcohol": ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"),
    "light_drink": ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"),
    "karaoke": ("不唱歌", "不要KTV", "别KTV", "不去KTV", "不想唱K"),
    "board_game": ("不桌游", "不要桌游", "别桌游", "不玩桌游"),
    "esports": ("不打游戏", "不要游戏", "不去网咖", "别电竞"),
    "hotpot": ("不吃火锅", "不要火锅", "别火锅"),
    "bbq": ("不吃烤肉", "不要烧烤", "别烧烤", "别烤肉"),
    "grill": ("不吃烤肉", "不要烧烤", "别烧烤", "别烤肉"),
    "light_food": ("不吃轻食", "不要轻食", "别轻食"),
    "light_meal": ("不吃轻食", "不要轻食", "别轻食"),
}
HIGH_SENSITIVITY_TERMS = (
    "抑郁症",
    "焦虑症",
    "糖尿病",
    "高血压",
    "诊断",
    "病历",
    "身份证",
    "银行卡",
    "手机号",
    "月薪",
    "收入",
    "工资",
    "离婚",
    "丧偶",
)
MEDIUM_SENSITIVITY_TERMS = ("孩子", "小孩", "老人", "爸妈", "父母", "备考", "减脂", "怀孕", "孕")
STABILITY_TERMS = (
    "以后",
    "下次",
    "每次",
    "总是",
    "长期",
    "平时",
    "一直",
    "我喜欢",
    "我不喜欢",
    "我偏好",
    "我习惯",
    "尽量",
)


class LifeMemoryService:
    FILE = MEMORIES_STORE_PATH

    def __init__(self, store: JsonFileStore, logging_service: LoggingService) -> None:
        self.store = store
        self.logging_service = logging_service

    def get_memory(self, user_id: str) -> Dict[str, Any]:
        payload = self._payload()
        user = self._ensure_user(payload, user_id)
        self._expire_memories(payload)
        items = [
            deepcopy(memory)
            for memory in payload.get("memories", {}).values()
            if isinstance(memory, dict)
            and memory.get("user_id") == user_id
            and memory.get("status") not in {"deleted", "expired"}
            and memory.get("user_visible", True)
            and memory.get("sensitivity") != "high"
        ]
        items = sorted(items, key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
        short_term = self._latest_short_term(payload, user_id)
        profile_summary = self._profile_summary(items, self._pending_candidates(payload, user_id), short_term)
        self.store.write(self.FILE, payload)
        return {
            "personalization_enabled": bool(user.get("personalization_enabled", True)),
            "items": items,
            "memories": items,
            "short_term_profile": short_term,
            "profile_summary": profile_summary,
            "page_info": {"page_size": 50, "next_page_token": None, "has_more": False},
        }

    def get_candidates(
        self,
        user_id: str,
        *,
        status: Optional[str] = None,
        source_trace_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self._payload()
        items = []
        for candidate in payload.get("memory_candidates", {}).values():
            if not isinstance(candidate, dict) or candidate.get("user_id") != user_id:
                continue
            if candidate.get("sensitivity") == "high":
                continue
            if status and candidate.get("status") != status:
                continue
            if source_trace_id and candidate.get("source_trace_id") != source_trace_id:
                continue
            source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
            if plan_id and source.get("plan_id") != plan_id:
                continue
            if candidate.get("status") in {"ignored", "enabled", "deleted"} and not status:
                continue
            items.append(deepcopy(candidate))
        items = sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)
        return {"items": items, "candidates": items}

    def confirm_candidate(self, user_id: str, candidate_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = body or {}
        payload = self._payload()
        candidate = self._candidate_for_user(payload, user_id, candidate_id)
        if candidate.get("sensitivity") == "high":
            raise AppError(
                ErrorCode.MEMORY_PRIVACY_VIOLATION,
                "high sensitivity candidate cannot be confirmed automatically.",
                "该信息较敏感，不会被自动保存。",
                400,
                False,
            )
        existing_memory_id = candidate.get("memory_id")
        if existing_memory_id and existing_memory_id in payload.get("memories", {}):
            return {"memory": deepcopy(payload["memories"][existing_memory_id]), "candidate_status": candidate.get("status", "enabled")}

        now = iso_now()
        ttl_days = self._bounded_ttl(body.get("ttl_days") or candidate.get("suggested_ttl_days"))
        enabled = bool(body.get("enabled", True))
        memory_id = new_id("mem")
        content = str(body.get("edited_content") or candidate.get("content") or "").strip()
        memory = {
            "memory_id": memory_id,
            "user_id": user_id,
            "source_trace_id": candidate["source_trace_id"],
            "last_used_trace_id": None,
            "content": content,
            "memory_type": candidate.get("memory_type") or "preference",
            "source": deepcopy(candidate.get("source") or {}),
            "confidence": float(candidate.get("confidence") or 0.72),
            "sensitivity": candidate.get("sensitivity") or "low",
            "ttl_days": ttl_days,
            "status": "enabled" if enabled else "disabled",
            "user_visible": True,
            "user_confirmed": True,
            "enabled": enabled,
            "hints": deepcopy(candidate.get("hints") or {}),
            "last_used_at": None,
            "created_at": now,
            "updated_at": now,
            "expires_at": self._expires_at(ttl_days),
        }
        payload.setdefault("memories", {})[memory_id] = memory
        candidate["status"] = "enabled" if enabled else "disabled"
        candidate["memory_id"] = memory_id
        candidate["updated_at"] = now
        self.store.write(self.FILE, payload)
        self.logging_service.log(
            candidate["source_trace_id"],
            TraceEventType.MEMORY_LOG,
            "LifeMemoryService",
            {
                "user_visible_message": "已确认一条可用于后续规划的生活记忆。",
                "candidate_id": candidate_id,
                "memory_id": memory_id,
                "sensitivity": memory["sensitivity"],
            },
        )
        return {"memory": deepcopy(memory), "candidate_status": candidate["status"]}

    def ignore_candidate(self, user_id: str, candidate_id: str) -> Dict[str, Any]:
        payload = self._payload()
        candidate = self._candidate_for_user(payload, user_id, candidate_id)
        now = iso_now()
        candidate["status"] = "ignored"
        candidate["updated_at"] = now
        self.store.write(self.FILE, payload)
        self.logging_service.log(
            candidate["source_trace_id"],
            TraceEventType.MEMORY_LOG,
            "LifeMemoryService",
            {
                "user_visible_message": "已忽略一条候选记忆。",
                "candidate_id": candidate_id,
            },
        )
        return {"candidate_id": candidate_id, "status": "ignored", "updated_at": now}

    def update_memory(self, user_id: str, memory_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._payload()
        memory = self._memory_for_user(payload, user_id, memory_id)
        if memory.get("status") == "deleted":
            raise not_found("memory")
        now = iso_now()
        if body.get("content") is not None:
            content = str(body.get("content") or "").strip()
            if not content:
                raise bad_request("content cannot be empty.")
            memory["content"] = content
            memory["hints"] = self._hints_from_text(content, str((memory.get("source") or {}).get("scenario") or "fallback_unknown"))
        if body.get("ttl_days") is not None:
            ttl_days = self._bounded_ttl(body.get("ttl_days"))
            memory["ttl_days"] = ttl_days
            memory["expires_at"] = self._expires_at(ttl_days)
        if body.get("enabled") is not None:
            enabled = bool(body.get("enabled"))
            memory["enabled"] = enabled
            memory["status"] = "enabled" if enabled else "disabled"
        memory["updated_at"] = now
        self.store.write(self.FILE, payload)
        return deepcopy(memory)

    def delete_memory(self, user_id: str, memory_id: str) -> Dict[str, Any]:
        payload = self._payload()
        memory = self._memory_for_user(payload, user_id, memory_id)
        now = iso_now()
        memory["enabled"] = False
        memory["status"] = "deleted"
        memory["deleted_at"] = now
        memory["updated_at"] = now
        self.store.write(self.FILE, payload)
        return {"memory_id": memory_id, "status": "deleted", "deleted_at": now}

    def set_personalization(self, user_id: str, enabled: bool) -> Dict[str, Any]:
        payload = self._payload()
        user = self._ensure_user(payload, user_id)
        now = iso_now()
        user["personalization_enabled"] = bool(enabled)
        user["updated_at"] = now
        self.store.write(self.FILE, payload)
        result = {
            "user_id": user_id,
            "personalization_enabled": bool(enabled),
            "updated_at": now,
        }
        if not enabled:
            result["effect"] = {
                "read_long_term_memory": False,
                "write_long_term_memory": False,
                "keep_current_session_context": True,
            }
        return result

    def prepare_for_planning(
        self,
        *,
        user_id: str,
        trace_id: str,
        raw_text: str,
        user_goal: Dict[str, Any],
        extracted: Dict[str, Any],
        use_memory: bool,
    ) -> Dict[str, Any]:
        constraints = deepcopy(extracted.get("constraints") or {})
        payload = self._payload()
        user = self._ensure_user(payload, user_id)
        personalization_enabled = bool(user.get("personalization_enabled", True))
        scenario = str(user_goal.get("scenario") or "fallback_unknown")
        short_profile = self._short_term_profile(raw_text, scenario, constraints)
        result = deepcopy(extracted)
        result["constraints"] = constraints
        result["_memory_profile"] = {
            "short_term_profile": short_profile,
            "personalization_enabled": personalization_enabled,
        }

        if not use_memory or not personalization_enabled:
            skipped_reason = "request_disabled" if not use_memory else "personalization_disabled"
            self._log_memory_retrieval(trace_id, 0, personalization_enabled, skipped_reason)
            if use_memory and personalization_enabled and not short_profile.get("sensitivity") == "high":
                self._record_short_term(payload, user_id, trace_id, short_profile)
                self.store.write(self.FILE, payload)
            result["memory_usage"] = []
            return result

        self._record_short_term(payload, user_id, trace_id, short_profile)
        self._expire_memories(payload)
        usage = []
        for memory in self._rank_relevant_memories(payload, user_id, scenario, raw_text, constraints, short_profile):
            applied, explanation = self._apply_memory_to_constraints(memory, constraints, raw_text)
            if not applied:
                continue
            now = iso_now()
            memory["last_used_trace_id"] = trace_id
            memory["last_used_at"] = now
            memory["updated_at"] = now
            usage.append(
                {
                    "memory_id": memory["memory_id"],
                    "used_for": applied,
                    "explanation": explanation,
                    "confidence": float(memory.get("confidence") or 0.72),
                    "user_visible": True,
                    "source_trace_id": memory.get("source_trace_id"),
                }
            )
        result["constraints"] = constraints
        result["memory_usage"] = usage
        result["_memory_profile"] = {
            "short_term_profile": short_profile,
            "long_term_count": len(usage),
            "personalization_enabled": personalization_enabled,
        }
        self.store.write(self.FILE, payload)
        self._log_memory_retrieval(trace_id, len(usage), personalization_enabled, None)
        return result

    def create_candidates_from_input(
        self,
        *,
        user_id: str,
        trace_id: str,
        raw_text: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        plan_id: Optional[str] = None,
        use_memory: bool = True,
    ) -> list[Dict[str, Any]]:
        payload = self._payload()
        user = self._ensure_user(payload, user_id)
        if not use_memory or not bool(user.get("personalization_enabled", True)):
            self._log_candidate_generation(trace_id, 0, {"skipped": 1})
            return []
        candidates = self._candidate_specs_from_text(
            raw_text,
            str(user_goal.get("scenario") or "fallback_unknown"),
            source_type="plan_input",
            require_stable=True,
        )
        saved = self._save_candidate_specs(payload, user_id, trace_id, candidates, plan_id=plan_id)
        self.store.write(self.FILE, payload)
        self._log_candidate_generation(trace_id, len(saved), self._sensitivity_summary(saved))
        return saved

    def create_candidates_from_feedback(
        self,
        *,
        user_id: str,
        plan: Dict[str, Any],
        feedback: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        payload = self._payload()
        user = self._ensure_user(payload, user_id)
        trace_id = str(plan.get("trace_id") or "")
        if not bool(user.get("personalization_enabled", True)):
            self._log_candidate_generation(trace_id, 0, {"skipped": 1})
            return []
        specs = self._candidate_specs_from_feedback(plan, feedback)
        saved = self._save_candidate_specs(payload, user_id, trace_id, specs, plan_id=plan.get("plan_id"))
        self.store.write(self.FILE, payload)
        self._log_candidate_generation(trace_id, len(saved), self._sensitivity_summary(saved))
        return saved

    def _payload(self) -> Dict[str, Any]:
        payload = self.store.read(
            self.FILE,
            {"version": "v0.1", "users": {}, "memories": {}, "memory_candidates": {}, "short_term": []},
        )
        payload.setdefault("users", {})
        payload.setdefault("memories", {})
        payload.setdefault("memory_candidates", {})
        payload.setdefault("short_term", [])
        if isinstance(payload["memories"], list):
            payload["memories"] = {item["memory_id"]: item for item in payload["memories"] if isinstance(item, dict) and item.get("memory_id")}
        if isinstance(payload["memory_candidates"], list):
            payload["memory_candidates"] = {
                item["candidate_id"]: item for item in payload["memory_candidates"] if isinstance(item, dict) and item.get("candidate_id")
            }
        return payload

    def _ensure_user(self, payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        now = iso_now()
        users = payload.setdefault("users", {})
        if user_id not in users:
            users[user_id] = {
                "user_id": user_id,
                "display_name": "陈小龙" if user_id == "user_demo_001" else user_id,
                "personalization_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        return users[user_id]

    def _candidate_for_user(self, payload: Dict[str, Any], user_id: str, candidate_id: str) -> Dict[str, Any]:
        candidate = payload.get("memory_candidates", {}).get(candidate_id)
        if not candidate or candidate.get("user_id") != user_id:
            raise not_found("memory candidate")
        return candidate

    def _memory_for_user(self, payload: Dict[str, Any], user_id: str, memory_id: str) -> Dict[str, Any]:
        memory = payload.get("memories", {}).get(memory_id)
        if not memory or memory.get("user_id") != user_id:
            raise not_found("memory")
        return memory

    def _short_term_profile(self, raw_text: str, scenario: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
        profile = normalize_intent_profile(raw_text, scenario, llm_tags=[], user_location=constraints.get("user_location"))
        tags = list(profile.get("normalized_tags") or [])
        high = self._classify_sensitivity(raw_text) == "high"
        display_tags = self._display_profile_tags(tags)
        summary = "、".join(display_tags[:5]) if display_tags else "本次偏好主要来自当前输入"
        return {
            "source_trace_id": None,
            "summary": f"本次画像：{summary}",
            "scenario": scenario,
            "normalized_tags": tags[:24],
            "tag_axes": profile.get("tag_axes") or {},
            "hints": self._hints_from_profile(profile, raw_text),
            "sensitivity": "high" if high else "low",
            "created_at": iso_now(),
            "expires_at": self._expires_at(SHORT_TERM_TTL_DAYS),
        }

    def _record_short_term(self, payload: Dict[str, Any], user_id: str, trace_id: str, short_profile: Dict[str, Any]) -> None:
        if short_profile.get("sensitivity") == "high":
            return
        record = deepcopy(short_profile)
        record["short_term_id"] = new_id("stm")
        record["user_id"] = user_id
        record["source_trace_id"] = trace_id
        records = [
            item
            for item in payload.setdefault("short_term", [])
            if isinstance(item, dict) and item.get("user_id") == user_id and not self._is_expired(item)
        ]
        records.append(record)
        other_users = [item for item in payload.get("short_term", []) if not isinstance(item, dict) or item.get("user_id") != user_id]
        payload["short_term"] = [*other_users, *sorted(records, key=lambda item: item.get("created_at") or "", reverse=True)[:10]]

    def _latest_short_term(self, payload: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        records = [
            item
            for item in payload.get("short_term", [])
            if isinstance(item, dict) and item.get("user_id") == user_id and not self._is_expired(item)
        ]
        if not records:
            return None
        return deepcopy(sorted(records, key=lambda item: item.get("created_at") or "", reverse=True)[0])

    def _rank_relevant_memories(
        self,
        payload: Dict[str, Any],
        user_id: str,
        scenario: str,
        raw_text: str,
        constraints: Dict[str, Any],
        short_profile: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        current_tags = set(short_profile.get("normalized_tags") or [])
        current_tags.update(str(item) for item in constraints.get("activity_preference") or [])
        current_tags.update(str(item) for item in constraints.get("dietary_preference") or [])
        current_area = constraints.get("preferred_area") or constraints.get("current_area") or area_from_text(raw_text, constraints.get("user_location"))
        rows = []
        for memory in payload.get("memories", {}).values():
            if not isinstance(memory, dict) or memory.get("user_id") != user_id:
                continue
            if memory.get("status") != "enabled" or not memory.get("enabled", True):
                continue
            if memory.get("sensitivity") == "high" or self._is_expired(memory):
                continue
            hints = self._memory_hints(memory, scenario)
            tags = set(hints.get("tags") or [])
            score = 0.25
            if scenario and scenario == hints.get("scenario"):
                score += 0.25
            if tags & current_tags:
                score += 0.35
            if current_area and hints.get("area") == current_area:
                score += 0.15
            if memory.get("memory_type") in {"negative_feedback", "preference", "scene_preference"}:
                score += 0.08
            if self._has_memory_conflict(hints, raw_text):
                score -= 0.75
            if score > 0.15:
                rows.append((score, memory))
        return [memory for _, memory in sorted(rows, key=lambda item: (-item[0], item[1].get("updated_at") or ""))[:8]]

    def _apply_memory_to_constraints(self, memory: Dict[str, Any], constraints: Dict[str, Any], raw_text: str) -> tuple[list[str], str]:
        hints = self._memory_hints(memory, str((constraints.get("recommendation_profile") or {}).get("scenario") or "fallback_unknown"))
        if self._has_memory_conflict(hints, raw_text):
            return [], "本次输入与这条记忆存在冲突，已以本次输入为准。"
        applied: list[str] = []
        tags = [tag for tag in hints.get("tags") or [] if tag]
        if tags:
            profile = constraints.setdefault("recommendation_profile", {})
            existing = list(profile.get("normalized_tags") or [])
            profile["normalized_tags"] = self._dedupe([*existing, *tags])[:40]
            weights = profile.setdefault("weights", {})
            if isinstance(weights, dict):
                weights["intent_match"] = max(float(weights.get("intent_match") or 42), 48.0)
                weights["status"] = max(float(weights.get("status") or 18), 22.0 if "low_queue" in tags else float(weights.get("status") or 18))
            applied.append("ranking")
        diet = [tag for tag in hints.get("dietary_preference") or [] if tag]
        if diet and not self._raw_text_negates_any(raw_text, set(diet)):
            constraints["dietary_preference"] = self._dedupe([*(constraints.get("dietary_preference") or []), *diet])[:8]
            applied.append("dining")
        activity = [tag for tag in hints.get("activity_preference") or [] if tag]
        if activity:
            constraints["activity_preference"] = self._dedupe([*(constraints.get("activity_preference") or []), *activity])[:12]
            applied.append("activity")
        if hints.get("queue_tolerance") == "low" and not any(token in raw_text for token in ("愿意排队", "可以排队", "排队也行")):
            constraints["queue_tolerance"] = "low"
            applied.append("queue")
        if hints.get("walking_tolerance") in {"low", "medium_low"} and not any(token in raw_text for token in ("走远点", "多走路", "走多点")):
            current = str(constraints.get("walking_tolerance") or "medium")
            constraints["walking_tolerance"] = "low" if hints["walking_tolerance"] == "low" or current == "low" else "medium_low"
            applied.append("pace")
        if hints.get("distance_preference") == "nearby" and not any(token in raw_text for token in ("远一点", "远点也行", "可以远")):
            constraints["distance_preference"] = "nearby"
            applied.append("route")
        avoid = [tag for tag in hints.get("must_not_have") or [] if tag and not self._raw_text_prefers_tag(raw_text, tag)]
        if avoid:
            constraints["must_not_have"] = self._dedupe([*(constraints.get("must_not_have") or []), *avoid])[:12]
            applied.append("avoid")
        if not applied:
            return [], ""
        explanation = memory.get("content") or "参考已确认的生活记忆调整排序。"
        return self._dedupe(applied), str(explanation)

    def _candidate_specs_from_feedback(self, plan: Dict[str, Any], feedback: Dict[str, Any]) -> list[Dict[str, Any]]:
        specs: list[Dict[str, Any]] = []
        selected = set(str(item) for item in feedback.get("selected_options") or [])
        scenario = str((plan.get("user_goal") or {}).get("scenario") or "fallback_unknown")
        if selected & {"queue", "queue_too_long"}:
            specs.append(self._spec("我偏好少排队、可预约或低等待的安排。", "negative_feedback", "low", {"tags": ["low_queue"], "queue_tolerance": "low"}))
        if selected & {"distance", "too_rushed"}:
            specs.append(
                self._spec(
                    "我偏好少转场、节奏不赶的安排。",
                    "negative_feedback",
                    "low",
                    {"tags": ["route_simple", "nearby", "relaxed"], "distance_preference": "nearby", "walking_tolerance": "medium_low"},
                )
            )
        if selected & {"budget"}:
            specs.append(self._spec("我对预算比较敏感，希望优先人均适中的方案。", "preference", "low", {"tags": ["budget_sensitive", "budget_fit"]}))
        if selected & {"child_bored", "child_not_interested"}:
            specs.append(
                self._spec(
                    "家庭亲子场景里，我更希望活动有互动感，孩子不容易无聊。",
                    "scene_preference",
                    "medium",
                    {"tags": ["child_friendly", "kid_safe", "hands_on", "amusement"], "activity_preference": ["child_friendly", "hands_on", "amusement"], "scenario": "family_parent_child"},
                )
            )
        if selected & {"restaurant", "restaurant_not_good"}:
            specs.append(self._spec("我希望餐厅更贴合本次餐饮偏好，不只选方便但不合口味的店。", "negative_feedback", "low", {"tags": ["proper_dining", "quality_dining"]}))
        free_text = str(feedback.get("free_text") or "").strip()
        if free_text:
            specs.extend(self._candidate_specs_from_text(free_text, scenario, source_type="trip_feedback", require_stable=False))
        return specs

    def _candidate_specs_from_text(self, raw_text: str, scenario: str, *, source_type: str, require_stable: bool) -> list[Dict[str, Any]]:
        text = str(raw_text or "").strip()
        if not text:
            return []
        sensitivity = self._classify_sensitivity(text)
        if sensitivity == "high":
            return [self._spec("该信息较敏感，不会保存为长期记忆。", "temporary_context", "high", {}, source_type=source_type, hidden=True)]
        stable = self._is_stable_preference_text(text)
        if require_stable and not stable:
            return []
        profile = normalize_intent_profile(text, scenario)
        hints = self._hints_from_profile(profile, text)
        tags = set(hints.get("tags") or [])
        specs: list[Dict[str, Any]] = []
        spec_sensitivity = "medium" if sensitivity == "medium" else "low"
        if tags & QUEUE_TAGS:
            specs.append(self._spec("我偏好少排队、可预约或低等待的安排。", "preference", "low", {"tags": ["low_queue"], "queue_tolerance": "low"}, source_type=source_type))
        if tags & ROUTE_TAGS or any(token in text for token in ("别太远", "少转场", "不想走太多", "路线简单")):
            specs.append(
                self._spec(
                    "我偏好近一点、少转场、路线不折腾的安排。",
                    "preference",
                    "low",
                    {"tags": sorted(tags & ROUTE_TAGS) or ["nearby", "route_simple"], "distance_preference": "nearby", "walking_tolerance": "medium_low"},
                    source_type=source_type,
                )
            )
        if tags & DIET_TAGS:
            specs.append(
                self._spec(
                    "我在用餐上偏好清淡、轻负担的选择。",
                    "preference",
                    spec_sensitivity,
                    {"tags": sorted(tags & DIET_TAGS), "dietary_preference": sorted((tags & DIET_TAGS) - {"light_dinner"})},
                    source_type=source_type,
                )
            )
        activity_tags = sorted(tags & ACTIVITY_TAGS)
        if activity_tags:
            specs.append(
                self._spec(
                    f"我偏好{self._display_text_for_tags(activity_tags)}这类氛围或活动。",
                    "scene_preference",
                    spec_sensitivity,
                    {"tags": activity_tags, "activity_preference": activity_tags},
                    source_type=source_type,
                )
            )
        dining_tags = sorted(tags & DINING_TAGS)
        if dining_tags:
            specs.append(
                self._spec(
                    f"我在餐饮上偏好{self._display_text_for_tags(dining_tags)}。",
                    "preference",
                    spec_sensitivity,
                    {"tags": dining_tags, "activity_preference": dining_tags},
                    source_type=source_type,
                )
            )
        if any(token in text for token in ("不要喝酒", "不喝酒", "别喝酒", "不安排酒")):
            specs.append(self._spec("我不希望默认安排喝酒或酒吧类节点。", "preference", "low", {"must_not_have": ["alcohol", "light_drink"]}, source_type=source_type))
        return self._dedupe_specs(specs)

    def _save_candidate_specs(
        self,
        payload: Dict[str, Any],
        user_id: str,
        trace_id: str,
        specs: Iterable[Dict[str, Any]],
        *,
        plan_id: Optional[str],
    ) -> list[Dict[str, Any]]:
        saved = []
        now = iso_now()
        for spec in specs:
            if spec.get("sensitivity") == "high":
                continue
            content = str(spec.get("content") or "").strip()
            if not content or self._candidate_or_memory_exists(payload, user_id, content, spec.get("hints") or {}):
                continue
            sensitivity = spec.get("sensitivity") or "low"
            ttl_days = MEDIUM_SENSITIVITY_TTL_DAYS if sensitivity == "medium" else LOW_SENSITIVITY_TTL_DAYS
            candidate_id = new_id("memcand")
            candidate = {
                "candidate_id": candidate_id,
                "user_id": user_id,
                "source_trace_id": trace_id,
                "content": content,
                "memory_type": spec.get("memory_type") or "preference",
                "source": {
                    "type": spec.get("source_type") or "plan_input",
                    "trace_id": trace_id,
                    "plan_id": plan_id,
                    "created_at": now,
                },
                "confidence": float(spec.get("confidence") or (0.78 if sensitivity == "low" else 0.68)),
                "sensitivity": sensitivity,
                "requires_confirmation": True,
                "status": "pending_confirmation",
                "suggested_ttl_days": ttl_days,
                "hints": deepcopy(spec.get("hints") or {}),
                "created_at": now,
                "updated_at": now,
            }
            payload.setdefault("memory_candidates", {})[candidate_id] = candidate
            saved.append(deepcopy(candidate))
        return saved

    def _spec(
        self,
        content: str,
        memory_type: str,
        sensitivity: str,
        hints: Dict[str, Any],
        *,
        source_type: str = "plan_input",
        hidden: bool = False,
    ) -> Dict[str, Any]:
        return {
            "content": content,
            "memory_type": memory_type,
            "sensitivity": sensitivity,
            "hints": hints,
            "source_type": source_type,
            "hidden": hidden,
        }

    def _candidate_or_memory_exists(self, payload: Dict[str, Any], user_id: str, content: str, hints: Dict[str, Any]) -> bool:
        key = self._memory_key(content, hints)
        for item in payload.get("memories", {}).values():
            if isinstance(item, dict) and item.get("user_id") == user_id and item.get("status") != "deleted":
                if self._memory_key(str(item.get("content") or ""), item.get("hints") or {}) == key:
                    return True
        for item in payload.get("memory_candidates", {}).values():
            if isinstance(item, dict) and item.get("user_id") == user_id and item.get("status") in {"pending_confirmation", "candidate"}:
                if self._memory_key(str(item.get("content") or ""), item.get("hints") or {}) == key:
                    return True
        return False

    def _memory_key(self, content: str, hints: Dict[str, Any]) -> str:
        tags = ",".join(sorted(str(tag) for tag in hints.get("tags") or []))
        return f"{content.strip()}|{tags}"

    def _hints_from_text(self, text: str, scenario: str) -> Dict[str, Any]:
        profile = normalize_intent_profile(text, scenario)
        return self._hints_from_profile(profile, text)

    def _hints_from_profile(self, profile: Dict[str, Any], text: str) -> Dict[str, Any]:
        tags = set(str(tag) for tag in profile.get("normalized_tags") or [])
        hints: Dict[str, Any] = {"tags": sorted(tags & (ROUTE_TAGS | QUEUE_TAGS | DIET_TAGS | ACTIVITY_TAGS | DINING_TAGS | {"budget_sensitive", "budget_fit", "relaxed", "low_pressure"}))}
        if tags & QUEUE_TAGS:
            hints["queue_tolerance"] = "low"
        if tags & {"nearby", "route_simple", "light_walk"}:
            hints["distance_preference"] = "nearby"
            hints["walking_tolerance"] = "medium_low"
        diet = sorted((tags & DIET_TAGS) - {"light_dinner"})
        if diet:
            hints["dietary_preference"] = diet
        activity = sorted(tags & ACTIVITY_TAGS)
        if activity:
            hints["activity_preference"] = activity
        if any(token in text for token in ("不喝酒", "不要喝酒", "别喝酒", "不安排酒")):
            hints["must_not_have"] = ["alcohol", "light_drink"]
        axes = profile.get("tag_axes") if isinstance(profile.get("tag_axes"), dict) else {}
        if axes.get("scenario"):
            hints["scenario"] = axes.get("scenario")
        area = axes.get("area") or area_from_text(text)
        if area:
            hints["area"] = area
        return hints

    def _memory_hints(self, memory: Dict[str, Any], fallback_scenario: str) -> Dict[str, Any]:
        hints = deepcopy(memory.get("hints") or {})
        if not hints:
            hints = self._hints_from_text(str(memory.get("content") or ""), fallback_scenario)
        hints.setdefault("tags", [])
        return hints

    def _has_memory_conflict(self, hints: Dict[str, Any], raw_text: str) -> bool:
        tags = set(str(tag) for tag in hints.get("tags") or [])
        return self._raw_text_negates_any(raw_text, tags)

    def _raw_text_negates_any(self, raw_text: str, tags: set[str]) -> bool:
        text = str(raw_text or "")
        for tag in tags:
            if any(token in text for token in NEGATED_MEMORY_TAGS.get(tag, ())):
                return True
        return False

    def _raw_text_prefers_tag(self, raw_text: str, tag: str) -> bool:
        text = str(raw_text or "")
        positive = {
            "alcohol": ("喝酒", "小酌", "酒吧", "清吧"),
            "light_drink": ("喝酒", "小酌", "酒吧", "清吧"),
            "coffee": ("咖啡",),
            "karaoke": ("KTV", "唱K", "唱歌"),
            "board_game": ("桌游", "棋牌"),
            "esports": ("打游戏", "电竞", "网咖"),
        }
        return any(token in text for token in positive.get(tag, (tag,)))

    def _classify_sensitivity(self, text: str) -> str:
        if any(term in text for term in HIGH_SENSITIVITY_TERMS):
            return "high"
        if re.search(r"\d+\s*(?:幢|栋|单元|室|号楼|楼)\b", text) or re.search(r"(?:住在|家在).{0,12}(?:小区|公寓|门牌)", text):
            return "high"
        if any(term in text for term in MEDIUM_SENSITIVITY_TERMS):
            return "medium"
        if re.search(r"孩子\s*[0-9一二三四五六七八九十两]{1,2}\s*岁", text):
            return "medium"
        return "low"

    def _is_stable_preference_text(self, text: str) -> bool:
        return any(term in text for term in STABILITY_TERMS)

    def _expire_memories(self, payload: Dict[str, Any]) -> None:
        now = now_shanghai()
        for memory in payload.get("memories", {}).values():
            if isinstance(memory, dict) and memory.get("status") == "enabled" and self._is_expired(memory, now=now):
                memory["status"] = "expired"
                memory["enabled"] = False
                memory["updated_at"] = iso_now()
        payload["short_term"] = [item for item in payload.get("short_term", []) if not isinstance(item, dict) or not self._is_expired(item, now=now)]

    def _is_expired(self, item: Dict[str, Any], *, now=None) -> bool:
        expires_at = item.get("expires_at")
        if not expires_at:
            return False
        try:
            expires = now_shanghai().__class__.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            return False
        current = now or now_shanghai()
        if expires.tzinfo is None and current.tzinfo is not None:
            expires = expires.replace(tzinfo=current.tzinfo)
        return expires <= current

    def _expires_at(self, ttl_days: int) -> str:
        return (now_shanghai() + timedelta(days=ttl_days)).replace(microsecond=0).isoformat()

    def _bounded_ttl(self, value: Any) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError):
            days = LOW_SENSITIVITY_TTL_DAYS
        return max(7, min(365, days))

    def _pending_candidates(self, payload: Dict[str, Any], user_id: str) -> list[Dict[str, Any]]:
        return [
            deepcopy(item)
            for item in payload.get("memory_candidates", {}).values()
            if isinstance(item, dict)
            and item.get("user_id") == user_id
            and item.get("status") == "pending_confirmation"
            and item.get("sensitivity") != "high"
        ]

    def _profile_summary(
        self,
        memories: list[Dict[str, Any]],
        candidates: list[Dict[str, Any]],
        short_term: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tags: list[str] = []
        for item in memories:
            hints = item.get("hints") if isinstance(item.get("hints"), dict) else {}
            tags.extend(str(tag) for tag in hints.get("tags") or [])
        top_tags = self._display_profile_tags(tags)
        return {
            "enabled_count": len([item for item in memories if item.get("status") == "enabled"]),
            "pending_count": len(candidates),
            "top_tags": top_tags[:8],
            "short_term_summary": (short_term or {}).get("summary"),
            "has_recent_short_term": bool(short_term),
        }

    def _display_profile_tags(self, tags: Iterable[Any]) -> list[str]:
        labels = {
            "low_queue": "少排队",
            "nearby": "近距离",
            "route_simple": "少转场",
            "light_walk": "轻松散步",
            "light_food": "清淡餐",
            "light_meal": "轻食",
            "healthy_light": "轻负担",
            "coffee": "咖啡/聊天",
            "conversation": "适合聊天",
            "quiet": "安静",
            "hands_on": "手作",
            "craft": "手作",
            "board_game": "桌游",
            "karaoke": "KTV",
            "esports": "游戏",
            "amusement": "亲子游乐",
            "quality_dining": "品质餐饮",
            "ambience_dining": "氛围感",
            "budget_sensitive": "预算敏感",
            "rain_safe": "雨天可去",
            "indoor": "室内优先",
            "alcohol": "小酌",
            "music": "音乐",
            "acoustic_music": "音乐",
        }
        result = []
        for tag in tags:
            label = labels.get(str(tag))
            if label and label not in result:
                result.append(label)
        return result

    def _display_text_for_tags(self, tags: Iterable[str]) -> str:
        labels = self._display_profile_tags(tags)
        if labels:
            return "、".join(labels[:3])
        return "当前表达的偏好"

    def _dedupe_specs(self, specs: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        result = []
        seen = set()
        for spec in specs:
            key = self._memory_key(str(spec.get("content") or ""), spec.get("hints") or {})
            if key in seen:
                continue
            seen.add(key)
            result.append(spec)
        return result

    def _dedupe(self, values: Iterable[Any]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    def _sensitivity_summary(self, candidates: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for candidate in candidates:
            key = str(candidate.get("sensitivity") or "low")
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _log_memory_retrieval(self, trace_id: str, used_count: int, personalization_enabled: bool, skipped_reason: Optional[str]) -> None:
        self.logging_service.log(
            trace_id,
            TraceEventType.MEMORY_LOG,
            "MemoryRetriever",
            {
                "user_visible_message": "已参考你确认过的生活记忆。" if used_count else "本次没有使用长期记忆。",
                "used_memory_count": used_count,
                "skipped_reason": skipped_reason,
                "personalization_enabled": personalization_enabled,
            },
        )

    def _log_candidate_generation(self, trace_id: str, candidate_count: int, sensitivity_summary: Dict[str, int]) -> None:
        self.logging_service.log(
            trace_id or "trace_unavailable",
            TraceEventType.MEMORY_LOG,
            "LifeMemoryService",
            {
                "user_visible_message": "已生成候选记忆，等待你确认。" if candidate_count else "本次没有新增候选记忆。",
                "candidate_count": candidate_count,
                "sensitivity_summary": sensitivity_summary,
            },
        )
