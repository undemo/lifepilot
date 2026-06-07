import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.time import iso_now, now_shanghai


class MockClock:
    def now(self) -> datetime:
        return now_shanghai()

    def iso_now(self) -> str:
        return iso_now()

    def parse(self, value: Optional[str]) -> datetime:
        if not value:
            return self.now()
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def target_date(self, value: Optional[str]) -> str:
        return self.parse(value).date().isoformat()

    def hour_bucket(self, value: Optional[str], bucket_hours: int = 2) -> str:
        dt = self.parse(value)
        bucket = (dt.hour // bucket_hours) * bucket_hours
        return f"{bucket:02d}:00"

    def expire_after(self, minutes: int) -> str:
        return (self.now() + timedelta(minutes=minutes)).replace(microsecond=0).isoformat()


class DeterministicSeedService:
    def __init__(self, demo_seed: Optional[str] = None) -> None:
        self.demo_seed = demo_seed or os.getenv("LIFEPILOT_DEMO_SEED") or "lifepilot-demo-seed-v1"

    def digest(self, *parts: Any) -> str:
        text = "|".join(str(part) for part in (self.demo_seed, *parts) if part is not None)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def ratio(self, *parts: Any) -> float:
        return int(self.digest(*parts)[:12], 16) / float(0xFFFFFFFFFFFF)

    def integer(self, low: int, high: int, *parts: Any) -> int:
        if high <= low:
            return low
        return low + int(self.ratio(*parts) * (high - low + 1))


class FailureMockEngine:
    def __init__(self, clock: MockClock, seed: DeterministicSeedService) -> None:
        self.clock = clock
        self.seed = seed

    def should_fail(
        self,
        poi: Dict[str, Any],
        when: Optional[str],
        party_size: Optional[int],
        failure_type: str,
        scenario: Optional[str] = None,
        probability: float = 0.03,
    ) -> bool:
        dt = self.clock.parse(when)
        return self.seed.ratio(poi.get("poi_id"), dt.date(), dt.hour, party_size, scenario, failure_type) < probability


class InventoryMockEngine:
    def __init__(self, clock: MockClock, seed: DeterministicSeedService) -> None:
        self.clock = clock
        self.seed = seed
        self.failure_engine = FailureMockEngine(clock, seed)

    def restaurant_slot(self, poi: Dict[str, Any], when: Optional[str], party_size: Optional[int]) -> Dict[str, Any]:
        dt = self.clock.parse(when)
        peak = self._restaurant_peak_factor(dt.hour, dt.minute)
        popularity = self._popularity(poi)
        capacity = self._restaurant_capacity(poi)
        pressure = min(0.95, peak + popularity * 0.32 + self.seed.ratio(poi.get("poi_id"), dt.date(), dt.hour, "restaurant_pressure") * 0.22)
        reserved = min(capacity, round(capacity * pressure))
        if self.failure_engine.should_fail(poi, when, party_size, "restaurant_failure"):
            reserved = capacity
        slot_start = dt.replace(minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(hours=2)
        return {
            "poi_id": poi.get("poi_id"),
            "slot_start": slot_start.isoformat(),
            "slot_end": slot_end.isoformat(),
            "base_tables": capacity,
            "reserved_tables": reserved,
            "max_party_size": self._max_party_size(poi),
            "booking_available": reserved < capacity,
            "source": "mock_engine",
            "mock_only": True,
        }

    def activity_slot(self, poi: Dict[str, Any], when: Optional[str], party_size: Optional[int]) -> Dict[str, Any]:
        dt = self.clock.parse(when)
        capacity = self._activity_capacity(poi)
        popularity = self._popularity(poi)
        peak = 0.24 if dt.weekday() >= 5 else 0.12
        if 13 <= dt.hour <= 20:
            peak += 0.18
        pressure = min(0.96, peak + popularity * 0.28 + self.seed.ratio(poi.get("poi_id"), dt.date(), dt.hour, "activity_pressure") * 0.28)
        remaining = max(0, capacity - round(capacity * pressure))
        if self.failure_engine.should_fail(poi, when, party_size, "activity_failure"):
            remaining = 0
        slot_start = dt.replace(minute=0, second=0, microsecond=0)
        slot_end = slot_start + timedelta(hours=2)
        return {
            "poi_id": poi.get("poi_id"),
            "slot_start": slot_start.isoformat(),
            "slot_end": slot_end.isoformat(),
            "remaining_tickets": remaining,
            "booking_available": remaining >= int(party_size or 1),
            "source": "mock_engine",
            "mock_only": True,
        }

    def _restaurant_peak_factor(self, hour: int, minute: int) -> float:
        value = hour + minute / 60
        if 11.5 <= value <= 13.5:
            return 0.48
        if 17.5 <= value <= 20:
            return 0.56
        if 14 <= value <= 17:
            return 0.18
        return 0.26

    def _restaurant_capacity(self, poi: Dict[str, Any]) -> int:
        tags = set(poi.get("tags") or [])
        if "mall" in tags:
            return 12
        if "coffee" in tags or "dessert" in tags:
            return 8
        return 10

    def _activity_capacity(self, poi: Dict[str, Any]) -> int:
        sub_category = str(poi.get("sub_category") or "")
        tags = set(poi.get("tags") or [])
        if any(key in sub_category for key in ("movie", "theater", "sports")) or "sports" in tags:
            return 80
        if any(key in sub_category for key in ("escape", "ktv", "pet", "board")):
            return 18
        if "mall" in tags:
            return 55
        return 36

    def _max_party_size(self, poi: Dict[str, Any]) -> int:
        tags = set(poi.get("tags") or [])
        if "coffee" in tags or "dessert" in tags:
            return 4
        return 8

    def _popularity(self, poi: Dict[str, Any]) -> float:
        rating = float(poi.get("rating") or 4.2)
        price = float(poi.get("price_per_person") or 50)
        photo_bonus = 0.08 if "has_photo" in set(poi.get("tags") or []) else 0
        return min(1.0, max(0.0, (rating - 3.8) / 1.2 + min(price, 180) / 900 + photo_bonus))


class StatusMockEngine:
    def __init__(self, clock: MockClock, seed: DeterministicSeedService) -> None:
        self.clock = clock
        self.seed = seed

    def generate(self, poi: Dict[str, Any], when: Optional[str], party_size: Optional[int], scenario: Optional[str] = None) -> Dict[str, Any]:
        dt = self.clock.parse(when)
        open_status = "open" if self._is_open(poi, dt) else "closed"
        indoor = self._is_indoor(poi)
        ttl_minutes = self.seed.integer(8, 22, poi.get("poi_id"), dt.date(), dt.hour, party_size, scenario, "ttl")
        queue_minutes = self._queue_minutes(poi, dt, party_size, scenario) if open_status == "open" else None
        available = open_status == "open"
        return {
            "available": available,
            "open_status": open_status,
            "queue_minutes": queue_minutes,
            "risk_level": self._risk_level(open_status, queue_minutes),
            "status_message": self._message(poi, open_status, queue_minutes),
            "expire_at": self.clock.expire_after(ttl_minutes),
            "updated_at": self.clock.iso_now(),
            "indoor": indoor,
            "duration_minutes": self._duration_minutes(poi),
            "source": "mock_engine",
            "mock_only": True,
        }

    def _is_open(self, poi: Dict[str, Any], dt: datetime) -> bool:
        opening_hours = poi.get("opening_hours") or {}
        key = "weekend" if dt.weekday() >= 5 else "weekday"
        windows = opening_hours.get(key) or opening_hours.get("weekday") or []
        if not windows:
            return True
        target = dt.hour * 60 + dt.minute
        for start, end in windows:
            try:
                start_h, start_m = [int(part) for part in start.split(":", 1)]
                end_h, end_m = [int(part) for part in end.split(":", 1)]
            except (AttributeError, ValueError):
                continue
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m
            if start_min <= end_min and start_min <= target <= end_min:
                return True
            if start_min > end_min and (target >= start_min or target <= end_min):
                return True
        return False

    def _queue_minutes(self, poi: Dict[str, Any], dt: datetime, party_size: Optional[int], scenario: Optional[str]) -> int:
        value = dt.hour + dt.minute / 60
        peak = 0
        if 11.5 <= value <= 13.5 or 17.5 <= value <= 20:
            peak = 14
        elif dt.weekday() >= 5 and 13 <= dt.hour <= 20:
            peak = 10
        risk = 8 if "queue_risk" in set(poi.get("risk_tags") or []) else 0
        rating = max(0, float(poi.get("rating") or 4.2) - 4.2) * 12
        party = max(0, int(party_size or 1) - 2) * 3
        jitter = self.seed.integer(0, 12, poi.get("poi_id"), dt.date(), dt.hour, party_size, scenario, "queue")
        return int(min(75, peak + risk + rating + party + jitter))

    def _risk_level(self, open_status: str, queue_minutes: Optional[int]) -> str:
        if open_status != "open":
            return "blocking"
        if queue_minutes is not None and queue_minutes >= 35:
            return "medium"
        return "low"

    def _message(self, poi: Dict[str, Any], open_status: str, queue_minutes: Optional[int]) -> str:
        if open_status != "open":
            return "Mock状态显示当前不在营业或可预约窗口内，建议调整时间。"
        if queue_minutes and queue_minutes >= 20:
            return f"Mock状态显示预计等待约{queue_minutes}分钟，建议保留备选。"
        return "Mock状态引擎生成的可执行状态，建议在窗口内确认。"

    def _is_indoor(self, poi: Dict[str, Any]) -> bool:
        tags = set(poi.get("tags") or [])
        if "outdoor" in tags or "outdoor_shade" in tags:
            return False
        return True

    def _duration_minutes(self, poi: Dict[str, Any]) -> int:
        if poi.get("category") == "restaurant":
            return 75
        sub_category = str(poi.get("sub_category") or "")
        if "sports" in sub_category:
            return 90
        if "coffee" in sub_category or "dessert" in sub_category:
            return 60
        return 75


class WeatherMockEngine:
    def __init__(self, clock: MockClock, seed: DeterministicSeedService) -> None:
        self.clock = clock
        self.seed = seed

    def generate(self, area: str, start_time: str, end_time: str, scenario: Optional[str] = None) -> Dict[str, Any]:
        start = self.clock.parse(start_time)
        month = start.month
        seasonal_temp = {12: 8, 1: 7, 2: 9, 3: 14, 4: 19, 5: 25, 6: 28, 7: 33, 8: 32, 9: 28, 10: 22, 11: 16}.get(month, 24)
        rain_base = 0.42 if month in {4, 5, 6, 7, 8} else 0.22
        rain_probability = min(0.92, rain_base + self.seed.ratio(area, start.date(), self.clock.hour_bucket(start_time), scenario, "rain") * 0.38)
        temperature = seasonal_temp + self.seed.integer(-3, 3, area, start.date(), self.clock.hour_bucket(start_time), "temp")
        if rain_probability >= 0.72:
            weather = "rain"
            outdoor_risk_level = "high"
        elif rain_probability >= 0.48:
            weather = "cloudy"
            outdoor_risk_level = "medium"
        else:
            weather = "clear"
            outdoor_risk_level = "low"
        return {
            "weather_id": f"weather_engine_{self.seed.digest(area, start.date(), self.clock.hour_bucket(start_time))[:10]}",
            "area": area,
            "time_range": {"start_time": start_time, "end_time": end_time},
            "weather": weather,
            "temperature": temperature,
            "rain_probability": round(rain_probability, 2),
            "outdoor_risk_level": outdoor_risk_level,
            "suggested_recovery": "indoor_activity" if outdoor_risk_level in {"medium", "high"} else None,
            "source": "mock_engine",
            "mock_only": True,
            "updated_at": self.clock.iso_now(),
        }


class SocialSignalMockEngine:
    def __init__(self, clock: MockClock, seed: DeterministicSeedService) -> None:
        self.clock = clock
        self.seed = seed

    def generate(self, poi: Dict[str, Any]) -> Dict[str, Any]:
        tags = set(str(tag) for tag in poi.get("tags") or [])
        risk_tags = set(str(tag) for tag in poi.get("risk_tags") or [])
        rating = float(poi.get("rating") or 4.2)
        heat_score = min(0.98, max(0.35, (rating - 3.6) / 1.4 + (0.08 if "has_photo" in tags else 0)))
        positive_tags = self._positive_tags(tags, poi)
        negative_tags = self._negative_tags(tags, risk_tags)
        summary = self._summary(poi, positive_tags, negative_tags)
        return {
            "signal_id": f"sig_engine_{self.seed.digest(poi.get('poi_id'), 'social')[:10]}",
            "poi_id": poi.get("poi_id"),
            "summary": summary,
            "positive_tags": positive_tags,
            "negative_tags": negative_tags,
            "heat_score": round(heat_score, 2),
            "is_mock": True,
            "source_type": "mock_social_signal",
            "updated_at": self.clock.iso_now(),
            "confidence": round(min(0.92, 0.62 + heat_score * 0.25), 2),
            "mock_sources": ["mock_profile", "mock_rating", "mock_tags"],
        }

    def _positive_tags(self, tags: set[str], poi: Dict[str, Any]) -> list[str]:
        result = []
        if "indoor" in tags:
            result.append("rain_safe")
        if "mall" in tags:
            result.append("easy_to_find")
        if "coffee" in tags or "dessert" in tags:
            result.append("short_rest")
        if "sports" in tags or "fitness" in tags:
            result.append("activity_energy")
        if float(poi.get("rating") or 0) >= 4.6:
            result.append("high_rating")
        return result[:4] or ["stable_choice"]

    def _negative_tags(self, tags: set[str], risk_tags: set[str]) -> list[str]:
        result = []
        if "queue_risk" in risk_tags:
            result.append("queue_risk")
        if "capacity_risk" in risk_tags:
            result.append("capacity_risk")
        if "mall" in tags:
            result.append("crowded_peak_hours")
        return result[:3]

    def _summary(self, poi: Dict[str, Any], positive_tags: list[str], negative_tags: list[str]) -> str:
        name = poi.get("name") or poi.get("poi_id")
        category = "餐饮" if poi.get("category") == "restaurant" else "活动"
        price = poi.get("price_per_person")
        good = "、".join(positive_tags) if positive_tags else "位置和基础体验稳定"
        bad = "，但高峰期可能存在" + "、".join(negative_tags) if negative_tags else "，目前没有明显负向标签"
        return f"{name} 的口碑为规则生成的Mock摘要，不代表真实即时评论抓取。该{category}点位评分和标签表现较稳定，客单价约{price}元，适合用于Demo里的候选比较；综合标签显示优势集中在{good}{bad}。"
