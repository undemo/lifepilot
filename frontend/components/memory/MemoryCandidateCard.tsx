import { Shield } from "lucide-react";
import type { LifeMemory, MemoryCandidate } from "@/types/schema";

export function MemoryCandidateCard({
  candidate,
  onConfirm,
  onIgnore
}: {
  candidate: MemoryCandidate;
  onConfirm?: () => void;
  onIgnore?: () => void;
}) {
  if (candidate.sensitivity === "high") {
    return (
      <section className="card">
        <div className="row">
          <Shield size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            候选记忆已隐藏
          </h2>
        </div>
        <p className="subtitle">该信息不会被自动保存。</p>
      </section>
    );
  }
  return (
    <section className="card">
      <div className="row-between">
        <h2 className="card-title">候选记忆</h2>
        <span className="badge gray">{sensitivityLabel(candidate.sensitivity)}</span>
      </div>
      <p className="subtitle">{candidate.content || "我可以把这条偏好作为下次规划参考，你可以确认或忽略。"}</p>
      <div className="row" style={{ flexWrap: "wrap", marginTop: 8 }}>
        <span className="badge gray">来源：{sourceLabel(candidate.source)}</span>
        <span className="badge gray">状态：{candidateStatusLabel(candidate.status)}</span>
        <span className="badge gray">需要确认：{candidate.requires_confirmation === false ? "否" : "是"}</span>
      </div>
      {(onConfirm || onIgnore) && (
        <div className="grid-2" style={{ marginTop: 12 }}>
          <button className="button full" onClick={onConfirm}>
            确认
          </button>
          <button className="button secondary full" onClick={onIgnore}>
            忽略
          </button>
        </div>
      )}
    </section>
  );
}

export function MemoryList({
  memories,
  onToggle,
  onDelete
}: {
  memories: LifeMemory[];
  onToggle?: (memory: LifeMemory) => void;
  onDelete?: (memory: LifeMemory) => void;
}) {
  if (!memories.length) {
    return (
      <section className="card">
        <h2 className="card-title">长期记忆</h2>
        <p className="subtitle">还没有长期记忆。本次不会影响规划。</p>
      </section>
    );
  }
  return (
    <section className="card">
      <h2 className="card-title">长期记忆</h2>
      <div className="stack">
        {memories.map((memory) => (
            <div className="timeline-card" key={memory.memory_id}>
            <div className="row-between">
              <strong>{memory.content || memory.memory_type || memory.memory_id}</strong>
            <span className="badge gray">{memoryStatusLabel(memory.status)}</span>
          </div>
            <p className="small muted">
              敏感度：{sensitivityLabel(memory.sensitivity)}
              {memory.last_used_at ? ` · 最近用于规划：${formatDate(memory.last_used_at)}` : ""}
            </p>
            {(onToggle || onDelete) && (
              <div className="grid-2" style={{ marginTop: 10 }}>
                <button className="button secondary full" onClick={() => onToggle?.(memory)}>
                  {memory.enabled === false || memory.status === "disabled" ? "启用" : "停用"}
                </button>
                <button className="button secondary full" onClick={() => onDelete?.(memory)}>
                  删除
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function sourceLabel(source?: Record<string, unknown>) {
  const type = typeof source?.type === "string" ? source.type : "";
  const map: Record<string, string> = {
    plan_input: "本次提问",
    trip_feedback: "行程反馈",
    feedback: "反馈"
  };
  return map[type] || "用户确认";
}

function sensitivityLabel(value?: string) {
  const map: Record<string, string> = {
    low: "低敏",
    medium: "中敏",
    high: "高敏"
  };
  return map[value || ""] || "低敏";
}

function memoryStatusLabel(value?: string) {
  const map: Record<string, string> = {
    enabled: "已启用",
    disabled: "已关闭",
    confirmed: "已确认",
    ignored: "已忽略",
    candidate: "候选"
  };
  return map[value || ""] || "已启用";
}

function candidateStatusLabel(value?: string) {
  const map: Record<string, string> = {
    pending_confirmation: "待确认",
    candidate: "候选",
    ignored: "已忽略",
    enabled: "已启用",
    disabled: "已关闭"
  };
  return map[value || ""] || "待确认";
}

function formatDate(value?: string | null) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  } catch {
    return value;
  }
}
