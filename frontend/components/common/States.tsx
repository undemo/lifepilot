import { AlertTriangle, Loader2 } from "lucide-react";
import type { StandardError } from "@/types/schema";

export function SimulationBadge({ label = "演示模拟数据" }: { label?: string }) {
  return <span className="badge warn">{label}</span>;
}

export function LoadingSkeleton({ lines = 5 }: { lines?: number }) {
  return (
    <div className="card stack" aria-label="加载中">
      {Array.from({ length: lines }).map((_, index) => (
        <div key={index} className="skeleton" style={{ width: `${96 - index * 10}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  debug = false,
  onRetry
}: {
  error?: StandardError | null;
  debug?: boolean;
  onRetry?: () => void;
}) {
  if (!error) return null;
  return (
    <section className="card">
      <div className="row">
        <AlertTriangle size={18} color="var(--danger)" />
        <h2 className="card-title" style={{ margin: 0 }}>
          {error.user_message || "请求失败，请重试。"}
        </h2>
      </div>
      {onRetry ? (
        <button className="button secondary full" style={{ marginTop: 12 }} onClick={onRetry}>
          重试
        </button>
      ) : null}
      {debug && error.details ? <pre className="pre">{JSON.stringify(error.details, null, 2)}</pre> : null}
    </section>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <section className="card">
      <h2 className="card-title">{title}</h2>
      {body ? <p className="subtitle">{body}</p> : null}
    </section>
  );
}

export function InlineLoading({ label }: { label: string }) {
  return (
    <span className="row muted">
      <Loader2 size={16} className="spin" /> {label}
    </span>
  );
}
