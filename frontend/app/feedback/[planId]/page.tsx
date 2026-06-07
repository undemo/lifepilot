"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { ErrorState, LoadingSkeleton } from "@/components/common/States";
import { MemoryCandidateCard } from "@/components/memory/MemoryCandidateCard";
import { api, ApiClientError } from "@/lib/api";
import type { FeedbackQuestion, MemoryCandidate, StandardError } from "@/types/schema";

export default function FeedbackPage() {
  return (
    <Suspense fallback={<FeedbackFallback />}>
      <FeedbackContent />
    </Suspense>
  );
}

function FeedbackFallback() {
  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="低打扰反馈" title="这次安排感觉怎么样" />
        <LoadingSkeleton lines={5} />
      </div>
    </AppShell>
  );
}

function FeedbackContent() {
  const params = useParams<{ planId: string }>();
  const search = useSearchParams();
  const [questions, setQuestions] = useState<FeedbackQuestion[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [rating, setRating] = useState("just_right");
  const [freeText, setFreeText] = useState("");
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<StandardError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.getFeedbackQuestions(params.planId);
      setQuestions((data.questions || []).slice(0, 2));
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "BAD_REQUEST", user_message: "反馈问题加载失败。" });
    } finally {
      setLoading(false);
    }
  }, [params.planId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(skipped = false) {
    setError(null);
    try {
      const { data } = await api.submitFeedback({
        plan_id: params.planId,
        execution_id: search.get("execution_id") || undefined,
        rating,
        selected_options: selected,
        free_text: freeText,
        skipped
      });
      setCandidates((data.memory_candidates || []).filter((item) => item.sensitivity !== "high"));
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "BAD_REQUEST", user_message: "反馈提交失败，请重试。" });
    }
  }

  async function confirm(candidate: MemoryCandidate) {
    try {
      await api.confirmMemoryCandidate(candidate.candidate_id, candidate.source_trace_id);
      setCandidates((items) => items.filter((item) => item.candidate_id !== candidate.candidate_id));
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  async function ignore(candidate: MemoryCandidate) {
    try {
      await api.ignoreMemoryCandidate(candidate.candidate_id, candidate.source_trace_id);
      setCandidates((items) => items.filter((item) => item.candidate_id !== candidate.candidate_id));
    } catch (err) {
      setError(err instanceof ApiClientError ? err.error : { code: "MEMORY_UNAVAILABLE", user_message: "记忆服务暂不可用。" });
    }
  }

  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="低打扰反馈" title="这次安排感觉怎么样" subtitle="最多两个问题；候选记忆需要你确认或忽略，不偷偷写画像。" />
        {loading ? <LoadingSkeleton lines={5} /> : null}
        <ErrorState error={error} onRetry={load} />
        {!submitted ? (
          <section className="card stack">
            <h2 className="card-title">轻量反馈</h2>
            <select className="select" value={rating} onChange={(event) => setRating(event.target.value)}>
              <option value="just_right">刚刚好</option>
              <option value="okay">一般</option>
              <option value="bad">不满意</option>
            </select>
            {questions.map((question) => (
              <div key={question.question_id}>
                <strong>{question.text}</strong>
                <div className="stack" style={{ marginTop: 8 }}>
                  {(question.options || []).map((option) => (
                    <label className="row" key={option.value}>
                      <input
                        type="checkbox"
                        checked={selected.includes(option.value)}
                        onChange={() =>
                          setSelected((current) => (current.includes(option.value) ? current.filter((item) => item !== option.value) : [...current, option.value]))
                        }
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <textarea className="textarea" value={freeText} onChange={(event) => setFreeText(event.target.value)} placeholder="可选：补充一句偏好" />
            <div className="grid-2">
              <button className="button secondary full" onClick={() => submit(true)}>
                跳过
              </button>
              <button className="button full" onClick={() => submit(false)}>
                提交
              </button>
            </div>
          </section>
        ) : (
          <section className="card">
            <h2 className="card-title">已收到反馈</h2>
            <p className="subtitle">我可以把低敏偏好作为下次规划参考，你可以确认或忽略。</p>
          </section>
        )}
        {candidates.map((candidate) => (
          <MemoryCandidateCard key={candidate.candidate_id} candidate={candidate} onConfirm={() => confirm(candidate)} onIgnore={() => ignore(candidate)} />
        ))}
        <div className="grid-2">
          <Link className="button secondary full" href="/">
            返回首页
          </Link>
          <Link className="button full" href="/memory">
            管理记忆
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
