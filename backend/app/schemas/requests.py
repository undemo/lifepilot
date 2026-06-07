from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def request_model_dump(model: BaseModel) -> Dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    return model.dict(exclude_none=True)


class PlanCreateRequest(BaseModel):
    input_text: str = Field(..., min_length=1)
    user_location: Optional[Dict[str, Any]] = None
    current_time: Optional[str] = None
    preferred_duration_hours: Optional[float] = None
    preferred_start_time: Optional[str] = None
    preferred_end_time: Optional[str] = None
    scenario_hint: Optional[str] = None
    generate_candidates: Optional[bool] = False
    use_memory: Optional[bool] = True
    debug: Optional[bool] = False


class PlanVerifyRequest(BaseModel):
    force_refresh_mock_status: Optional[bool] = False
    reason: Optional[str] = "manual_verify"


class PlanExecuteRequest(BaseModel):
    confirmed: bool
    execute_action_ids: Optional[List[str]] = None
    allow_auto_recovery: Optional[bool] = True
    allow_message_mock_send: Optional[bool] = True
    confirmation_note: Optional[str] = None


class PlanRecoverRequest(BaseModel):
    trigger: str
    failed_step_id: Optional[str] = None
    failed_action_id: Optional[str] = None
    preferred_backup_plan_id: Optional[str] = None
    recovery_strategy: Optional[str] = None
    auto_verify: Optional[bool] = True


class PlanRefreshWindowRequest(BaseModel):
    reason: Optional[str] = "window_expired"
    force_refresh: Optional[bool] = True


class ConsensusCreateRequest(BaseModel):
    plan_group_id: Optional[str] = None
    candidate_plan_ids: List[str]
    title: Optional[str] = None
    expire_at: Optional[str] = None
    allow_anonymous: Optional[bool] = True
    creator_user_id: Optional[str] = None


class ConsensusVoteRequest(BaseModel):
    participant: Dict[str, Any]
    liked_plan_ids: Optional[List[str]] = None
    disliked_plan_ids: Optional[List[str]] = None
    budget_max: Optional[float] = None
    time_preference: Optional[str] = None
    walking_tolerance: Optional[str] = None
    queue_tolerance: Optional[str] = None
    free_text: Optional[str] = None
    client_vote_token: Optional[str] = None


class ConsensusFinalizeRequest(BaseModel):
    close_voting: Optional[bool] = True
    force_regenerate: Optional[bool] = False
    min_vote_count_policy: Optional[str] = "allow_low_vote_count"


class FeedbackRequest(BaseModel):
    plan_id: str
    execution_id: Optional[str] = None
    rating: Optional[str] = None
    selected_options: Optional[List[str]] = None
    free_text: Optional[str] = None
    skipped: Optional[bool] = False


class MemoryCandidateConfirmRequest(BaseModel):
    edited_content: Optional[str] = None
    ttl_days: Optional[int] = None
    enabled: Optional[bool] = True
    confirmed: Optional[bool] = True


class MemoryPatchRequest(BaseModel):
    content: Optional[str] = None
    ttl_days: Optional[int] = None
    enabled: Optional[bool] = None


class LLMSettingsPatch(BaseModel):
    provider: Optional[str] = None
    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    credential: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: Optional[float] = None
    retry: Optional[int] = None
    enable_thinking: Optional[bool] = None
