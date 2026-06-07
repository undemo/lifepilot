import Link from "next/link";
import { CheckCircle2, GitCompare, ReceiptText, Send } from "lucide-react";
import type { ExecutionResult, JsonRecord, RecoveryResult, ToolAction } from "@/types/schema";
import { formatTime, statusLabel } from "@/lib/formatters";
import { SimulationBadge } from "@/components/common/States";

type ExecutionVoucher = NonNullable<ExecutionResult["vouchers"]>[number];

export function ExecutionResultCard({ result, actions = [] }: { result?: ExecutionResult | null; actions?: ToolAction[] }) {
  const actionResults = result?.action_results || [];
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <CheckCircle2 size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            执行进度
          </h2>
        </div>
        <span className="badge">{statusLabel(result?.status)}</span>
      </div>
      <p className="subtitle">{result?.user_message || "执行结果来自模拟执行状态，页面不自行判断执行成功。"}</p>
      <div className="stack" style={{ marginTop: 10 }}>
        {(actionResults.length ? actionResults : actions).map((item, index) => {
          const detail = actionDetail((item as { result?: JsonRecord }).result);
          return (
          <div className="timeline-card" key={(item as ToolAction).action_id || index}>
            <div className="row-between">
              <span>{toolLabel((item as ToolAction).type || (item as { type?: string }).type)}</span>
              <span className="badge gray">{statusLabel((item as ToolAction).status || (item as { status?: string }).status)}</span>
            </div>
            {detail ? <p className="small muted">{detail}</p> : null}
          </div>
          );
        })}
      </div>
    </section>
  );
}

export function ExecutionVoucherCard({ result }: { result?: ExecutionResult | null }) {
  const vouchers = result?.vouchers?.length ? result.vouchers : deriveVouchersFromActionResults(result);
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <ReceiptText size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            模拟凭证
          </h2>
        </div>
        <SimulationBadge label="模拟凭证" />
      </div>
      {vouchers.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {vouchers.map((voucher, index) => (
            <div className="timeline-card" key={`${voucher.value}-${index}`}>
              <strong>{voucherLabel(voucher.type)}</strong>
              <p className="voucher-value">{voucher.value}</p>
              {voucher.poi_name ? <p className="small muted">关联地点：{voucher.poi_name}</p> : null}
              <p className="small muted">{formatTime(voucher.created_at)}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="subtitle">暂无凭证。执行成功后会展示模拟预约号、模拟订座号、模拟订单号或模拟消息。</p>
      )}
    </section>
  );
}

function deriveVouchersFromActionResults(result?: ExecutionResult | null): ExecutionVoucher[] {
  const actionResults = result?.action_results || [];
  const fields = [
    { field: "booking_id", type: "booking_id", displayName: "模拟预约号" },
    { field: "reservation_id", type: "reservation_id", displayName: "模拟订座号" },
    { field: "queue_number", type: "queue_number", displayName: "模拟排号" },
    { field: "order_id", type: "order_id", displayName: "模拟订单号" },
    { field: "message_id", type: "message_id", displayName: "模拟消息号" }
  ];

  return actionResults.flatMap((action) => {
    const actionResult = action.result;
    if (!actionResult) return [];
    const vouchers: ExecutionVoucher[] = [];
    fields.forEach((item) => {
      const value = actionResult[item.field];
      if (typeof value !== "string" && typeof value !== "number") return;
      vouchers.push({
        type: item.type,
        value: String(value),
        display_name: item.displayName,
        poi_id: typeof actionResult.poi_id === "string" ? actionResult.poi_id : undefined,
        poi_name: typeof actionResult.poi_name === "string" ? actionResult.poi_name : undefined,
        mock_only: true,
        created_at: typeof actionResult.created_at === "string" ? actionResult.created_at : result?.created_at
      });
    });
    return vouchers;
  });
}

export function RecoveryDiffCard({ recovery }: { recovery?: RecoveryResult | null }) {
  if (!recovery) {
    return (
      <section className="card">
        <div className="row">
          <GitCompare size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            方案调整
          </h2>
        </div>
        <p className="subtitle">当前没有恢复记录。若执行受阻，系统会生成新计划版本。</p>
      </section>
    );
  }
  const failureReasons = recoveryFailureReasons(recovery);
  const candidateSummary = recoveryCandidateSummary(recovery);
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <GitCompare size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            方案已调整
          </h2>
        </div>
        <span className="badge warn">{statusLabel(recovery.status)}</span>
      </div>
      <p className="subtitle">{recovery.user_explanation || String(recovery.trigger || "已生成替代计划。")}</p>
      {recovery.diff ? <p className="subtitle small">{String(recovery.diff.user_visible_summary || "已计算替代方案差异。")}</p> : null}
      {failureReasons.length ? (
        <div className="stack" style={{ marginTop: 10 }}>
          {failureReasons.map((reason, index) => (
            <div className="timeline-card" key={`${reason.code}-${index}`}>
              <strong>{reason.message}</strong>
              {reason.code ? <p className="small muted">{reasonLabel(reason.code)}</p> : null}
            </div>
          ))}
        </div>
      ) : null}
      {candidateSummary ? <p className="small muted">{candidateSummary}</p> : null}
      {recovery.updated_plan_id ? (
        <Link className="button secondary full" href={`/plans/${recovery.updated_plan_id}`}>
          查看新计划版本
        </Link>
      ) : null}
    </section>
  );
}

