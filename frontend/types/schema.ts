export type JsonRecord = Record<string, unknown>;

export type StandardError = {
  code: string;
  message?: string;
  user_message: string;
  recoverable?: boolean;
  details?: JsonRecord;
};

export type StandardResponse<T> = {
  success: boolean;
  trace_id: string | null;
  data: T | null;
  error: StandardError | null;
};

export type Participant = {
  participant_id?: string;
  role?: string;
  display_name?: string;
  participant_name?: string;
  anonymous?: boolean;
  preference_tags?: string[];
  constraints?: unknown[];
};

export type RouteEstimate = {
  duration_minutes?: number;
  distance_km?: number;
  distance_meters?: number;
  transport_mode?: string;
  traffic_level?: string;
  summary?: string;
};

export type PlanStep = {
  step_id: string;
  order: number;
  type: string;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  duration_minutes?: number;
  poi_id?: string | null;
  from_poi_id?: string | null;
  to_poi_id?: string | null;
  transport_mode?: string | null;
  estimated_route?: RouteEstimate | null;
  booking_required?: boolean;
  reservation_required?: boolean;
  status?: string;
  related_tool_action_ids?: string[];
  display_tags?: string[];
  user_visible_notes?: string;
};

export type Budget = {
  currency?: string;
  estimated_total?: number;
  price_per_person?: number;
  items?: Array<{ name?: string; amount?: number; source?: string }>;
};

export type ExecutableWindow = {
  window_minutes?: number;
  confidence?: number;
  expire_at?: string;
  reasons?: string[];
  risk_factors?: string[];
  lockable_resources?: string[];
  calculated_from?: string[];
  display_message?: string;
};

export type Risk = {
  risk_id?: string;
  type?: string;
  level?: string;
  message?: string;
  description?: string;
  mitigation?: string;
  user_visible?: boolean;
  related_step_id?: string;
  related_poi_id?: string;
};

export type BackupPlan = {
  backup_plan_id?: string;
  trigger?: string;
  description?: string;
  replace_step_id?: string | null;
  original_poi_id?: string | null;
  new_poi_id?: string | null;
  expected_diff?: JsonRecord;
  verifier_result?: VerifierResult | null;
  priority?: number;
  status?: string;
};

