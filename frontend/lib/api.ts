import type {
  ConsensusSessionPayload,
  ExecutionResult,
  FeedbackQuestion,
  LifeMemory,
  LLMSettings,
  MemoryCandidate,
  MemoryPayload,
  PlanCreateResponse,
  PlanPayload,
  StandardError,
  StandardResponse,
  TraceEvent
} from "@/types/schema";
import { getOrCreateIdempotencyKey, newIdempotencyKey } from "./idempotency";
import { getOrCreateTraceId, saveTraceId } from "./trace";

export class ApiClientError extends Error {
  error: StandardError;
  traceId: string | null;

  constructor(error: StandardError, traceId: string | null) {
    super(error.user_message || "请求失败");
    this.error = error;
    this.traceId = traceId;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  traceId?: string;
  idempotencyKey?: string;
  idempotencyScope?: string;
  execution?: boolean;
  debug?: boolean;
};

const API_BASE = "/api/v1";

export type PlanCreateBody = {
  input_text: string;
  scenario_hint?: string;
  generate_candidates?: boolean;
  use_memory?: boolean;
  debug?: boolean;
  user_location?: { label?: string; area?: string; lat?: number; lng?: number };
  current_time?: string;
  preferred_duration_hours?: number;
  preferred_start_time?: string;
  preferred_end_time?: string;
};

export type PlanCreateStreamPrepared = {
  body: PlanCreateBody;
  traceId: string;
  idempotencyKey: string;
};

export type PlanCreateAgentEvent = {
  event_id?: string;
  phase?: "thinking" | "tool" | "verify" | "render" | "error" | string;
  kind?: string;
  title?: string;
  message?: string;
  status?: "success" | "warning" | "error" | string;
  created_at?: string;
};

export type PlanCreateStreamEvent =
  | { event: "start"; data: { trace_id?: string } }
  | { event: "agent_event"; data: PlanCreateAgentEvent }
  | { event: "complete"; data: { trace_id?: string; data: PlanCreateResponse } }
  | { event: "error"; data: { trace_id?: string; error: StandardError } };

export async function request<T>(path: string, options: RequestOptions = {}): Promise<{ data: T; traceId: string | null }> {
  if (!path.startsWith("/")) {
    throw new Error("API path must start with /");
  }
  const method = options.method || "GET";
  const isWrite = method !== "GET";
  const traceId = resolveTraceId(options, isWrite);
  const headers = buildHeaders(path, options, traceId, isWrite);

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store"
  });
  const parsed = (await response.json().catch(() => null)) as StandardResponse<T> | null;
  if (!parsed || parsed.success !== true || !response.ok) {
    const fallback: StandardError = {
      code: "INTERNAL_ERROR",
      user_message: "系统暂时不可用，请稍后再试。",
      recoverable: true,
      details: {}
    };
    throw new ApiClientError(parsed?.error || fallback, parsed?.trace_id || traceId || null);
  }
  saveTraceId(parsed.trace_id);
  return { data: parsed.data as T, traceId: parsed.trace_id };
}

function resolveTraceId(options: RequestOptions, isWrite: boolean): string | undefined {
  return isWrite ? options.traceId || getOrCreateTraceId() : options.traceId;
}

function buildHeaders(path: string, options: RequestOptions, traceId: string | undefined, isWrite: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Client-Version": "web-demo-0.1",
    "X-Demo-User-Id": "user_demo_001"
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (traceId) headers["X-Trace-Id"] = traceId;
  if (options.debug) headers["X-Debug-Mode"] = "true";
  if (isWrite) headers["X-Idempotency-Key"] = resolveIdempotencyKey(path, options);
  if (options.execution && !headers["X-Idempotency-Key"]) headers["X-Idempotency-Key"] = newIdempotencyKey("exec");
  return headers;
}

function resolveIdempotencyKey(path: string, options: RequestOptions): string {
  if (options.idempotencyKey) return options.idempotencyKey;
  if (options.idempotencyScope) {
    return getOrCreateIdempotencyKey(options.idempotencyScope, JSON.stringify({ path, body: options.body ?? null }));
  }
  return newIdempotencyKey(options.execution ? "exec" : "write");
}

