"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/common/States";
import {
  BackupPlanCard,
  BudgetCard,
  ConfirmExecuteBar,
  DigitalTwinSnapshotCard,
  ExecutableWindowCard,
  MapRoutePanel,
  MemoryUsageNotice,
  PlanGoalSummary,
  PlanTimeline,
  RiskCard,
  ShareableRouteSummaryCard,
  ReputationSignalCard,
  ToolTracePanel
} from "@/components/plan/PlanCards";
import { api, ApiClientError } from "@/lib/api";
import { minutesUntil } from "@/lib/formatters";
import { rememberPlanHistory } from "@/lib/plan-history";
import { toToolTraceView } from "@/lib/view-models";
import type { PlanContract, PlanPayload, StandardError, TraceEvent } from "@/types/schema";

export default function PlanPage() {
  const params = useParams<{ planId: string }>();
  const router = useRouter();
  const planId = params.planId;
  const [payload, setPayload] = useState<PlanPayload | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<StandardError | null>(null);

  const plan: PlanContract | null = payload?.plan_contract || null;
  const expired = minutesUntil(plan?.executable_window?.expire_at) === 0;
  const candidatePlanIds = useMemo(() => candidateIdsFromPlan(plan, payload), [plan, payload]);
  const canVote = plan?.user_goal?.scenario === "friend_group" && candidatePlanIds.length >= 2;
  const votePending = plan?.user_goal?.scenario === "friend_group" && candidatePlanIds.length > 0 && candidatePlanIds.length < 2;
  const verifierStatus = plan?.verifier_result?.status;
  const verifierFailed = verifierStatus === "fail";
  const canExecute =
    !!plan &&
    ["executable", "confirmed", "verified"].includes(plan.status || "") &&
    ["pass", "warning"].includes(verifierStatus || "") &&
    !expired &&
    !executing;
  const toolItems = useMemo(() => toToolTraceView(plan?.tool_actions, events, plan), [plan, events]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [{ data }, traceResult] = await Promise.all([
        api.getPlan(planId),
        api.getPlanTrace(planId).catch(() => ({ data: { events: [] as TraceEvent[] } }))
      ]);
      setPayload(data);
      rememberPlanHistory(data.plan_contract);
      window.sessionStorage.setItem(
        "lifepilot_last_create",
        JSON.stringify({
          plan_id: data.plan_contract.plan_id,
          trace_id: data.plan_contract.trace_id,
          candidate_plan_ids: candidateIdsFromPlan(data.plan_contract, data)
        })
      );
      setEvents(traceResult.data.events || []);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "计划加载失败，请重试。" });
    } finally {
      setLoading(false);
    }
  }, [planId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function refreshWindow() {
    if (!plan) return;
    try {
      setError(null);
      await api.refreshWindow(plan.plan_id, plan.trace_id);
      await load();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "刷新失败，请重试。" });
    }
  }

  async function execute() {
    if (!plan || !canExecute || executing) return;
    setExecuting(true);
    setError(null);
    try {
      const { data } = await api.executePlan(plan.plan_id, plan.trace_id);
      window.sessionStorage.setItem(
        `lifepilot_execution:${data.execution_id}`,
        JSON.stringify({ plan_id: plan.plan_id, execution_result: data.execution_result, active_plan_id: data.active_plan_id })
      );
      router.push(`/execution/${data.execution_id}?plan_id=${encodeURIComponent(plan.plan_id)}`);
    } catch (err) {
      const nextError = err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "执行失败，请重试。" };
      setError(nextError);
      if (nextError.code === "PLAN_EXECUTABLE_WINDOW_EXPIRED") {
        await refreshWindow();
      }
    } finally {
      setExecuting(false);
    }
  }

  async function createVote() {
    if (!plan || !canVote) return;
    try {
      const { data } = await api.createConsensus(candidatePlanIds, plan.trace_id);
      window.sessionStorage.setItem("lifepilot_last_vote", data.vote_page_id);
      router.push(`/vote/${data.vote_page_id}`);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "创建投票失败，请重试。" });
    }
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="时间轴" title="这一段生活时间怎么过" subtitle="按时间顺序查看每一段安排和转场。" />
        {loading ? <LoadingSkeleton lines={8} /> : null}
        <ErrorState error={error} onRetry={load} />
        {!loading && !plan ? <EmptyState title="计划不存在" body="返回首页重新生成。" /> : null}
        {plan ? (
          <>
            <ShareableRouteSummaryCard plan={plan} />
            <PlanGoalSummary plan={plan} />
            <MemoryUsageNotice plan={plan} />
            <PlanTimeline plan={plan} />
            <MapRoutePanel plan={plan} />
            <DigitalTwinSnapshotCard plan={plan} events={events} />
            <ExecutableWindowCard window={plan.executable_window} />
            <BudgetCard budget={plan.budget} partySize={Number(plan.constraints?.party_size || plan.participants?.length || 1)} />
            <RiskCard risks={plan.risks} />
            <BackupPlanCard backups={plan.backup_plans} />
            <ToolTracePanel items={toolItems} events={events} plan={plan} />
            <ReputationSignalCard signals={plan.social_signals} />
            <ConfirmExecuteBar
              expired={expired}
              executing={executing}
              canExecute={canExecute}
              canVote={canVote}
              votePending={votePending}
              verifierFailed={verifierFailed}
              onRefresh={refreshWindow}
              onExecute={execute}
              onVote={canVote ? createVote : undefined}
            />
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function candidateIdsFromPlan(plan: PlanContract | null, payload: PlanPayload | null) {
  if (payload?.candidate_plan_ids?.length) {
    return payload.candidate_plan_ids.filter((item) => item.startsWith("plan_"));
  }
  const raw = plan?.messages?.consensus_candidate_plan_ids || plan?.messages?.candidate_plan_ids;
  if (Array.isArray(raw)) {
    return raw.filter((item): item is string => typeof item === "string" && item.startsWith("plan_"));
  }
  if (typeof window !== "undefined") {
    const cached = window.sessionStorage.getItem("lifepilot_last_create");
    if (cached) {
      try {
        const parsed = JSON.parse(cached) as { plan_id?: string; candidate_plan_ids?: unknown };
        if (parsed.plan_id === plan?.plan_id && Array.isArray(parsed.candidate_plan_ids)) {
          return parsed.candidate_plan_ids.filter((item): item is string => typeof item === "string" && item.startsWith("plan_"));
        }
      } catch {
        return [];
      }
    }
  }
  return [];
}
