"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, MapPin, Plus, Route } from "lucide-react";
import { AppShell } from "@/components/common/AppShell";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/common/States";
import { api } from "@/lib/api";
import { formatClock, statusLabel } from "@/lib/formatters";
import { PlanHistoryItem, readLastCreatedPlanHistory, readPlanHistory, rememberPlanHistory } from "@/lib/plan-history";
import { sanitizeUserText } from "@/lib/view-models";
import type { StandardError } from "@/types/schema";

export default function PlansOverviewPage() {
  const [plans, setPlans] = useState<PlanHistoryItem[]>([]);
  const [selectedDate, setSelectedDate] = useState("");
  const [viewMode, setViewMode] = useState<"day" | "week">("day");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<StandardError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const seed = mergeLastCreated(readPlanHistory());
    const initialDate = firstDateKey(seed) || referenceDateKey();
    setPlans(seed);
    setSelectedDate((current) => current || initialDate);
    if (!seed.length) {
      setLoading(false);
      return;
    }

    let enrichedCount = 0;
    await Promise.all(
      seed.map(async (item) => {
        try {
          const { data } = await api.getPlan(item.planId);
          rememberPlanHistory(data.plan_contract);
          enrichedCount += 1;
        } catch {
          // Keep the cached summary. The detail page will surface the API error if opened.
        }
      })
    );
    const next = mergeLastCreated(readPlanHistory());
    const nextInitialDate = firstDateKey(next.length ? next : seed) || referenceDateKey();
    setPlans(next.length ? next : seed);
    setSelectedDate((current) => current || nextInitialDate);
    if (!enrichedCount && seed.some((item) => item.stepCount === 0)) {
      setError({ code: "PLAN_HISTORY_PARTIAL", user_message: "部分历史计划暂时无法同步详情，仍可尝试打开查看。" });
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const anchorDate = selectedDate || firstDateKey(plans) || referenceDateKey();
  const planCountByDate = useMemo(() => countPlansByDate(plans), [plans]);
  const weekDays = useMemo(() => buildWeekDays(anchorDate, planCountByDate), [anchorDate, planCountByDate]);
  const weekPlanKeys = new Set(weekDays.map((day) => day.key));
  const visiblePlans = plans
    .filter((plan) => {
      const key = dateKey(planDate(plan));
      return viewMode === "week" ? weekPlanKeys.has(key) : key === selectedDate;
    })
    .sort((left, right) => dateSortValue(planDate(left)) - dateSortValue(planDate(right)));
  const groupedPlans = groupByDate(visiblePlans);
  const featuredPlanId = visiblePlans[0]?.planId;
  const monthLabel = weekRangeText(weekDays);
  const currentDateKey = referenceDateKey();
  const currentLabel = todayTitle(currentDateKey);
  const isCurrentWeek = weekDays.some((day) => day.key === currentDateKey);

  function shiftWeek(days: number) {
    setSelectedDate((current) => dateKey(addDays(parseDateKey(current || anchorDate) || new Date(), days)));
    setViewMode("week");
  }

  function handleWeekButton() {
    if (viewMode === "day") {
      setViewMode("week");
      return;
    }
    if (!isCurrentWeek) {
      setSelectedDate(currentDateKey);
    }
    setViewMode("week");
  }

  return (
    <AppShell>
      <div className="page plans-page">
        <section className="plans-heading">
          <div>
            <p className="eyebrow">计划总览</p>
            <h1 className="title">{currentLabel}</h1>
            <p className="subtitle">每张卡片代表一段可回看的时间安排。</p>
          </div>
          <Link className="icon-button" href="/" title="新建计划">
            <Plus size={18} />
          </Link>
        </section>

        <section className="calendar-strip" aria-label="周计划选择">
          <div className="row-between calendar-strip-title">
            <span>{monthLabel}</span>
            <div className="week-controls" aria-label="切换周计划表">
              <button aria-label="上一周" className="week-nav-button" onClick={() => shiftWeek(-7)} type="button">
                <ChevronLeft size={17} />
              </button>
              <button className="week-current-button" onClick={handleWeekButton} type="button">
                <CalendarDays size={15} />
                {viewMode === "day" ? (isCurrentWeek ? "本周" : "看整周") : isCurrentWeek ? "本周全部" : "回本周"}
              </button>
              <button aria-label="下一周" className="week-nav-button" onClick={() => shiftWeek(7)} type="button">
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
          <div className="day-scroll">
            {weekDays.map((day) => (
              <button
                className={viewMode === "day" && selectedDate === day.key ? "day-pill active" : "day-pill"}
                key={day.key}
                onClick={() => {
                  setSelectedDate(day.key);
                  setViewMode("day");
                }}
                type="button"
              >
                <span>{day.weekday}</span>
                <strong>{day.day}</strong>
                {day.planCount > 0 ? <em>{day.planCount}项</em> : null}
              </button>
            ))}
          </div>
        </section>

        <ErrorState error={error} onRetry={load} />
        {loading && !plans.length ? <LoadingSkeleton lines={6} /> : null}
        {!loading && !plans.length ? (
          <EmptyState title="还没有计划" body="从首页生成一段计划后，这里会按日期保存，方便之后回看时间轴。" />
        ) : null}
        {!loading && plans.length > 0 && visiblePlans.length === 0 ? (
          <EmptyState
            title={viewMode === "week" ? "这一周还没有计划" : "这一天还没有计划"}
            body={viewMode === "week" ? "用左右箭头切换到过去/未来周，或点某一天查看单日计划。" : "点上方其他日期，或用左右箭头切换到过去/未来的周计划表。"}
          />
        ) : null}

        {groupedPlans.map((group) => (
          <section className="plan-day-group" key={group.key}>
            <h2>{dateHeading(group.key)}</h2>
            <div className="stack">
              {group.items.map((plan) => (
                <PlanOverviewCard featured={plan.planId === featuredPlanId} key={plan.planId} plan={plan} referenceDateKey={currentDateKey} />
              ))}
            </div>
          </section>
        ))}
      </div>
      {plans.length ? (
        <Link className="plan-fab" href="/" title="新建计划">
          <Plus size={30} />
        </Link>
      ) : null}
    </AppShell>
  );
}

function PlanOverviewCard({ featured, plan, referenceDateKey }: { featured?: boolean; plan: PlanHistoryItem; referenceDateKey: string }) {
  const timeLabel = plan.startTime && plan.endTime ? `${formatClock(plan.startTime)} - ${formatClock(plan.endTime)}` : "时间待同步";
  const relationLabel = dateRelationLabel(planDate(plan), referenceDateKey);
  const content = (
    <>
      <div aria-hidden="true" className={featured ? "plan-card-media large" : "plan-card-media"} style={{ backgroundImage: `url(${plan.image})` }}>
        {featured ? <span className="badge plan-card-floating-status">{statusLabel(plan.status)}</span> : null}
      </div>
      <div className="plan-card-body">
        <div className="row-between plan-card-title-row">
          <h3>{sanitizeUserText(plan.title)}</h3>
          {!featured ? <span className="badge gray">{statusLabel(plan.status)}</span> : null}
        </div>
        <p className="subtitle small">{sanitizeUserText(plan.summary)}</p>
        <div className="plan-meta-row">
          <span>
            <CalendarDays size={17} />
            {relationLabel}
          </span>
          <span>
            <Clock3 size={17} />
            {timeLabel}
          </span>
          {plan.area ? (
            <span>
              <MapPin size={17} />
              {sanitizeUserText(plan.area)}
            </span>
          ) : null}
        </div>
        <div className="row-between">
          <div className="mini-avatar-row">
            {Array.from({ length: Math.min(Math.max(plan.participantCount, 1), 3) }).map((_, index) => (
              <span className="mini-avatar" key={index}>
                {index === 0 ? "我" : index + 1}
              </span>
            ))}
            {plan.participantCount > 3 ? <span className="mini-avatar muted-avatar">+{plan.participantCount - 3}</span> : null}
          </div>
          <span className="plan-card-open">
            <Route size={16} />
            时间轴
            <ChevronRight size={17} />
          </span>
        </div>
      </div>
    </>
  );
  return (
    <Link className={featured ? "plan-overview-card featured" : "plan-overview-card"} href={`/plans/${plan.planId}`}>
      {featured ? content : <div className="compact-plan-layout">{content}</div>}
    </Link>
  );
}

function mergeLastCreated(items: PlanHistoryItem[]) {
  const lastCreated = readLastCreatedPlanHistory();
  if (!lastCreated || items.some((item) => item.planId === lastCreated.planId)) return items;
  return [lastCreated, ...items];
}

function groupByDate(items: PlanHistoryItem[]) {
  const groups = new Map<string, PlanHistoryItem[]>();
  for (const item of items) {
    const key = dateKey(planDate(item));
    const list = groups.get(key) || [];
    list.push(item);
    groups.set(key, list);
  }
  return Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, groupItems]) => ({ key, items: groupItems }));
}

