from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import default_data_dir
from app.api.mock import create_mock_router
from app.api.v1.consensus import router as consensus_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.memory import router as memory_router
from app.api.v1.plans import router as plans_router
from app.api.v1.settings import router as settings_router
from app.api.v1.vote_pages import router as vote_pages_router
from app.core.constants import API_PREFIX, ErrorCode, TraceEventType
from app.core.context import ensure_trace_middleware
from app.core.errors import AppError
from app.core.responses import error_response, success_response
from app.services.container import ServiceContainer


def create_app(data_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="LifePilot Backend API", version="0.1.0")
    resolved_data_dir = data_dir or default_data_dir()
    app.state.data_dir = resolved_data_dir
    container = ServiceContainer(resolved_data_dir)
    app.state.container = container

    app.middleware("http")(ensure_trace_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    app.include_router(plans_router, prefix=API_PREFIX)
    app.include_router(consensus_router, prefix=API_PREFIX)
    app.include_router(vote_pages_router, prefix=API_PREFIX)
    app.include_router(feedback_router, prefix=API_PREFIX)
    app.include_router(memory_router, prefix=API_PREFIX)
    app.include_router(settings_router, prefix=API_PREFIX)
    app.include_router(create_mock_router(container.mock_api_service))

    @app.get("/health")
    def health():
        return success_response(None, {"status": "ok"})

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        trace_id = getattr(request.state, "trace_id", None)
        if not request.url.path.startswith("/api/v1/mock/"):
            _log_error(request, trace_id, exc.code.value, exc.message)
        return error_response(
            trace_id,
            exc.code,
            exc.message,
            exc.user_message,
            exc.recoverable,
            exc.status_code,
            exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", None)
        if not request.url.path.startswith("/api/v1/mock/"):
            _log_error(request, trace_id, ErrorCode.BAD_REQUEST.value, "request validation failed.")
        return error_response(
            trace_id,
            ErrorCode.BAD_REQUEST,
            "request validation failed.",
            "请求参数不完整，请检查后重试。",
            True,
            400,
            {"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", None)
        if not request.url.path.startswith("/api/v1/mock/"):
            _log_error(request, trace_id, ErrorCode.INTERNAL_ERROR.value, "unexpected internal error.", visible_to_user=False)
        return error_response(
            trace_id,
            ErrorCode.INTERNAL_ERROR,
            "unexpected internal error.",
            "系统暂时不可用，请稍后重试。",
            True,
            500,
            {},
        )

    return app


def _log_error(request: Request, trace_id, code: str, message: str, visible_to_user: bool = False) -> None:
    try:
        request.app.state.container.logging_service.log(
            trace_id or "trace_unavailable",
            TraceEventType.ERROR_LOG,
            "BackendAPI",
            {"code": code, "message": message, "user_visible_message": "请求处理失败。"},
            visible_to_user=visible_to_user,
            level="error",
        )
    except Exception:
        pass


app = create_app()
