const TRACE_KEY = "lifepilot_current_trace_id";

export function createTraceId() {
  const random = Math.random().toString(36).slice(2, 8);
  return `trace_web_${Date.now()}_${random}`;
}

export function saveTraceId(traceId?: string | null) {
  if (!traceId || typeof window === "undefined") return;
  window.sessionStorage.setItem(TRACE_KEY, traceId);
}

export function getTraceId() {
  if (typeof window === "undefined") return undefined;
  return window.sessionStorage.getItem(TRACE_KEY) || undefined;
}

export function getOrCreateTraceId() {
  const existing = getTraceId();
  if (existing) return existing;
  const traceId = createTraceId();
  saveTraceId(traceId);
  return traceId;
}
