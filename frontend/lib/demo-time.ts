const SHANGHAI_TIME_ZONE = "Asia/Shanghai";
const DEFAULT_CURRENT_TIME_HOUR = 8;
const DEFAULT_CURRENT_TIME_MINUTE = 0;

export function getDefaultCurrentTimeValue() {
  const configured = getConfiguredDemoNow();
  const configuredValue = configured ? toDateTimeLocalValue(configured) : "";
  return configuredValue || todayShanghaiDateTimeLocal(DEFAULT_CURRENT_TIME_HOUR, DEFAULT_CURRENT_TIME_MINUTE);
}

export function getDemoNowTimestamp() {
  const configured = getConfiguredDemoNow();
  if (configured) {
    const timestamp = new Date(configured).getTime();
    if (!Number.isNaN(timestamp)) return timestamp;
  }
  return Date.now();
}

function getConfiguredDemoNow() {
  return process.env.NEXT_PUBLIC_LIFEPILOT_DEMO_NOW?.trim() || "";
}

function toDateTimeLocalValue(value: string) {
  const match = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/);
  return match?.[1] || "";
}

function todayShanghaiDateTimeLocal(hour: number, minute: number) {
  const parts = shanghaiDateParts(new Date());
  return `${parts.year}-${parts.month}-${parts.day}T${pad2(hour)}:${pad2(minute)}`;
}

function shanghaiDateParts(date: Date) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: SHANGHAI_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit"
    }).formatToParts(date);
    return {
      year: partValue(parts, "year"),
      month: partValue(parts, "month"),
      day: partValue(parts, "day")
    };
  } catch {
    return {
      year: String(date.getFullYear()),
      month: pad2(date.getMonth() + 1),
      day: pad2(date.getDate())
    };
  }
}

function partValue(parts: Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) {
  return parts.find((part) => part.type === type)?.value || "";
}

function pad2(value: number) {
  return String(value).padStart(2, "0");
}
