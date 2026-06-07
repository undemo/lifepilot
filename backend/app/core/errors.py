from typing import Any, Dict, Optional

from .constants import ErrorCode


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        user_message: str,
        status_code: int = 400,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.user_message = user_message
        self.status_code = status_code
        self.recoverable = recoverable
        self.details = details or {}
        super().__init__(message)


def bad_request(message: str, user_message: str = "请求参数不完整，请检查后重试。") -> AppError:
    return AppError(ErrorCode.BAD_REQUEST, message, user_message, 400, True)


def not_found(resource: str) -> AppError:
    return AppError(
        ErrorCode.RESOURCE_NOT_FOUND,
        f"{resource} not found.",
        "没有找到对应资源，可能已被删除或链接错误。",
        404,
        False,
    )

