import type { PlanContract } from "@/types/schema";

export type PlanHistoryItem = {
  planId: string;
  title: string;
  summary: string;
  scenario?: string;
  status?: string;
  startTime?: string;
  endTime?: string;
  createdAt?: string;
  updatedAt?: string;
  area?: string;
  image: string;
  stepCount: number;
  participantCount: number;
};

const HISTORY_KEY = "lifepilot_plan_history";
const MAX_HISTORY = 24;
const PLAN_SESSION_KEYS = [
  "lifepilot_last_create",
  "lifepilot_pending_create",
  "lifepilot_pending_clarification",
  "lifepilot_last_vote",
  "lifepilot_current_trace_id"
];
const PLAN_SESSION_PREFIXES = ["lifepilot_execution:", "lifepilot_idem:"];
const PLAN_LOCAL_PREFIXES = ["lifepilot_vote_token:"];

const scenarioImages: Record<string, string> = {
  family_parent_child: "https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=720&q=80",
  friend_group: "https://images.unsplash.com/photo-1528605248644-14dd04022da1?auto=format&fit=crop&w=720&q=80",
  anniversary_emotion: "https://images.unsplash.com/photo-1529636798458-92182e662485?auto=format&fit=crop&w=720&q=80",
  solo_mood_relief: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=720&q=80",
  fallback_unknown: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=720&q=80"
};

const activityImages: Record<string, string> = {
  esports: "https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=720&q=80",
  karaoke: "https://images.unsplash.com/photo-1516280440614-37939bbacd81?auto=format&fit=crop&w=720&q=80",
  board_game: "https://images.unsplash.com/photo-1610890716171-6b1bb98ffd09?auto=format&fit=crop&w=720&q=80",
  movie: "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?auto=format&fit=crop&w=720&q=80",
  hotpot: "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?auto=format&fit=crop&w=720&q=80",
  bbq: "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?auto=format&fit=crop&w=720&q=80",
  korean: "https://images.unsplash.com/photo-1498654896293-37aacf113fd9?auto=format&fit=crop&w=720&q=80",
  japanese: "https://images.unsplash.com/photo-1579584425555-c3ce17fd4351?auto=format&fit=crop&w=720&q=80",
  buffet: "https://images.unsplash.com/photo-1543352634-a1c51d9f1fa7?auto=format&fit=crop&w=720&q=80",
  coffee: "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=720&q=80",
  craft: "https://images.unsplash.com/photo-1452860606245-08befc0ff44b?auto=format&fit=crop&w=720&q=80",
  walk: "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=720&q=80"
};

export function planHistoryFromPlan(plan: PlanContract): PlanHistoryItem {
  const scenario = plan.user_goal?.scenario;
  const activity = inferActivity(plan);
  const firstVisibleStep = (plan.timeline || []).find((step) => step.type !== "transport");
  const lastVisibleStep = (plan.timeline || []).slice().reverse().find((step) => step.type !== "transport");
  const timeWindowStart = plan.time_window?.start_time || plan.timeline?.[0]?.start_time;
  const timeWindowEnd = plan.time_window?.end_time || plan.timeline?.[plan.timeline.length - 1]?.end_time;
  return {
    planId: plan.plan_id,
    title: planTitle(plan, activity),
    summary: planSummary(plan, activity, firstVisibleStep, lastVisibleStep),
    scenario,
    status: plan.status,
    startTime: timeWindowStart,
    endTime: timeWindowEnd,
    createdAt: plan.created_at,
    updatedAt: plan.updated_at,
    area: planArea(plan),
    image: activityImages[activity.key] || scenarioImages[scenario || ""] || scenarioImages.fallback_unknown,
    stepCount: (plan.timeline || []).filter((step) => step.type !== "transport").length || plan.timeline?.length || 0,
    participantCount: Number(plan.constraints?.party_size || plan.participants?.length || 1)
  };
}

export function rememberPlanHistory(plan: PlanContract) {
  return upsertPlanHistory(planHistoryFromPlan(plan));
}

export function upsertPlanHistory(item: PlanHistoryItem) {
  if (typeof window === "undefined") return [item];
  const current = readPlanHistory();
  const next = [item, ...current.filter((historyItem) => historyItem.planId !== item.planId)]
    .sort((left, right) => sortTime(right) - sortTime(left))
    .slice(0, MAX_HISTORY);
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}

export function readPlanHistory(): PlanHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isPlanHistoryItem);
  } catch {
    return [];
  }
}

export function readLastCreatedPlanHistory(): PlanHistoryItem | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem("lifepilot_last_create");
    const parsed = raw ? (JSON.parse(raw) as { plan_id?: unknown }) : null;
    const planId = typeof parsed?.plan_id === "string" ? parsed.plan_id : "";
    if (!planId) return null;
    return {
      planId,
      title: "最近生成的时间导航",
      summary: "打开后会同步最新时间线。",
      image: scenarioImages.fallback_unknown,
      stepCount: 0,
      participantCount: 1
    };
  } catch {
    return null;
  }
}

