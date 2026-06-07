import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertCircle, BrainCircuit, Check, Coins, Copy, GitBranch, MapPinned, Radar, Route, ShieldCheck, Sparkles, TimerReset } from "lucide-react";
import type { BackupPlan, Budget, ExecutableWindow, JsonRecord, PlanContract, Risk, TraceEvent } from "@/types/schema";
import type { TimelineViewItem, ToolTraceViewItem } from "@/types/view-model";
import { formatClock, formatMoney, formatTime, minutesUntil, statusLabel } from "@/lib/formatters";
import { mapUserLabels, riskText, routeSummary, sanitizeUserText, statusLevelLabel, toTimelineView } from "@/lib/view-models";
import { SimulationBadge } from "@/components/common/States";

export function ShareableRouteSummaryCard({ plan }: { plan: PlanContract }) {
  const summary = useMemo(() => buildShareableRouteSummary(plan), [plan]);
  const [copied, setCopied] = useState(false);

  async function copySummary() {
    const success = await copyText(summary);
    setCopied(success);
    if (success) window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <section className="card share-summary-card">
      <div className="row-between">
        <div className="row">
          <Sparkles size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            AI路线小结
          </h2>
        </div>
        <button className="button secondary share-copy-button" type="button" onClick={copySummary} aria-label="复制路线总结">
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "复制好了" : "复制文案"}
        </button>
      </div>
      <div className="share-summary-text" aria-label="路线总结">
        {summary.split("\n").map((line, index) => (
          <p key={`${index}-${line}`}>{line}</p>
        ))}
      </div>
    </section>
  );
}

export function PlanGoalSummary({ plan }: { plan: PlanContract }) {
  const constraints = plan.constraints || {};
  const participantLabels = participantBadges(plan);
  return (
    <section className="card">
      <div className="row-between">
        <h2 className="card-title">目标理解</h2>
        <span className="badge">{statusLabel(plan.status)}</span>
      </div>
      <p style={{ margin: "0 0 10px", lineHeight: 1.55 }}>{plan.user_goal?.goal_summary || "已生成结构化生活时间计划。"}</p>
      <div className="row" style={{ flexWrap: "wrap" }}>
        {participantLabels.map((label) => (
          <span className="badge gray" key={label}>
            {label}
          </span>
        ))}
        {typeof constraints.budget_max === "number" ? <span className="badge gray">预算{formatMoney(constraints.budget_max)}</span> : null}
        {constraints.queue_tolerance ? <span className="badge gray">排队{statusLabel(String(constraints.queue_tolerance))}</span> : null}
      </div>
      <RecommendationPrioritySummary constraints={constraints} />
    </section>
  );
}

