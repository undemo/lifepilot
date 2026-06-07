import type { PlanSummary } from "@/types/schema";
import { formatMoney, statusLabel } from "@/lib/formatters";

export function VoteCard({
  summary,
  liked,
  disliked,
  onLike,
  onDislike
}: {
  summary: PlanSummary;
  liked: boolean;
  disliked: boolean;
  onLike: () => void;
  onDislike: () => void;
}) {
  const selected = liked || disliked;
  return (
    <section className={selected ? "vote-venue-card active" : "vote-venue-card"}>
      <div className="vote-venue-media">
        <div className="badge" style={{ position: "absolute", right: 10, top: 10, zIndex: 1 }}>
          {summary.score ? `${Math.round(summary.score * 100)}分` : statusLabel(summary.status)}
        </div>
      </div>
      <div style={{ padding: 14 }}>
        <div className="row-between">
          <h2 className="card-title">{summary.title || summary.goal_summary || summary.plan_id}</h2>
          <span className="badge gray">{liked ? "已喜欢" : disliked ? "已反选" : "待选择"}</span>
        </div>
        <p className="subtitle">{(summary.timeline_summary || []).join(" / ") || "候选方案摘要，完整执行仍基于plan_id。"}</p>
        <div className="row" style={{ flexWrap: "wrap" }}>
          <span className="badge gray">总预算 {formatMoney(summary.budget?.estimated_total, summary.budget?.currency)}</span>
          <span className="badge gray">窗口 {summary.executable_window?.window_minutes ?? "-"} 分钟</span>
        </div>
        <div className="grid-2" style={{ marginTop: 12 }}>
          <button className={liked ? "button full" : "button secondary full"} onClick={onLike}>
            喜欢
          </button>
          <button className={disliked ? "button warn full" : "button secondary full"} onClick={onDislike}>
            不想选
          </button>
        </div>
      </div>
    </section>
  );
}

export function ConsensusSummaryCard({ summary }: { summary?: Record<string, unknown> | null }) {
  return (
    <section className="card">
      <h2 className="card-title">共识摘要</h2>
      {summary ? (
        <div className="stack">
          <p className="subtitle">{String(summary.explanation || "已基于投票压缩出最终偏好。")}</p>
          {summary.vote_count !== undefined ? <span className="badge gray">有效投票 {String(summary.vote_count)}</span> : null}
          {Array.isArray(summary.detected_conflicts) && summary.detected_conflicts.length ? (
            <p className="subtitle small">已识别冲突：{summary.detected_conflicts.length}项</p>
          ) : (
            <p className="subtitle small">暂无强冲突。</p>
          )}
        </div>
      ) : (
        <p className="subtitle">还没有生成最终共识，可继续收集投票或直接生成。</p>
      )}
    </section>
  );
}
