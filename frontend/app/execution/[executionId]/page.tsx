"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { EmptyState, ErrorState, SimulationBadge } from "@/components/common/States";
import { ExecutionResultCard, ExecutionVoucherCard, GroupMessageCard, RecoveryDiffCard } from "@/components/execution/ExecutionCards";
import { ToolTracePanel } from "@/components/plan/PlanCards";
import { api, ApiClientError } from "@/lib/api";
import { toToolTraceView } from "@/lib/view-models";
import type { ExecutionResult, PlanPayload, StandardError } from "@/types/schema";

export default function ExecutionPage() {
  return (
    <Suspense fallback={<ExecutionFallback />}>
      <ExecutionContent />
    </Suspense>
  );
}

function ExecutionFallback() {
  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="执行结果" title="模拟执行完成情况" />
      </div>
    </AppShell>
  );
}

type StoredExecutionPayload = {
  plan_id?: string;
  active_plan_id?: string;
  execution_result?: ExecutionResult | null;
};

function ExecutionContent() {
  const params = useParams<{ executionId: string }>();
  const search = useSearchParams();
  const planId = search.get("plan_id");
  const [payload, setPayload] = useState<PlanPayload | null>(null);
  const [execution, setExecution] = useState<ExecutionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<StandardError | null>(null);

  const plan = payload?.plan_contract;
  const recovery = useMemo(() => {
    const list = execution?.recovery_results || payload?.latest_recovery_results || plan?.recovery_results || [];
    return list[0] || null;
  }, [execution, payload?.latest_recovery_results, plan?.recovery_results]);
  const hasExecutionContext = Boolean(execution || plan);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const storedData = readStoredExecution(params.executionId);
    const storedExecution = storedData?.execution_result || null;
    if (storedExecution) {
      setExecution(storedExecution);
    }

    const targetPlanId = planId || storedData?.active_plan_id || storedData?.plan_id || storedExecution?.plan_id;
    if (!targetPlanId) {
      setLoading(false);
      return;
    }

    try {
      const { data } = await api.getPlan(targetPlanId);
      setPayload(data);
      setExecution(storedData?.execution_result || data.latest_execution_result || null);
    } catch (err) {
      if (!storedExecution) {
        setError(err instanceof ApiClientError ? err.error : { code: "RESOURCE_NOT_FOUND", user_message: "执行记录暂不可用，请返回计划页。" });
      }
    } finally {
      setLoading(false);
    }
  }, [params.executionId, planId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="执行结果" title="模拟执行完成情况" subtitle="系统基于当前计划执行模拟动作，凭证均为模拟结果。" />
        <ErrorState error={error} onRetry={load} />
        {!loading && !hasExecutionContext ? <EmptyState title="执行记录暂不可用" body="可以返回计划页查看当前状态。" /> : null}
        {hasExecutionContext ? (
          <>
            <section className="card">
              <div className="row-between">
                <strong>执行边界</strong>
                <SimulationBadge label="模拟凭证" />
              </div>
              <p className="subtitle">不展示真实支付、真实短信、真实微信、真实订座或真实票务文案。</p>
            </section>
            <ExecutionResultCard result={execution} actions={plan?.tool_actions} />
            <ExecutionVoucherCard result={execution} />
            <RecoveryDiffCard recovery={recovery} />
            <ToolTracePanel items={toToolTraceView(plan?.tool_actions)} />
            <GroupMessageCard message={typeof plan?.messages?.to_group === "string" ? plan.messages.to_group : undefined} />
            <div className="grid-2">
              {plan ? (
                <Link className="button secondary full" href={`/plans/${plan.plan_id}`}>
                  返回计划页
                </Link>
              ) : null}
              {plan ? (
                <Link className="button full" href={`/feedback/${plan.plan_id}?execution_id=${params.executionId}`}>
                  给一点反馈
                </Link>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}

function readStoredExecution(executionId: string): StoredExecutionPayload | null {
  try {
    const stored = window.sessionStorage.getItem(`lifepilot_execution:${executionId}`);
    return stored ? (JSON.parse(stored) as StoredExecutionPayload) : null;
  } catch {
    return null;
  }
}