export function MemoryUsageNotice({ plan }: { plan: PlanContract }) {
  const usage = (plan.memory_usage || []).filter((item) => item && item.user_visible !== false);
  const shortSummary =
    plan.messages && typeof plan.messages === "object"
      ? ((plan.messages.memory_profile_summary as JsonRecord | undefined)?.short_term_summary as string | undefined)
      : undefined;
  if (!usage.length && !shortSummary) return null;
  return (
    <section className="card">
      <div className="row">
        <BrainCircuit size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          个人偏好参考
        </h2>
      </div>
      {usage.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {usage.slice(0, 4).map((item, index) => (
            <div className="timeline-card" key={String(item.memory_id || index)}>
              <strong>{sanitizeUserText(String(item.explanation || "已参考一条确认过的偏好。"))}</strong>
              <p className="small muted">用于：{usageLabel(item.used_for)}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="subtitle">本次没有使用长期记忆，只参考当前输入。</p>
      )}
      {shortSummary ? <p className="subtitle small">{sanitizeUserText(shortSummary)}</p> : null}
    </section>
  );
}

function usageLabel(value: unknown) {
  const values = Array.isArray(value) ? value : [value];
  const labels = values
    .map((item) => String(item || ""))
    .map((item) =>
      ({
        ranking: "排序",
        dining: "餐饮",
        activity: "活动",
        queue: "排队",
        pace: "节奏",
        route: "路线",
        avoid: "避开项"
      })[item] || ""
    )
    .filter(Boolean);
  return labels.length ? labels.join("、") : "偏好排序";
}

function RecommendationPrioritySummary({ constraints }: { constraints: Record<string, unknown> }) {
  const profile = constraints.recommendation_profile;
  if (!profile || typeof profile !== "object") return null;
  const tags = Array.isArray((profile as { normalized_tags?: unknown }).normalized_tags)
    ? ((profile as { normalized_tags?: unknown[] }).normalized_tags || [])
    : [];
  const labels = mapUserLabels(tags).slice(0, 5);
  if (!labels.length) return null;
  return (
    <div style={{ marginTop: 10 }}>
      <p className="small muted" style={{ margin: "0 0 6px" }}>
        类脑推荐优先级
      </p>
      <div className="row" style={{ flexWrap: "wrap" }}>
        {labels.map((label) => (
          <span className="badge" key={label}>
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

function participantBadges(plan: PlanContract) {
  const partySize = typeof plan.constraints?.party_size === "number" ? plan.constraints.party_size : plan.participants?.length;
  const scenario = plan.user_goal?.scenario;
  if (scenario === "friend_group") return [`朋友局 ${partySize || 4}人`];
  if (scenario === "family_parent_child") return ["家庭亲子", `${partySize || 3}人`];
  if (scenario === "anniversary_emotion") return ["约会/纪念日", `${partySize || 2}人`];
  if (scenario === "city_light_explore") return ["家人来访", `${partySize || 2}人`];
  return [`${partySize || 1}人`];
}

export function PlanTimeline({ items, plan }: { items?: TimelineViewItem[]; plan?: PlanContract }) {
  const timelineItems = items || toTimelineView(plan);
  const backupsByStep = new Map<string, BackupPlan[]>();
  for (const backup of plan?.backup_plans || []) {
    if (!backup.replace_step_id) continue;
    const current = backupsByStep.get(backup.replace_step_id) || [];
    current.push(backup);
    backupsByStep.set(backup.replace_step_id, current);
  }
  if (!timelineItems.length) {
    return (
      <section className="card">
        <h2 className="card-title">时间线</h2>
        <p className="muted">暂无时间线节点。</p>
      </section>
    );
  }
  return (
    <section className="card">
      <div className="row">
        <MapPinned size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          时间线
        </h2>
      </div>
      <div className="timeline" style={{ marginTop: 12 }}>
        {timelineItems.map((item) => (
          <div key={item.stepId}>
            <TimelineStepCard item={item} />
            {(backupsByStep.get(item.stepId) || []).map((backup, index) => (
              <TimelineBranchCard backup={backup} key={backup.backup_plan_id || index} />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function TimelineStepCard({ item }: { item: TimelineViewItem }) {
  return (
    <div className="timeline-item">
      <span className="timeline-dot" />
      <div className="timeline-card">
        <div className="row-between">
          <strong>{item.title}</strong>
          <span className="small muted">{item.timeLabel}</span>
        </div>
        {item.description ? <p className="subtitle">{item.description}</p> : null}
        <div className="row" style={{ flexWrap: "wrap", marginTop: 8 }}>
          {item.tags.slice(0, 5).map((tag) => (
            <span className="badge gray" key={tag}>
              {tag}
            </span>
          ))}
          {item.bookingLabel ? <span className="badge warn">{item.bookingLabel}</span> : null}
          {item.routeLabel ? <span className="badge gray">{item.routeLabel}</span> : null}
        </div>
        {item.note && item.note !== item.description ? <p className="subtitle small">{item.note}</p> : null}
      </div>
    </div>
  );
}

function TimelineBranchCard({ backup }: { backup: BackupPlan }) {
  const summary = backupSummary(backup);
  return (
    <div className="timeline-branch">
      <span className="timeline-branch-dot" />
      <div className="timeline-branch-card">
        <div className="row-between">
          <strong>{backupTitle(backup.trigger)}</strong>
          <span className="badge danger">备选</span>
        </div>
        <p className="subtitle">{sanitizeUserText(summary || backup.description || "如果当前节点不可用，切换同区域备选。")}</p>
      </div>
    </div>
  );
}

export function MapRoutePanel({ plan }: { plan: PlanContract }) {
  const stepByPoi = new Map<string, string>();
  for (const step of plan.timeline || []) {
    if (step.poi_id && step.title) stepByPoi.set(step.poi_id, step.title);
  }
  const routes = (plan.timeline || []).filter((step) => step.type === "transport" && step.estimated_route);
  const stops = (plan.timeline || []).filter((step) => step.type !== "transport").slice(0, 4);
  return (
    <section className="card">
      <div className="row">
        <Route size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          路线与转场
        </h2>
      </div>
      <div className="soft-map" aria-label="路线轨迹示意" style={{ marginTop: 12 }}>
        {stops.map((step, index) => (
          <span
            className="soft-map-marker"
            key={step.step_id}
            title={sanitizeUserText(step.title)}
            style={{
              left: `${18 + (index * 21) % 66}%`,
              top: `${56 - (index % 2) * 26}%`
            }}
          >
            {index + 1}
          </span>
        ))}
        <div className="badge gray" style={{ position: "absolute", left: 12, top: 12 }}>
          模拟路线轨迹
        </div>
      </div>
      {routes.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {routes.map((step, index) => {
            const route = step.estimated_route;
            const from = step.from_poi_id ? stepByPoi.get(step.from_poi_id) : undefined;
            const to = step.to_poi_id ? stepByPoi.get(step.to_poi_id) : undefined;
            return (
              <div className="timeline-card" key={step.step_id || index}>
                <div className="row-between">
                  <strong>{from && to ? `${from} → ${to}` : `转场 ${index + 1}`}</strong>
                  <span className="badge gray">{route?.traffic_level === "smooth" ? "通畅" : "模拟路况"}</span>
                </div>
                <p className="subtitle">{routeSummary(route, step.transport_mode || undefined) || "路线来自模拟估算。"}</p>
                {typeof route?.distance_km === "number" ? <p className="small muted">距离约{route.distance_km.toFixed(1)}km</p> : null}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="subtitle">路线时间由模拟路线引擎生成；当前方案无需明显转场或正在等待刷新。</p>
      )}
    </section>
  );
}

export function ExecutableWindowCard({ window }: { window?: ExecutableWindow }) {
  const left = minutesUntil(window?.expire_at);
  const expired = left === 0;
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <TimerReset size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            可执行窗口
          </h2>
        </div>
        <span className={expired ? "badge danger" : "badge"}>{expired ? "已过期" : `约${left ?? window?.window_minutes ?? "-"}分钟`}</span>
      </div>
      <p className="subtitle">{window?.display_message || "当前窗口由系统可执行性校验计算，页面只展示结果。"}</p>
      <div className="grid-2" style={{ marginTop: 10 }}>
        <Metric label="过期时间" value={formatTime(window?.expire_at)} />
        <Metric label="置信度" value={typeof window?.confidence === "number" ? `${Math.round(window.confidence * 100)}%` : "待定"} />
      </div>
      <div className="row" style={{ flexWrap: "wrap", marginTop: 10 }}>
        {(window?.reasons || []).slice(0, 3).map((reason) => (
          <span className="badge gray" key={reason}>
            {sanitizeUserText(reason)}
          </span>
        ))}
      </div>
    </section>
  );
}

export function BudgetCard({ budget, partySize }: { budget?: Budget; partySize?: number }) {
  const perPersonLabel = partySize && partySize > 1 ? "人均" : "单人";
  return (
    <section className="card">
      <div className="row">
        <Coins size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          预算
        </h2>
      </div>
      <div className="grid-2" style={{ marginTop: 10 }}>
        <Metric label="总预算" value={formatMoney(budget?.estimated_total, budget?.currency)} />
        <Metric label={perPersonLabel} value={formatMoney(budget?.price_per_person, budget?.currency)} />
      </div>
      {(budget?.items || []).map((item, index) => (
        <div className="row-between" key={`${item.name}-${index}`} style={{ marginTop: 10 }}>
          <span className="muted">{item.name || "预算项"}</span>
          <strong>{formatMoney(item.amount, budget?.currency)}</strong>
        </div>
      ))}
    </section>
  );
}

export function RiskCard({ risks = [] }: { risks?: Risk[] }) {
  const visibleRisks = risks.filter((risk) => risk.user_visible !== false);
  return (
    <section className="card">
      <div className="row">
        <AlertCircle size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          风险提醒
        </h2>
      </div>
      {visibleRisks.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {visibleRisks.map((risk, index) => (
            <div key={risk.risk_id || index}>
              <span className="badge warn">{statusLevelLabel(risk.level)}</span>
              <p className="subtitle">{riskText(risk.type, risk.description || risk.message)}</p>
              {risk.mitigation ? <p className="small muted">{sanitizeUserText(risk.mitigation)}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="subtitle">当前没有需要用户处理的显著风险。</p>
      )}
    </section>
  );
}

export function BackupPlanCard({ backups = [] }: { backups?: BackupPlan[] }) {
  return (
    <section className="card">
      <div className="row">
        <GitBranch size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          PlanB / 改道
        </h2>
      </div>
      {backups.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {backups.map((backup, index) => (
            <div className="timeline-card" key={backup.backup_plan_id || index}>
              <div className="row-between">
                <strong>{backupTitle(backup.trigger)}</strong>
                <span className={backup.new_poi_id ? "badge" : "badge gray"}>{backup.new_poi_id ? "已绑定地点" : statusLabel(backup.status)}</span>
              </div>
              <p className="subtitle">{sanitizeUserText(backupSummary(backup) || backup.description || "确认前保留备选方案。")}</p>
              {backup.verifier_result?.status ? <p className="small muted">备选校验：{statusLabel(backup.verifier_result.status)}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="subtitle">当前方案暂无可用PlanB，建议刷新窗口。</p>
      )}
    </section>
  );
}

export function DigitalTwinSnapshotCard({ plan, events = [] }: { plan: PlanContract; events?: TraceEvent[] }) {
  const snapshot = digitalTwinSnapshot(plan, events);
  return (
    <section className="card">
      <div className="row">
        <Radar size={18} />
        <h2 className="card-title" style={{ margin: 0 }}>
          数字孪生快照
        </h2>
      </div>
      <div className="metric-grid" style={{ marginTop: 10 }}>
        <Metric label="候选池" value={snapshot.candidateLabel} />
        <Metric label="状态检查" value={snapshot.statusLabel} />
        <Metric label="路线估算" value={snapshot.routeLabel} />
        <Metric label="天气窗口" value={snapshot.weatherLabel} />
      </div>
      <p className="subtitle small">{snapshot.areaLabel}；推荐优先级来自用户目标、时间窗、区域、队列和预算约束的综合打分。</p>
    </section>
  );
}

export function ToolTracePanel({ items, events = [], plan, debug = false }: { items: ToolTraceViewItem[]; events?: TraceEvent[]; plan?: PlanContract | null; debug?: boolean }) {
  const details = toolCallDetails(events, plan);
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <ShieldCheck size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            可行性检查摘要
          </h2>
        </div>
        <SimulationBadge label="当前模拟状态" />
      </div>
      {items.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {items.map((item) => (
            <div className="row-between" key={item.id}>
              <span>{item.label}</span>
              {item.status ? <span className="badge gray">{statusLabel(item.status)}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="subtitle">正在准备工具检查摘要。</p>
      )}
      {details.length ? (
        <div className="tool-call-list" aria-label="工具调用明细">
          {details.map((detail) => (
            <div className="tool-call-row" key={detail.key}>
              <span>{detail.label}</span>
              <small>{detail.target}</small>
            </div>
          ))}
        </div>
      ) : null}
      {debug ? <p className="subtitle small">调试页可展示脱敏明细；普通用户页仅展示摘要。</p> : null}
    </section>
  );
}

export function ReputationSignalCard({ signals = [] }: { signals?: unknown[] }) {
  if (!signals.length) return null;
  return (
    <section className="card">
      <div className="row-between">
        <h2 className="card-title">口碑雷达</h2>
        <SimulationBadge label="模拟口碑信号" />
      </div>
      <p className="subtitle">社交口碑仅为演示模拟数据，不代表真实平台抓取。</p>
    </section>
  );
}

export function ConfirmExecuteBar({
  expired,
  executing,
  canExecute,
  canVote,
  votePending,
  verifierFailed,
  onRefresh,
  onExecute,
  onVote
}: {
  expired: boolean;
  executing: boolean;
  canExecute: boolean;
  canVote: boolean;
  votePending?: boolean;
  verifierFailed?: boolean;
  onRefresh: () => void;
  onExecute: () => void;
  onVote?: () => void;
}) {
  const primaryText = expired
    ? "刷新可执行窗口"
    : verifierFailed
      ? "刷新可执行窗口"
      : executing
        ? "模拟执行中"
        : "确认模拟执行";
  const primaryAction = expired || verifierFailed ? onRefresh : onExecute;
  const primaryDisabled = verifierFailed ? executing : !expired && (!canExecute || executing);
  return (
    <div className="bottom-bar">
      {canVote ? (
        <button className="button secondary" onClick={onVote} disabled={executing}>
          发起投票
        </button>
      ) : votePending ? (
        <button className="button secondary" disabled>
          正在生成更多候选方案
        </button>
      ) : null}
      <button className="button" onClick={primaryAction} disabled={primaryDisabled}>
        {primaryText}
      </button>
    </div>
  );
}

export function GroupMessageCard({ message, planId }: { message?: string; planId?: string }) {
  return (
    <section className="card">
      <div className="row-between">
        <h2 className="card-title">群聊消息</h2>
        <SimulationBadge label="模拟消息已生成" />
      </div>
      <p className="subtitle">{message || "可复制消息已生成，当前Demo不真实发送微信或短信。"}</p>
      {planId ? (
        <Link className="button secondary full" href={`/plans/${planId}`}>
          查看最终方案
        </Link>
      ) : null}
    </section>
  );
}

function buildShareableRouteSummary(plan: PlanContract) {
  const stops = (plan.timeline || []).filter((step) => step.type !== "transport");
  const transportSteps = (plan.timeline || []).filter((step) => step.type === "transport");
  const timeText = routeTimeText(stops);
  const pathText = routePathText(stops);
  const transportText = routeTransportText(transportSteps);
  const budgetText = routeBudgetText(plan);
  const paceText = routePaceText(plan);
  const windowText = routeWindowText(plan);
  const scene = routeSceneLabel(plan);
  const goal = sanitizeUserText(plan.user_goal?.goal_summary || "一段刚刚好的生活时间");

  return [
    `我把${scene}整理成了一条更舒服的路线：${goal}`,
    [timeText, pathText].filter(Boolean).join("，") + "。",
    [transportText, paceText].filter(Boolean).join("；") + "。",
    [budgetText, windowText].filter(Boolean).join("；") + "。",
    "如果你们也喜欢这个节奏，我们就照这条线走，把时间花在真正值得停下来的地方。"
  ]
    .map((line) => line.replace(/^。$/, "").trim())
    .filter((line) => line && line !== "。")
    .join("\n");
}

function routeTimeText(stops: NonNullable<PlanContract["timeline"]>) {
  const first = stops[0];
  const last = stops[stops.length - 1];
  if (!first?.start_time || !last?.end_time) return "";
  return `${formatClock(first.start_time)}到${formatClock(last.end_time)}`;
}

function routePathText(stops: NonNullable<PlanContract["timeline"]>) {
  const names = stops
    .map((step) => sanitizeUserText(step.title))
    .filter(Boolean)
    .slice(0, 4);
  if (!names.length) return "先留出一段从容的生活时间";
  if (names.length === 1) return `在${names[0]}慢慢展开`;
  if (names.length === 2) return `从${names[0]}开始，再去${names[1]}收束`;
  const middle = names.slice(1, -1).join("，");
  return `从${names[0]}开始，去${middle}，最后在${names[names.length - 1]}收束`;
}

function routeTransportText(stops: NonNullable<PlanContract["timeline"]>) {
  const minutes = stops.reduce((sum, step) => {
    const routeMinutes = step.estimated_route?.duration_minutes;
    const duration = typeof routeMinutes === "number" ? routeMinutes : typeof step.duration_minutes === "number" ? step.duration_minutes : 0;
    return sum + duration;
  }, 0);
  if (!minutes) return "中间不把路程排得太满，留一点聊天和缓冲";
  return `中间转场约${minutes}分钟，不赶路，也不把好心情消耗在路上`;
}

function routeBudgetText(plan: PlanContract) {
  const total = plan.budget?.estimated_total;
  const perPerson = plan.budget?.price_per_person;
  if (typeof total !== "number" && typeof perPerson !== "number") return "";
  if (typeof perPerson === "number" && Number(plan.constraints?.party_size || plan.participants?.length || 1) > 1) {
    return `预算大约人均${formatMoney(perPerson, plan.budget?.currency)}`;
  }
  if (typeof total !== "number" && typeof perPerson === "number") {
    return `预算大约${formatMoney(perPerson, plan.budget?.currency)}`;
  }
  return `预算大约${formatMoney(total, plan.budget?.currency)}`;
}

function routePaceText(plan: PlanContract) {
  const profile = plan.constraints?.recommendation_profile;
  const normalizedTags =
    profile && typeof profile === "object" && Array.isArray((profile as JsonRecord).normalized_tags)
      ? ((profile as JsonRecord).normalized_tags as unknown[])
      : [];
  const labels = mapUserLabels([...(plan.user_goal?.intent_tags || []), ...normalizedTags]).slice(0, 3);
  if (!labels.length) return "节奏是轻一点、稳一点，让每一段都像刚好发生";
  return `关键词是${labels.join("、")}，节奏轻一点、稳一点`;
}

function routeWindowText(plan: PlanContract) {
  const left = minutesUntil(plan.executable_window?.expire_at);
  if (typeof left === "number" && left > 0) {
    return `接下来的${left}分钟里，这条线更适合直接定下来`;
  }
  return "如果放久了，我们出发前再重新看一眼，保留一点从容";
}

function routeSceneLabel(plan: PlanContract) {
  const scenario = plan.user_goal?.scenario;
  if (scenario === "friend_group") return "这次小聚";
  if (scenario === "family_parent_child") return "这段亲子时间";
  if (scenario === "anniversary_emotion") return "这个轻纪念日";
  if (scenario === "city_light_explore") return "这次城市散步";
  return "这段时间";
}

async function copyText(value: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
    const node = document.createElement("textarea");
    node.value = value;
    node.setAttribute("readonly", "");
    node.style.position = "fixed";
    node.style.left = "-9999px";
    document.body.appendChild(node);
    node.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(node);
    return copied;
  } catch {
    return false;
  }
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 10 }}>
      <div className="small muted">{label}</div>
      <strong>{value}</strong>
    </div>
  );
}

function backupSummary(backup: BackupPlan) {
  const diff = (backup.expected_diff || {}) as JsonRecord;
  const summary = typeof diff.user_visible_summary === "string" ? diff.user_visible_summary : "";
  if (summary) return summary;
  const replacement = typeof diff.replacement_poi_name === "string" ? diff.replacement_poi_name : "";
  if (replacement) return `已准备切换到${replacement}。`;
  return backup.description || "";
}

function digitalTwinSnapshot(plan: PlanContract, events: TraceEvent[]) {
  const candidatePayload = firstPayload(events, "CandidateRetriever");
  const counts = (candidatePayload?.candidate_counts || {}) as JsonRecord;
  const candidateTotal = ["activity", "restaurant", "tail"].reduce((sum, key) => sum + Number(counts[key] || 0), 0);
  const toolNames = visibleToolNames(events);
  const statusChecks = toolNames.filter((name) => ["get_restaurant_status", "get_poi_status"].includes(name)).length;
  const routeChecks = toolNames.filter((name) => name === "estimate_route").length;
  const weatherChecks = toolNames.filter((name) => name === "get_weather").length;
  const userLocation = plan.constraints?.user_location;
  const locationArea =
    userLocation && typeof userLocation === "object" && "area" in userLocation
      ? String((userLocation as JsonRecord).area || "")
      : "";
  const area = String(plan.constraints?.preferred_area || plan.constraints?.current_area || locationArea || "杭州下沙/金沙湖");
  return {
    candidateLabel: candidateTotal ? `${candidateTotal}个` : "已检索",
    statusLabel: `${statusChecks || plan.tool_actions?.length || 0}次`,
    routeLabel: `${routeChecks || (plan.timeline || []).filter((step) => step.type === "transport").length}段`,
    weatherLabel: weatherChecks ? `${weatherChecks}次` : "已纳入",
    areaLabel: `区域锚点：${sanitizeUserText(area)}`
  };
}

function firstPayload(events: TraceEvent[], moduleName: string): JsonRecord | null {
  const event = events.find((item) => item.module === moduleName && item.payload && typeof item.payload === "object");
  return (event?.payload || null) as JsonRecord | null;
}

function visibleToolNames(events: TraceEvent[]) {
  return events
    .filter((event) => event.visible_to_user !== false && event.event_type === "tool_log")
    .map((event) => (event.payload || {}) as JsonRecord)
    .map((payload) => (typeof payload.tool_name === "string" ? payload.tool_name : ""))
    .filter(Boolean);
}

function toolCallDetails(events: TraceEvent[], plan?: PlanContract | null) {
  const stepNames = new Map<string, string>();
  for (const step of plan?.timeline || []) {
    if (step.poi_id && step.title) stepNames.set(step.poi_id, step.title);
  }
  const seen = new Set<string>();
  const rows: Array<{ key: string; label: string; target: string }> = [];
  const pushRow = (label: string, target: string) => {
    if (!label || !target || rows.length >= 6) return;
    const key = `${label}:${target}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ key, label, target });
  };
  for (const event of events) {
    if (event.visible_to_user === false || event.event_type !== "tool_log") continue;
    const payload = (event.payload || {}) as JsonRecord;
    const toolName = typeof payload.tool_name === "string" ? payload.tool_name : "";
    const label = toolLabelForTrace(toolName);
    if (!label) continue;
    const poiId = typeof payload.poi_id === "string" ? payload.poi_id : "";
    const target = poiId ? stepNames.get(poiId) || "候选地点" : traceTarget(payload);
    pushRow(label, target);
  }
  for (const detail of fallbackToolCallDetails(plan, stepNames)) {
    pushRow(detail.label, detail.target);
  }
  return rows;
}

function fallbackToolCallDetails(plan: PlanContract | null | undefined, stepNames: Map<string, string>) {
  const rows: Array<{ label: string; target: string }> = [];
  const timeline = plan?.timeline || [];
  const area = planAreaLabel(plan);
  if (timeline.some((step) => step.poi_id && step.type !== "restaurant" && step.type !== "transport")) {
    rows.push({ label: "检索地点候选", target: area });
  }
  if (timeline.some((step) => step.type === "restaurant")) {
    rows.push({ label: "检索餐厅候选", target: area });
  }
  if (timeline.length) {
    rows.push({ label: "查询天气窗口", target: area });
  }
  for (const step of timeline) {
    if (step.type === "transport") {
      const from = step.from_poi_id ? stepNames.get(step.from_poi_id) : "";
      const to = step.to_poi_id ? stepNames.get(step.to_poi_id) : "";
      rows.push({ label: "估算转场路线", target: from && to ? `${from} → ${to}` : "计划转场" });
      continue;
    }
    if (step.type === "restaurant") {
      rows.push({ label: "查询餐厅余位", target: sanitizeUserText(step.title || "用餐节点") });
    } else if (step.poi_id) {
      rows.push({ label: "查询地点状态", target: sanitizeUserText(step.title || "计划节点") });
    }
  }
  for (const action of plan?.tool_actions || []) {
    if (action.user_visible === false || !action.type) continue;
    const label = toolLabelForTrace(action.type);
    if (!label) continue;
    const target = action.target_poi_id ? stepNames.get(action.target_poi_id) || actionTarget(action.payload) : actionTarget(action.payload);
    rows.push({ label, target });
  }
  return rows;
}

function planAreaLabel(plan: PlanContract | null | undefined) {
  const userLocation = plan?.constraints?.user_location;
  const locationArea =
    userLocation && typeof userLocation === "object" && "area" in userLocation
      ? String((userLocation as JsonRecord).area || "")
      : "";
  return sanitizeUserText(String(plan?.constraints?.preferred_area || plan?.constraints?.current_area || locationArea || "当前区域"));
}

function toolLabelForTrace(toolName: string) {
  const map: Record<string, string> = {
    search_poi: "检索地点候选",
    search_restaurant: "检索餐厅候选",
    get_restaurant_status: "查询餐厅余位",
    get_poi_status: "查询地点状态",
    estimate_route: "估算转场路线",
    get_weather: "查询天气窗口",
    get_social_signal_mock: "读取口碑雷达",
    book_activity: "生成活动预约凭证",
    reserve_restaurant: "生成餐厅订座凭证",
    order_item: "生成服务订单凭证",
    send_message: "生成消息草案"
  };
  return map[toolName] || "";
}

function traceTarget(payload: JsonRecord) {
  if (typeof payload.category === "string") {
    const categoryMap: Record<string, string> = {
      activity: "活动候选",
      restaurant: "餐厅候选",
      walk_spot: "散步节点",
      service: "服务节点",
      transport_anchor: "接驳节点"
    };
    return categoryMap[String(payload.category)] || "候选地点";
  }
  if (typeof payload.area === "string") return sanitizeUserText(String(payload.area));
  if (typeof payload.status === "string") return statusLabel(String(payload.status));
  return "系统检查";
}

function actionTarget(payload?: JsonRecord | null) {
  if (payload && typeof payload.poi_name === "string") return sanitizeUserText(payload.poi_name);
  if (payload && typeof payload.name === "string") return sanitizeUserText(payload.name);
  if (payload && payload.delivery_target && typeof payload.delivery_target === "object") {
    const target = payload.delivery_target as JsonRecord;
    if (typeof target.label === "string") return `送达${sanitizeUserText(target.label)}`;
  }
  return "计划节点";
}

function backupTitle(trigger?: string) {
  const map: Record<string, string> = {
    restaurant_capacity: "餐厅备选",
    weather: "天气备选",
    weather_risk: "天气备选",
    route_delay: "路线备选",
    queue_time: "排队备选",
    activity_ticket: "活动备选",
    service_order: "服务备选",
    verifier_risk: "可执行性备选"
  };
  return map[trigger || ""] || "备选方案";
}
