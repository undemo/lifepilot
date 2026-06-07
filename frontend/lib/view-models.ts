import type { PlanContract, ToolAction, TraceEvent } from "@/types/schema";
import type { TimelineViewItem, ToolTraceViewItem } from "@/types/view-model";
import { formatClock } from "./formatters";

// Fallback only. Canonical tag display labels live in backend/app/rules/recommendation_taxonomy.py.
const FALLBACK_TAG_LABELS: Record<string, string> = {
  quiet_alone: "安静独处",
  alcohol: "可小酌",
  light_drink: "轻饮",
  music: "有音乐",
  acoustic_music: "轻音乐",
  ambience_dining: "有氛围",
  beautiful_dining: "漂亮饭",
  hotpot: "火锅",
  crayfish: "小龙虾",
  cuisine_japanese: "日料",
  sushi: "寿司",
  izakaya: "居酒屋",
  bbq: "烤肉",
  grill: "烤肉",
  western_cuisine: "西餐",
  steak: "牛排",
  lamb: "羊肉",
  healthy_light: "低负担",
  light_meal: "清淡餐",
  light_dinner: "清淡晚饭",
  mood_relief: "放松情绪",
  rain_safe: "雨天可去",
  low_queue: "少排队",
  esports: "电竞游戏",
  group_ok: "适合组队",
  child_friendly: "亲子友好",
  kid_safe: "适合孩子",
  family_time: "家庭时间",
  family_friendly: "家庭友好",
  family_parent_child: "适合亲子",
  low_calorie: "清淡低负担",
  light_food: "清淡低负担",
  budget_friendly: "预算友好",
  budget_sensitive: "预算友好",
  photo_friendly: "适合拍照",
  photo: "适合拍照",
  interactive: "互动体验",
  hands_on: "手作体验",
  craft: "手工",
  flower: "鲜花",
  cake: "蛋糕",
  delivery: "可送达",
  light_ritual: "轻仪式感",
  nearby: "距离较近",
  quiet: "安静放松",
  alone: "适合独处",
  low_pressure: "低压力",
  light_walk: "轻松走走",
  relaxed: "轻松一点",
  visitor_friendly: "到达方便",
  visiting_family: "家人来访",
  host_guest: "招待友好",
  showcase_local: "下沙代表性",
  quality_dining: "品质正餐",
  proper_dining: "正式用餐",
  adult_family: "成年家人",
  sibling: "兄弟姐妹",
  conversation: "适合聊天",
  indoor: "室内可去",
  reserve_restaurant: "模拟订座",
  book_activity: "模拟预约",
  order_item: "模拟下单",
  send_message: "模拟消息草案"
};

const HIDDEN_INTERNAL_VALUES = new Set([
  "mock_route",
  "mock_api",
  "rule_generated",
  "source",
  "tool_log",
  "verifier_log",
  "executor_log",
  "constraint_log",
  "explicit_dining"
]);

const ENGLISH_ENUM_PATTERN = /^[a-z][a-z0-9_]*$/;

const routeModeLabels: Record<string, string> = {
  walk: "步行",
  taxi: "车程",
  drive: "车程",
  bike: "骑行",
  mixed: "转场",
  subway: "地铁"
};

export function toTimelineView(plan?: PlanContract | null): TimelineViewItem[] {
  return (plan?.timeline || [])
    .slice()
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map((step) => {
      const routeLabel = routeSummary(step.estimated_route || undefined, step.transport_mode || undefined);
      const isTransport = step.type === "transport";
      return {
        stepId: step.step_id,
        order: step.order,
        title: isTransport ? "转场" : sanitizeUserText(step.title || "计划节点"),
        description: isTransport ? routeLabel : sanitizeUserText(step.description || step.user_visible_notes || ""),
        timeLabel: `${formatClock(step.start_time)} - ${formatClock(step.end_time)}`,
        tags: isTransport ? ["短转场"] : mapUserLabels(step.display_tags).slice(0, 5),
        routeLabel,
        bookingLabel: step.booking_required ? "需要模拟预约" : step.reservation_required ? "需要模拟订座" : undefined,
        note: isTransport ? undefined : sanitizeUserText(step.user_visible_notes || "")
      };
    });
}

