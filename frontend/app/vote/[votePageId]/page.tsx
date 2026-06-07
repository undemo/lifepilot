"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { EmptyState, ErrorState, LoadingSkeleton, SimulationBadge } from "@/components/common/States";
import { VoteCard } from "@/components/consensus/VoteCard";
import { api, ApiClientError } from "@/lib/api";
import type { ConsensusSessionPayload, PlanSummary, StandardError } from "@/types/schema";

type VotePagePayload = ConsensusSessionPayload & { candidate_plans?: PlanSummary[] };

export default function VotePage() {
  const params = useParams<{ votePageId: string }>();
  const [data, setData] = useState<VotePagePayload | null>(null);
  const [liked, setLiked] = useState<string[]>([]);
  const [disliked, setDisliked] = useState<string[]>([]);
  const [participantName, setParticipantName] = useState("匿名朋友");
  const [budgetMax, setBudgetMax] = useState("");
  const [walking, setWalking] = useState("");
  const [queue, setQueue] = useState("");
  const [freeText, setFreeText] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<StandardError | null>(null);
  const candidates = useMemo(() => uniquePlanSummaries(data?.candidate_plans || data?.plan_summaries || data?.candidates || []), [data]);
  const closed = data?.status === "finalized" || data?.status === "closed" || data?.status === "expired";
  const preview = useMemo(() => constraintPreview(candidates, liked, budgetMax, walking, queue, freeText), [budgetMax, candidates, freeText, liked, queue, walking]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: next } = await api.getVotePage(params.votePageId);
      setData(next as VotePagePayload);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "RESOURCE_NOT_FOUND", user_message: "投票页不存在。" });
    } finally {
      setLoading(false);
    }
  }, [params.votePageId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (data?.vote_page_id) {
      window.sessionStorage.setItem("lifepilot_last_vote", data.vote_page_id);
    }
  }, [data?.vote_page_id]);

  function toggleLike(id: string) {
    setLiked((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
    setDisliked((current) => current.filter((item) => item !== id));
  }

  function toggleDislike(id: string) {
    setDisliked((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
    setLiked((current) => current.filter((item) => item !== id));
  }

  async function submit() {
    if (!data || submitting) return;
    const overlap = liked.filter((id) => disliked.includes(id));
    if (overlap.length) {
      setError({ code: "CONSENSUS_VOTE_INVALID", user_message: "同一个方案不能同时选择喜欢和不想选，请修改后提交。" });
      return;
    }
    if (!liked.length && !disliked.length && !freeText.trim() && !budgetMax && !walking && !queue) {
      setError({ code: "CONSENSUS_VOTE_INVALID", user_message: "请至少选择一个方案、填写预算/容忍度或写一句偏好。" });
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const voteTokenKey = `vote_token:${data.vote_page_id}`;
      const voteToken = window.localStorage.getItem(voteTokenKey) || `vote_${Date.now()}`;
      window.localStorage.setItem(voteTokenKey, voteToken);
      await api.submitVote(
        data.consensus_session_id,
        {
          participant: { participant_name: participantName || "匿名朋友", anonymous: true },
          liked_plan_ids: liked,
          disliked_plan_ids: disliked,
          budget_max: budgetMax ? Number(budgetMax) : undefined,
          walking_tolerance: walking || undefined,
          queue_tolerance: queue || undefined,
          free_text: freeText.trim(),
          client_vote_token: voteToken
        },
        data.trace_id
      );
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "BAD_REQUEST", user_message: "投票内容有误，请修改后提交。" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="朋友投票" title={data?.title || "选一个大家都能接受的方案"} subtitle="可复制投票链接已生成，当前为模拟分享卡体验。" />
        {loading ? <LoadingSkeleton lines={6} /> : null}
        <ErrorState error={error} onRetry={load} />
        {closed ? <EmptyState title="投票已结束" body="finalize后不可再投。" /> : null}
        {!loading && !candidates.length ? <EmptyState title="候选方案为空" body="投票链接异常或候选已失效。" /> : null}

        <section className="card">
          <div className="row-between">
            <h2 className="card-title" style={{ margin: 0 }}>好友同步状态</h2>
            <span className="badge warn">{submitted ? "已收到你的偏好" : "收集中"}</span>
          </div>
          <div className="sync-strip" style={{ marginTop: 14 }}>
            <FriendNode label="已就绪" initials="你" active />
            <FriendNode label="已投票" initials="A" active />
            <FriendNode label="考虑中" initials="B" />
            <FriendNode label="邀请" initials="+" />
          </div>
        </section>

        <section className="card">
          <div className="row-between">
            <strong>分享说明</strong>
            <SimulationBadge label="模拟分享卡" />
          </div>
          <p className="subtitle">不要求真实微信分享；复制链接后朋友可直接打开投票。</p>
          {data?.share_url ? <p className="small muted">{data.share_url}</p> : null}
        </section>
        {candidates.map((candidate) => (
          <VoteCard
            key={candidate.plan_id}
            summary={candidate}
            liked={liked.includes(candidate.plan_id)}
            disliked={disliked.includes(candidate.plan_id)}
            onLike={() => toggleLike(candidate.plan_id)}
            onDislike={() => toggleDislike(candidate.plan_id)}
          />
        ))}
        {!closed && candidates.length ? (
          <section className="card stack">
            <h2 className="card-title">你的偏好</h2>
            <div className="timeline-card">
              <strong>动态调整预览</strong>
              <p className="subtitle small">{preview}</p>
            </div>
            <input className="input" value={participantName} onChange={(event) => setParticipantName(event.target.value)} placeholder="昵称，可匿名" />
            <input className="input" type="number" value={budgetMax} onChange={(event) => setBudgetMax(event.target.value)} placeholder="人均预算上限，可不填" />
            <select className="select" value={walking} onChange={(event) => setWalking(event.target.value)}>
              <option value="">步行偏好不指定</option>
              <option value="low">少走路</option>
              <option value="medium_low">能少走就少走</option>
              <option value="medium">适中</option>
              <option value="high">可以多走</option>
            </select>
            <select className="select" value={queue} onChange={(event) => setQueue(event.target.value)}>
              <option value="">排队偏好不指定</option>
              <option value="low">不想排队</option>
              <option value="medium">可接受短队</option>
              <option value="high">可排队</option>
            </select>
            <textarea className="textarea" value={freeText} onChange={(event) => setFreeText(event.target.value)} placeholder="一句话补充偏好，可不填" />
            <button className="button full" onClick={submit} disabled={submitting || submitted}>
              {submitted ? "已提交" : submitting ? "提交中" : "提交投票"}
            </button>
            {submitted ? <Link href={`/consensus/${data?.consensus_session_id}`} className="button secondary full">查看共识结果</Link> : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}

function FriendNode({ label, initials, active = false }: { label: string; initials: string; active?: boolean }) {
  return (
    <div className="friend-node">
      <span className="friend-avatar" style={{ opacity: active ? 1 : 0.56 }}>
        {initials}
      </span>
      <span className={active ? "small" : "small muted"}>{label}</span>
    </div>
  );
}

function uniquePlanSummaries(candidates: PlanSummary[]) {
  const seen = new Set<string>();
  const result: PlanSummary[] = [];
  for (const candidate of candidates) {
    const signature = [
      (candidate.timeline_summary || []).join("|"),
      candidate.budget?.estimated_total ?? "",
      candidate.budget?.price_per_person ?? ""
    ].join("::");
    if (seen.has(signature)) continue;
    seen.add(signature);
    result.push(candidate);
  }
  return result;
}

function constraintPreview(candidates: PlanSummary[], liked: string[], budgetMax: string, walking: string, queue: string, freeText: string) {
  const selectedNames = liked
    .map((planId) => candidates.find((candidate) => candidate.plan_id === planId)?.title)
    .filter((item): item is string => Boolean(item));
  const likedText = selectedNames.length ? `优先参考${selectedNames.slice(0, 2).join("、")}` : "还未指定偏好的候选";
  const budgetText = budgetMax ? `人均不超过${budgetMax}元` : "预算沿用候选方案";
  const walkingText = walking === "low" ? "路线会压低步行" : walking === "medium_low" ? "路线会少走路" : walking === "medium" ? "路线强度适中" : walking === "high" ? "可接受更丰富路线" : "步行沿用候选方案";
  const queueText = queue === "low" ? "优先低排队和可预约" : queue === "medium" ? "可接受短队" : queue === "high" ? "可接受排队换体验" : "排队沿用候选方案";
  const text = freeText.trim() ? `，补充偏好：${freeText.trim().slice(0, 36)}` : "";
  return `${likedText}，${budgetText}，${walkingText}，${queueText}${text}。`;
}
