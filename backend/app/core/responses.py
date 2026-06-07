from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

from .constants import ErrorCode


def success_response(trace_id: Optional[str], data: Any) -> Dict[str, Any]:
    return {
        "success": True,
        "trace_id": trace_id,
        "data": data,
        "error": None,
    }


def error_payload(
    code: ErrorCode,
    message: str,
    user_message: str,
    recoverable: bool,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "code": code.value,
        "message": message,
        "user_message": user_message,
        "recoverable": recoverable,
        "details": details or {},
    }


def error_response(
    trace_id: Optional[str],
    code: ErrorCode,
    message: str,
    user_message: str,
    recoverable: bool,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "trace_id": trace_id,
            "data": None,
            "error": error_payload(code, message, user_message, recoverable, details),
        },
    )