export function clearPlanHistory() {
  if (typeof window === "undefined") return { historyCount: 0, removedKeys: 0 };
  const historyCount = readPlanHistory().length;
  let removedKeys = 0;
  try {
    removedKeys += removeStorageItem(window.localStorage, HISTORY_KEY);
    removedKeys += removeStorageByPrefix(window.localStorage, PLAN_LOCAL_PREFIXES);
    for (const key of PLAN_SESSION_KEYS) {
      removedKeys += removeStorageItem(window.sessionStorage, key);
    }
    removedKeys += removeStorageByPrefix(window.sessionStorage, PLAN_SESSION_PREFIXES);
  } catch {
    return { historyCount, removedKeys };
  }
  return { historyCount, removedKeys };
}

function removeStorageItem(storage: Storage, key: string) {
  if (storage.getItem(key) === null) return 0;
  storage.removeItem(key);
  return 1;
}

function removeStorageByPrefix(storage: Storage, prefixes: string[]) {
  let removed = 0;
  for (const key of Object.keys(storage)) {
    if (prefixes.some((prefix) => key.startsWith(prefix))) {
      storage.removeItem(key);
      removed += 1;
    }
  }
  return removed;
}

function planTitle(plan: PlanContract, activity: ActivityProfile) {
  const messageTitle = shortMessageTitle(plan);
  if (messageTitle) return messageTitle;
  const scenario = plan.user_goal?.scenario || "";
  const rawText = plan.user_goal?.raw_text || "";
  const timePrefix = activityTimePrefix(rawText);
  if (activity.key) {
    if (activity.key === "esports") return timePrefix ? `${timePrefix}电竞组队` : scenario === "friend_group" ? "朋友电竞局" : "电竞放松";
    if (activity.key === "karaoke") return timePrefix ? `${timePrefix}K歌局` : "朋友K歌局";
    if (activity.key === "board_game") return timePrefix ? `${timePrefix}桌游局` : "朋友桌游局";
    if (activity.key === "movie") return timePrefix ? `${timePrefix}电影安排` : "电影时间";
    if (activity.key === "hotpot") return timePrefix ? `${timePrefix}火锅局` : "朋友火锅局";
    if (activity.key === "bbq") return timePrefix ? `${timePrefix}烤肉局` : "朋友烤肉局";
    if (activity.key === "korean") return timePrefix ? `${timePrefix}韩餐` : "韩餐计划";
    if (activity.key === "japanese") return timePrefix ? `${timePrefix}日料安排` : "日料聚餐";
    if (activity.key === "buffet") return timePrefix ? `${timePrefix}自助餐` : "自助餐聚会";
    if (activity.key === "coffee") return timePrefix ? `${timePrefix}咖啡时间` : "咖啡小坐";
    if (activity.key === "craft") return scenario === "family_parent_child" ? "亲子手作下午" : timePrefix ? `${timePrefix}手作体验` : "手作体验";
    if (activity.key === "walk") return timePrefix ? `${timePrefix}散心走走` : "轻松散心";
  }
  if (scenario === "family_parent_child") return "家庭亲子下午";
  if (scenario === "friend_group") return "朋友出行计划";
  if (scenario === "anniversary_emotion") return "纪念日约会";
  if (scenario === "solo_mood_relief") return "一个人散心";
  return compactTitleFromPlan(plan) || "生活计划";
}

type ActivityProfile = {
  key: string;
  label: string;
};

function planSummary(
  plan: PlanContract,
  activity: ActivityProfile,
  firstVisibleStep?: NonNullable<PlanContract["timeline"]>[number],
  lastVisibleStep?: NonNullable<PlanContract["timeline"]>[number]
) {
  const rawText = plan.user_goal?.raw_text || "";
  if (activity.key === "esports") return friendPhrase(rawText, "一起打电竞，保留吃饭和转场节奏。");
  if (activity.key === "karaoke") return friendPhrase(rawText, "一起唱K，兼顾预算、距离和转场。");
  if (activity.key === "board_game") return friendPhrase(rawText, "一起玩桌游，按轻松聊天的节奏安排。");
  if (activity.key === "movie") return "围绕电影时段安排转场、吃饭和后续活动。";
  if (activity.key === "craft") return plan.user_goal?.scenario === "family_parent_child" ? "适合孩子参与的手作体验，衔接轻松晚饭。" : "围绕手作体验安排一段轻松时间。";
  if (lastVisibleStep?.title && firstVisibleStep?.title && lastVisibleStep.title !== firstVisibleStep.title) {
    return `${firstVisibleStep.title} → ${lastVisibleStep.title}`;
  }
  return plan.user_goal?.goal_summary || firstVisibleStep?.description || "已生成一段生活时间导航。";
}

function friendPhrase(rawText: string, fallback: string) {
  return /朋友|同学|室友|同事|组队|一起/.test(rawText) ? fallback : fallback.replace("一起", "");
}

