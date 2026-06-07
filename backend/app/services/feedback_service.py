from typing import Any, Dict

from app.core.constants import TraceEventType
from app.core.data_paths import FEEDBACK_STORE_PATH
from app.core.errors import bad_request
from app.core.ids import new_id
from app.core.time import iso_now
from app.services.logging_service import LoggingService
from app.services.plan_service import PlanService
from app.storage.json_store import JsonFileStore


class FeedbackService:
    FILE = FEEDBACK_STORE_PATH

    def __init__(self, store: JsonFileStore, logging_service: LoggingService, plan_service: PlanService, life_memory_service=None) -> None:
        self.store = store
        self.logging_service = logging_service
        self.plan_service = plan_service
        self.life_memory_service = life_memory_service

    def questions(self, plan_id: str) -> Dict[str, Any]:
        self.plan_service.get_plan(plan_id)
        return {
            "plan_id": plan_id,
            "questions": [
                {
                    "question_id": "q_0001",
                    "type": "single_choice",
                    "text": "今天这套安排整体感觉怎么样？",
                    "options": [
                        {"value": "just_right", "label": "刚刚好"},
                        {"value": "too_rushed", "label": "有点赶"},
                        {"value": "child_not_interested", "label": "孩子不太感兴趣"},
                        {"value": "restaurant_not_good", "label": "餐厅不太合适"},
                        {"value": "queue_too_long", "label": "排队还是太久"},
                    ],
                },
                {
                    "question_id": "q_0002",
                    "type": "single_choice",
                    "text": "下次家庭出行，你更希望我优先避开哪类问题？",
                    "options": [
                        {"value": "queue", "label": "排队"},
                        {"value": "distance", "label": "距离"},
                        {"value": "budget", "label": "预算"},
                        {"value": "child_bored", "label": "孩子无聊"},
                        {"value": "restaurant", "label": "餐饮不合适"},
                    ],
                },
            ],
            "max_questions": 2,
            "skippable": True,
        }

    def submit(self, user_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        plan_id = body.get("plan_id")
        if not plan_id:
            raise bad_request("plan_id is required.")
        plan = self.plan_service.get_plan(plan_id)
        now = iso_now()
        skipped = bool(body.get("skipped", False))
        feedback_id = new_id("fb")
        free_text = str(body.get("free_text") or "").strip()
        memory_candidates = []
        if not skipped and self.life_memory_service is not None and (free_text or body.get("selected_options")):
            memory_candidates = self.life_memory_service.create_candidates_from_feedback(
                user_id=user_id,
                plan=plan,
                feedback={**body, "free_text": free_text},
            )
        record = {
            "feedback_id": feedback_id,
            "user_id": user_id,
            "plan_id": plan_id,
            "execution_id": body.get("execution_id"),
            "rating": body.get("rating"),
            "selected_options": body.get("selected_options") or [],
            "free_text": free_text,
            "skipped": skipped,
            "memory_candidates": memory_candidates,
            "created_at": now,
        }
        payload = self.store.read(self.FILE, {"version": "v0.1", "feedback": {}})
        payload.setdefault("feedback", {})[feedback_id] = record
        self.store.write(self.FILE, payload)
        self.logging_service.log(
            plan["trace_id"],
            TraceEventType.FEEDBACK_LOG,
            "FeedbackService",
            {"user_visible_message": "已收到反馈。", "feedback_id": feedback_id, "skipped": skipped},
            plan_id=plan_id,
        )
        return {
            "feedback_id": feedback_id,
            "plan_id": plan_id,
            "accepted": True,
            "skipped": skipped,
            "memory_candidates": memory_candidates,
            "created_at": now,
        }
