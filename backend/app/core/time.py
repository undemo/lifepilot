import os
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback.
    ZoneInfo = None


def now_shanghai() -> datetime:
    fixed_now = os.getenv("LIFEPILOT_DEMO_NOW")
    if fixed_now:
        value = fixed_now.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(value)
            if ZoneInfo is not None and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            return parsed
        except ValueError:
            pass
    if ZoneInfo is None:
        return datetime.now().astimezone()
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def iso_now() -> str:
    return now_shanghai().replace(microsecond=0).isoformat()


def iso_after(minutes: int) -> str:
    return (now_shanghai() + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


def id_date() -> str:
    return now_shanghai().strftime("%Y%m%d")
