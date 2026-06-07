const PREFIX = "lifepilot_idem:";

export function newIdempotencyKey(scope: string) {
  const random = Math.random().toString(36).slice(2, 10);
  return `idem_${scope}_${Date.now()}_${random}`;
}

export function getOrCreateIdempotencyKey(scope: string, stableId: string) {
  if (typeof window === "undefined") {
    return newIdempotencyKey(scope);
  }
  const storageKey = `${PREFIX}${scope}:${stableId}`;
  const existing = window.sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const key = newIdempotencyKey(scope);
  window.sessionStorage.setItem(storageKey, key);
  return key;
}

export function clearIdempotencyKey(scope: string, stableId: string) {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(`${PREFIX}${scope}:${stableId}`);
}
