"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Baby, BrainCircuit, CalendarClock, CloudSun, GitBranch, Heart, MapPin, Navigation, ShieldCheck, TrafficCone, Users, Wine, X } from "lucide-react";
import { AppShell } from "@/components/common/AppShell";
import { ErrorState, SimulationBadge } from "@/components/common/States";
import { api, type PlanCreateBody } from "@/lib/api";
import { buildClarificationQuestions, type ClarificationQuestion } from "@/lib/clarifications";
import { getDefaultCurrentTimeValue } from "@/lib/demo-time";
import type { StandardError } from "@/types/schema";

const CURRENT_TIME_STORAGE_KEY = "lifepilot_current_time_anchor";
const DATETIME_LOCAL_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const HERO_INPUT_MAX_HEIGHT = 178;

const scenarios = [
  {
    key: "family_parent_child",
    title: "家庭亲子",
    subtitle: "孩子有得玩，晚饭更轻松",
    icon: Baby,
    image: "https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=500&q=80",
    text: "今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。"
  },
  {
    key: "friend_group",
    title: "朋友局",
    subtitle: "候选方案发起投票",
    icon: Users,
    image: "https://images.unsplash.com/photo-1528605248644-14dd04022da1?auto=format&fit=crop&w=500&q=80",
    text: "周六下午4个朋友想在下沙附近聚一下，别走太多路，预算人均100左右，最好能投票决定。"
  },
  {
    key: "anniversary_emotion",
    title: "纪念日",
    subtitle: "不夸张但显得用心",
    icon: Heart,
    image: "https://images.unsplash.com/photo-1529636798458-92182e662485?auto=format&fit=crop&w=500&q=80",
    text: "今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。"
  },
  {
    key: "solo_mood_relief",
    title: "周末独处",
    subtitle: "散心、小酌、低压力",
    icon: Wine,
    image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=500&q=80",
    text: "周末下午我想去一个人散散心，顺便喝杯酒。"
  }
];