export const api = {
  createPlan(body: PlanCreateBody) {
    return request<PlanCreateResponse>("/plans/create", {
      method: "POST",
      body,
      idempotencyScope: "plans.create"
    });
  },
  prepareCreatePlanStream(body: PlanCreateBody): PlanCreateStreamPrepared {
    const traceId = getOrCreateTraceId();
    const idempotencyKey = getOrCreateIdempotencyKey("plans.create", planCreateStableId(body));
    return { body, traceId, idempotencyKey };
  },
  streamCreatePlan(
    prepared: PlanCreateStreamPrepared,
    onEvent: (event: PlanCreateStreamEvent) => void,
    signal?: AbortSignal
  ) {
    return streamCreatePlan(prepared, onEvent, signal);
  },
  getPlan(planId: string) {
    return request<PlanPayload>(`/plans/${encodeURIComponent(planId)}`);
  },
  verifyPlan(planId: string, traceId?: string) {
    return request(`/plans/${encodeURIComponent(planId)}/verify`, {
      method: "POST",
      traceId,
      body: { reason: "manual_verify", force_refresh_mock_status: false },
      idempotencyScope: "plans.verify"
    });
  },
  refreshWindow(planId: string, traceId?: string) {
    return request(`/plans/${encodeURIComponent(planId)}/refresh-window`, {
      method: "POST",
      traceId,
      body: { reason: "window_expired", force_refresh: true },
      idempotencyScope: "plans.refresh-window"
    });
  },
  executePlan(planId: string, traceId?: string) {
    return request<{ execution_id: string; execution_result: ExecutionResult; active_plan_id?: string; recovery_results?: unknown[] }>(
      `/plans/${encodeURIComponent(planId)}/execute`,
      {
        method: "POST",
        traceId,
        execution: true,
        idempotencyScope: "plans.execute",
        body: { confirmed: true, allow_auto_recovery: true, allow_message_mock_send: true }
      }
    );
  },
  recoverPlan(planId: string, trigger: string, traceId?: string) {
    return request(`/plans/${encodeURIComponent(planId)}/recover`, {
      method: "POST",
      traceId,
      execution: true,
      idempotencyScope: "plans.recover",
      body: { trigger, recovery_strategy: "replace_poi_same_area", auto_verify: true }
    });
  },
  getPlanTrace(planId: string, includeDebug = false) {
    return request<{ plan_id: string; events: TraceEvent[] }>(
      `/plans/${encodeURIComponent(planId)}/trace?visible_only=${includeDebug ? "false" : "true"}&include_debug=${includeDebug ? "true" : "false"}`
    );
  },
  createConsensus(candidatePlanIds: string[], traceId?: string) {
    const expireAt = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
    return request<{ consensus_session_id: string; vote_page_id: string; share_url?: string }>(
      "/consensus/create",
      {
        method: "POST",
        traceId,
        body: {
          candidate_plan_ids: candidatePlanIds,
          title: "朋友局投票",
          expire_at: expireAt,
          allow_anonymous: true
        },
        idempotencyScope: "consensus.create"
      }
    );
  },
  getVotePage(votePageId: string) {
    return request<ConsensusSessionPayload>(`/vote-pages/${encodeURIComponent(votePageId)}`);
  },
  getConsensus(consensusSessionId: string) {
    return request<ConsensusSessionPayload>(`/consensus/${encodeURIComponent(consensusSessionId)}`);
  },
  submitVote(consensusSessionId: string, body: unknown, traceId?: string) {
    return request(`/consensus/${encodeURIComponent(consensusSessionId)}/vote`, {
      method: "POST",
      traceId,
      body,
      idempotencyScope: "consensus.vote"
    });
  },
  finalizeConsensus(consensusSessionId: string, traceId?: string) {
    return request<{ final_plan_id?: string; consensus_summary?: unknown; group_message?: string }>(
      `/consensus/${encodeURIComponent(consensusSessionId)}/finalize`,
      {
        method: "POST",
        traceId,
        body: { close_voting: true, min_vote_count_policy: "allow_low_vote_count" },
        idempotencyScope: "consensus.finalize"
      }
    );
  },
  getConsensusSummary(consensusSessionId: string) {
    return request<ConsensusSessionPayload>(`/consensus/${encodeURIComponent(consensusSessionId)}/summary`);
  },
  getFeedbackQuestions(planId: string) {
    return request<{ plan_id: string; questions: FeedbackQuestion[]; max_questions?: number; skippable?: boolean }>(
      `/feedback/questions?plan_id=${encodeURIComponent(planId)}`
    );
  },
  submitFeedback(body: unknown, traceId?: string) {
    return request<{ feedback_id: string; plan_id: string; accepted: boolean; skipped?: boolean; memory_candidates?: MemoryCandidate[] }>(
      "/feedback",
      {
        method: "POST",
        traceId,
        body,
        idempotencyScope: "feedback.submit"
      }
    );
  },
  getMemory() {
    return request<MemoryPayload>("/memory");
  },
  getMemoryCandidates() {
    return request<{ candidates?: MemoryCandidate[]; items?: MemoryCandidate[] }>("/memory/candidates");
  },
  confirmMemoryCandidate(candidateId: string, traceId?: string) {
    return request(`/memory/candidates/${encodeURIComponent(candidateId)}/confirm`, {
      method: "POST",
      traceId,
      body: { confirmed: true },
      idempotencyScope: "memory.confirm"
    });
  },
  ignoreMemoryCandidate(candidateId: string, traceId?: string) {
    return request(`/memory/candidates/${encodeURIComponent(candidateId)}/ignore`, {
      method: "POST",
      traceId,
      body: { ignored: true },
      idempotencyScope: "memory.ignore"
    });
  },
  enableMemoryPersonalization(traceId?: string) {
    return request<{ personalization_enabled: boolean; updated_at?: string }>("/memory/personalization/enable", {
      method: "POST",
      traceId,
      body: {},
      idempotencyScope: "memory.personalization.enable"
    });
  },
  disableMemoryPersonalization(traceId?: string) {
    return request<{ personalization_enabled: boolean; updated_at?: string }>("/memory/personalization/disable", {
      method: "POST",
      traceId,
      body: {},
      idempotencyScope: "memory.personalization.disable"
    });
  },
  updateMemory(memoryId: string, body: { content?: string; enabled?: boolean; ttl_days?: number }, traceId?: string) {
    return request<LifeMemory>(`/memory/${encodeURIComponent(memoryId)}`, {
      method: "PATCH",
      traceId,
      body,
      idempotencyScope: "memory.update"
    });
  },
  deleteMemory(memoryId: string, traceId?: string) {
    return request<{ memory_id: string; status: string; deleted_at?: string }>(`/memory/${encodeURIComponent(memoryId)}`, {
      method: "DELETE",
      traceId,
      idempotencyScope: "memory.delete"
    });
  },
  getTrace(traceId: string) {
    return request<{ trace_id: string; events?: TraceEvent[] }>(`/traces/${encodeURIComponent(traceId)}`, { debug: true });
  },
  getTraceEvents(traceId: string) {
    return request<{ trace_id: string; events: TraceEvent[] }>(`/traces/${encodeURIComponent(traceId)}/events`, { debug: true });
  },
  mockSearchRestaurants() {
    return request(`/mock/restaurants/search?area=${encodeURIComponent("金沙湖")}&limit=5`, { debug: true });
  },
  mockWeather() {
    return request(`/mock/weather?area=${encodeURIComponent("金沙湖")}&start_time=2026-05-20T13:00:00%2B08:00&end_time=2026-05-20T18:00:00%2B08:00`, {
      debug: true
    });
  },
  getLlmSettings() {
    return request<LLMSettings>("/settings/llm", { debug: true });
  },
  updateLlmSettings(body: Partial<LLMSettings> & { credential?: string }) {
    return request<LLMSettings>("/settings/llm", {
      method: "PATCH",
      body,
      debug: true,
      idempotencyScope: "settings.llm"
    });
  }
};

