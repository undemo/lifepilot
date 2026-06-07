import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.constants import TraceEventType
from app.rules.intent_rules import looks_solo_mood_relief
from app.rules.recommendation_taxonomy import area_from_text, area_marker, extract_budget_max_per_person, extract_dining_preference, negates_activity_type, normalize_intent_profile
from app.core.time import now_shanghai
from app.services.logging_service import LoggingService


JAPANESE_CUISINE_TERMS = ("日料", "日式", "日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风", "会席", "日式咖喱", "回转寿司")
SUSHI_TERMS = ("寿司", "鮨", "刺身", "回转寿司")
IZAKAYA_TERMS = ("居酒屋", "烧鸟")
BUFFET_TERMS = ("自助餐", "自助烤肉", "自助烧烤", "自助火锅", "自助小火锅", "放题", "海鲜自助", "烤肉自助", "烧烤自助")
AMUSEMENT_TERMS = ("游乐园", "儿童乐园", "乐园", "嘉年华", "童宇宙", "游艺")
KARAOKE_TERMS = ("唱K", "KTV", "ktv", "K歌", "麦颂", "量贩KTV", "自助KTV", "AI智慧KTV")
GAME_TERMS = ("打游戏", "游戏", "电竞", "网咖", "网吧", "电玩", "PS5", "ps5", "Switch", "switch")
COFFEE_TERMS = ("咖啡", "咖啡店", "星巴克", "瑞幸", "M Stand", "Manner")
CONVERSATION_TERMS = ("聊天", "好聊天", "坐着聊", "聊一聊", "坐坐", "坐一会", "待一会", "聊")
POST_MEAL_TERMS = ("饭后", "餐后", "吃完饭", "吃完晚饭", "吃完", "吃好饭", "晚饭后")
LIGHT_WALK_TERMS = ("散步", "走走", "逛逛", "转转", "消食", "溜达")


