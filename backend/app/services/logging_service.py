import threading
from contextlib import contextmanager
from queue import Queue
from typing import Any, Dict, Iterator, List, Optional

from app.core.constants import FORBIDDEN_LOG_KEYS, TraceEventType, USER_HIDDEN_LOG_KEYS
from app.core.data_paths import TRACES_STORE_PATH
from app.core.ids import new_id
from app.core.time import iso_now
from app.services.schema_validator import SchemaValidator
from app.storage.json_store import JsonFileStore


class LoggingService:
    FILE = TRACES_STORE_PATH

    def __init__(self, store: JsonFileStore, validator: SchemaValidator) -> None:
        self.store = store
        self.validator = validator
        self._subscriber_lock = threading.RLock()
        self._subscribers: Dict[str, List[Queue]] = {}

    def log(
        self,
        trace_id: str,
        event_type: TraceEventType,
        module: str,
        payload: Dict[str, Any],
        plan_id: Optional[str] = None,
        level: str = "info",
        visible_to_user: bool = True,
    ) -> Dict[str, Any]:
        self.validator.validate_trace_event_type(event_type.value)
        record = {
            "log_id": new_id("log"),
            "trace_id": trace_id,
            "plan_id": plan_id,
            "module": module,
            "event_type": event_type.value,
            "level": level,
            "payload": self._sanitize(payload, FORBIDDEN_LOG_KEYS),
            "visible_to_user": visible_to_user,
            "created_at": iso_now(),
        }
        payload = self.store.read(self.FILE, {"version": "v0.1", "logs": []})
        payload.setdefault("logs", []).append(record)
        self.store.write(self.FILE, payload)
        self._publish(record)
        return record

    @contextmanager
    def subscribe(self, trace_id: str) -> Iterator[Queue]:
        queue: Queue = Queue()
        with self._subscriber_lock:
            self._subscribers.setdefault(trace_id, []).append(queue)
        try:
            yield queue
        finally:
            with self._subscriber_lock:
                subscribers = self._subscribers.get(trace_id, [])
                if queue in subscribers:
                    subscribers.remove(queue)
                if not subscribers:
                    self._subscribers.pop(trace_id, None)

    def list_for_plan(self, plan_id: str, trace_id: str, visible_only: bool = True) -> List[Dict[str, Any]]:
        payload = self.store.read(self.FILE, {"version": "v0.1", "logs": []})
        events = []
        for record in payload.get("logs", []):
            if record.get("trace_id") != trace_id:
                continue
            if record.get("plan_id") not in (plan_id, None):
                continue
            if visible_only and not record.get("visible_to_user", False):
                continue
            events.append(self.to_user_visible_event(record))
        return sorted(events, key=lambda item: item["created_at"])

    def to_user_visible_event(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._sanitize(record.get("payload", {}), USER_HIDDEN_LOG_KEYS)
        return {
            "log_id": record["log_id"],
            "trace_id": record["trace_id"],
            "event_type": record["event_type"],
            "module": record["module"],
            "level": record["level"],
            "user_visible_message": payload.get("user_visible_message") or payload.get("message") or record["module"],
            "created_at": record["created_at"],
        }

    def _sanitize(self, value: Any, forbidden_keys: set) -> Any:
        if isinstance(value, dict):
            return {
                key: self._sanitize(child, forbidden_keys)
                for key, child in value.items()
                if not self._is_forbidden_key(str(key), forbidden_keys)
            }
        if isinstance(value, list):
            return [self._sanitize(item, forbidden_keys) for item in value]
        return value

    def _is_forbidden_key(self, key: str, forbidden_keys: set) -> bool:
        normalized = key.lower()
        return normalized in forbidden_keys or "api_key" in normalized

    def _publish(self, record: Dict[str, Any]) -> None:
        with self._subscriber_lock:
            subscribers = list(self._subscribers.get(record["trace_id"], []))
        for queue in subscribers:
            queue.put(record)