export default function HomePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [input, setInput] = useState(scenarios[0].text);
  const [scenarioHint, setScenarioHint] = useState<string | undefined>(scenarios[0].key);
  const [area, setArea] = useState("金沙湖");
  const [locationLabel, setLocationLabel] = useState("杭州金沙湖地铁站");
  const [currentTime, setCurrentTime] = useState(() => getDefaultCurrentTimeValue());
  const [durationHours, setDurationHours] = useState("4");
  const [stateDialogOpen, setStateDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<StandardError | null>(null);
  const invalid = input.trim().length < 5;
  const clarificationQuestions = buildClarificationQuestions(input, scenarioHint);

  useEffect(() => {
    const storedCurrentTime = readStoredCurrentTime();
    if (storedCurrentTime) {
      setCurrentTime(storedCurrentTime);
      return;
    }
    const initialCurrentTime = getDefaultCurrentTimeValue();
    setCurrentTime(initialCurrentTime);
    persistCurrentTime(initialCurrentTime);
  }, []);

  useEffect(() => {
    const textarea = inputRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const nextHeight = Math.min(textarea.scrollHeight, HERO_INPUT_MAX_HEIGHT);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > HERO_INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }, [input]);

  async function submit() {
    if (invalid || submitting) return;
    const body = buildPlanCreateBody(input.trim());
    if (clarificationQuestions.length > 0) {
      startClarification(body, clarificationQuestions);
      return;
    }
    await createPlanNow(body);
  }

  function buildPlanCreateBody(inputText: string): PlanCreateBody {
    return {
      input_text: inputText,
      scenario_hint: scenarioHint === "solo_mood_relief" ? undefined : scenarioHint,
      generate_candidates: shouldGenerateCandidates(inputText, scenarioHint),
      use_memory: true,
      debug: false,
      user_location: {
        label: locationLabel.trim() || `杭州${area}`,
        area
      },
      current_time: toShanghaiIso(currentTime),
      preferred_duration_hours: Number(durationHours) || 4
    };
  }

  function updateCurrentTime(value: string) {
    setCurrentTime(value);
    persistCurrentTime(value);
  }

  function startClarification(body: PlanCreateBody, questions: ClarificationQuestion[]) {
    setSubmitting(true);
    setError(null);
    try {
      const clarifyId = createClarifyId();
      window.sessionStorage.setItem(
        "lifepilot_pending_clarification",
        JSON.stringify({
          clarify_id: clarifyId,
          body,
          question_count: questions.length,
          created_at: Date.now()
        })
      );
      window.sessionStorage.removeItem("lifepilot_pending_create");
      router.push(`/plans/creating?clarify_id=${encodeURIComponent(clarifyId)}`);
    } catch {
      setError({ code: "INTERNAL_ERROR", user_message: "无法进入生成页，请重试。" });
      setSubmitting(false);
    }
  }

  async function createPlanNow(body: PlanCreateBody) {
    setSubmitting(true);
    setError(null);
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
      router.push(`/plans/creating?trace_id=${encodeURIComponent(prepared.traceId)}`);
    } catch {
      setError({ code: "INTERNAL_ERROR", user_message: "无法进入生成页，请重试。" });
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="page">
        <section className="hero-panel">
          <p className="eyebrow">生活时间导航助手</p>
          <h1 className="hero-question">今天下午有什么计划？</h1>
          <div className="hero-input-card">
            <div className="hero-input-row">
              <textarea
                className="hero-input"
                ref={inputRef}
                value={input}
                aria-label="输入生活目标"
                onChange={(event) => {
                  setInput(event.target.value);
                  setScenarioHint(undefined);
                }}
              />
              <div className="hero-tools">
                <button
                  aria-label="设置初始状态"
                  className="round-tool state-trigger"
                  onClick={() => setStateDialogOpen(true)}
                  title={`初始状态：${area} · ${durationHours}小时`}
                  type="button"
                >
                  <MapPin size={18} />
                </button>
              </div>
            </div>
            <button className="button full" disabled={invalid || submitting} onClick={submit}>
              {submitting ? "生成中" : "生成计划"}
              <ArrowRight size={18} />
            </button>
            {submitting ? <p className="subtitle small">正在理解你的目标并检查可执行性，开启模型时可能需要十几秒。</p> : null}
            <p className="subtitle small">输入一句目标，系统会生成可验证、可执行、可恢复的结构化计划。</p>
            {invalid ? <p className="subtitle small">请至少输入5个字。</p> : null}
          </div>
          <ErrorState error={error} />
        </section>

        <section className="realtime-section">
          <div className="section-title">
            <h2>本地实时</h2>
            <SimulationBadge label="模拟状态" />
          </div>
          <div className="status-grid">
            <div className="status-tile">
              <div className="row-between">
                <CloudSun size={22} color="var(--accent)" />
                <span className="badge warn">适合出行</span>
              </div>
              <div>
                <div className="status-value">24°C</div>
                <p className="subtitle small">杭州 · {area}</p>
              </div>
            </div>
            <div className="status-tile">
              <div className="row-between">
                <TrafficCone size={22} color="var(--brand-strong)" />
                <span className="badge gray">通畅</span>
              </div>
              <div>
                <div className="status-value">15 分钟</div>
                <p className="subtitle small">周边转场压力较低</p>
              </div>
            </div>
          </div>
        </section>

        <section className="scenarios-section">
          <div className="section-title">
            <h2>快捷场景</h2>
            <span className="badge gray">可体验流程</span>
          </div>
          <div className="horizontal-scroll">
          {scenarios.map((scenario) => {
            const Icon = scenario.icon;
            return (
              <button
                className={scenarioHint === scenario.key ? "scenario-card active" : "scenario-card"}
                key={scenario.key}
                onClick={() => {
                  setInput(scenario.text);
                  setScenarioHint(scenario.key);
                }}
              >
                <div aria-hidden="true" className="scenario-media" style={{ backgroundImage: `url(${scenario.image})` }} />
                <div className="scenario-body">
                  <div className="row">
                    <Icon size={18} />
                    <strong>{scenario.title}</strong>
                  </div>
                  <p className="subtitle small">{scenario.subtitle}</p>
                </div>
              </button>
            );
          })}
          </div>
        </section>

        <section className="large-feature">
          <span className="badge">今日灵感</span>
          <h2 className="card-title" style={{ marginTop: 12 }}>把“随便安排”变成可出发时间线</h2>
          <p className="subtitle">系统会检查路线、余位、排队、预算和备选方案，确认后只生成模拟凭证。</p>
          <button className="button secondary" onClick={() => setInput(scenarios[0].text)} style={{ marginTop: 12 }}>
            试试亲子下午
            <Navigation size={16} />
          </button>
        </section>

        <section className="card">
          <div className="row-between">
            <strong>LifePilot 当前优势</strong>
            <SimulationBadge />
          </div>
          <div className="advantage-grid" style={{ marginTop: 12 }}>
            <Advantage icon={<BrainCircuit size={18} />} title="结构化计划" body="一句话先变成目标、约束、时间线和工具动作。" />
            <Advantage icon={<ShieldCheck size={18} />} title="可执行性校验" body="余位、路线、天气和预算由系统统一校验。" />
            <Advantage icon={<GitBranch size={18} />} title="失败可恢复" body="餐厅满座或窗口过期时生成新计划版本。" />
            <Advantage icon={<Users size={18} />} title="朋友局共识" body="候选方案可投票，再压缩成最终方案。" />
          </div>
          <p className="subtitle small">当前演示使用模拟状态与模拟凭证，不承诺真实商家、真实支付或真实消息发送。</p>
        </section>
        {stateDialogOpen ? (
          <div className="state-modal-backdrop" onClick={() => setStateDialogOpen(false)}>
            <section
              aria-labelledby="initial-state-title"
              aria-modal="true"
              className="state-modal-sheet"
              onClick={(event) => event.stopPropagation()}
              role="dialog"
            >
              <div className="row-between">
                <div>
                  <p className="eyebrow">数字孪生区域</p>
                  <h2 className="card-title" id="initial-state-title">设置初始状态</h2>
                </div>
                <button aria-label="关闭初始状态设置" className="icon-button" onClick={() => setStateDialogOpen(false)} type="button">
                  <X size={18} />
                </button>
              </div>
              <div className="state-summary">
                <span>{area}</span>
                <span>{locationLabel || `杭州${area}`}</span>
                <span>{durationHours}小时</span>
              </div>
              <label className="field">
                当前区域
                <select className="select" value={area} onChange={(event) => setArea(event.target.value)}>
                  <option value="金沙湖">金沙湖</option>
                  <option value="下沙">下沙</option>
                  <option value="高教园区">高教园区</option>
                </select>
              </label>
              <label className="field">
                当前位置
                <input className="input" value={locationLabel} onChange={(event) => setLocationLabel(event.target.value)} />
              </label>
              <div className="grid-2">
                <label className="field">
                  <span className="row">
                    <CalendarClock size={14} />
                    当前时间锚点
                  </span>
                  <input className="input" type="datetime-local" value={currentTime} onChange={(event) => updateCurrentTime(event.target.value)} />
                </label>
                <label className="field">
                  可规划时长
                  <select className="select" value={durationHours} onChange={(event) => setDurationHours(event.target.value)}>
                    <option value="3">3小时</option>
                    <option value="4">4小时</option>
                    <option value="5">5小时</option>
                    <option value="6">6小时</option>
                  </select>
                </label>
              </div>
              <p className="subtitle small">这里表示“现在是几点”，不是强制出发时间；系统会结合“今天下午、周末、今晚”等自然语言生成计划窗口。</p>
              <button className="button full" onClick={() => setStateDialogOpen(false)} type="button">
                保存状态
              </button>
            </section>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

function readStoredCurrentTime() {
  if (typeof window === "undefined") return "";
  try {
    const value = window.localStorage.getItem(CURRENT_TIME_STORAGE_KEY) || "";
    return DATETIME_LOCAL_PATTERN.test(value) ? value : "";
  } catch {
    return "";
  }
}

function persistCurrentTime(value: string) {
  if (typeof window === "undefined") return;
  try {
    if (DATETIME_LOCAL_PATTERN.test(value)) {
      window.localStorage.setItem(CURRENT_TIME_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(CURRENT_TIME_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in private or restricted browser modes.
  }
}

function Advantage({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="advantage-tile">
      <div className="row" style={{ color: "var(--brand-strong)" }}>
        {icon}
        <strong>{title}</strong>
      </div>
      <p className="subtitle small">{body}</p>
    </div>
  );
}

function toShanghaiIso(value: string) {
  if (!value) return undefined;
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return `${withSeconds}+08:00`;
}

function shouldGenerateCandidates(input: string, scenarioHint?: string) {
  return scenarioHint === "friend_group" || /朋友|同学|4个人|四个人|4人/.test(input);
}

function createClarifyId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `clarify_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