class ConstraintExtractor:
    def __init__(self, logging_service: LoggingService) -> None:
        self.logging_service = logging_service

    def extract(
        self,
        trace_id: str,
        raw_text: str,
        user_goal: Dict[str, Any],
        body: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        scenario = user_goal["scenario"]
        party_size = self._party_size(raw_text, scenario)
        time_window = self._time_window(raw_text, body)
        solo_mood = self._is_solo_mood_relief(raw_text, scenario)
        user_location = self._user_location(body)
        preferred_area = area_from_text(raw_text)
        explicit_stop_range = self._target_stop_count(raw_text)
        target_stop_range, target_stop_source = self._target_stop_count_with_fallback(raw_text, scenario, time_window, explicit_stop_range)
        recommendation_profile = normalize_intent_profile(
            raw_text,
            scenario,
            llm_tags=user_goal.get("intent_tags"),
            user_location=user_location,
        )
        dining_preference = recommendation_profile.get("dining_preference") or extract_dining_preference(raw_text, user_goal.get("intent_tags"))
        constraints = {
            "party_size": party_size,
            "distance_preference": "nearby" if solo_mood or "远" in raw_text or "附近" in raw_text or scenario in {"family_parent_child", "friend_group"} else "same_area",
            "budget_max": self._budget_max(raw_text, scenario, party_size),
            "budget_max_per_person": self._budget_pp(raw_text, scenario),
            "budget_is_strict": self._budget_is_strict(raw_text),
            "walking_tolerance": "medium_low" if solo_mood else ("low" if "轻松" in raw_text or "别太远" in raw_text else "medium"),
            "queue_tolerance": "low",
            "dietary_preference": self._diet(raw_text, scenario),
            "activity_preference": self._activities(raw_text, scenario),
            "weather_sensitive": True,
            "child_friendly_required": scenario == "family_parent_child",
            "indoor_preferred": solo_mood or scenario in {"family_parent_child", "friend_group"},
            "emotion_intensity": "light" if "不想太夸张" in raw_text or scenario == "anniversary_emotion" else "medium",
            "emotion_goal": "放松/散心/低压力" if solo_mood else user_goal.get("emotion_goal"),
            "time_flexibility": "medium",
            "must_have": self._must_have(raw_text, scenario),
            "must_not_have": self._must_not_have(raw_text, scenario),
            "preferred_area": preferred_area,
            "current_area": user_location.get("area"),
            "user_location": user_location,
            "planning_start_time": time_window["start_time"],
            "planning_end_time": time_window["end_time"],
            "planning_anchor_time": time_window.get("anchor_time"),
            "time_intent": time_window.get("time_intent"),
            "target_stop_count": self._preferred_stop_count(target_stop_range, target_stop_source),
            "target_stop_count_range": list(target_stop_range) if target_stop_range else None,
            "target_stop_count_source": target_stop_source,
            "recommendation_profile": recommendation_profile,
            "dining_preference": dining_preference,
        }
        marker = area_marker(preferred_area)
        if marker and marker not in constraints["must_have"]:
            constraints["must_have"].append(marker)
        participants = self._participants(user_id, scenario, party_size)
        result = {
            "constraints": constraints,
            "time_window": time_window,
            "participants": participants,
            "source_notes": {
                "explicit": self._explicit_notes(raw_text),
                "assumptions": ["Demo默认区域为杭州下沙/金沙湖/高教园区。"],
            },
        }
        self.logging_service.log(
            trace_id,
            TraceEventType.CONSTRAINT_LOG,
            "ConstraintExtractor",
            {
                "user_visible_message": "已抽取人数、时间、预算和节奏偏好。",
                "party_size": party_size,
                "distance_preference": constraints["distance_preference"],
                "budget_max_per_person": constraints["budget_max_per_person"],
                "must_have": constraints["must_have"],
                "normalized_tags": recommendation_profile["normalized_tags"][:10],
                "time_intent": time_window.get("time_intent"),
                "dining_preference": {
                    "explicit": bool(dining_preference.get("explicit")),
                    "mode": dining_preference.get("mode"),
                    "specific_tags": dining_preference.get("specific_tags", [])[:6],
                },
            },
        )
        return result

    def _party_size(self, raw_text: str, scenario: str) -> int:
        explicit_number = self._explicit_party_size(raw_text)
        if explicit_number is not None:
            return explicit_number
        if "4个人" in raw_text or "四个人" in raw_text or "4人" in raw_text:
            return 4
        if "一个人" in raw_text or "自己" in raw_text or "独自" in raw_text:
            return 1
        if any(token in raw_text for token in ("女朋友", "对象", "情侣", "姐姐", "我姐", "妹妹", "哥哥", "弟弟")):
            return 2
        if scenario == "family_parent_child":
            return 3
        if scenario == "anniversary_emotion":
            return 2
        if scenario == "city_light_explore":
            return 2
        if scenario == "friend_group":
            return 4
        return 1

    def _explicit_party_size(self, raw_text: str) -> Optional[int]:
        match = re.search(r"([1-9]\d?)\s*(?:个)?人(?:以上|左右)?", raw_text)
        if match:
            return max(1, min(20, int(match.group(1))))
        match = re.search(r"([一二两三四五六七八九十])\s*(?:个)?人(?:以上|左右)?", raw_text)
        if not match:
            return None
        value = self._hour_value(match.group(1))
        return max(1, min(20, int(value))) if value else None

    def _time_window(self, raw_text: str, body: Dict[str, Any]) -> Dict[str, str]:
        if body.get("preferred_start_time") and body.get("preferred_end_time"):
            return {
                "start_time": body["preferred_start_time"],
                "end_time": body["preferred_end_time"],
                "time_flexibility": "medium",
                "anchor_time": body.get("current_time") or body.get("demo_now") or body["preferred_start_time"],
                "time_intent": "explicit_preferred_window",
            }
        anchor = self._anchor_now(body)
        duration_hours = self._preferred_duration_hours(body)
        explicit_window = self._explicit_text_window(raw_text, anchor, duration_hours)
        if explicit_window:
            start_dt, end_dt, time_intent = explicit_window
            return {
                "start_time": start_dt.replace(microsecond=0).isoformat(),
                "end_time": end_dt.replace(microsecond=0).isoformat(),
                "time_flexibility": "medium",
                "anchor_time": anchor.replace(microsecond=0).isoformat(),
                "time_intent": time_intent,
            }
        start_dt, end_dt, time_intent = self._default_window(raw_text, anchor, duration_hours)
        return {
            "start_time": start_dt.replace(microsecond=0).isoformat(),
            "end_time": end_dt.replace(microsecond=0).isoformat(),
            "time_flexibility": "medium",
            "anchor_time": anchor.replace(microsecond=0).isoformat(),
            "time_intent": time_intent,
        }

    def _default_window(
        self,
        raw_text: str,
        now: Optional[datetime] = None,
        duration_hours: Optional[float] = None,
    ) -> tuple[datetime, datetime, str]:
        now = now or now_shanghai()
        duration_minutes = self._duration_minutes(duration_hours)
        day_anchor = self._target_day_anchor(raw_text, now)
        deadline = self._deadline_before(raw_text, day_anchor)
        if deadline:
            if any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆", "音乐", "live", "Live", "爵士", "演出")):
                evening_start = deadline.replace(hour=18, minute=0, second=0, microsecond=0)
                if evening_start >= deadline:
                    evening_start = deadline - timedelta(hours=2)
                start_floor = self._same_tz(day_anchor, now)
                start = max((start_floor + timedelta(minutes=30)).replace(second=0, microsecond=0), evening_start)
            else:
                start = (day_anchor + timedelta(minutes=30)).replace(second=0, microsecond=0)
            if start >= deadline:
                soon = (day_anchor + timedelta(minutes=1)).replace(second=0, microsecond=0)
                start = soon if soon < deadline else deadline - timedelta(minutes=5)
            return start, deadline, "deadline_anchored"
        if self._has_dinner_request(raw_text) and "下午" not in raw_text:
            start = day_anchor.replace(hour=17, minute=0, second=0, microsecond=0)
            end_hour = 21 if any(token in raw_text for token in ("女朋友", "约会", "情侣", "对象", "火锅", "烤肉", "烧烤", "烧肉", "西餐", "牛排", "羊排", "羊肉", *JAPANESE_CUISINE_TERMS, *BUFFET_TERMS)) else 20
            end = day_anchor.replace(hour=end_hour, minute=30, second=0, microsecond=0)
            if now >= end:
                start = start + timedelta(days=1)
                end = end + timedelta(days=1)
            elif self._same_calendar_day(start, now) and now > start:
                start = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
            return start, end, "dinner_window"
        if "下午" not in raw_text and self._has_evening_request(raw_text):
            start = day_anchor.replace(hour=17, minute=0, second=0, microsecond=0)
            end = day_anchor.replace(hour=22, minute=0, second=0, microsecond=0)
            if now >= end:
                start = start + timedelta(days=1)
                end = end + timedelta(days=1)
            elif self._same_calendar_day(start, now) and now > start:
                start = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
            return start, end, "evening_window"
        if "下午" not in raw_text and any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆", "音乐", "live", "Live", "爵士", "演出")):
            start = day_anchor.replace(hour=18, minute=0, second=0, microsecond=0)
            end = day_anchor.replace(hour=22, minute=0, second=0, microsecond=0)
            if now >= end:
                start = start + timedelta(days=1)
                end = end + timedelta(days=1)
            elif self._same_calendar_day(start, now) and now > start:
                start = (now + timedelta(minutes=30)).replace(second=0, microsecond=0)
            return start, end, "evening_drink_window"
        if self._future_unspecified_leisure_window(raw_text, day_anchor, now):
            start = day_anchor.replace(hour=14, minute=0, second=0, microsecond=0)
            return start, start + timedelta(minutes=duration_minutes), "future_afternoon_default"
        if "下午" not in raw_text:
            start = day_anchor + timedelta(minutes=30)
            return start, start + timedelta(minutes=duration_minutes), "floating_short_window"
        if self._has_dinner_request(raw_text):
            start = day_anchor.replace(hour=15, minute=0, second=0, microsecond=0)
            end_hour = 21 if any(token in raw_text for token in ("女朋友", "约会", "情侣", "对象", "火锅", "烤肉", "烧烤", "烧肉", *JAPANESE_CUISINE_TERMS, *BUFFET_TERMS)) else 20
            end_minute = 30
            end = day_anchor.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        elif any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆")):
            start = day_anchor.replace(hour=15, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=max(duration_minutes, 240))
        else:
            start = day_anchor.replace(hour=14, minute=0, second=0, microsecond=0)
            end = start + timedelta(minutes=duration_minutes)
        if now >= end:
            start = start + timedelta(days=1)
            end = end + timedelta(days=1)
        return start, end, "afternoon_window"

    def _explicit_text_window(
        self,
        raw_text: str,
        anchor: datetime,
        duration_hours: Optional[float],
    ) -> Optional[tuple[datetime, datetime, str]]:
        mentions = self._time_mentions(raw_text, self._target_day_anchor(raw_text, anchor))
        if not mentions:
            return None
        start = self._mention_near_keywords(mentions, raw_text, ("出发", "开始", "开玩", "出门", "碰头", "集合"), prefer_last=False)
        end = self._mention_near_keywords(mentions, raw_text, ("回来", "回家", "到家", "结束", "前", "之前", "准时", "返回"), prefer_last=True)
        if not start and not end:
            return None
        if start and end:
            if end <= start:
                end += timedelta(days=1)
            return start, end, "explicit_text_window"
        if start:
            return start, start + timedelta(minutes=self._duration_minutes(duration_hours)), "explicit_start_window"
        if end:
            duration = timedelta(minutes=self._duration_minutes(duration_hours))
            start = max(anchor + timedelta(minutes=30), end - duration)
            return start.replace(second=0, microsecond=0), end, "deadline_anchored"
        return None

    def _anchor_now(self, body: Dict[str, Any]) -> datetime:
        for key in ("current_time", "demo_now", "now"):
            value = body.get(key)
            if not value:
                continue
            parsed = self._parse_dt(str(value))
            if parsed:
                return parsed
        return now_shanghai()

    def _parse_dt(self, value: str) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        current = now_shanghai()
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=current.tzinfo)
        return parsed.astimezone(current.tzinfo)

    def _preferred_duration_hours(self, body: Dict[str, Any]) -> Optional[float]:
        value = body.get("preferred_duration_hours") or body.get("duration_hours")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _duration_minutes(self, duration_hours: Optional[float]) -> int:
        if duration_hours is None:
            return 240
        return int(max(120, min(360, round(duration_hours * 60))))

    def _target_stop_count(self, raw_text: str) -> Optional[tuple[int, int]]:
        number = r"([0-9一二两三四五六七八九十])"
        target_words = r"(?:个)?(?:活动|地点|节点|项目|去处|地方|站)"
        range_match = re.search(number + r"\s*(?:-|~|到|至)\s*" + number + r"\s*" + target_words, raw_text)
        if range_match:
            low = self._hour_value(range_match.group(1))
            high = self._hour_value(range_match.group(2))
            if low and high:
                return max(1, min(low, high)), max(low, high)
        single_match = re.search(number + r"\s*" + target_words, raw_text)
        if single_match:
            count = self._hour_value(single_match.group(1))
            if count:
                return count, count
        return None

    def _target_stop_count_with_fallback(
        self,
        raw_text: str,
        scenario: str,
        time_window: Dict[str, Any],
        explicit_stop_range: Optional[tuple[int, int]],
    ) -> tuple[Optional[tuple[int, int]], str]:
        if explicit_stop_range:
            return explicit_stop_range, "explicit"
        if self._explicit_meal_without_activity(raw_text):
            return (1, 1), "meal_inferred"
        if self._explicit_activity_without_meal(raw_text):
            return (1, 2), "activity_inferred"
        if self._wants_light_density(raw_text, scenario):
            return (2, 3), "mood_inferred"
        duration_minutes = self._time_window_minutes(time_window)
        if duration_minutes >= 360:
            return (4, 5), "time_inferred"
        if duration_minutes >= 240:
            return (3, 4), "time_inferred"
        if duration_minutes >= 150:
            return (2, 3), "time_inferred"
        return (3, 4), "default"

    def _preferred_stop_count(self, target_stop_range: Optional[tuple[int, int]], source: str) -> Optional[int]:
        if not target_stop_range:
            return None
        low, high = target_stop_range
        if source == "explicit":
            return high
        return low

    def _time_window_minutes(self, time_window: Dict[str, Any]) -> int:
        try:
            start = datetime.fromisoformat(str(time_window["start_time"]))
            end = datetime.fromisoformat(str(time_window["end_time"]))
        except (KeyError, TypeError, ValueError):
            return 240
        return max(0, int((end - start).total_seconds() // 60))

    def _wants_light_density(self, raw_text: str, scenario: str) -> bool:
        light_words = ("轻松", "放松", "散心", "压力大", "有点累", "很累", "不想折腾", "别折腾", "别太折腾", "少转场", "低压力", "慢一点")
        if any(token in raw_text for token in light_words):
            return True
        return self._is_solo_mood_relief(raw_text, scenario)

    def _explicit_activity_without_meal(self, raw_text: str) -> bool:
        if self._has_meal_request(raw_text):
            return False
        return self._has_activity_request(raw_text)

    def _explicit_meal_without_activity(self, raw_text: str) -> bool:
        return self._has_meal_request(raw_text) and not self._has_activity_request(raw_text)

    def _has_activity_request(self, raw_text: str) -> bool:
        activity_terms = (
            *GAME_TERMS,
            *KARAOKE_TERMS,
            *LIGHT_WALK_TERMS,
            "桌游",
            "剧本杀",
            "密室",
            "台球",
            "羽毛球",
            "电影",
            "看电影",
            "手工",
            "手作",
            "活动",
            "出去玩",
            "出去转转",
            "出去逛逛",
            "去玩",
            "逛逛",
            "散步",
            "转转",
            "溜一圈",
            "公园",
            "景点",
        )
        if any(term in raw_text for term in activity_terms):
            return True
        return bool(re.search(r"玩\s*(?:几个|[0-9一二两三四五六七八九十]+)\s*(?:小?时|钟头)", raw_text))

    def _future_unspecified_leisure_window(self, raw_text: str, day_anchor: datetime, now: datetime) -> bool:
        if any(token in raw_text for token in ("上午", "中午", "下午", "晚上", "今晚", "早上", "一早")):
            return False
        if self._has_dinner_request(raw_text) or self._has_evening_request(raw_text):
            return False
        current = self._same_tz(day_anchor, now)
        if day_anchor.date() == current.date():
            return False
        leisure_terms = (
            "周末",
            "这周末",
            "本周末",
            "朋友",
            "同学",
            "出去玩",
            "活动",
            "打游戏",
            "游戏",
            "电竞",
            "网咖",
            "网吧",
            "KTV",
            "唱歌",
            "桌游",
            "剧本杀",
            "电影",
            "逛逛",
            "散步",
        )
        return any(term in raw_text for term in leisure_terms)

    def _target_day_anchor(self, raw_text: str, now: datetime) -> datetime:
        target_date = self._target_date(raw_text, now)
        return now.replace(year=target_date.year, month=target_date.month, day=target_date.day)

    def _target_date(self, raw_text: str, now: datetime):
        if "明天" in raw_text:
            return (now + timedelta(days=1)).date()
        if "后天" in raw_text:
            return (now + timedelta(days=2)).date()
        if "今天" in raw_text or "今日" in raw_text:
            return now.date()

        weekday = self._explicit_weekday(raw_text)
        if weekday is not None:
            days = (weekday - now.weekday()) % 7
            if days == 0 and self._period_passed(raw_text, now):
                days = 7
            return (now + timedelta(days=days)).date()

        if any(token in raw_text for token in ("周末", "这周末", "本周末")):
            weekday_now = now.weekday()
            if weekday_now < 5:
                return (now + timedelta(days=5 - weekday_now)).date()
            if weekday_now == 5:
                return (now + timedelta(days=1 if self._period_passed(raw_text, now) else 0)).date()
            return (now + timedelta(days=6 if self._period_passed(raw_text, now) else 0)).date()

        return now.date()

    def _explicit_weekday(self, raw_text: str) -> Optional[int]:
        mapping = {
            "一": 0,
            "1": 0,
            "二": 1,
            "2": 1,
            "三": 2,
            "3": 2,
            "四": 3,
            "4": 3,
            "五": 4,
            "5": 4,
            "六": 5,
            "6": 5,
            "日": 6,
            "天": 6,
            "7": 6,
        }
        match = re.search(r"(?:周|星期|礼拜)([一二三四五六日天1-7])", raw_text)
        if not match:
            return None
        return mapping.get(match.group(1))

    def _period_passed(self, raw_text: str, now: datetime) -> bool:
        if "下午" in raw_text:
            return now.hour >= 18
        if self._has_dinner_request(raw_text) or any(token in raw_text for token in ("晚上", "今晚", "喝酒", "小酌", "酒吧", "酒馆")):
            return now.hour >= 22
        return False

    def _same_calendar_day(self, left: datetime, right: datetime) -> bool:
        return left.date() == right.astimezone(left.tzinfo).date() if left.tzinfo else left.date() == right.date()

    def _same_tz(self, target: datetime, source: datetime) -> datetime:
        if target.tzinfo and source.tzinfo:
            return source.astimezone(target.tzinfo)
        return source

    def _has_dinner_request(self, raw_text: str) -> bool:
        if any(token in raw_text for token in ("晚饭", "晚餐", "晚上吃", "晚上我们想去吃", "晚上想去吃", *JAPANESE_CUISINE_TERMS, *BUFFET_TERMS)):
            return True
        dining_preference = extract_dining_preference(raw_text)
        return bool(dining_preference.get("explicit")) and "下午茶" not in raw_text

    def _has_meal_request(self, raw_text: str) -> bool:
        if self._has_dinner_request(raw_text):
            return True
        meal_terms = (
            "吃饭",
            "吃个饭",
            "吃点",
            "吃人均",
            "吃",
            "饭",
            "餐",
            "午饭",
            "午餐",
            "晚饭",
            "晚餐",
            "正餐",
            "人均",
        )
        if any(term in raw_text for term in meal_terms):
            return True
        return bool(extract_dining_preference(raw_text).get("explicit"))

    def _has_evening_request(self, raw_text: str) -> bool:
        return any(token in raw_text for token in ("今晚", "晚上", "晚些时候", "夜里", "夜晚"))

    def _deadline_before(self, raw_text: str, now: datetime) -> Optional[datetime]:
        if not any(token in raw_text for token in ("之前", "前", "回来", "回家", "到家", "结束", "准时")):
            return None
        mentions = self._time_mentions(raw_text, now)
        mention = self._mention_near_keywords(mentions, raw_text, ("回来", "回家", "到家", "结束", "前", "之前", "准时"), prefer_last=True)
        return mention or (mentions[-1] if mentions else None)

    def _time_mentions(self, raw_text: str, day_anchor: datetime) -> list[datetime]:
        matches = list(re.finditer(r"(?:(上午|中午|下午|晚上|晚|今晚|今天下午|今天晚上)\s*)?([0-2]?\d|[一二两三四五六七八九十])点(?:钟|半|([0-5]?\d)分?)?", raw_text))
        mentions: list[datetime] = []
        for match in matches:
            period, hour_text, minute_text = match.groups()
            parsed = self._time_from_match(raw_text, day_anchor, period or "", hour_text, minute_text, match.group(0))
            if parsed:
                mentions.append(parsed)
        return mentions

    def _mention_near_keywords(
        self,
        mentions: list[datetime],
        raw_text: str,
        keywords: tuple[str, ...],
        prefer_last: bool,
    ) -> Optional[datetime]:
        if not mentions:
            return None
        matches = list(re.finditer(r"(?:(上午|中午|下午|晚上|晚|今晚|今天下午|今天晚上)\s*)?([0-2]?\d|[一二两三四五六七八九十])点(?:钟|半|([0-5]?\d)分?)?", raw_text))
        candidates: list[tuple[int, datetime]] = []
        for index, match in enumerate(matches):
            if index >= len(mentions):
                continue
            left = max(0, match.start() - 10)
            right = min(len(raw_text), match.end() + 14)
            context = raw_text[left:right]
            if any(keyword in context for keyword in keywords):
                candidates.append((match.start(), mentions[index]))
        if candidates:
            return candidates[-1][1] if prefer_last else candidates[0][1]
        return None

    def _time_from_match(
        self,
        raw_text: str,
        day_anchor: datetime,
        period: str,
        hour_text: str,
        minute_text: Optional[str],
        matched_text: str,
    ) -> Optional[datetime]:
        hour = self._hour_value(hour_text)
        if hour is None:
            return None
        minute = 30 if "点半" in matched_text else int(minute_text or 0)
        if period in {"下午", "晚上", "晚", "今晚", "今天下午", "今天晚上"} and hour < 12:
            hour += 12
        if not period and hour <= 11 and any(token in raw_text for token in ("今晚", "晚上", "晚", "夜", "回家", "到家", "喝酒", "酒", "音乐")):
            hour += 12
        if period == "中午" and hour < 11:
            hour += 12
        return day_anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _hour_value(self, value: str) -> Optional[int]:
        if value.isdigit():
            return int(value)
        numerals = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        if value in numerals:
            return numerals[value]
        if value.startswith("十") and len(value) == 2 and value[1] in numerals:
            return 10 + numerals[value[1]]
        return None

    def _budget_pp(self, raw_text: str, scenario: str) -> Optional[float]:
        explicit_budget = extract_budget_max_per_person(raw_text)
        if explicit_budget is not None:
            return explicit_budget
        if "别太贵" in raw_text or "不贵" in raw_text:
            return 100.0
        if any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆")):
            return 180.0
        if any(token in raw_text for token in ("漂亮饭", "有氛围", "氛围感", "精致", "体面", "好一点")):
            return 300.0
        if any(token in raw_text for token in ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅")):
            return 160.0
        if any(token in raw_text for token in BUFFET_TERMS):
            return 240.0
        if "椰子鸡" in raw_text:
            return 180.0
        if any(token in raw_text for token in JAPANESE_CUISINE_TERMS):
            return 220.0
        if any(token in raw_text for token in ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉")):
            return 180.0
        dining_preference = extract_dining_preference(raw_text)
        if dining_preference.get("budget_max_per_person_hint"):
            inferred_budget = float(dining_preference["budget_max_per_person_hint"])
            if scenario == "family_parent_child":
                return max(inferred_budget, 220.0)
            return inferred_budget
        if scenario == "anniversary_emotion" and self._target_stop_count(raw_text):
            return 400.0
        if scenario == "anniversary_emotion":
            return 180.0
        if scenario == "family_parent_child":
            return 220.0
        if self._is_solo_mood_relief(raw_text, scenario):
            return 80.0
        return None

    def _budget_max(self, raw_text: str, scenario: str, party_size: int) -> Optional[float]:
        per_person = self._budget_pp(raw_text, scenario)
        return None if per_person is None else per_person * party_size

    def _budget_is_strict(self, raw_text: str) -> bool:
        if extract_budget_max_per_person(raw_text) is None:
            return False
        return any(token in raw_text for token in ("不超过", "不超", "不高于", "以内", "以下", "封顶", "上限", "控制在"))

    def _diet(self, raw_text: str, scenario: str) -> list[str]:
        preferences = []
        if any(token in raw_text for token in ("减脂", "低卡", "轻食", "清淡", "清淡一点", "晚饭清淡", "晚饭要清淡")):
            preferences.extend(["light_food", "light_meal"])
        if "减脂" in raw_text or "低卡" in raw_text:
            preferences.extend(["low_calorie", "healthy_light"])
        if scenario == "family_parent_child":
            preferences.append("family_friendly")
        return list(dict.fromkeys(preferences))

    def _activities(self, raw_text: str, scenario: str) -> list[str]:
        if scenario == "family_parent_child":
            values = ["child_friendly", "kid_safe", "rain_safe", "light", "low_queue"]
            if any(token in raw_text for token in AMUSEMENT_TERMS):
                values.append("amusement")
            return values
        if scenario == "friend_group":
            values = ["chat", "relaxed", "budget_sensitive", "group_ok"]
            if any(token in raw_text for token in ("下雨", "雨天", "下雨也能去")):
                values.extend(["rain_safe", "indoor"])
            if any(token in raw_text for token in ("逛商场", "商场", "购物中心")):
                values.append("mall_walk")
            if self._has_light_walk_request(raw_text):
                values.append("light_walk")
            if self._has_conversation_request(raw_text):
                values.extend(["conversation", "quiet"])
                if self._has_coffee_request(raw_text):
                    values.append("coffee")
                if self._has_post_meal_conversation(raw_text):
                    values.append("post_meal_conversation")
            if not negates_activity_type(raw_text, ("桌游", "棋牌", "狼人杀", "剧本杀", "KTV", "电竞", "游戏")) and any(token in raw_text for token in ("桌游", "棋牌", "狼人杀", "剧本杀")):
                values.extend(["board_game", "group_ok"])
            if not negates_activity_type(raw_text, KARAOKE_TERMS) and any(token in raw_text for token in KARAOKE_TERMS):
                values.extend(["karaoke", "group_ok", "indoor"])
            if not negates_activity_type(raw_text, GAME_TERMS) and any(token in raw_text for token in GAME_TERMS):
                values.extend(["esports", "group_ok", "indoor"])
            return list(dict.fromkeys(values))
        if scenario == "anniversary_emotion":
            values = ["quiet", "photo", "light_ritual", "date_friendly"]
            if self._has_light_walk_request(raw_text):
                values.append("light_walk")
            if any(token in raw_text for token in ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画")):
                values.extend(["hands_on", "craft"])
            if any(token in raw_text for token in ("漂亮饭", "有氛围", "氛围感", "精致", "体面", "好一点")):
                values.extend(["beautiful_dining", "quality_dining", "ambience_dining"])
            return list(dict.fromkeys(values))
        if scenario == "city_light_explore":
            return ["visitor_friendly", "host_guest", "showcase_local", "conversation", "photo", "light_walk", "quality_dining"]
        if self._is_solo_mood_relief(raw_text, scenario):
            values = ["quiet", "light_walk", "mood_relief", "nearby", "low_pressure", "low_queue"]
            alcohol_negated = any(token in raw_text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"))
            if not alcohol_negated and any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆")):
                values.extend(["alcohol", "light_drink"])
            if any(token in raw_text for token in ("音乐", "live", "Live", "爵士", "演出")):
                values.extend(["music", "acoustic_music"])
            if any(token in raw_text for token in ("咖啡", "咖啡店", "星巴克", "瑞幸", "M Stand", "Manner")):
                values.extend(["coffee", "quiet"])
            return list(dict.fromkeys(values))
        return ["light"]

    def _must_have(self, raw_text: str, scenario: str) -> list[str]:
        result = []
        if "别太远" in raw_text or "不远" in raw_text or "附近" in raw_text:
            result.append("nearby")
        if "金沙湖" in raw_text:
            result.append("area_jinshahu")
        elif "高教园区" in raw_text or "高教园" in raw_text:
            result.append("area_gaojiao")
        elif "下沙" in raw_text:
            result.append("area_xiasha")
        if "轻松" in raw_text:
            result.append("low_walking")
        if any(token in raw_text for token in ("路线简单", "路线要简单", "别折腾", "别太折腾", "少转场")):
            result.append("route_simple")
        if any(token in raw_text for token in ("不排队", "少排队", "低排队", "别排队", "不排长队")):
            result.append("low_queue")
        if any(token in raw_text for token in ("下雨", "雨天", "下雨也能去")):
            result.extend(["rain_safe", "indoor"])
        if any(token in raw_text for token in ("逛商场", "商场", "购物中心")):
            result.append("mall_walk")
        if self._has_light_walk_request(raw_text):
            result.append("light_walk")
        if self._has_conversation_request(raw_text):
            result.append("conversation")
        if self._has_post_meal_conversation(raw_text):
            result.append("post_meal_conversation")
        if self._has_restaurant_first_request(raw_text):
            result.append("restaurant_first_request")
        coffee_negated = self._has_coffee_negation(raw_text)
        if not coffee_negated and self._has_coffee_request(raw_text):
            result.append("coffee")
        if any(token in raw_text for token in ("安静", "不要太吵", "不太吵", "别太吵", "不吵")):
            result.append("quiet")
        if not negates_activity_type(raw_text, ("桌游", "棋牌", "狼人杀", "剧本杀", "KTV", "电竞", "游戏")) and any(token in raw_text for token in ("桌游", "棋牌", "狼人杀", "剧本杀")):
            result.extend(["board_game", "group_ok"])
        if not negates_activity_type(raw_text, KARAOKE_TERMS) and any(token in raw_text for token in KARAOKE_TERMS):
            result.extend(["karaoke", "group_ok", "indoor"])
        if not negates_activity_type(raw_text, GAME_TERMS) and any(token in raw_text for token in GAME_TERMS):
            result.extend(["esports", "group_ok", "indoor"])
        if "预算" in raw_text:
            result.append("budget_fit")
        if "正餐" in raw_text:
            result.extend(["proper_dining", "dinner"])
        if any(token in raw_text for token in AMUSEMENT_TERMS):
            result.append("amusement")
        if self._has_dinner_request(raw_text):
            result.append("dinner")
        if scenario == "anniversary_emotion" and any(token in raw_text for token in ("今晚", "晚上", "晚些时候", "夜里")):
            result.append("dinner")
        if any(token in raw_text for token in ("清淡", "轻食", "晚饭清淡", "晚饭要清淡", "清淡一点")):
            result.extend(["light_meal", "light_food"])
        if any(token in raw_text for token in ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅")):
            result.extend(["hotpot", "dinner"])
        if any(token in raw_text for token in BUFFET_TERMS):
            result.extend(["buffet", "dinner"])
        if any(token in raw_text for token in JAPANESE_CUISINE_TERMS):
            result.extend(["cuisine_japanese", "dinner"])
        if any(token in raw_text for token in SUSHI_TERMS):
            result.extend(["sushi", "cuisine_japanese", "dinner"])
        if any(token in raw_text for token in IZAKAYA_TERMS):
            result.extend(["izakaya", "cuisine_japanese", "dinner"])
        if any(token in raw_text for token in ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉")):
            result.extend(["bbq", "grill", "dinner"])
        dining_preference = extract_dining_preference(raw_text)
        if dining_preference.get("explicit"):
            for tag in dining_preference.get("normalized_tags") or []:
                if tag not in {"explicit_dining", "proper_dining", "quality_dining", "ambience_dining"}:
                    result.append(str(tag))
            result.append("dinner")
        if self._is_solo_mood_relief(raw_text, scenario):
            result.extend(["quiet", "low_pressure"])
        alcohol_negated = any(token in raw_text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"))
        if not alcohol_negated and any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆")):
            result.extend(["alcohol", "light_drink"])
        if any(token in raw_text for token in ("音乐", "live", "Live", "爵士", "演出")):
            result.extend(["music", "acoustic_music"])
        if scenario == "family_parent_child":
            result.extend(["child_friendly", "kid_safe", "family_time"])
        if scenario == "anniversary_emotion":
            result.append("thoughtful_but_low_key")
        if scenario == "city_light_explore":
            result.extend(["visitor_friendly", "host_guest", "route_simple", "showcase_local", "conversation"])
        if any(token in raw_text for token in ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画")):
            result.extend(["hands_on", "craft"])
        if any(token in raw_text for token in ("漂亮饭", "有氛围", "氛围感", "精致", "体面", "好一点")):
            result.extend(["beautiful_dining", "quality_dining", "ambience_dining"])
        return list(dict.fromkeys(result))

    def _has_coffee_request(self, raw_text: str) -> bool:
        return any(token in raw_text for token in COFFEE_TERMS)

    def _has_conversation_request(self, raw_text: str) -> bool:
        return any(token in raw_text for token in CONVERSATION_TERMS)

    def _has_light_walk_request(self, raw_text: str) -> bool:
        return any(token in raw_text for token in LIGHT_WALK_TERMS)

    def _has_coffee_negation(self, raw_text: str) -> bool:
        if "咖啡" not in raw_text:
            return False
        direct_phrases = (
            "不要咖啡",
            "别喝咖啡",
            "不喝咖啡",
            "不想喝咖啡",
            "不想再喝咖啡",
            "不安排咖啡",
            "别安排咖啡",
            "别给咖啡",
            "不用咖啡",
            "别用咖啡",
        )
        if any(token in raw_text for token in direct_phrases):
            return True
        return bool(
            re.search(r"(不要|别|不想|不喝|不安排|不用|别安排|别给)[^，。,.；;]{0,12}咖啡", raw_text)
            or re.search(r"咖啡[^，。,.；;]{0,8}(不要|别|不想|不喝|不安排|不用)", raw_text)
        )

    def _has_restaurant_first_request(self, raw_text: str) -> bool:
        if not self._has_dinner_request(raw_text):
            return False
        if any(token in raw_text for token in ("先吃", "先去吃", "先找地方吃", "先把饭吃了", "先吃饭", "先吃晚饭", "先吃晚餐")):
            return True
        activity_terms = (
            *KARAOKE_TERMS,
            "唱歌",
            "K歌",
            "散步",
            "走走",
            "逛逛",
            "转转",
            "消食",
            "看电影",
            "电影",
            "聊天",
            "坐着聊",
            "坐坐",
            "咖啡",
        )
        for meal_term in POST_MEAL_TERMS:
            meal_index = raw_text.find(meal_term)
            if meal_index < 0:
                continue
            if any(raw_text.find(term, meal_index + len(meal_term)) >= 0 for term in activity_terms):
                return True
        return self._has_post_meal_conversation(raw_text)

    def _has_post_meal_conversation(self, raw_text: str) -> bool:
        if any(token in raw_text for token in POST_MEAL_TERMS) and self._has_conversation_request(raw_text):
            return True
        dining_terms = (
            "吃饭",
            "晚饭",
            "晚餐",
            "正餐",
            *BUFFET_TERMS,
            "火锅",
            "烤肉",
            "烧烤",
            "烧肉",
            *JAPANESE_CUISINE_TERMS,
        )
        conversation_terms = tuple(token for token in CONVERSATION_TERMS if token != "聊") + ("聊",)
        for dining in dining_terms:
            dining_index = raw_text.find(dining)
            if dining_index < 0:
                continue
            for conversation in conversation_terms:
                conversation_index = raw_text.find(conversation, dining_index + len(dining))
                if conversation_index < 0:
                    continue
                bridge = raw_text[dining_index:conversation_index]
                if any(token in bridge for token in ("再", "然后", "之后", "后面", "接着", "吃完")):
                    return True
        return False

    def _must_not_have(self, raw_text: str, scenario: str) -> list[str]:
        result = []
        if "别太贵" in raw_text or "不贵" in raw_text:
            result.append("expensive")
        if "不想太夸张" in raw_text:
            result.append("overly_grand")
        if any(token in raw_text for token in ("漂亮饭", "有氛围", "氛围感", "精致", "体面", "好一点")):
            result.extend(["fast_food", "low_end_chain", "canteen_style"])
        if self._has_coffee_negation(raw_text):
            result.append("coffee")
        if any(token in raw_text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒")):
            result.extend(["alcohol", "light_drink"])
        if negates_activity_type(raw_text, ("桌游", "棋牌", "狼人杀", "剧本杀", "电竞")):
            result.extend(["board_game", "low_fit_activity"])
        if negates_activity_type(raw_text, KARAOKE_TERMS):
            result.extend(["karaoke", "low_fit_activity"])
        if any(token in raw_text for token in ("清淡", "轻食", "晚饭清淡", "晚饭要清淡", "清淡一点")) and not any(token in raw_text for token in ("火锅", "烤肉", "烧烤", "烧肉")):
            result.append("spicy_heavy")
        if scenario == "city_light_explore":
            result.extend(["strong_social", "long_queue", "low_fit_activity"])
        if scenario == "family_parent_child":
            result.extend(["strong_social", "long_queue", "low_fit_activity", "alcohol", "light_drink"])
        if self._is_solo_mood_relief(raw_text, scenario):
            result.extend(["strong_social", "high_pressure", "long_queue"])
        return list(dict.fromkeys(result))

    def _participants(self, user_id: str, scenario: str, party_size: int) -> list[Dict[str, Any]]:
        participants = [
            {
                "participant_id": "part_user_001",
                "role": "user",
                "display_name": user_id,
                "age": None,
                "constraints": [],
                "preference_tags": [],
            }
        ]
        if scenario == "family_parent_child":
            participants.extend(
                [
                    {
                        "participant_id": "part_spouse_001",
                        "role": "spouse",
                        "display_name": "老婆",
                        "age": None,
                        "constraints": ["diet_light"],
                        "preference_tags": ["light_food"],
                    },
                    {
                        "participant_id": "part_child_001",
                        "role": "child",
                        "display_name": "孩子",
                        "age": 5,
                        "constraints": ["child_friendly_required"],
                        "preference_tags": ["pet_friendly", "rain_safe"],
                    },
                ]
            )
        elif scenario == "anniversary_emotion":
            participants.append(
                {
                    "participant_id": "part_spouse_001",
                    "role": "spouse",
                    "display_name": "老婆",
                    "age": None,
                    "constraints": [],
                    "preference_tags": ["quiet_alone", "mood_relief"],
                }
            )
        elif scenario == "city_light_explore":
            participants.append(
                {
                    "participant_id": "part_family_001",
                    "role": "family_guest",
                    "display_name": "来访家人",
                    "age": None,
                    "constraints": ["visitor_friendly"],
                    "preference_tags": ["conversation", "showcase_local", "route_simple"],
                }
            )
        elif party_size > 1:
            for index in range(2, party_size + 1):
                participants.append(
                    {
                        "participant_id": f"part_friend_{index:03d}",
                        "role": "friend",
                        "display_name": f"朋友{index - 1}",
                        "age": None,
                        "constraints": [],
                        "preference_tags": ["relaxed"],
                    }
                )
        return participants[:party_size]

    def _explicit_notes(self, raw_text: str) -> list[str]:
        notes = []
        for token in ("别太远", "别太贵", "轻松", "减脂", "清淡", "晚饭", "晚餐", "不排长队", "5岁", "用心", "下午", "一个人", "散心", "失恋", "喝酒", "音乐", "回家", "纪念日", "不夸张", "预算", "女朋友", "游乐园", "嘉年华", "自助餐", "放题", "火锅", "日料", "日本料理", "寿司", "居酒屋", "烧鸟", "烤肉", "烧烤", "手工", "漂亮饭", "唱K", "KTV", "姐姐", "来下沙"):
            if token in raw_text:
                notes.append(token)
        return notes

    def _is_solo_mood_relief(self, raw_text: str, scenario: str) -> bool:
        if scenario != "fallback_unknown":
            return False
        return looks_solo_mood_relief(raw_text)

    def _user_location(self, body: Dict[str, Any]) -> Dict[str, Any]:
        value = body.get("user_location")
        if not isinstance(value, dict):
            return {"label": "杭州金沙湖", "area": "金沙湖"}
        label = str(value.get("label") or value.get("name") or "").strip()[:40] or "杭州金沙湖"
        area = str(value.get("area") or "").strip()
        result: Dict[str, Any] = {"label": label, "area": area or "金沙湖"}
        for key in ("lat", "lng"):
            try:
                if value.get(key) is not None:
                    result[key] = float(value[key])
            except (TypeError, ValueError):
                continue
        return result
