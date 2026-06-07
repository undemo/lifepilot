from dataclasses import dataclass
from typing import Optional

from fastapi import Header, Request

from .constants import DEFAULT_DEMO_USER_ID
from .ids import new_id


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    trace_id: str
    idempotency_key: Optional[str]
    debug: bool


async def ensure_trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or new_id("trace")
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


def get_context(
    request: Request,
    x_demo_user_id: Optional[str] = Header(default=None, alias="X-Demo-User-Id"),
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
    x_debug_mode: Optional[str] = Header(default=None, alias="X-Debug-Mode"),
) -> RequestContext:
    trace_id = getattr(request.state, "trace_id", None) or new_id("trace")
    return RequestContext(
        user_id=x_demo_user_id or DEFAULT_DEMO_USER_ID,
        trace_id=trace_id,
        idempotency_key=x_idempotency_key,
        debug=(x_debug_mode or "").lower() == "true",
    )

