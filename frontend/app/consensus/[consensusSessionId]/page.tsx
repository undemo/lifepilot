"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { ErrorState, LoadingSkeleton, SimulationBadge } from "@/components/common/States";
import { ConsensusSummaryCard } from "@/components/consensus/VoteCard";
import { GroupMessageCard, PlanGoalSummary, PlanTimeline } from "@/components/plan/PlanCards";
import { api, ApiClientError } from "@/lib/api";
import { toTimelineView } from "@/lib/view-models";
import type { ConsensusSessionPayload, PlanContract, StandardError } from "@/types/schema";

type FinalizeData = {
  consensus_summary?: Record<string, unknown>;
  final_plan_contract?: PlanContract;
  final_plan_id?: string;
};

export default function ConsensusPage() {
  const params = useParams<{ consensusSessionId: string }>();
  const [session, setSession] = useState<ConsensusSessionPayload | null>(null);
  const [finalPlan, setFinalPlan] = useState<PlanContract | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState<StandardError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sessionResult, summaryResult] = await Promise.all([
        api.getConsensus(params.consensusSessionId),
        api.getConsensusSummary(params.consensusSessionId).catch(() => ({ data: null }))
      ]);
      setSession(sessionResult.data);
      const summaryPayload = summaryResult.data as ConsensusSessionPayload | null;
      setSummary((summaryPayload?.consensus_summary as Record<string, unknown>) || null);
      if (summaryPayload?.final_plan_id) {
        const plan = await api.getPlan(summaryPayload.final_plan_id);
        setFinalPlan(plan.data.plan_contract);
      }
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "RESOURCE_NOT_FOUND", user_message: "共识会话不存在。" });
    } finally {
      setLoading(false);
    }
  }, [params.consensusSessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function finalize() {
    if (!session || finalizing) return;
    setFinalizing(true);
    setError(null);
    try {
      const { data } = await api.finalizeConsensus(session.consensus_session_id, session.trace_id);
      const finalized = data as FinalizeData;
      setSummary(finalized.consensus_summary || null);
      setFinalPlan(finalized.final_plan_contract || null);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "PLAN_SCHEMA_INVALID", user_message: "最终方案生成失败，可重试。" });
    } finally {
      setFinalizing(false);
    }
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="共识结果" title="把群聊拉扯压缩成最终方案" subtitle="最终方案会重新校验；群聊消息只做可复制或模拟生成。" />
        {loading ? <LoadingSkeleton lines={6} /> : null}
        <ErrorState error={error} onRetry={load} />
        <section className="card">
          <div className="row-between">
            <strong>投票统计</strong>
            <SimulationBadge label="可复制消息已生成" />
          </div>
          <p className="subtitle">当前状态：{session?.status || "加载中"}，有效投票：{String((session as Record<string, unknown> | null)?.vote_count ?? "-")}</p>
          <button className="button full" onClick={finalize} disabled={finalizing || Boolean(finalPlan)}>
            {finalPlan ? "已生成最终方案" : finalizing ? "生成中" : "生成共识方案"}
          </button>
        </section>
        <ConsensusSummaryCard summary={summary} />
        {finalPlan ? (
          <>
            <PlanGoalSummary plan={finalPlan} />
            <PlanTimeline items={toTimelineView(finalPlan)} />
            <GroupMessageCard message={typeof finalPlan.messages?.to_group === "string" ? finalPlan.messages.to_group : undefined} planId={finalPlan.plan_id} />
            <Link href={`/plans/${finalPlan.plan_id}`} className="button full">
              进入最终计划
            </Link>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
