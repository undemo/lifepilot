from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.core.context import RequestContext, get_context
from app.core.responses import success_response
from app.schemas.requests import ConsensusCreateRequest, ConsensusFinalizeRequest, ConsensusVoteRequest, request_model_dump
from app.services.container import ServiceContainer

router = APIRouter(prefix="/consensus", tags=["consensus"])


@router.post("/create")
def create_consensus(
    body: ConsensusCreateRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.consensus_service.create_session(
        context.user_id,
        context.trace_id,
        context.idempotency_key,
        request_model_dump(body),
    )
    return success_response(context.trace_id, data)


@router.get("/{consensus_session_id}")
def get_consensus(
    consensus_session_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.consensus_service.get_session_payload(consensus_session_id)
    return success_response(data["trace_id"], data)


@router.post("/{consensus_session_id}/vote")
def vote(
    consensus_session_id: str,
    body: ConsensusVoteRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    session = container.consensus_service.get_session(consensus_session_id)
    data = container.consensus_service.vote(consensus_session_id, session["trace_id"], request_model_dump(body))
    return success_response(session["trace_id"], data)


@router.post("/{consensus_session_id}/finalize")
def finalize(
    consensus_session_id: str,
    body: ConsensusFinalizeRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    session = container.consensus_service.get_session(consensus_session_id)
    data = container.consensus_service.finalize(consensus_session_id, context.user_id, request_model_dump(body))
    return success_response(session["trace_id"], data)


@router.get("/{consensus_session_id}/summary")
def summary(
    consensus_session_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.consensus_service.summary(consensus_session_id)
    return success_response(data["trace_id"], data)