export type ToolAction = {
  action_id: string;
  plan_id?: string;
  step_id?: string;
  type: string;
  target_poi_id?: string | null;
  target?: string | null;
  payload?: JsonRecord | null;
  status?: "pending" | "running" | "success" | "failed" | "recovered" | "skipped" | string;
  depends_on?: string[];
  retry_count?: number;
  idempotency_key?: string;
  result?: JsonRecord | null;
  error_code?: string | null;
  user_visible?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type VerifierResult = {
  status?: string;
  score?: number;
  checks?: JsonRecord[];
  failed_checks?: JsonRecord[];
  warnings?: string[];
  required_recovery?: boolean;
  suggestions?: string[];
  created_at?: string;
};

export type RecoveryResult = {
  recovery_id?: string;
  trigger?: string;
  status?: string;
  original?: JsonRecord;
  replacement?: JsonRecord;
  diff?: JsonRecord;
  updated_plan_id?: string;
  verifier_result?: VerifierResult;
  user_explanation?: string;
  created_at?: string;
};

export type ExecutionResult = {
  execution_id: string;
  plan_id: string;
  trace_id?: string;
  status?: string;
  action_results?: Array<{ action_id?: string; type?: string; status?: string; result?: JsonRecord }>;
  vouchers?: Array<{ type?: string; value?: string; display_name?: string; poi_id?: string; poi_name?: string; mock_only?: boolean; created_at?: string }>;
  failed_actions?: ToolAction[];
  recovery_results?: RecoveryResult[];
  user_message?: string;
  created_at?: string;
};

export type PlanContract = {
  plan_id: string;
  trace_id: string;
  version?: string;
  status?: string;
  user_goal?: {
    raw_text?: string;
    scenario?: string;
    goal_summary?: string;
    intent_tags?: string[];
    emotion_goal?: string | null;
    source?: string;
    confidence?: number;
  };
  participants?: Participant[];
  time_window?: { start_time?: string; end_time?: string; time_flexibility?: string };
  constraints?: JsonRecord;
  timeline?: PlanStep[];
  budget?: Budget;
  executable_window?: ExecutableWindow;
  risks?: Risk[];
  backup_plans?: BackupPlan[];
  tool_actions?: ToolAction[];
  messages?: JsonRecord;
  verifier_result?: VerifierResult;
  recovery_results?: RecoveryResult[];
  execution_summary?: JsonRecord | null;
  memory_usage?: JsonRecord[];
  social_signals?: JsonRecord[];
  created_at?: string;
  updated_at?: string;
};

export type PlanPayload = {
  plan_contract: PlanContract;
  latest_execution_result?: ExecutionResult | null;
  latest_recovery_results?: RecoveryResult[];
  candidate_plan_ids?: string[];
};

export type PlanCreateResponse = {
  trace_id: string;
  plan_id: string;
  plan_contract: PlanContract;
  UserVisiblePlanProjection?: JsonRecord;
  candidate_plan_ids?: string[];
  tool_trace_summary?: Array<{ module?: string; event?: string; status?: string }>;
  memory_candidates?: MemoryCandidate[];
};

export type ConsensusSessionPayload = {
  consensus_session_id: string;
  vote_page_id: string;
  plan_group_id?: string;
  trace_id: string;
  title?: string;
  status?: string;
  candidate_plan_ids?: string[];
  candidates?: PlanSummary[];
  plan_summaries?: PlanSummary[];
  votes?: JsonRecord[];
  consensus_summary?: ConsensusSummary | null;
  final_plan_id?: string | null;
  share_url?: string;
  expire_at?: string;
};

export type PlanSummary = {
  plan_id: string;
  title?: string;
  goal_summary?: string;
  status?: string;
  score?: number;
  timeline_summary?: string[];
  budget?: Budget;
  executable_window?: ExecutableWindow;
  walking_tolerance_label?: string;
  queue_risk_label?: string;
};

export type ConsensusSummary = {
  consensus_session_id?: string;
  final_plan_id?: string;
  support_count_by_plan?: Record<string, number>;
  oppose_count_by_plan?: Record<string, number>;
  detected_conflicts?: JsonRecord[];
  explanation?: string;
  group_message?: string;
  vote_count?: number;
};

export type FeedbackQuestion = {
  question_id: string;
  type: string;
  text: string;
  options?: Array<{ value: string; label: string }>;
};

export type MemoryCandidate = {
  candidate_id: string;
  user_id?: string;
  source_trace_id?: string;
  content?: string;
  memory_type?: string;
  source?: JsonRecord;
  confidence?: number;
  sensitivity?: "low" | "medium" | "high" | string;
  requires_confirmation?: boolean;
  status?: string;
  suggested_ttl_days?: number;
  hints?: JsonRecord;
  created_at?: string;
  updated_at?: string;
};

export type LifeMemory = {
  memory_id: string;
  user_id?: string;
  content?: string;
  memory_type?: string;
  sensitivity?: string;
  status?: string;
  source?: JsonRecord;
  source_trace_id?: string;
  last_used_trace_id?: string;
  confidence?: number;
  ttl_days?: number;
  user_confirmed?: boolean;
  enabled?: boolean;
  hints?: JsonRecord;
  last_used_at?: string | null;
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
};

export type ShortTermProfile = {
  short_term_id?: string;
  source_trace_id?: string;
  summary?: string;
  scenario?: string;
  normalized_tags?: string[];
  tag_axes?: JsonRecord;
  created_at?: string;
  expires_at?: string;
};

export type MemoryProfileSummary = {
  enabled_count?: number;
  pending_count?: number;
  top_tags?: string[];
  short_term_summary?: string;
  has_recent_short_term?: boolean;
};

export type MemoryPayload = {
  personalization_enabled?: boolean;
  memories?: LifeMemory[];
  items?: LifeMemory[];
  short_term_profile?: ShortTermProfile | null;
  profile_summary?: MemoryProfileSummary;
  page_info?: JsonRecord;
};

export type TraceEvent = {
  trace_id: string;
  event_type: string;
  module?: string;
  created_at?: string;
  visible_to_user?: boolean;
  plan_id?: string;
  payload?: JsonRecord;
};

export type LLMProviderOption = {
  provider: string;
  label: string;
  default_base_url: string;
  default_model: string;
};

export type LLMSettings = {
  provider: string;
  enabled: boolean;
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
  timeout: number;
  retry: number;
  enable_thinking: boolean;
  credential_configured: boolean;
  credential_mask: string;
  available_providers: LLMProviderOption[];
};
