from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.core.context import RequestContext, get_context
from app.core.responses import success_response
from app.schemas.requests import FeedbackRequest, request_model_dump
from app.services.container import ServiceContainer

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/questions")
def feedback_questions(
    plan_id: str,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.feedback_service.questions(plan_id)
    plan = container.plan_service.get_plan(plan_id)
    return success_response(plan["trace_id"], data)


@router.post("")
def submit_feedback(
    body: FeedbackRequest,
    context: RequestContext = Depends(get_context),
    container: ServiceContainer = Depends(get_container),
):
    data = container.feedback_service.submit(context.user_id, request_model_dump(body))
    plan = container.plan_service.get_plan(data["plan_id"])
    return success_response(plan["trace_id"], data)
