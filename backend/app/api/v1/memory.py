from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_container
from app.core.context import RequestContext, get_context
from app.core.responses import success_response
from app.schemas.requests import MemoryCandidateConfirmRequest, MemoryPatchRequest, request_model_dump
from app.services.container import ServiceContainer

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def list_memory(
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.get_memory(context.user_id)
    return success_response(context.trace_id, data)


@router.get("/candidates")
def list_memory_candidates(
    status: Optional[str] = Query(default=None),
    source_trace_id: Optional[str] = Query(default=None),
    plan_id: Optional[str] = Query(default=None),
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.get_candidates(
        context.user_id,
        status=status,
        source_trace_id=source_trace_id,
        plan_id=plan_id,
    )
    return success_response(context.trace_id, data)


@router.post("/candidates/{candidate_id}/confirm")
def confirm_memory_candidate(
    candidate_id: str,
    body: MemoryCandidateConfirmRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.confirm_candidate(context.user_id, candidate_id, request_model_dump(body))
    return success_response(context.trace_id, data)


@router.post("/candidates/{candidate_id}/ignore")
def ignore_memory_candidate(
    candidate_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.ignore_candidate(context.user_id, candidate_id)
    return success_response(context.trace_id, data)


@router.patch("/{memory_id}")
def update_memory(
    memory_id: str,
    body: MemoryPatchRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.update_memory(context.user_id, memory_id, request_model_dump(body))
    return success_response(context.trace_id, data)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.delete_memory(context.user_id, memory_id)
    return success_response(context.trace_id, data)


@router.post("/personalization/disable")
def disable_personalization(
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.set_personalization(context.user_id, False)
    return success_response(context.trace_id, data)


@router.post("/personalization/enable")
def enable_personalization(
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.life_memory_service.set_personalization(context.user_id, True)
    return success_response(context.trace_id, data)
