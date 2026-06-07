"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, BrainCircuit, CheckCircle2, CircleDashed, Loader2, Route, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { AppShell, PageHeader } from "@/components/common/AppShell";
import { EmptyState, ErrorState, SimulationBadge } from "@/components/common/States";
import { api, ApiClientError, type PlanCreateAgentEvent, type PlanCreateBody, type PlanCreateStreamPrepared } from "@/lib/api";
import { buildClarificationQuestions, enrichInputWithClarifications, type ClarificationQuestion } from "@/lib/clarifications";
import { formatClock } from "@/lib/formatters";
import { rememberPlanHistory } from "@/lib/plan-history";
import { mapUserLabels } from "@/lib/view-models";
import type { PlanContract, PlanStep, StandardError } from "@/types/schema";

type StreamStatus = "idle" | "clarifying" | "streaming" | "completed" | "error";

type PendingClarificationCreate = {
  clarify_id: string;
  body: PlanCreateBody;
  created_at?: number;
};

export default function CreatingPage() {
  return (
    <Suspense fallback={<CreatingFallback />}>
      <CreatingContent />
    </Suspense>
  );
}

function CreatingFallback() {
  return (
    <AppShell>
      <div className="page">
        <PageHeader eyebrow="生成中" title="正在生成时间线" />
        <section className="agent-stream-panel">
          <div className="agent-current-line">
            <Loader2 size={18} className="spin" />
            <span>正在连接规划服务</span>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function CreatingContent() {
  const router = useRouter();
  const params = useSearchParams();
  const queryTraceId = params.get("trace_id");
  const queryPlanId = params.get("plan_id");
  const queryClarifyId = params.get("clarify_id");
  const pending = useMemo(() => readPendingCreate(queryTraceId), [queryTraceId]);
  const pendingClarification = useMemo(() => readPendingClarification(queryClarifyId), [queryClarifyId]);
  const [clarificationSession, setClarificationSession] = useState<PendingClarificationCreate | null>(pendingClarification);
  const clarificationQuestions = useMemo(() => {
    if (!clarificationSession) return [];
    return buildClarificationQuestions(clarificationSession.body.input_text, clarificationSession.body.scenario_hint);
  }, [clarificationSession]);
  const [clarificationStepIndex, setClarificationStepIndex] = useState(0);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const initialClarificationEvent = pendingClarification ? clarificationIntroEvent() : null;
  const [status, setStatus] = useState<StreamStatus>(pending ? "streaming" : pendingClarification ? "clarifying" : "idle");
  const [events, setEvents] = useState<PlanCreateAgentEvent[]>(() => (initialClarificationEvent ? [initialClarificationEvent] : []));
  const [currentEvent, setCurrentEvent] = useState<PlanCreateAgentEvent | null>(initialClarificationEvent);
  const [plan, setPlan] = useState<PlanContract | null>(null);
  const [renderedCount, setRenderedCount] = useState(0);
  const [error, setError] = useState<StandardError | null>(null);
  const startedRef = useRef(false);
  const localEventIndexRef = useRef(0);
  const eventIdsRef = useRef(new Set<string>());
  const renderPanelRef = useRef<HTMLElement | null>(null);
  const focusedPlanRef = useRef<string | null>(null);

  const appendLocalEvent = useCallback((event: PlanCreateAgentEvent) => {
    const item = {
      ...event,
      event_id: event.event_id || `local_${Date.now()}_${localEventIndexRef.current++}`
    };
    setEvents((current) => [...current, item].slice(-24));
    setCurrentEvent(item);
  }, []);

  const beginStream = useCallback((prepared: PlanCreateStreamPrepared) => {
    if (startedRef.current) return;
    startedRef.current = true;
    eventIdsRef.current.clear();
    setStatus("streaming");
    setError(null);
    setCurrentEvent({
      phase: "thinking",
      kind: "thinking",
      title: "正在思考",
      message: "正在连接真实规划链路。"
    });

    void api
      .streamCreatePlan(prepared, (event) => {
        if (event.event === "start") {
          setStatus("streaming");
          return;
        }
        if (event.event === "agent_event") {
          const item = event.data;
          const eventId = item.event_id || `${item.created_at || ""}:${item.title || ""}:${item.message || ""}`;
          if (eventIdsRef.current.has(eventId)) return;
          eventIdsRef.current.add(eventId);
          setEvents((current) => [...current, item].slice(-24));
          setCurrentEvent(item);
          return;
        }
        if (event.event === "complete") {
          const data = event.data.data;
          setStatus("completed");
          setPlan(data.plan_contract);
          setCurrentEvent({
            phase: "render",
            kind: "render",
            title: "渲染时间线",
            message: "真实计划已返回，正在把时间线节点渲染到页面。"
          });
          window.sessionStorage.setItem(
            "lifepilot_last_create",
            JSON.stringify({
              plan_id: data.plan_id,
              trace_id: event.data.trace_id || data.trace_id,
              candidate_plan_ids: data.candidate_plan_ids || [],
              tool_trace_summary: data.tool_trace_summary || []
            })
          );
          window.sessionStorage.removeItem("lifepilot_pending_create");
          rememberPlanHistory(data.plan_contract);
          return;
        }
        if (event.event === "error") {
          setStatus("error");
          setError(event.data.error);
          setCurrentEvent({
            phase: "error",
            kind: "error",
            title: "生成失败",
            message: event.data.error.user_message
          });
        }
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setStatus("error");
        setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "计划生成失败，请重试。" });
      });
  }, []);

  const beginCreateFromBody = useCallback(
    (body: PlanCreateBody) => {
      try {
        const prepared = api.prepareCreatePlanStream(body);
        window.sessionStorage.setItem(
          "lifepilot_pending_create",
          JSON.stringify({
            ...prepared,
            created_at: Date.now()
          })
        );
        window.sessionStorage.removeItem("lifepilot_pending_clarification");
        setClarificationSession(null);
        router.replace(`/plans/creating?trace_id=${encodeURIComponent(prepared.traceId)}`);
        beginStream(prepared);
      } catch {
        setStatus("error");
        setError({ code: "INTERNAL_ERROR", user_message: "无法进入生成页，请重试。" });
      }
    },
    [beginStream, router]
  );

  useEffect(() => {
    if (!pending || clarificationSession || startedRef.current) return;
    beginStream(pending);
  }, [beginStream, clarificationSession, pending]);

  useEffect(() => {
    if (status !== "clarifying" || !clarificationSession || clarificationQuestions.length > 0 || startedRef.current) return;
    beginCreateFromBody(clarificationSession.body);
  }, [beginCreateFromBody, clarificationQuestions.length, clarificationSession, status]);

  useEffect(() => {
    if (pending || clarificationSession || !queryPlanId || startedRef.current) return;
    startedRef.current = true;
    void api
      .getPlan(queryPlanId)
      .then(({ data }) => {
        setPlan(data.plan_contract);
        setStatus("completed");
        setCurrentEvent({
          phase: "render",
          kind: "render",
          title: "渲染时间线",
          message: "真实计划已返回，正在把时间线节点渲染到页面。"
        });
        rememberPlanHistory(data.plan_contract);
      })
      .catch((err) => {
        setStatus("error");
          setError(err instanceof ApiClientError ? err.error : { code: "INTERNAL_ERROR", user_message: "计划加载失败，请重试。" });
      });
  }, [clarificationSession, pending, queryPlanId]);

  useEffect(() => {
    if (!plan) return;
    setRenderedCount(0);
    const total = plan.timeline?.length || 0;
    const timer = window.setInterval(() => {
      setRenderedCount((current) => {
        if (current >= total) {
          window.clearInterval(timer);
          return current;
        }
        return current + 1;
      });
    }, 180);
    return () => window.clearInterval(timer);
  }, [plan]);

  useEffect(() => {
    if (!plan || focusedPlanRef.current === plan.plan_id) return;
    focusedPlanRef.current = plan.plan_id;
    window.requestAnimationFrame(() => {
      renderPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [plan]);

  const renderedSteps = (plan?.timeline || []).slice(0, renderedCount);
  const pendingSteps = Math.max(0, (plan?.timeline?.length || 0) - renderedCount);

  function chooseClarification(questionId: string, value: string) {
    const nextAnswers = { ...clarificationAnswers, [questionId]: value };
    setClarificationAnswers(nextAnswers);
    const currentIndex = clarificationQuestions.findIndex((question) => question.id === questionId);
    const question = clarificationQuestions[currentIndex];
    const answer = question?.options.find((option) => option.value === value);
    const isLastQuestion = currentIndex < 0 || currentIndex >= clarificationQuestions.length - 1;
    appendLocalEvent({
      phase: "tool",
      kind: "tool_result",
      title: isLastQuestion ? "补充完成" : "已记录偏好",
      message: answer ? `已记录：${answer.label}。` : "已记录偏好。",
      status: "success"
    });
    if (!isLastQuestion) {
      setClarificationStepIndex(currentIndex + 1);
      return;
    }
    if (clarificationSession) {
      beginCreateFromBody({
        ...clarificationSession.body,
        input_text: enrichInputWithClarifications(clarificationSession.body.input_text, nextAnswers, clarificationQuestions)
      });
    }
  }

  function skipCurrentClarification() {
    if (clarificationStepIndex < clarificationQuestions.length - 1) {
      setClarificationStepIndex((current) => current + 1);
      appendLocalEvent({
        phase: "tool",
        kind: "tool_result",
        title: "跳过偏好",
        message: "暂不补充这一项，继续确认下一项。",
        status: "warning"
      });
      return;
    }
    skipClarifications();
  }

  function skipClarifications() {
    if (!clarificationSession) return;
    appendLocalEvent({
      phase: "tool",
      kind: "tool_result",
      title: "直接生成",
      message: "暂不补充偏好，开始调用规划工具。",
      status: "warning"
    });
    beginCreateFromBody(clarificationSession.body);
  }

  return (
    <AppShell>
      <div className="page creating-page">
        <PageHeader
          eyebrow={status === "completed" ? "时间线已生成" : status === "clarifying" ? "补充偏好" : "生成中"}
          title={status === "completed" ? "时间线正在成形" : status === "clarifying" ? "先确认一个关键信息" : "正在生成时间线"}
          subtitle={
            status === "clarifying"
              ? "这里先确认影响体验的关键偏好，再进入规划流程。"
              : "这里展示规划进度；底层提示词和内部调试字段不会展示。"
          }
        />

        {!pending && !clarificationSession && !queryPlanId && !plan ? <EmptyState title="没有找到待生成请求" body="返回首页重新发起一次计划生成。" /> : null}
        <ErrorState error={error} onRetry={() => window.location.reload()} />

        <section className="agent-stream-panel" ref={renderPanelRef}>
          <div className="row-between">
            <div className="row">
              <PhaseIcon phase={currentEvent?.phase} spinning={status === "streaming"} />
              <div>
                <h2 className="card-title" style={{ margin: 0 }}>
                  {currentEvent?.title || "准备开始"}
                </h2>
                <p className="subtitle small" style={{ marginTop: 4 }}>
                  {currentEvent?.message || "等待第一条规划事件返回。"}
                </p>
              </div>
            </div>
            <SimulationBadge label={status === "clarifying" ? "偏好补充" : "模拟状态检查"} />
          </div>
          {status === "streaming" ? (
            <div className="agent-thinking-bar">
              <span>正在思考</span>
              <span className="thinking-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          ) : null}
          {status === "clarifying" && clarificationSession ? (
            <ClarificationToolCard
              answers={clarificationAnswers}
              currentIndex={clarificationStepIndex}
              onChoose={chooseClarification}
              onSkip={skipCurrentClarification}
              questions={clarificationQuestions}
            />
          ) : null}
          {plan ? (
            <TimelineRenderPreview
              plan={plan}
              renderedCount={renderedCount}
              renderedSteps={renderedSteps}
              pendingSteps={pendingSteps}
              onOpenPlan={() => router.replace(`/plans/${plan.plan_id}`)}
            />
          ) : null}
        </section>

        <section className="agent-event-stream" aria-label="Agent事件流">
          {events.length ? (
            events.map((event, index) => <AgentEventRow event={event} key={event.event_id || `${event.created_at || ""}-${index}`} />)
          ) : (
            <div className="agent-event-row waiting">
              <CircleDashed size={16} />
              <span>等待真实事件返回</span>
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function clarificationIntroEvent(): PlanCreateAgentEvent {
  return {
    event_id: "local_clarification_start",
    phase: "tool",
    kind: "tool_call",
    title: "补充偏好",
    message: "有个关键信息会影响计划质量，我先在这里确认。",
    status: "warning"
  };
}

function ClarificationToolCard({
  answers,
  currentIndex,
  onChoose,
  onSkip,
  questions
}: {
  answers: Record<string, string>;
  currentIndex: number;
  onChoose: (questionId: string, value: string) => void;
  onSkip: () => void;
  questions: ClarificationQuestion[];
}) {
  if (!questions.length) {
    return (
      <div className="clarification-tool-card">
        <p className="subtitle">没有需要补充的信息，正在进入规划链路。</p>
      </div>
    );
  }
  return (
    <div className="clarification-tool-card" aria-label="补充偏好工具步骤">
      <ClarificationStream answers={answers} currentIndex={currentIndex} onChoose={onChoose} questions={questions} />
      <button className="button secondary full" onClick={onSkip} type="button">
        跳过此项
      </button>
    </div>
  );
}

function ClarificationStream({
  answers,
  currentIndex,
  onChoose,
  questions
}: {
  answers: Record<string, string>;
  currentIndex: number;
  onChoose: (questionId: string, value: string) => void;
  questions: ClarificationQuestion[];
}) {
  const currentQuestion = questions[Math.min(currentIndex, Math.max(questions.length - 1, 0))];
  const answeredQuestions = questions.slice(0, currentIndex).filter((question) => answers[question.id]);
  if (!currentQuestion) return null;
  const Icon = currentQuestion.icon;
  return (
    <div className="clarification-stream">
      <div className="clarification-thinking">
        <span className="thinking-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span>{`偏好 ${Math.min(currentIndex + 1, questions.length)}/${questions.length}`}</span>
      </div>
      {answeredQuestions.map((question) => {
        const answer = question.options.find((option) => option.value === answers[question.id]);
        return answer ? (
          <div className="clarification-history" key={question.id}>
            <span>{question.question}</span>
            <strong>{answer.label}</strong>
          </div>
        ) : null;
      })}
      <div className="clarification-question active">
        <div className="row">
          <Icon size={16} />
          <strong>{currentQuestion.question}</strong>
        </div>
        <div className="clarification-options">
          {currentQuestion.options.map((option) => (
            <button
              className={answers[currentQuestion.id] === option.value ? "choice-chip active" : "choice-chip"}
              key={option.value}
              onClick={() => onChoose(currentQuestion.id, option.value)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function TimelineRenderPreview({
  plan,
  renderedCount,
  renderedSteps,
  pendingSteps,
  onOpenPlan
}: {
  plan: PlanContract;
  renderedCount: number;
  renderedSteps: PlanStep[];
  pendingSteps: number;
  onOpenPlan: () => void;
}) {
  const timelineLength = plan.timeline?.length || 0;
  const isRendered = renderedCount >= timelineLength;

  return (
    <div className="timeline-render-preview">
      <div className="row-between">
        <div className="row">
          <Sparkles size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            时间线渲染
          </h2>
        </div>
        <span className="badge">{isRendered ? "真实结果" : "正在渲染"}</span>
      </div>
      {timelineLength ? (
        <div className="timeline render-timeline" style={{ marginTop: 14 }}>
          {renderedSteps.map((step) => (
            <RenderedStep step={step} key={step.step_id} />
          ))}
          {Array.from({ length: Math.min(pendingSteps, 3) }).map((_, index) => (
            <div className="timeline-item ghost" key={`pending-${index}`}>
              <span className="timeline-dot ghost" />
              <div className="timeline-card render-placeholder">
                <span className="skeleton" />
                <span className="skeleton short" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="timeline-render-empty">
          <Route size={22} />
          <p>真实计划已返回，暂无可展示的时间线节点。</p>
        </div>
      )}
      <button className="button full" onClick={onOpenPlan} style={{ marginTop: 14 }}>
        查看完整计划
        <ArrowRight size={18} />
      </button>
    </div>
  );
}

function AgentEventRow({ event }: { event: PlanCreateAgentEvent }) {
  return (
    <div className={`agent-event-row ${event.phase || "thinking"} ${event.status || "success"}`}>
      <PhaseIcon phase={event.phase} />
      <div>
        <strong>{event.title || "规划步骤"}</strong>
        <p>{event.message || "已完成一步真实规划。"}</p>
      </div>
      <span>{statusText(event.status)}</span>
    </div>
  );
}

function RenderedStep({ step }: { step: PlanStep }) {
  const visibleTags = mapUserLabels(step.display_tags).slice(0, 4);

  return (
    <div className="timeline-item rendered">
      <span className="timeline-dot" />
      <div className="timeline-card">
        <div className="row-between">
          <strong>{step.title}</strong>
          <span className="small muted">
            {formatClock(step.start_time)}-{formatClock(step.end_time)}
          </span>
        </div>
        {step.description || step.user_visible_notes ? <p className="subtitle">{step.description || step.user_visible_notes}</p> : null}
        <div className="row" style={{ flexWrap: "wrap", marginTop: 8 }}>
          {visibleTags.map((tag) => (
            <span className="badge gray" key={tag}>
              {tag}
            </span>
          ))}
          {step.estimated_route?.duration_minutes ? <span className="badge gray">转场{step.estimated_route.duration_minutes}分钟</span> : null}
        </div>
      </div>
    </div>
  );
}

function PhaseIcon({ phase, spinning = false }: { phase?: string; spinning?: boolean }) {
  const className = spinning ? "spin" : undefined;
  if (phase === "tool") return <Wrench size={18} className={className} />;
  if (phase === "verify") return <ShieldCheck size={18} className={className} />;
  if (phase === "render") return <Sparkles size={18} className={className} />;
  if (phase === "error") return <CircleDashed size={18} />;
  if (phase === "completed") return <CheckCircle2 size={18} />;
  return <BrainCircuit size={18} className={className} />;
}

function statusText(status?: string) {
  if (status === "warning") return "提醒";
  if (status === "error") return "失败";
  return "完成";
}

function readPendingCreate(queryTraceId: string | null): PlanCreateStreamPrepared | null {
  if (typeof window === "undefined") return null;
  if (!queryTraceId) return null;
  try {
    const raw = window.sessionStorage.getItem("lifepilot_pending_create");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PlanCreateStreamPrepared;
    if (!parsed?.body || !parsed.traceId || !parsed.idempotencyKey) return null;
    if (parsed.traceId !== queryTraceId) return null;
    return parsed;
  } catch {
    return null;
  }
}

function readPendingClarification(queryClarifyId: string | null): PendingClarificationCreate | null {
  if (typeof window === "undefined") return null;
  if (!queryClarifyId) return null;
  try {
    const raw = window.sessionStorage.getItem("lifepilot_pending_clarification");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PendingClarificationCreate;
    if (!parsed?.body?.input_text || !parsed.clarify_id) return null;
    if (parsed.clarify_id !== queryClarifyId) return null;
    return parsed;
  } catch {
    return null;
  }
}
