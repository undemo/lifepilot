from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.constants import ErrorCode, TraceEventType
from app.core.data_paths import CONSENSUS_STORE_PATH
from app.core.errors import AppError, bad_request, not_found
from app.core.ids import new_id
from app.core.time import iso_now
from app.services.idempotency_service import IdempotencyService
from app.services.logging_service import LoggingService
from app.services.plan_service import PlanService
from app.storage.json_store import JsonFileStore


class ConsensusService:
    FILE = CONSENSUS_STORE_PATH

    def __init__(
        self,
        store: JsonFileStore,
        logging_service: LoggingService,
        idempotency_service: IdempotencyService,
        plan_service: PlanService,
    ) -> None:
        self.store = store
        self.logging_service = logging_service
        self.idempotency_service = idempotency_service
        self.plan_service = plan_service

    def create_session(
        self,
        user_id: str,
        trace_id: str,
        idempotency_key: Optional[str],
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidate_plan_ids = body.get("candidate_plan_ids") or []
        if not candidate_plan_ids:
            raise bad_request("candidate_plan_ids is required.")
        if not body.get("expire_at"):
            raise bad_request("expire_at is required.")
        candidate_plan_ids = self._unique_candidate_plan_ids(candidate_plan_ids)
        body = {**body, "candidate_plan_ids": candidate_plan_ids}
        fingerprint = self.idempotency_service.fingerprint(body)
        cached = self.idempotency_service.get(user_id, idempotency_key, "consensus.create", fingerprint)
        if cached:
            return cached

        now = iso_now()
        plan_group_id = body.get("plan_group_id") or new_id("plangrp")
        session = {
            "consensus_session_id": new_id("cs"),
            "vote_page_id": new_id("vpage"),
            "plan_group_id": plan_group_id,
            "trace_id": trace_id,
            "creator_user_id": user_id,
            "title": body.get("title") or "朋友局投票",
            "status": "collecting",
            "candidate_plan_ids": candidate_plan_ids,
            "share_url": "",
            "expire_at": body.get("expire_at"),
            "allow_anonymous": body.get("allow_anonymous", True),
            "created_at": now,
            "finalized_at": None,
            "consensus_summary": None,
            "final_plan_id": None,
        }
        session["share_url"] = f"https://demo.lifepilot.local/vote/{session['vote_page_id']}"
        self._save_plan_group(
            {
                "plan_group_id": plan_group_id,
                "trace_id": trace_id,
                "creator_user_id": user_id,
                "candidate_plan_ids": candidate_plan_ids,
                "title": session["title"],
                "created_at": now,
            }
        )
        self._save_session(session)
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "ConsensusService",
            {
                "user_visible_message": "已创建朋友局投票。",
                "plan_group_id": session["plan_group_id"],
                "candidate_count": len(candidate_plan_ids),
            },
        )
        data = {
            "consensus_session_id": session["consensus_session_id"],
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "share_url": session["share_url"],
            "candidate_plan_ids": candidate_plan_ids,
            "status": session["status"],
            "expire_at": session["expire_at"],
            "created_at": now,
        }
        self.idempotency_service.save(user_id, idempotency_key, "consensus.create", fingerprint, data)
        return data

    def vote(self, consensus_session_id: str, trace_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_session(consensus_session_id)
        if session["status"] in {"closed", "expired", "finalized"}:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "consensus session is not collecting.",
                "投票已结束，不能继续修改。",
                400,
                True,
            )
        liked = body.get("liked_plan_ids") or []
        disliked = body.get("disliked_plan_ids") or []
        free_text = str(body.get("free_text") or "").strip()
        unknown_plan_ids = sorted((set(liked) | set(disliked)) - set(session["candidate_plan_ids"]))
        if unknown_plan_ids:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "liked_plan_ids or disliked_plan_ids contain unknown candidate plan ids.",
                "投票包含不存在的候选方案，请刷新后重试。",
                400,
                True,
                {"unknown_plan_ids": unknown_plan_ids},
            )
        has_budget = body.get("budget_max") is not None
        has_preference_field = any(body.get(key) for key in ("time_preference", "walking_tolerance", "queue_tolerance"))
        if not liked and not disliked and not free_text and not has_budget and not has_preference_field:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "liked_plan_ids, disliked_plan_ids, budget_max, tolerance or free_text is required.",
                "请至少选择一个方案、填写预算/容忍度或写一句偏好。",
                400,
                True,
            )
        overlap = sorted(set(liked) & set(disliked))
        if overlap:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "liked_plan_ids and disliked_plan_ids overlap.",
                "同一个方案不能同时选择喜欢和不想选，请修改后提交。",
                400,
                True,
                {"overlap_plan_ids": overlap},
            )
        if body.get("walking_tolerance") is not None and body["walking_tolerance"] not in {"low", "medium_low", "medium", "high"}:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "walking_tolerance is invalid.",
                "步行容忍度不合法，请修改后提交。",
                400,
                True,
            )
        if body.get("queue_tolerance") is not None and body["queue_tolerance"] not in {"low", "medium", "high"}:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "queue_tolerance is invalid.",
                "排队容忍度不合法，请修改后提交。",
                400,
                True,
            )
        if body.get("budget_max") is not None and float(body["budget_max"]) <= 0:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "budget_max must be greater than 0.",
                "人均预算需要大于0，请修改后提交。",
                400,
                True,
            )
        if len(free_text) > 200:
            raise AppError(
                ErrorCode.CONSENSUS_VOTE_INVALID,
                "free_text is too long.",
                "偏好文字太长，请控制在200字以内。",
                400,
                True,
            )
        now = iso_now()
        participant_payload = body.get("participant") or {}
        client_vote_token = body.get("client_vote_token") or participant_payload.get("client_vote_token")
        payload = self._read()
        votes = payload.setdefault("votes", {}).setdefault(consensus_session_id, [])
        existing_vote = None
        if client_vote_token:
            existing_vote = next((vote for vote in votes if vote.get("client_vote_token") == client_vote_token), None)
        vote = {
            "vote_id": existing_vote["vote_id"] if existing_vote else new_id("vote"),
            "consensus_session_id": consensus_session_id,
            "trace_id": session["trace_id"],
            "participant": {
                "participant_id": (existing_vote or {}).get("participant", {}).get("participant_id") or new_id("anon_part"),
                "participant_name": participant_payload.get("participant_name", "匿名朋友"),
                "anonymous": participant_payload.get("anonymous", True),
                "role": "friend",
                "preference_tags": [],
                "hard_constraints": [],
                "soft_constraints": [],
            },
            "liked_plan_ids": liked,
            "disliked_plan_ids": disliked,
            "budget_max": body.get("budget_max"),
            "time_preference": body.get("time_preference"),
            "walking_tolerance": body.get("walking_tolerance"),
            "queue_tolerance": body.get("queue_tolerance"),
            "free_text": free_text,
            "client_vote_token": client_vote_token,
            "submitted_at": (existing_vote or {}).get("submitted_at") or now,
            "updated_at": now,
        }
        if existing_vote:
            votes[votes.index(existing_vote)] = vote
        else:
            votes.append(vote)
        self.store.write(self.FILE, payload)
        self.logging_service.log(
            session["trace_id"],
            TraceEventType.TOOL_LOG,
            "ConsensusService",
            {"user_visible_message": "已收到一条朋友偏好。", "vote_id": vote["vote_id"]},
        )
        return {
            "vote_id": vote["vote_id"],
            "consensus_session_id": consensus_session_id,
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "vote": vote,
            "vote_count": len(votes),
        }

    def finalize(self, consensus_session_id: str, user_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        session = self.get_session(consensus_session_id)
        if session.get("consensus_summary") and session.get("final_plan_id"):
            final_plan = self.plan_service.get_plan(session["final_plan_id"])
            return self._finalize_response(session, final_plan)

        payload = self._read()
        votes = payload.get("votes", {}).get(consensus_session_id, [])
        now = iso_now()
        support_count_by_plan = self._count(votes, "liked_plan_ids", session["candidate_plan_ids"])
        oppose_count_by_plan = self._count(votes, "disliked_plan_ids", session["candidate_plan_ids"])
        base_plan = self._best_supported_plan(session["candidate_plan_ids"], support_count_by_plan, oppose_count_by_plan)
        consensus_constraints = self._consensus_constraints(base_plan, votes)
        detected_conflicts = self._detected_conflicts(votes, consensus_constraints)
        final_plan = self._clone_supported_plan_for_consensus(base_plan, consensus_constraints, session, now)
        final_plan = self._apply_consensus_constraints(final_plan, consensus_constraints)
        final_plan.setdefault("messages", {})["to_group"] = self._group_message(consensus_constraints)
        final_plan["messages"]["consensus_source_plan_id"] = base_plan["plan_id"]
        final_plan["user_goal"]["raw_text"] = self._final_plan_input_text(consensus_constraints, base_plan)
        final_plan["user_goal"]["goal_summary"] = "综合朋友投票后生成的共识朋友局方案。"
        final_plan["user_goal"]["intent_tags"] = sorted(set(final_plan["user_goal"].get("intent_tags", []) + ["friend_group", "consensus"]))
        verifier_output = self.plan_service.verifier_service.verify_plan_contract(final_plan, "consensus_finalize")
        final_plan["verifier_result"] = verifier_output["verifier_result"]
        final_plan["executable_window"] = verifier_output["executable_window"]
        final_plan["risks"] = verifier_output["risks"]
        final_plan["status"] = "failed" if verifier_output["verifier_result"]["status"] == "fail" else "executable"
        step_status = "planned" if verifier_output["verifier_result"]["status"] == "fail" else "verified"
        for step in final_plan.get("timeline", []):
            step["status"] = step_status
        final_plan["updated_at"] = now
        self.plan_service.validator.validate_plan_contract(final_plan)
        self.plan_service._save_plan(user_id, final_plan)
        summary = {
            "consensus_session_id": consensus_session_id,
            "trace_id": session["trace_id"],
            "vote_count": len(votes),
            "support_count_by_plan": support_count_by_plan,
            "oppose_count_by_plan": oppose_count_by_plan,
            "detected_conflicts": detected_conflicts,
            "consensus_constraints": consensus_constraints,
            "explanation": self._explanation(consensus_constraints, detected_conflicts),
            "final_plan_id": final_plan["plan_id"],
            "source_plan_id": base_plan["plan_id"],
            "generated_at": now,
        }
        session["status"] = "finalized"
        session["finalized_at"] = now
        session["consensus_summary"] = summary
        session["final_plan_id"] = final_plan["plan_id"]
        payload.setdefault("sessions", {})[consensus_session_id] = session
        self.store.write(self.FILE, payload)
        self.logging_service.log(
            session["trace_id"],
            TraceEventType.CONSTRAINT_LOG,
            "ConsensusService",
            {
                "user_visible_message": "已生成朋友局共识方案。",
                "final_plan_id": final_plan["plan_id"],
                "consensus_constraints_summary": {
                    "party_size": consensus_constraints.get("party_size"),
                    "budget_max_per_person": consensus_constraints.get("budget_max_per_person"),
                    "walking_tolerance": consensus_constraints.get("walking_tolerance"),
                    "queue_tolerance": consensus_constraints.get("queue_tolerance"),
                },
            },
        )
        self.logging_service.log(
            session["trace_id"],
            TraceEventType.VERIFIER_LOG,
            "VerifierService",
            {
                "user_visible_message": "最终共识方案已重新校验。",
                "final_plan_verifier_status": final_plan["verifier_result"]["status"],
                "final_plan_id": final_plan["plan_id"],
            },
            plan_id=final_plan["plan_id"],
            level="error" if final_plan["verifier_result"]["status"] == "fail" else "info",
        )
        return self._finalize_response(session, final_plan)

    def get_session(self, consensus_session_id: str) -> Dict[str, Any]:
        session = self._read().get("sessions", {}).get(consensus_session_id)
        if not session:
            raise not_found("consensus session")
        return session

    def get_session_payload(self, consensus_session_id: str) -> Dict[str, Any]:
        session = self.get_session(consensus_session_id)
        vote_count = len(self._read().get("votes", {}).get(consensus_session_id, []))
        return {
            "consensus_session_id": session["consensus_session_id"],
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "trace_id": session["trace_id"],
            "creator_user_id": session["creator_user_id"],
            "status": session["status"],
            "candidate_plan_ids": session["candidate_plan_ids"],
            "share_url": session["share_url"],
            "vote_count": vote_count,
            "can_finalize": session["status"] == "collecting",
            "expire_at": session["expire_at"],
            "created_at": session["created_at"],
            "finalized_at": session["finalized_at"],
        }

    def get_vote_page(self, vote_page_id: str) -> Dict[str, Any]:
        session = self._session_by_vote_page_id(vote_page_id)
        return {
            "consensus_session_id": session["consensus_session_id"],
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "trace_id": session["trace_id"],
            "title": session["title"],
            "status": session["status"],
            "expire_at": session["expire_at"],
            "share_url": session["share_url"],
            "candidate_plans": [self._plan_summary(plan_id) for plan_id in session["candidate_plan_ids"]],
            "vote_rules": {
                "liked_plan_ids_required": False,
                "minimum_one_of": ["liked_plan_ids", "disliked_plan_ids", "budget_max", "walking_tolerance", "queue_tolerance", "free_text"],
                "liked_disliked_must_not_overlap": True,
            },
        }

    def summary(self, consensus_session_id: str) -> Dict[str, Any]:
        session = self.get_session(consensus_session_id)
        if not session.get("consensus_summary"):
            return {
                "consensus_session_id": session["consensus_session_id"],
                "vote_page_id": session["vote_page_id"],
                "plan_group_id": session["plan_group_id"],
                "trace_id": session["trace_id"],
                "status": session["status"],
                "consensus_summary": None,
                "final_plan_id": None,
            }
        return {
            "consensus_session_id": session["consensus_session_id"],
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "trace_id": session["trace_id"],
            "status": session["status"],
            "consensus_summary": session["consensus_summary"],
            "final_plan_id": session["final_plan_id"],
        }

    def _session_by_vote_page_id(self, vote_page_id: str) -> Dict[str, Any]:
        session = next((item for item in self._read().get("sessions", {}).values() if item.get("vote_page_id") == vote_page_id), None)
        if not session:
            raise not_found("vote page")
        return session

    def _plan_summary(self, plan_id: str) -> Dict[str, Any]:
        plan = self.plan_service.get_plan(plan_id)
        visible_steps = [step for step in (plan.get("timeline") or []) if step.get("type") != "transport"]
        first_step = visible_steps[0] if visible_steps else (plan.get("timeline") or [{}])[0]
        budget = plan.get("budget") or {}
        constraints = plan.get("constraints") or {}
        timeline_summary = [
            f"{step.get('title')} {str(step.get('start_time') or '')[11:16]}"
            for step in (plan.get("timeline") or [])
            if step.get("type") != "transport" and step.get("title")
        ][:3]
        return {
            "plan_id": plan_id,
            "title": first_step.get("title") or plan.get("user_goal", {}).get("goal_summary") or "候选方案",
            "goal_summary": plan.get("user_goal", {}).get("goal_summary") or first_step.get("description") or "",
            "status": plan.get("status"),
            "score": (plan.get("verifier_result") or {}).get("score"),
            "timeline_summary": timeline_summary,
            "budget": {
                "currency": budget.get("currency", "CNY"),
                "estimated_total": budget.get("estimated_total"),
                "price_per_person": budget.get("price_per_person"),
            },
            "executable_window": plan.get("executable_window"),
            "walking_tolerance_label": constraints.get("walking_tolerance"),
            "queue_risk_label": constraints.get("queue_tolerance"),
        }

    def _unique_candidate_plan_ids(self, candidate_plan_ids: List[str]) -> List[str]:
        unique_ids: list[str] = []
        seen: set[tuple] = set()
        for plan_id in candidate_plan_ids:
            plan = self.plan_service.get_plan(plan_id)
            self.plan_service.validator.validate_plan_contract(plan)
            signature = self._plan_option_signature(plan)
            if signature in seen:
                continue
            seen.add(signature)
            unique_ids.append(plan_id)
        return unique_ids

    def _plan_option_signature(self, plan: Dict[str, Any]) -> tuple:
        steps = []
        for step in plan.get("timeline") or []:
            if step.get("type") == "transport":
                continue
            steps.append((
                str(step.get("type") or ""),
                str(step.get("poi_id") or step.get("title") or ""),
            ))
        if not steps:
            steps.append(("empty", str((plan.get("user_goal") or {}).get("goal_summary") or "")))
        return tuple(steps)

    def _finalize_response(self, session: Dict[str, Any], final_plan: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "consensus_session_id": session["consensus_session_id"],
            "vote_page_id": session["vote_page_id"],
            "plan_group_id": session["plan_group_id"],
            "share_url": session["share_url"],
            "candidate_plan_ids": session["candidate_plan_ids"],
            "consensus_summary": session["consensus_summary"],
            "final_plan_contract": final_plan,
        }

    def _count(self, votes, key, candidates):
        return {plan_id: sum(1 for vote in votes if plan_id in vote.get(key, [])) for plan_id in candidates}

    def _read(self) -> Dict[str, Any]:
        return self.store.read(self.FILE, {"version": "v0.1", "plan_groups": {}, "sessions": {}, "votes": {}})

    def _save_session(self, session: Dict[str, Any]) -> None:
        payload = self._read()
        payload.setdefault("sessions", {})[session["consensus_session_id"]] = session
        self.store.write(self.FILE, payload)

    def _save_plan_group(self, plan_group: Dict[str, Any]) -> None:
        payload = self._read()
        payload.setdefault("plan_groups", {})[plan_group["plan_group_id"]] = plan_group
        self.store.write(self.FILE, payload)

    def _consensus_constraints(
        self,
        base_plan: Dict[str, Any],
        votes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base_constraints = deepcopy(base_plan.get("constraints") or {})
        party_size = int(base_constraints.get("party_size") or 4)
        budgets = [float(vote["budget_max"]) for vote in votes if vote.get("budget_max") is not None]
        budget_max_per_person = min(budgets) if budgets else base_constraints.get("budget_max_per_person")
        walking_tolerance = self._strictest_tolerance(
            [vote.get("walking_tolerance") for vote in votes if vote.get("walking_tolerance")],
            ["low", "medium_low", "medium", "high"],
            base_constraints.get("walking_tolerance") or "medium",
        )
        queue_tolerance = self._strictest_tolerance(
            [vote.get("queue_tolerance") for vote in votes if vote.get("queue_tolerance")],
            ["low", "medium", "high"],
            base_constraints.get("queue_tolerance") or "medium",
        )
        activity_preference = list(dict.fromkeys((base_constraints.get("activity_preference") or []) + self._feedback_tags(votes)))
        must_have = list(dict.fromkeys(base_constraints.get("must_have") or []))
        must_not_have = list(dict.fromkeys(base_constraints.get("must_not_have") or []))
        if walking_tolerance in {"low", "medium_low"}:
            must_have.append("low_walking")
            must_not_have.append("walk_too_much")
        if queue_tolerance == "low":
            must_have.append("low_queue")
            must_not_have.append("long_queue")
        if budget_max_per_person is not None:
            must_not_have.append(f"per_person_over_{int(float(budget_max_per_person))}")
        constraints = deepcopy(base_constraints)
        constraints.update(
            {
                "party_size": party_size,
                "distance_preference": base_constraints.get("distance_preference") or "nearby",
                "budget_max": round(float(budget_max_per_person) * party_size, 2) if budget_max_per_person is not None else base_constraints.get("budget_max"),
                "budget_max_per_person": budget_max_per_person,
                "walking_tolerance": walking_tolerance,
                "queue_tolerance": queue_tolerance,
                "dietary_preference": base_constraints.get("dietary_preference") or [],
                "activity_preference": activity_preference or ["chat", "relaxed"],
                "weather_sensitive": base_constraints.get("weather_sensitive", True),
                "child_friendly_required": False,
                "indoor_preferred": base_constraints.get("indoor_preferred", True) or "indoor" in activity_preference,
                "emotion_intensity": base_constraints.get("emotion_intensity") or "light",
                "time_flexibility": base_constraints.get("time_flexibility") or "medium",
                "must_have": list(dict.fromkeys(must_have)),
                "must_not_have": list(dict.fromkeys(must_not_have)),
            }
        )
        return constraints

    def _best_supported_plan(
        self,
        candidate_plan_ids: List[str],
        support_count_by_plan: Dict[str, int],
        oppose_count_by_plan: Dict[str, int],
    ) -> Dict[str, Any]:
        ranked = sorted(
            enumerate(candidate_plan_ids),
            key=lambda pair: (
                support_count_by_plan.get(pair[1], 0) - oppose_count_by_plan.get(pair[1], 0),
                support_count_by_plan.get(pair[1], 0),
                -pair[0],
            ),
            reverse=True,
        )
        selected_plan_id = ranked[0][1] if ranked else candidate_plan_ids[0]
        return self.plan_service.get_plan(selected_plan_id)

    def _strictest_tolerance(self, values: List[str], ordered_values: List[str], default: str) -> str:
        known_values = [value for value in values if value in ordered_values]
        if not known_values:
            return default if default in ordered_values else ordered_values[0]
        return min(known_values, key=ordered_values.index)

    def _feedback_tags(self, votes: List[Dict[str, Any]]) -> List[str]:
        text = " ".join(str(vote.get("free_text") or "") for vote in votes)
        tags = ["consensus"]
        if any(token in text for token in ("室内", "下雨", "雨天", "别晒")):
            tags.append("indoor")
        if any(token in text for token in ("聊天", "桌游", "坐着", "轻松")):
            tags.extend(["chat", "relaxed"])
        if any(token in text for token in ("拍照", "打卡")):
            tags.append("photo")
        if any(token in text for token in ("吃", "咖啡", "甜品")):
            tags.append("food")
        return list(dict.fromkeys(tags))

    def _detected_conflicts(self, votes: List[Dict[str, Any]], constraints: Dict[str, Any]) -> List[Dict[str, Any]]:
        conflicts = []
        if len(votes) < 2:
            conflicts.append({
                "type": "low_vote_count",
                "level": "medium",
                "description": "当前投票人数较少，最终方案基于已有反馈和候选方案降级生成。",
            })
        if constraints.get("walking_tolerance") in {"low", "medium_low"}:
            conflicts.append({
                "type": "walking_tolerance",
                "level": "medium",
                "description": "已有反馈显示步行容忍较低，最终方案优先少走路。",
            })
        if constraints.get("queue_tolerance") == "low":
            conflicts.append({
                "type": "queue_tolerance",
                "level": "medium",
                "description": "已有反馈显示排队容忍较低，最终方案优先低排队。",
            })
        if constraints.get("budget_max_per_person") is not None:
            conflicts.append({
                "type": "budget",
                "level": "medium",
                "description": f"已有反馈希望人均不超过{int(float(constraints['budget_max_per_person']))}元。",
            })
        return conflicts

    def _apply_consensus_constraints(self, plan: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
        final_plan = deepcopy(plan)
        merged_constraints = deepcopy(final_plan.get("constraints") or {})
        merged_constraints.update(deepcopy(constraints))
        final_plan["constraints"] = merged_constraints
        party_size = constraints.get("party_size")
        for action in final_plan.get("tool_actions", []):
            if isinstance(action.get("payload"), dict) and party_size:
                action["payload"]["party_size"] = party_size
        return final_plan

    def _clone_supported_plan_for_consensus(
        self,
        base_plan: Dict[str, Any],
        constraints: Dict[str, Any],
        session: Dict[str, Any],
        now: str,
    ) -> Dict[str, Any]:
        final_plan = deepcopy(base_plan)
        final_plan["plan_id"] = new_id("plan")
        final_plan["trace_id"] = session["trace_id"]
        final_plan["created_at"] = now
        final_plan["updated_at"] = now
        final_plan["status"] = "planned"
        self._remap_tool_action_ids(final_plan)
        final_plan.setdefault("messages", {})
        final_plan["messages"].pop("consensus_candidate_plan_ids", None)
        final_plan["messages"]["consensus_source_plan_id"] = base_plan.get("plan_id")
        final_plan["messages"]["to_group"] = self._group_message(constraints)
        return final_plan

    def _remap_tool_action_ids(self, plan: Dict[str, Any]) -> None:
        action_id_map: Dict[str, str] = {}
        for action in plan.get("tool_actions") or []:
            old_id = action.get("action_id")
            if not old_id:
                continue
            new_action_id = new_id("act")
            action_id_map[str(old_id)] = new_action_id
            action["action_id"] = new_action_id
        if not action_id_map:
            return
        for step in plan.get("timeline") or []:
            related_ids = step.get("related_tool_action_ids")
            if isinstance(related_ids, list):
                step["related_tool_action_ids"] = [action_id_map.get(str(action_id), action_id) for action_id in related_ids]

    def _final_plan_input_text(self, constraints: Dict[str, Any], base_plan: Optional[Dict[str, Any]] = None) -> str:
        budget = constraints.get("budget_max_per_person")
        budget_text = f"人均不超过{int(float(budget))}元，" if budget is not None else ""
        original_text = ((base_plan or {}).get("user_goal") or {}).get("raw_text")
        if original_text:
            return f"朋友局共识最终方案：保留「{original_text}」的核心安排，{budget_text}按大家投票收束。"
        return (
            "朋友局共识最终方案："
            f"{budget_text}少走路，少排队，适合{constraints.get('party_size', 4)}人，"
            "优先轻松聊天和室内备选。"
        )

    def _group_message(self, constraints: Dict[str, Any]) -> str:
        budget = constraints.get("budget_max_per_person")
        budget_text = f"人均约{int(float(budget))}以内，" if budget is not None else ""
        markers = set(str(item) for item in constraints.get("must_have") or [])
        if "esports" in markers and "dinner" in markers:
            focus = "保留打游戏和吃饭安排"
        elif "esports" in markers:
            focus = "保留打游戏安排"
        elif "karaoke" in markers:
            focus = "保留唱歌安排"
        elif "board_game" in markers:
            focus = "保留桌游棋牌安排"
        else:
            focus = "保留大家票数最高的候选方案"
        preferences = []
        if constraints.get("walking_tolerance") in {"low", "medium_low"}:
            preferences.append("少走路")
        if constraints.get("queue_tolerance") == "low":
            preferences.append("少排队")
        preference_text = "，" + "、".join(preferences) if preferences else ""
        return f"我让LifePilot按大家投票收束了一版：{budget_text}{focus}{preference_text}。"

    def _explanation(self, constraints: Dict[str, Any], detected_conflicts: List[Dict[str, Any]]) -> str:
        if not detected_conflicts:
            return "已将朋友投票压缩为共识约束，并基于该约束生成最终方案。"
        focus = "、".join(conflict["type"] for conflict in detected_conflicts[:3])
        return f"已优先处理{focus}等反馈，并将其转为最终方案约束。"
