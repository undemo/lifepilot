"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, UserRound } from "lucide-react";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { EmptyState, ErrorState } from "@/components/common/States";
import { MemoryCandidateCard, MemoryList } from "@/components/memory/MemoryCandidateCard";
import { api, ApiClientError } from "@/lib/api";
import type { LifeMemory, MemoryCandidate, MemoryPayload, MemoryProfileSummary, ShortTermProfile, StandardError } from "@/types/schema";

export default function MemoryPage() {
  const [memories, setMemories] = useState<LifeMemory[]>([]);
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [personalized, setPersonalized] = useState(true);
  const [summary, setSummary] = useState<MemoryProfileSummary | null>(null);
  const [shortTerm, setShortTerm] = useState<ShortTermProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<StandardError | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    const nextMemories: LifeMemory[] = [];
    const nextCandidates: MemoryCandidate[] = [];
    try {
      const memory = await api.getMemory().catch(() => ({ data: { memories: [], items: [], personalization_enabled: true } as MemoryPayload }));
      const candidate = await api
        .getMemoryCandidates()
        .catch(() => ({ data: { candidates: [], items: [] } as { candidates?: MemoryCandidate[]; items?: MemoryCandidate[] } }));
      nextMemories.push(...((memory.data.memories || memory.data.items || []) as LifeMemory[]));
      nextCandidates.push(...((candidate.data.candidates || candidate.data.items || []) as MemoryCandidate[]).filter((item) => item.sensitivity !== "high"));
      setPersonalized(memory.data.personalization_enabled !== false);
      setSummary(memory.data.profile_summary || null);
      setShortTerm(memory.data.short_term_profile || null);
      setMemories(nextMemories);
      setCandidates(nextCandidates);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function confirm(candidate: MemoryCandidate) {
    try {
      await api.confirmMemoryCandidate(candidate.candidate_id, candidate.source_trace_id);
      setCandidates((items) => items.filter((item) => item.candidate_id !== candidate.candidate_id));
    } catch {
      setError({ code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  async function ignore(candidate: MemoryCandidate) {
    try {
      await api.ignoreMemoryCandidate(candidate.candidate_id, candidate.source_trace_id);
      setCandidates((items) => items.filter((item) => item.candidate_id !== candidate.candidate_id));
    } catch {
      setError({ code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  async function togglePersonalization(nextValue: boolean) {
    const previous = personalized;
    setPersonalized(nextValue);
    try {
      if (nextValue) {
        await api.enableMemoryPersonalization();
      } else {
        await api.disableMemoryPersonalization();
      }
      await load();
    } catch (err) {
      setPersonalized(previous);
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  async function toggleMemory(memory: LifeMemory) {
    try {
      const enabled = memory.enabled === false || memory.status === "disabled";
      await api.updateMemory(memory.memory_id, { enabled });
      await load();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  async function deleteMemory(memory: LifeMemory) {
    try {
      await api.deleteMemory(memory.memory_id);
      setMemories((items) => items.filter((item) => item.memory_id !== memory.memory_id));
      await load();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="LifeMemory" title="生活记忆与个人资料" subtitle="低打扰、可审计、用户可控；高敏候选不展示也不保存。" />
        <ErrorState error={error} onRetry={load} />
        <section className="profile-hero">
          <div className="row-between">
            <div className="row">
              <span className="avatar-mark">陈</span>
              <div>
                <h2 className="card-title" style={{ margin: 0 }}>陈小龙</h2>
                <p className="subtitle small" style={{ marginTop: 3 }}>
                  {summary?.enabled_count || memories.length}条长期记忆 · {summary?.pending_count || candidates.length}条待确认
                </p>
              </div>
            </div>
            <UserRound size={22} color="var(--brand-strong)" />
          </div>
        </section>
        <section className="card">
          <div className="row-between">
            <div className="row">
              <ShieldCheck size={18} />
              <strong>个性化</strong>
            </div>
            <label className="row">
              <input type="checkbox" checked={personalized} onChange={(event) => void togglePersonalization(event.target.checked)} />
              {personalized ? "启用" : "关闭"}
            </label>
          </div>
          <p className="subtitle">{personalized ? "规划时可使用你确认过的长期记忆。" : "本次不使用长期记忆。"}</p>
        </section>
        <section className="card">
          <div className="section-title">
            <h2>个人画像摘要</h2>
            <span className="badge gray">{personalized ? "可用于规划" : "已暂停"}</span>
          </div>
          {summary?.top_tags?.length ? (
            <div className="row" style={{ flexWrap: "wrap" }}>
              {summary.top_tags.map((tag) => (
                <span className="badge" key={tag}>{tag}</span>
              ))}
            </div>
          ) : (
            <p className="subtitle">确认候选后，这里会沉淀常用偏好。</p>
          )}
          {shortTerm?.summary ? <p className="subtitle small" style={{ marginTop: 10 }}>{shortTerm.summary}</p> : null}
        </section>
        <section className="card">
          <div className="section-title">
            <h2>记忆语境</h2>
            <span className="badge gray">{memories.length}条已确认</span>
          </div>
          <div className="memory-band">
            <div className="timeline-card memory-level medium">
              <strong>需要确认的候选</strong>
              <p className="subtitle small">中敏偏好会先等你确认，不能偷偷写入长期记忆。</p>
            </div>
            <div className="timeline-card memory-level low">
              <strong>低打扰偏好</strong>
              <p className="subtitle small">例如少排队、清淡餐、孩子友好、预算敏感，只服务下一次规划。</p>
            </div>
          </div>
        </section>
        {!loading ? <MemoryList memories={memories} onToggle={toggleMemory} onDelete={deleteMemory} /> : null}
        {!loading ? (
          candidates.length ? (
            candidates.map((candidate) => (
              <MemoryCandidateCard key={candidate.candidate_id} candidate={candidate} onConfirm={() => confirm(candidate)} onIgnore={() => ignore(candidate)} />
            ))
          ) : (
            <EmptyState title="暂无待确认候选" body="反馈后出现的低敏或中敏候选会在这里等待确认。" />
          )
        ) : null}
      </div>
    </AppShell>
  );
}
