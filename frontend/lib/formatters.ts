import { getDemoNowTimestamp } from "./demo-time";

export function formatTime(value?: string | null) {
  if (!value) return "待定";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

export function formatClock(value?: string | null) {
  if (!value) return "待定";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

export function formatMoney(value?: number, currency = "CNY") {
  if (typeof value !== "number") return "待估";
  const prefix = currency === "CNY" ? "¥" : `${currency} `;
  return `${prefix}${Math.round(value)}`;
}

export function minutesUntil(value?: string) {
  if (!value) return null;
  const end = new Date(value).getTime();
  if (Number.isNaN(end)) return null;
  const now = getDemoNowTimestamp();
  return Math.max(0, Math.ceil((end - now) / 60000));
}

export function statusLabel(status?: string) {
  const map: Record<string, string> = {
    executable: "可执行",
    confirmed: "已确认",
    completed: "已完成",
    recovered: "已恢复",
    failed: "失败",
    pass: "通过",
    warning: "有提醒",
    pending: "待执行",
    running: "执行中",
    success: "成功",
    skipped: "已跳过",
    finalized: "已生成共识",
    collecting: "收集中",
    verified: "已验证",
    low: "低",
    medium_low: "较低",
    medium: "中",
    high: "高",
    blocking: "阻断",
    planned: "已规划"
  };
  return status ? map[status] || "已更新" : "待确认";
}

export function compactJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