function firstDateKey(items: PlanHistoryItem[]) {
  return items[0] ? dateKey(planDate(items[0])) : "";
}

function planDate(plan?: PlanHistoryItem) {
  return plan?.startTime || plan?.createdAt || plan?.updatedAt;
}

function buildWeekDays(anchorKey: string, planCountByDate: Record<string, number>) {
  const anchor = parseDateKey(anchorKey) || new Date();
  const weekday = anchor.getDay() || 7;
  const monday = new Date(anchor);
  monday.setDate(anchor.getDate() - weekday + 1);
  return Array.from({ length: 7 }).map((_, index) => {
    const day = new Date(monday);
    day.setDate(monday.getDate() + index);
    const key = dateKey(day);
    return {
      key,
      weekday: ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][index],
      day: day.getDate(),
      planCount: planCountByDate[key] || 0
    };
  });
}

function dateKey(value?: string | Date | null) {
  if (value instanceof Date) {
    return formatDateKey(value);
  }
  if (typeof value === "string") {
    const isoDate = value.match(/^(\d{4}-\d{2}-\d{2})/);
    if (isoDate) return isoDate[1];
  }
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  return formatDateKey(date);
}

function parseDateKey(key: string) {
  if (!key) return null;
  const match = key.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateHeading(key: string) {
  const date = parseDateKey(key);
  if (!date) return "待同步日期";
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
  return `${weekday}，${date.getMonth() + 1}月${date.getDate()}日`;
}

function todayTitle(key: string) {
  const date = parseDateKey(key);
  if (!date) return "今天";
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
  return `今天是 ${date.getMonth() + 1}月${date.getDate()}日 ${weekday}`;
}

function countPlansByDate(items: PlanHistoryItem[]) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = dateKey(planDate(item));
    if (!key) return counts;
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function referenceDateKey() {
  return dateKey(process.env.NEXT_PUBLIC_LIFEPILOT_DEMO_NOW || new Date());
}

function weekRangeText(days: Array<{ key: string }>) {
  const first = parseDateKey(days[0]?.key || "");
  const last = parseDateKey(days[days.length - 1]?.key || "");
  if (!first || !last) return "";
  if (first.getFullYear() === last.getFullYear() && first.getMonth() === last.getMonth()) {
    return `${first.getFullYear()}年${first.getMonth() + 1}月`;
  }
  if (first.getFullYear() === last.getFullYear()) {
    return `${first.getFullYear()}年${first.getMonth() + 1}月-${last.getMonth() + 1}月`;
  }
  return `${first.getFullYear()}年${first.getMonth() + 1}月-${last.getFullYear()}年${last.getMonth() + 1}月`;
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(date.getDate() + days);
  return next;
}

function formatDateKey(date: Date) {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function dateSortValue(value?: string) {
  const key = dateKey(value);
  const date = parseDateKey(key);
  if (!date) return 0;
  const raw = typeof value === "string" ? new Date(value).getTime() : date.getTime();
  return Number.isNaN(raw) ? date.getTime() : raw;
}

function dateRelationLabel(value: string | undefined, referenceKey: string) {
  const key = dateKey(value);
  const date = parseDateKey(key);
  const reference = parseDateKey(referenceKey);
  if (!date || !reference) return "日期待同步";
  const diffDays = Math.round((date.getTime() - reference.getTime()) / 86400000);
  if (diffDays === 0) return "今天";
  if (diffDays === 1) return "明天";
  if (diffDays === -1) return "昨天";
  return diffDays > 0 ? `${diffDays}天后` : `${Math.abs(diffDays)}天前`;
}
