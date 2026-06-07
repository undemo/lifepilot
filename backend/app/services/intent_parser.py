import re
from typing import Any, Dict, Optional

from app.core.constants import TraceEventType
from app.rules.intent_rules import looks_solo_mood_relief
from app.rules.recommendation_taxonomy import CONTROLLED_TAGS, negates_activity_type, normalize_intent_profile, normalize_tags
from app.services.llm_client import LLMClient
from app.services.logging_service import LoggingService


P0_SCENARIOS = {"family_parent_child", "friend_group", "anniversary_emotion"}
SUPPORTED_SCENARIOS = P0_SCENARIOS | {"city_light_explore", "fallback_unknown"}
SOLO_MOOD_TAGS = {"alone", "mood_relief", "quiet", "nearby", "low_pressure", "light_walk"}
KARAOKE_TERMS = ("唱K", "KTV", "ktv", "K歌", "麦颂", "量贩KTV", "自助KTV", "AI智慧KTV")
GAME_TERMS = ("打游戏", "游戏", "电竞", "网咖", "网吧", "电玩", "PS5", "ps5", "Switch", "switch")
LIGHT_WALK_TERMS = ("散步", "走走", "逛逛", "转转", "消食", "溜达")


class IntentParser:
    def __init__(self, logging_service: LoggingService, llm_client: Optional[LLMClient] = None) -> None:
        self.logging_service = logging_service
        self.llm_client = llm_client

    def parse(self, trace_id: str, raw_text: str, scenario_hint: Optional[str] = None) -> Dict[str, Any]:
        llm_intent = self._llm_intent(trace_id, raw_text, scenario_hint)
        if self._looks_solo_mood_relief(raw_text):
            scenario = "fallback_unknown"
            llm_intent = None
        else:
            scenario = self._rule_corrected_scenario(raw_text, scenario_hint, llm_intent)
        llm_tags = self._safe_tags(llm_intent.get("intent_tags")) if llm_intent else []
        profile = normalize_intent_profile(raw_text, scenario, llm_tags=llm_tags)
        rule_tags = self._tags(scenario, raw_text)
        activity_dining_summary = self._activity_dining_summary(raw_text, scenario, profile)
        explicit_dining_summary = self._explicit_dining_summary(raw_text, profile)
        user_goal = {
            "raw_text": raw_text,
            "scenario": scenario,
            "goal_summary": activity_dining_summary
            or explicit_dining_summary
            or (self._safe_text(llm_intent.get("goal_summary"), 80) if llm_intent else self._summary(scenario, raw_text)),
            "intent_tags": self._merge_tags(rule_tags, profile["normalized_tags"]),
            "emotion_goal": self._safe_optional_text(llm_intent.get("emotion_goal"), 60) if llm_intent else self._emotion_goal(scenario, raw_text),
            "source": "user_input",
            "confidence": self._safe_confidence(llm_intent.get("confidence")) if llm_intent else (0.93 if scenario in P0_SCENARIOS else 0.86 if scenario == "city_light_explore" else 0.62),
        }
        if not user_goal["intent_tags"]:
            user_goal["intent_tags"] = self._tags(scenario, raw_text)
        if self._is_solo_mood_relief(raw_text, scenario):
            user_goal["intent_tags"] = sorted(set(user_goal["intent_tags"]) | SOLO_MOOD_TAGS | set(self._drink_music_tags(raw_text)))
            user_goal["emotion_goal"] = user_goal["emotion_goal"] or "一个人放松、散心、低压力"
            user_goal["goal_summary"] = self._solo_mood_summary(raw_text)
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "IntentParser",
            {
                "user_visible_message": f"已识别为{scenario}场景。",
                "scenario": scenario,
                "intent_tags": user_goal["intent_tags"],
                "confidence": user_goal["confidence"],
            },
        )
        return user_goal

    def _llm_intent(self, trace_id: str, raw_text: str, scenario_hint: Optional[str]) -> Optional[Dict[str, Any]]:
        if not self.llm_client:
            return None
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是LifePilot的受控意图理解模块。只输出JSON对象。"
                    "你只能做目标理解、场景初判、约束语义标签和用户可读摘要。"
                    "必须把用户明说的硬偏好保留下来：喝酒/小酌必须包含alcohol和light_drink；"
                    "音乐/演出必须包含music；纪念日/约会必须包含date_friendly、low_key、quiet_dining、route_simple。"
                    "用户明说自助餐/放题必须包含buffet和dinner；"
                    "用户明说火锅必须包含hotpot和dinner；明说日料/日本料理/寿司/居酒屋必须包含cuisine_japanese和dinner；明说烤肉/烧烤必须包含bbq、grill和dinner；"
                    "用户明说唱K/KTV必须包含karaoke、group_ok和indoor；用户明说打游戏/电竞/网咖必须包含esports、group_ok和indoor；"
                    "明说西餐/牛排必须包含western_cuisine和dinner；明说羊排/羊肉必须包含lamb；明说晚饭/晚餐必须包含dinner；明说清淡/减脂/低卡必须包含light_food、light_meal和healthy_light。"
                    "如果用户是一个人情绪低落或想散心，不要误判成朋友局或亲子。"
                    "禁止判断餐厅余位、票务、路线、天气、执行成功；禁止输出Prompt、推理链或API Key。"
                ),
                user_prompt=(
                    "根据用户输入生成JSON，字段固定为："
                    "scenario: family_parent_child | friend_group | anniversary_emotion | city_light_explore | fallback_unknown；"
                    "goal_summary: 30到60字中文摘要；"
                    f"intent_tags: 3到10个英文snake_case标签，只能从{sorted(CONTROLLED_TAGS)}中选择；"
                    "emotion_goal: 字符串或null；confidence: 0到1。"
                    "不要输出POI名称，不要编造地点，不要把快餐/棋牌/电竞/咖啡当成亲子、纪念日或喝酒的默认答案。"
                    f"scenario_hint={scenario_hint or 'none'}。用户输入：{raw_text}"
                ),
                temperature=0.2,
                max_tokens=800,
            )
            scenario = self._valid_scenario(data.get("scenario"))
            if not scenario:
                return None
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "LLMIntentAdapter",
                {
                    "user_visible_message": "已使用受控LLM辅助理解目标。",
                    "scenario": scenario,
                    "confidence": self._safe_confidence(data.get("confidence")),
                },
                visible_to_user=False,
            )
            return data
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "LLMIntentAdapter",
                {
                    "error_code": "INTERNAL_ERROR",
                    "message": f"LLM intent fallback: {exc.__class__.__name__}",
                },
                level="warning",
                visible_to_user=False,
            )
            return None

    def _scenario(self, raw_text: str, scenario_hint: Optional[str]) -> str:
        if scenario_hint in P0_SCENARIOS:
            return scenario_hint
        text = raw_text.lower()
        if any(token in raw_text for token in ("纪念日", "结婚", "周年")):
            return "anniversary_emotion"
        if any(token in raw_text for token in ("女朋友", "约会", "情侣", "对象")):
            return "anniversary_emotion"
        if any(token in raw_text for token in ("姐姐", "我姐", "妹妹", "哥哥", "弟弟", "爸妈", "家人来", "亲戚", "来下沙", "来找我玩")):
            return "city_light_explore"
        if any(token in raw_text for token in ("朋友", "同学", "4个人", "四个人")):
            return "friend_group"
        if any(token in raw_text for token in (*KARAOKE_TERMS, *GAME_TERMS)) and not looks_solo_mood_relief(raw_text):
            return "friend_group"
        if any(token in raw_text for token in ("孩子", "亲子", "老婆孩子", "小朋友")):
            return "family_parent_child"
        if "anniversary" in text:
            return "anniversary_emotion"
        return "fallback_unknown"

    def _rule_corrected_scenario(
        self,
        raw_text: str,
        scenario_hint: Optional[str],
        llm_intent: Optional[Dict[str, Any]],
    ) -> str:
        rule_scenario = self._scenario(raw_text, scenario_hint)
        if rule_scenario in P0_SCENARIOS:
            return rule_scenario
        if llm_intent:
            return self._valid_scenario(llm_intent.get("scenario")) or "fallback_unknown"
        return rule_scenario

    def _summary(self, scenario: str, raw_text: str = "") -> str:
        if scenario == "family_parent_child":
            return "安排一段离家不远、兼顾孩子体验和低负担饮食的家庭出行时间线。"
        if scenario == "friend_group":
            return "安排一段不远、不贵、轻松聊天的朋友局出行时间线。"
        if scenario == "anniversary_emotion":
            if any(token in raw_text for token in ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画")):
                return "安排一段适合约会的手作体验，再接一顿有氛围但不夸张的漂亮饭。"
            if any(token in raw_text for token in ("女朋友", "约会", "情侣", "对象")):
                return "安排一段自然、有氛围、不尴尬的约会时间线。"
            return "安排一段自然、不夸张、有轻仪式感的纪念日约会流程。"
        if scenario == "city_light_explore":
            return "安排一段招待家人来下沙玩的轻松行程，兼顾代表性、好聊天和不折腾。"
        if scenario == "fallback_unknown":
            return "安排一个人下午低压力散心的短时轻探索路线，少排队、短转场，可中途结束。"
        return "将用户目标整理成一段可验证、可执行的生活时间线。"

    def _tags(self, scenario: str, raw_text: str) -> list[str]:
        tags = [scenario]
        if "别太远" in raw_text or "不远" in raw_text or "附近" in raw_text:
            tags.append("nearby")
        if "别太贵" in raw_text or "不贵" in raw_text:
            tags.append("budget_sensitive")
        if "轻松" in raw_text:
            tags.append("relaxed")
        if any(token in raw_text for token in ("路线简单", "路线要简单", "别折腾", "别太折腾", "少转场")):
            tags.append("route_simple")
        if any(token in raw_text for token in ("下雨", "雨天", "下雨也能去")):
            tags.extend(["rain_safe", "indoor"])
        if any(token in raw_text for token in ("逛商场", "商场", "购物中心")):
            tags.append("mall_walk")
        if any(token in raw_text for token in ("咖啡", "聊天", "好聊天", "坐着聊", "聊一聊", "聊")):
            tags.extend(["coffee", "conversation"])
        if any(token in raw_text for token in ("安静", "不要太吵", "不太吵", "别太吵", "不吵")):
            tags.append("quiet")
        if not negates_activity_type(raw_text, ("桌游", "棋牌", "狼人杀", "剧本杀", "KTV", "电竞", "游戏")) and any(token in raw_text for token in ("桌游", "棋牌", "狼人杀", "剧本杀")):
            tags.extend(["board_game", "group_ok"])
        if not negates_activity_type(raw_text, KARAOKE_TERMS) and any(token in raw_text for token in KARAOKE_TERMS):
            tags.extend(["karaoke", "group_ok", "indoor"])
        if not negates_activity_type(raw_text, GAME_TERMS) and any(token in raw_text for token in GAME_TERMS):
            tags.extend(["esports", "group_ok", "indoor"])
        if "正餐" in raw_text:
            tags.extend(["proper_dining", "dinner"])
        if "预算" in raw_text:
            tags.extend(["budget_fit", "budget_sensitive"])
        if "减脂" in raw_text or "低卡" in raw_text:
            tags.extend(["light_food", "light_meal", "healthy_light"])
        if any(token in raw_text for token in ("清淡", "轻食", "晚饭清淡", "晚饭要清淡", "清淡一点")):
            tags.extend(["light_food", "light_meal", "light_dinner"])
        if any(token in raw_text for token in ("晚饭", "晚餐", "晚上吃", "晚上我们想去吃")):
            tags.append("dinner")
        if scenario == "anniversary_emotion" and any(token in raw_text for token in ("今晚", "晚上", "晚些时候", "夜里")):
            tags.append("dinner")
        if any(token in raw_text for token in ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅")):
            tags.extend(["hotpot", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("自助餐", "自助烤肉", "自助烧烤", "自助火锅", "自助小火锅", "放题", "海鲜自助", "烤肉自助", "烧烤自助")):
            tags.extend(["buffet", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("日料", "日式", "日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风", "会席", "日式咖喱", "回转寿司")):
            tags.extend(["cuisine_japanese", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("寿司", "鮨", "刺身", "回转寿司")):
            tags.extend(["sushi", "cuisine_japanese", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("居酒屋", "烧鸟")):
            tags.extend(["izakaya", "cuisine_japanese", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉")):
            tags.extend(["bbq", "grill", "proper_dining", "dinner"])
        if any(token in raw_text for token in ("不排队", "少排队", "低排队", "别排队", "不排长队")):
            tags.append("low_queue")
        if any(token in raw_text for token in ("游乐园", "儿童乐园", "乐园", "嘉年华", "童宇宙", "游艺")):
            tags.extend(["amusement", "child_friendly", "kid_safe", "family_time"])
        if any(token in raw_text for token in ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画")):
            tags.extend(["hands_on", "craft", "indoor"])
        if any(token in raw_text for token in ("女朋友", "约会", "情侣", "对象")):
            tags.extend(["date_friendly", "romantic", "thoughtful"])
        if any(token in raw_text for token in ("漂亮饭", "有氛围", "氛围感", "有点氛围", "想有点氛围", "精致", "体面", "好一点")):
            tags.extend(["beautiful_dining", "quality_dining", "ambience_dining"])
        if any(token in raw_text for token in ("姐姐", "我姐", "妹妹", "哥哥", "弟弟", "爸妈", "家人来", "亲戚", "来找我玩")):
            tags.extend(["visiting_family", "host_guest", "visitor_friendly", "showcase_local", "conversation"])
        if self._is_solo_mood_relief(raw_text, scenario):
            tags.extend(SOLO_MOOD_TAGS)
            tags.extend(self._drink_music_tags(raw_text))
        if scenario == "anniversary_emotion":
            tags.extend(["light_ritual", "quiet_restaurant"])
        if scenario == "family_parent_child":
            tags.extend(["child_friendly", "kid_safe", "family_time"])
        if scenario == "city_light_explore":
            tags.extend(["visitor_friendly", "host_guest", "showcase_local", "route_simple", "quality_dining"])
        return sorted(set(tags))

    def _explicit_dining_summary(self, raw_text: str, profile: Dict[str, Any]) -> Optional[str]:
        dining_preference = profile.get("dining_preference") or {}
        if not dining_preference.get("explicit"):
            return None
        raw_terms = [str(term).strip() for term in dining_preference.get("raw_terms") or [] if str(term).strip()]
        target = raw_terms[0] if raw_terms else "这顿饭"
        day = ""
        if any(token in raw_text for token in ("周六", "星期六", "礼拜六")):
            day = "周六"
        elif any(token in raw_text for token in ("周日", "星期日", "星期天", "礼拜日", "礼拜天")):
            day = "周日"
        elif any(token in raw_text for token in ("周末", "本周末", "这周末")):
            day = "周末"
        return f"安排{day}一顿以{target}为主的用餐计划，优先匹配口味、排队和转场可控的餐厅。"

    def _activity_dining_summary(self, raw_text: str, scenario: str, profile: Dict[str, Any]) -> Optional[str]:
        dining_preference = profile.get("dining_preference") or {}
        if not dining_preference.get("explicit") or not self._has_activity_request(raw_text):
            return None
        if scenario == "family_parent_child":
            dining_label = self._dining_summary_label(dining_preference)
            queue_label = "、少排队" if "low_queue" in set(profile.get("normalized_tags") or []) or "排队" in raw_text else ""
            return f"安排一段离家不远的亲子下午活动，并把晚饭收束到{dining_label}{queue_label}的家庭正餐。"
        return None

    def _dining_summary_label(self, dining_preference: Dict[str, Any]) -> str:
        tags = set(str(tag) for tag in dining_preference.get("specific_tags") or [])
        if tags & {"light_meal", "light_food", "light_dinner", "healthy_light", "low_calorie"}:
            return "清淡低负担"
        if "buffet" in tags:
            return "自助餐"
        if "hotpot" in tags:
            return "火锅"
        if tags & {"bbq", "grill"}:
            return "烤肉"
        if tags & {"cuisine_japanese", "sushi", "izakaya"}:
            return "日料"
        if tags & {"western_cuisine", "steak"}:
            return "西餐"
        if "lamb" in tags:
            return "羊肉"
        if "crayfish" in tags:
            return "小龙虾"
        raw_terms = [str(term).strip() for term in dining_preference.get("raw_terms") or [] if str(term).strip()]
        return raw_terms[0] if raw_terms else "合适"

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
            "溜一圈",
            "公园",
            "景点",
        )
        if any(term in raw_text for term in activity_terms):
            return True
        return bool(re.search(r"玩\s*(?:几个|[0-9一二两三四五六七八九十]+)\s*(?:小?时|钟头)", raw_text))

    def _emotion_goal(self, scenario: str, raw_text: str) -> Optional[str]:
        if scenario == "anniversary_emotion":
            return "让对方觉得被重视，但不过度尴尬"
        if self._is_solo_mood_relief(raw_text, scenario):
            return "一个人放松、散心、低压力"
        if "用心" in raw_text:
            return "让同行者觉得被照顾"
        if scenario == "city_light_explore":
            return "让来访家人觉得被认真招待，同时路线轻松"
        return None

    def _drink_music_tags(self, raw_text: str) -> list[str]:
        tags = []
        alcohol_negated = any(token in raw_text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"))
        if not alcohol_negated and any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆")):
            tags.extend(["alcohol", "light_drink"])
        if any(token in raw_text for token in ("音乐", "live", "Live", "爵士", "演出")):
            tags.extend(["music", "acoustic_music"])
        return tags

    def _solo_mood_summary(self, raw_text: str) -> str:
        alcohol_negated = any(token in raw_text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"))
        wants_drink = not alcohol_negated and any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆"))
        wants_music = any(token in raw_text for token in ("音乐", "live", "Live", "爵士", "演出"))
        has_deadline = any(token in raw_text for token in ("回家", "到家", "回来", "之前", "前", "准时"))
        if wants_drink and wants_music and has_deadline:
            return "先找个能安静喝一杯的地方缓一缓，再去有轻音乐的空间散心，按时回家收住。"
        if wants_drink and wants_music:
            return "先找个能安静喝一杯的地方缓一缓，再去有轻音乐的空间散心。"
        if wants_drink and has_deadline:
            return "找个能安静喝一杯的地方缓一缓，控制节奏，按时回家收住。"
        if wants_drink:
            return "找个能安静喝一杯的地方缓一缓，少转场、低压力。"
        return "一个人低压力散心的短时轻探索路线，少排队、短转场，可中途结束。"

    def _valid_scenario(self, value: Any) -> Optional[str]:
        scenario = str(value or "").strip()
        if scenario in SUPPORTED_SCENARIOS:
            return scenario
        return None

    def _safe_text(self, value: Any, limit: int) -> str:
        text = str(value or "").strip()
        return text[:limit] if text else "将用户目标整理成一段可验证、可执行的生活时间线。"

    def _safe_optional_text(self, value: Any, limit: int) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text[:limit] if text else None

    def _safe_tags(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return normalize_tags(value)[:10]

    def _merge_tags(self, rule_tags: list[str], llm_tags: list[str]) -> list[str]:
        allowed = CONTROLLED_TAGS | P0_SCENARIOS | {"fallback_unknown"}
        merged = []
        for tag in [*rule_tags, *llm_tags]:
            if tag in allowed and tag not in merged:
                merged.append(tag)
        priority = [
            "alcohol",
            "light_drink",
            "music",
            "acoustic_music",
            "buffet",
            "hotpot",
            "cuisine_japanese",
            "sushi",
            "izakaya",
            "bbq",
            "grill",
            "western_cuisine",
            "steak",
            "lamb",
            "dinner",
            "light_dinner",
            "light_meal",
            "light_food",
            "healthy_light",
            "explicit_dining",
            "budget_fit",
            "budget_sensitive",
            "ambience_dining",
            "anniversary_emotion",
            "date_friendly",
            "quiet_dining",
            "low_key",
            "thoughtful",
            "route_simple",
            "mood_relief",
            "alone",
            "nearby",
            "low_pressure",
            "low_queue",
            "rain_safe",
            "indoor",
            "mall_walk",
            "conversation",
            "coffee",
            "esports",
            "child_friendly",
            "kid_safe",
            "family_time",
            "karaoke",
            "board_game",
            "group_ok",
            "proper_dining",
            "amusement",
        ]
        ordered = [tag for tag in priority if tag in merged]
        ordered.extend(tag for tag in merged if tag not in ordered)
        return ordered[:12]

    def _is_solo_mood_relief(self, raw_text: str, scenario: str) -> bool:
        if scenario != "fallback_unknown":
            return False
        return self._looks_solo_mood_relief(raw_text)

    def _looks_solo_mood_relief(self, raw_text: str) -> bool:
        return looks_solo_mood_relief(raw_text)

    def _safe_confidence(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.72
        return max(0.0, min(1.0, number))