function recoveryFailureReasons(recovery: RecoveryResult): Array<{ code: string; message: string }> {
  const replacement = (recovery.replacement || {}) as JsonRecord;
  const diff = (recovery.diff || {}) as JsonRecord;
  const diagnostics = (diff.recovery_diagnostics || {}) as JsonRecord;
  const rawReasons = Array.isArray(replacement.failure_reasons)
    ? replacement.failure_reasons
    : Array.isArray(diagnostics.failure_reasons)
      ? diagnostics.failure_reasons
      : [];
  return rawReasons
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const reason = item as JsonRecord;
      const message = typeof reason.message === "string" ? reason.message : "";
      if (!message) return null;
      return {
        code: typeof reason.code === "string" ? reason.code : "",
        message
      };
    })
    .filter((item): item is { code: string; message: string } => Boolean(item));
}

function recoveryCandidateSummary(recovery: RecoveryResult): string | null {
  const replacement = (recovery.replacement || {}) as JsonRecord;
  const summary = (replacement.candidate_summary || {}) as JsonRecord;
  const considered = typeof summary.considered === "number" ? summary.considered : null;
  if (considered === null) return null;
  const semanticMismatch = typeof summary.semantic_mismatch === "number" ? summary.semantic_mismatch : 0;
  const notAvailable = typeof summary.not_available === "number" ? summary.not_available : 0;
  const queueExceeded = typeof summary.queue_exceeded === "number" ? summary.queue_exceeded : 0;
  return `已检查${considered}个候选，其中${semanticMismatch}个语义不匹配、${notAvailable}个无可用资源、${queueExceeded}个排队超出偏好。`;
}

function reasonLabel(code: string) {
  const map: Record<string, string> = {
    no_same_semantic_restaurant_available: "没有输出不符合原意的餐厅替代",
    same_semantic_restaurant_capacity_or_queue_failed: "同餐型候选存在，但资源状态不足",
    same_semantic_restaurant_no_capacity: "同餐型候选无可订桌位",
    same_semantic_restaurant_queue_exceeded: "同餐型候选排队偏长",
    same_semantic_activity_weather_unsafe: "同类活动受天气影响",
    replacement_plan_weather_failed: "替代节点可用，但整条路线仍有天气风险",
    replacement_plan_route_failed: "替代节点可用，但路线不够稳",
    replacement_plan_budget_failed: "替代节点可用，但预算不匹配"
  };
  return map[code] || code;
}

export function GroupMessageCard({ message }: { message?: string }) {
  return (
    <section className="card">
      <div className="row-between">
        <div className="row">
          <Send size={18} />
          <h2 className="card-title" style={{ margin: 0 }}>
            可复制消息
          </h2>
        </div>
        <SimulationBadge label="模拟消息已生成" />
      </div>
      <p className="subtitle">{message || "当前Demo只生成可复制消息，不真实发送微信或短信。"}</p>
    </section>
  );
}

function toolLabel(type?: string) {
  const map: Record<string, string> = {
    book_activity: "活动预约模拟处理中",
    reserve_restaurant: "餐厅订座模拟处理中",
    order_item: "订单模拟处理中",
    send_message: "模拟消息生成中"
  };
  return type ? map[type] || "模拟动作" : "模拟动作";
}

function voucherLabel(type?: string) {
  if (type?.includes("reservation")) return "模拟订座号已生成";
  if (type?.includes("booking")) return "模拟预约号已生成";
  if (type?.includes("order")) return "模拟订单号已生成";
  if (type?.includes("message")) return "模拟消息已生成";
  return "模拟凭证已生成";
}

function actionDetail(result?: JsonRecord | null) {
  if (!result) return "";
  if (typeof result.available_tables_before === "number") {
    const queue = typeof result.queue_minutes === "number" ? `，预计等${result.queue_minutes}分钟` : "";
    const venue = typeof result.poi_name === "string" ? `${result.poi_name}，` : "";
    return `${venue}订座前模拟余桌${result.available_tables_before}桌${queue}`;
  }
  if (typeof result.remaining_tickets_before === "number") {
    const venue = typeof result.poi_name === "string" ? `${result.poi_name}，` : "";
    return `${venue}预约前模拟余票${result.remaining_tickets_before}张`;
  }
  if (typeof result.order_status === "string" && typeof result.poi_name === "string") {
    const target = result.delivery_target && typeof result.delivery_target === "object" ? (result.delivery_target as JsonRecord).label : "";
    return target ? `${result.poi_name}，送达${String(target)}` : `${result.poi_name}，订单已生成`;
  }
  if (typeof result.display_text === "string") {
    return result.display_text;
  }
  return "";
}
