import hashlib
import json
from typing import Any, Dict, Optional

from app.core.constants import ErrorCode
from app.core.data_paths import IDEMPOTENCY_STORE_PATH
from app.core.errors import AppError
from app.storage.json_store import JsonFileStore


class IdempotencyService:
    FILE = IDEMPOTENCY_STORE_PATH

    def __init__(self, store: JsonFileStore) -> None:
        self.store = store

    def require_key(self, key: Optional[str], api_name: str) -> str:
        if not key:
            raise AppError(
                ErrorCode.BAD_REQUEST,
                "X-Idempotency-Key is required for execution APIs.",
                "请勿重复提交，刷新后再试。",
                400,
                True,
                {"api": api_name},
            )
        return key

    def fingerprint(self, value: Any) -> str:
        normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, user_id: str, key: Optional[str], scope: str, fingerprint: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        payload = self.store.read(self.FILE, {"version": "v0.1", "records": {}})
        record_key = self._record_key(user_id, key, scope)
        record = payload.get("records", {}).get(record_key)
        if not record:
            return None
        if record.get("fingerprint") != fingerprint:
            raise AppError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "X-Idempotency-Key was reused for different input.",
                "请求已提交过，但本次内容不同，请刷新后重试。",
                409,
                True,
                {"scope": scope},
            )
        return record.get("response_data")

    def save(self, user_id: str, key: Optional[str], scope: str, fingerprint: str, response_data: Dict[str, Any]) -> None:
        if not key:
            return
        payload = self.store.read(self.FILE, {"version": "v0.1", "records": {}})
        payload.setdefault("records", {})[self._record_key(user_id, key, scope)] = {
            "user_id": user_id,
            "key": key,
            "scope": scope,
            "fingerprint": fingerprint,
            "response_data": response_data,
        }
        self.store.write(self.FILE, payload)

    def _record_key(self, user_id: str, key: str, scope: str) -> str:
        return f"{user_id}:{scope}:{key}"