async function streamCreatePlan(
  prepared: PlanCreateStreamPrepared,
  onEvent: (event: PlanCreateStreamEvent) => void,
  signal?: AbortSignal
) {
  const path = "/plans/create/stream";
  const headers = buildHeaders(
    path,
    {
      method: "POST",
      body: prepared.body,
      traceId: prepared.traceId,
      idempotencyKey: prepared.idempotencyKey
    },
    prepared.traceId,
    true
  );
  headers.Accept = "text/event-stream";

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(prepared.body),
    cache: "no-store",
    signal
  });
  saveTraceId(response.headers.get("X-Trace-Id") || prepared.traceId);
  if (!response.ok || !response.body) {
    const parsed = (await response.json().catch(() => null)) as StandardResponse<unknown> | null;
    const fallback: StandardError = {
      code: "INTERNAL_ERROR",
      user_message: "系统暂时不可用，请稍后再试。",
      recoverable: true,
      details: {}
    };
    throw new ApiClientError(parsed?.error || fallback, parsed?.trace_id || prepared.traceId);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseSseEvent(part);
      if (event) onEvent(event);
    }
  }
  buffer += decoder.decode();
  const event = parseSseEvent(buffer);
  if (event) onEvent(event);
}

function parseSseEvent(raw: string): PlanCreateStreamEvent | null {
  const lines = raw.split(/\r?\n/);
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  const data = JSON.parse(dataLines.join("\n")) as unknown;
  if (eventName === "start" || eventName === "agent_event" || eventName === "complete" || eventName === "error") {
    return { event: eventName, data } as PlanCreateStreamEvent;
  }
  return null;
}

function planCreateStableId(body: PlanCreateBody) {
  return JSON.stringify({ path: "/plans/create", body });
}
