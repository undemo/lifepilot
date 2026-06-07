from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.core.context import RequestContext, get_context
from app.core.responses import success_response
from app.services.container import ServiceContainer

router = APIRouter(prefix="/vote-pages", tags=["vote-pages"])


@router.get("/{vote_page_id}")
def get_vote_page(
    vote_page_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.consensus_service.get_vote_page(vote_page_id)
    return success_response(data["trace_id"], data)
