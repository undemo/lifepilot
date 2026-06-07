from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.core.context import RequestContext, get_context
from app.core.errors import bad_request
from app.core.responses import success_response
from app.schemas.requests import LLMSettingsPatch, request_model_dump
from app.services.container import ServiceContainer

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm")
def get_llm_settings(
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    return success_response(context.trace_id, container.llm_client.snapshot())


@router.patch("/llm")
def update_llm_settings(
    body: LLMSettingsPatch,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    try:
        data = container.llm_client.update_settings(request_model_dump(body))
    except ValueError as exc:
        raise bad_request(str(exc), "模型设置参数不合法，请检查后重试。") from exc
    return success_response(context.trace_id, data)