export function toToolTraceView(actions?: ToolAction[], events?: TraceEvent[], plan?: PlanContract | null): ToolTraceViewItem[] {
  if (!(actions || []).length && !(events || []).length) {
    return [{ id: "trace_preparing", label: "正在准备工具检查摘要", status: "running" }];
  }

  const eventTypes = new Set((events || []).filter((event) => event.visible_to_user !== false).map((event) => event.event_type));
  const actionStatuses = (actions || []).filter((action) => action.user_visible !== false).map((action) => action.status || "pending");
  const actionDone = actionStatuses.length > 0 && actionStatuses.every((status) => ["success", "skipped", "recovered"].includes(status));
  const actionRunning = actionStatuses.some((status) => ["running", "pending"].includes(status));
  const verifierStatus = plan?.verifier_result?.status;
  const executed = eventTypes.has("executor_log") || plan?.status === "completed";

  const items: ToolTraceViewItem[] = [
    { id: "goal", label: "已理解目标", status: eventTypes.has("intent_log") ? "success" : "pending" },
    { id: "constraints", label: "已提取约束", status: eventTypes.has("constraint_log") ? "success" : "pending" },
    { id: "candidates", label: "已检索候选地点", status: eventTypes.has("poi_log") ? "success" : "pending" },
    {
      id: "checks",
      label: "已检查余位、路线和天气",
      status: actionDone ? "success" : actionRunning || eventTypes.has("tool_log") ? "running" : "pending"
    },
    {
      id: "verifier",
      label: "已完成可执行性校验",
      status: verifierStatus === "fail" ? "failed" : verifierStatus === "warning" ? "warning" : eventTypes.has("verifier_log") ? "success" : "pending"
    },
    {
      id: "execution",
      label: executed ? "已完成模拟执行" : "等待用户确认执行",
      status: executed ? "success" : "pending"
    }
  ];

  return items.slice(0, 6);
}

export function traceEventLabel(eventType: string) {
  const map: Record<string, string> = {
    input_log: "已记录输入",
    intent_log: "已理解目标",
    constraint_log: "已抽取约束",
    memory_log: "已检查可用记忆",
    poi_log: "已检索候选",
    tool_log: "已完成工具检查",
    verifier_log: "已完成可执行性校验",
    recovery_log: "已完成恢复规划",
    executor_log: "已完成模拟执行",
    feedback_log: "已收到反馈",
    error_log: "出现可恢复异常"
  };
  return map[eventType] || eventType;
}

export function planTitle(plan?: PlanContract | null) {
  return plan?.user_goal?.goal_summary || "生活时间导航方案";
}

export function mapUserLabels(values?: unknown[]): string[] {
  const labels: string[] = [];
  for (const value of values || []) {
    const key = String(value || "").trim();
    if (!key || HIDDEN_INTERNAL_VALUES.has(key)) continue;
    const label = getFallbackTagLabel(key);
    if (label) {
      labels.push(label);
    } else if (!ENGLISH_ENUM_PATTERN.test(key)) {
      labels.push(sanitizeUserText(key));
    }
  }
  return Array.from(new Set(labels));
}

export function getFallbackTagLabel(tag: string): string {
  return FALLBACK_TAG_LABELS[tag] ?? "";
}

export function riskText(type?: string, fallback?: string) {
  const map: Record<string, string> = {
    restaurant_capacity: "餐厅余位偏紧，已准备备选餐厅。",
    weather: "天气存在不确定性，已准备室内备选。",
    weather_risk: "天气存在不确定性，已准备室内备选。",
    route_delay: "路线时间可能波动，建议保留一点缓冲。",
    queue: "排队可能偏长，已准备低排队备选。",
    queue_time: "排队时间可能偏长，已优先选择低排队方案。",
    executable_window: "当前可执行窗口较短，建议尽快确认。",
    activity_ticket: "活动名额可能变化，已准备替换策略。",
    budget_constraint: "预算接近上限，已控制高消费节点。"
  };
  return sanitizeUserText(map[type || ""] || fallback || "当前方案存在轻微不确定性，已准备恢复策略。");
}

export function statusLevelLabel(level?: string) {
  const map: Record<string, string> = {
    low: "低风险",
    medium: "中风险",
    high: "高风险",
    blocking: "阻断风险",
    warning: "需留意"
  };
  return map[level || ""] || "需留意";
}

export function sanitizeUserText(value?: string) {
  const text = String(value || "").trim();
  if (!text) return "";
  return applyFallbackTagLabels(text
    .replace(/MockAPI/g, "模拟状态")
    .replace(/mock_api/g, "模拟状态")
    .replace(/mock_route/g, "模拟路线")
    .replace(/restaurant_capacity/g, "餐厅余位风险")
    .replace(/restaurant_full/g, "同区域低排队备选餐厅")
    .replace(/activity_full/g, "同区域低强度备选活动"));
}

function applyFallbackTagLabels(text: string) {
  return Object.entries(FALLBACK_TAG_LABELS)
    .sort(([left], [right]) => right.length - left.length)
    .reduce((result, [tag, label]) => result.replaceAll(tag, label), text);
}

export function routeSummary(route?: { duration_minutes?: number; transport_mode?: string } | null, fallbackMode?: string) {
  const minutes = route?.duration_minutes;
  if (!minutes) return undefined;
  const mode = routeModeLabels[route.transport_mode || fallbackMode || ""] || "转场";
  if (mode === "步行") return `步行约${minutes}分钟，路线来自模拟估算`;
  return `约${minutes}分钟${mode}，路线来自模拟估算`;
}