function inferActivity(plan: PlanContract): ActivityProfile {
  const text = [
    plan.user_goal?.raw_text,
    plan.user_goal?.goal_summary,
    ...(plan.user_goal?.intent_tags || []),
    ...(plan.timeline || []).flatMap((step) => [step.title, step.description, step.user_visible_notes, ...(step.display_tags || [])])
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  const rules: Array<[string, string, RegExp]> = [
    ["esports", "电竞", /电竞|打游戏|游戏|网咖|网吧|电玩|ps5|switch|esports/],
    ["karaoke", "K歌", /ktv|karaoke|唱k|k歌|唱歌/],
    ["board_game", "桌游", /桌游|剧本杀|狼人杀|board_game/],
    ["movie", "电影", /电影|影院|cinema|movie/],
    ["hotpot", "火锅", /火锅|hotpot/],
    ["bbq", "烤肉", /烤肉|烧烤|bbq|grill/],
    ["korean", "韩餐", /韩国料理|韩餐|韩料|韩式|部队锅|泡菜|korean/],
    ["japanese", "日料", /日料|日本料理|寿司|居酒屋|sushi|izakaya|cuisine_japanese/],
    ["buffet", "自助餐", /自助|放题|buffet/],
    ["coffee", "咖啡", /咖啡|coffee|cafe/],
    ["craft", "手作", /手作|diy|手工|陶艺|油画|craft|hands_on/],
    ["walk", "散心", /散心|走走|散步|公园|湖|light_walk|mood_relief/]
  ];
  const matched = rules.find(([, , pattern]) => pattern.test(text));
  return matched ? { key: matched[0], label: matched[1] } : { key: "", label: "" };
}

function activityTimePrefix(rawText: string) {
  if (/周六|星期六|礼拜六/.test(rawText)) return "周六";
  if (/周日|星期日|星期天|礼拜日|礼拜天/.test(rawText)) return "周日";
  if (/这周末|本周末|周末/.test(rawText)) return "周末";
  if (/今晚|今天晚上|晚上/.test(rawText)) return "今晚";
  if (/今天下午|下午/.test(rawText)) return "下午";
  if (/明天/.test(rawText)) return "明天";
  return "";
}

function shortMessageTitle(plan: PlanContract) {
  const raw = plan.messages?.plan_card_title;
  if (typeof raw !== "string") return "";
  const compact = raw.replace(/[\s，。！？、；;,.!?：:（）()[\]【】《》"'“”]/g, "");
  return compact.length >= 2 && compact.length <= 8 ? compact : "";
}

function compactTitleFromPlan(plan: PlanContract) {
  const text = [
    plan.user_goal?.raw_text,
    plan.user_goal?.goal_summary,
    ...(plan.user_goal?.intent_tags || []),
    ...(plan.timeline || []).flatMap((step) => [step.title, step.description, ...(step.display_tags || [])])
  ]
    .filter(Boolean)
    .join(" ");
  const prefix = activityTimePrefix(text);
  const rules: Array<[RegExp, string]> = [
    [/韩国料理|韩餐|韩料|韩式|部队锅|泡菜|korean/, "韩餐"],
    [/寿司|鮨|刺身|回转寿司|sushi/, "寿司"],
    [/日料|日本料理|居酒屋|烧鸟|cuisine_japanese|izakaya/, "日料"],
    [/火锅|hotpot/, "火锅"],
    [/烤肉|烧烤|烧肉|bbq|grill/, "烤肉"],
    [/自助|放题|buffet/, "自助餐"],
    [/电竞|打游戏|网咖|网吧|esports/, "电竞"],
    [/ktv|karaoke|唱k|k歌|唱歌/i, "K歌"],
    [/桌游|剧本杀|狼人杀|board_game/, "桌游"]
  ];
  const matched = rules.find(([pattern]) => pattern.test(text));
  if (!matched) return "";
  const title = prefix ? `${prefix}${matched[1]}` : `${matched[1]}计划`;
  return title.length <= 6 ? title : matched[1];
}

function planArea(plan: PlanContract) {
  const location = plan.constraints?.user_location;
  if (location && typeof location === "object" && "area" in location) {
    const area = (location as { area?: unknown }).area;
    if (typeof area === "string" && area.trim()) return area.trim();
  }
  const preferredArea = plan.constraints?.preferred_area || plan.constraints?.current_area;
  return typeof preferredArea === "string" ? preferredArea : "";
}

function isPlanHistoryItem(value: unknown): value is PlanHistoryItem {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<PlanHistoryItem>;
  return typeof item.planId === "string" && typeof item.title === "string" && typeof item.image === "string";
}

function sortTime(item: PlanHistoryItem) {
  const raw = item.startTime || item.updatedAt || item.createdAt || "";
  const value = raw ? new Date(raw).getTime() : 0;
  return Number.isNaN(value) ? 0 : value;
}
