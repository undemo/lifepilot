from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from app.rules.intent_rules import looks_solo_mood_relief


@dataclass(frozen=True)
class TagDefinition:
    key: str
    display_label: str
    category: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    negative_keywords: tuple[str, ...] = ()
    user_visible: bool = True


SCENARIO_TAGS = {
    "city_light_explore",
    "family_parent_child",
    "friend_group",
    "anniversary_emotion",
    "fallback_unknown",
}

CONTROLLED_TAGS = {
    *SCENARIO_TAGS,
    "acoustic_music",
    "alcohol",
    "alone",
    "ambience_dining",
    "adult_family",
    "amusement",
    "beautiful_dining",
    "board_game",
    "bbq",
    "buffet",
    "budget_fit",
    "budget_sensitive",
    "child_friendly",
    "coffee",
    "conversation",
    "craft",
    "crayfish",
    "cuisine_japanese",
    "date_friendly",
    "dessert",
    "dinner",
    "esports",
    "explicit_dining",
    "family_time",
    "group_ok",
    "grill",
    "hands_on",
    "healthy_light",
    "host_guest",
    "hotpot",
    "indoor",
    "izakaya",
    "karaoke",
    "kid_safe",
    "lake_walk",
    "lamb",
    "light_drink",
    "light_dinner",
    "light_food",
    "light_meal",
    "light_ritual",
    "light_walk",
    "low_calorie",
    "low_key",
    "low_pressure",
    "low_queue",
    "mall_walk",
    "mood_relief",
    "music",
    "nearby",
    "photo",
    "photo_spot",
    "proper_dining",
    "quality_dining",
    "quiet",
    "quiet_dining",
    "quiet_restaurant",
    "rain_safe",
    "relaxed",
    "romantic",
    "route_simple",
    "showcase_local",
    "sibling",
    "spicy_heavy",
    "steak",
    "sushi",
    "thoughtful",
    "visiting_family",
    "visitor_friendly",
    "western_cuisine",
}

TAG_ALIASES = {
    "budget_conscious": "budget_sensitive",
    "budget_friendly": "budget_fit",
    "calm": "quiet",
    "couple": "date_friendly",
    "emotional_relief": "mood_relief",
    "leisure_walk": "light_walk",
    "location_preference": "nearby",
    "low_cost": "budget_sensitive",
    "low_wait": "low_queue",
    "mood_adjustment": "mood_relief",
    "not_crowded": "low_queue",
    "photo_friendly": "photo_spot",
    "proximity_preference": "nearby",
    "relaxed_mood": "relaxed",
    "return_home": "nearby",
    "romance": "romantic",
    "simple_route": "route_simple",
    "social_gathering": "friend_group",
    "temporal_reference": "nearby",
    "western": "western_cuisine",
}

AREA_KEYWORDS = {
    "金沙湖": "金沙湖",
    "金沙": "金沙湖",
    "高教园区": "高教园区",
    "高教园": "高教园区",
    "下沙": "下沙",
}

AREA_TO_MARKER = {
    "金沙湖": "area_jinshahu",
    "高教园区": "area_gaojiao",
    "下沙": "area_xiasha",
}

OPEN_TERM_PATTERNS = {
    "coffee": ("咖啡", "咖啡店", "星巴克", "瑞幸", "manner", "Manner"),
    "dessert": ("甜品", "蛋糕", "奶茶", "柠檬水", "茶", "蜜雪", "烘焙"),
    "music": ("音乐", "live", "Live", "爵士", "民谣", "演出"),
    "alcohol": ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧", "酒馆"),
    "photo": ("拍照", "合照", "出片", "照片"),
    "hands_on": ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画", "做点东西"),
    "craft": ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画"),
    "date_friendly": ("女朋友", "约会", "对象", "情侣"),
    "beautiful_dining": ("漂亮饭", "好看的饭", "有氛围", "氛围感", "精致点", "体面一点"),
    "quality_dining": ("漂亮饭", "品质", "好一点", "精致", "体面", "漂亮"),
    "visiting_family": ("姐姐", "我姐", "妹妹", "哥哥", "弟弟", "家人", "亲戚", "来找我玩"),
    "host_guest": ("来找我玩", "来下沙", "来杭州", "我安排", "招待"),
    "board_game": ("桌游", "棋牌", "狼人杀", "剧本杀"),
    "karaoke": ("唱K", "KTV", "ktv", "K歌", "麦颂", "量贩KTV", "自助KTV", "AI智慧KTV"),
    "esports": ("打游戏", "游戏", "电竞", "网咖", "网吧", "电玩", "PS5", "ps5", "Switch", "switch"),
    "amusement": ("游乐园", "儿童乐园", "乐园", "嘉年华", "童宇宙", "游艺"),
    "buffet": ("自助餐", "自助烤肉", "自助烧烤", "自助火锅", "自助小火锅", "放题", "海鲜自助", "烤肉自助", "烧烤自助"),
    "low_queue": ("不排队", "少排队", "低排队", "别排队", "不排长队"),
    "route_simple": ("路线简单", "别折腾", "别太折腾", "少转场", "不折腾"),
    "low_key": ("不夸张", "低调", "自然", "别太隆重"),
    "light_meal": ("清淡", "轻食", "低卡", "减脂"),
    "light_dinner": ("晚饭清淡", "晚饭要清淡", "晚餐清淡", "清淡一点", "清淡"),
    "dinner": ("晚饭", "晚餐", "晚上吃", "晚上我们想去吃"),
    "western_cuisine": ("西餐", "西式", "牛排", "意面", "披萨", "比萨", "LOFT"),
    "steak": ("牛排", "肋眼", "西冷", "菲力"),
    "lamb": ("羊排", "羊肉", "烤全羊", "羊肉串", "羊肉炉", "羊庄", "羊汤", "牛羊"),
    "healthy_light": ("减脂", "低卡", "轻食", "沙拉", "健康", "杂粮", "鸡胸"),
    "hotpot": ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅"),
    "crayfish": ("小龙虾", "龙虾", "虾尾", "麻小"),
    "cuisine_japanese": ("日料", "日式", "日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风", "会席", "日式咖喱", "回转寿司"),
    "sushi": ("寿司", "鮨", "刺身", "回转寿司"),
    "izakaya": ("居酒屋", "烧鸟"),
    "bbq": ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉"),
    "grill": ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉"),
}

DINING_TERM_TAGS = {
    "buffet": OPEN_TERM_PATTERNS["buffet"],
    "bbq": OPEN_TERM_PATTERNS["bbq"],
    "grill": OPEN_TERM_PATTERNS["grill"],
    "hotpot": OPEN_TERM_PATTERNS["hotpot"],
    "crayfish": OPEN_TERM_PATTERNS["crayfish"],
    "cuisine_japanese": OPEN_TERM_PATTERNS["cuisine_japanese"],
    "sushi": OPEN_TERM_PATTERNS["sushi"],
    "izakaya": OPEN_TERM_PATTERNS["izakaya"],
    "western_cuisine": OPEN_TERM_PATTERNS["western_cuisine"],
    "steak": OPEN_TERM_PATTERNS["steak"],
    "lamb": OPEN_TERM_PATTERNS["lamb"],
    "light_meal": (*OPEN_TERM_PATTERNS["light_meal"], "椰子鸡", "粥", "蒸菜", "蒸", "鱼", "顺德小馆"),
    "light_dinner": OPEN_TERM_PATTERNS["light_dinner"],
    "light_food": ("清淡", "轻食", "低卡", "减脂"),
    "healthy_light": OPEN_TERM_PATTERNS["healthy_light"],
}

DINING_MATCH_EXPANSIONS = {
    "buffet": ("自助餐", "自助烤肉", "自助烧烤", "自助火锅", "自助小火锅", "放题", "海鲜自助", "烤肉自助", "烧烤自助"),
    "bbq": ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "炭火", "烤全羊"),
    "grill": ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "炭火", "烤全羊"),
    "hotpot": ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅"),
    "crayfish": ("小龙虾", "龙虾", "虾尾", "麻小"),
    "cuisine_japanese": ("日料", "日式", "日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风", "会席", "料理"),
    "sushi": ("寿司", "鮨", "刺身", "回转寿司"),
    "izakaya": ("居酒屋", "烧鸟"),
    "western_cuisine": ("西餐", "西餐厅", "西式", "牛排", "意面", "披萨", "比萨", "LOFT", "扒房"),
    "steak": ("牛排", "肋眼", "西冷", "菲力"),
    "lamb": ("羊排", "羊肉", "烤全羊", "羊肉串", "羊肉炉", "羊庄", "羊汤", "牛羊", "内蒙"),
    "light_meal": ("清淡", "轻食", "低卡", "减脂", "沙拉", "健康", "杂粮", "鸡胸", "粥", "蒸", "汤", "鱼", "椰子鸡"),
    "light_food": ("清淡", "轻食", "低卡", "减脂", "沙拉", "健康", "杂粮", "鸡胸", "粥", "蒸", "汤", "鱼", "椰子鸡"),
    "healthy_light": ("清淡", "轻食", "低卡", "减脂", "沙拉", "健康", "杂粮", "鸡胸"),
}

DINING_GENERIC_TAGS = {
    "dinner",
    "explicit_dining",
    "proper_dining",
    "quality_dining",
    "ambience_dining",
    "beautiful_dining",
    "date_friendly",
    "romantic",
}

DINING_PROFILE_TAGS = {
    *DINING_GENERIC_TAGS,
    "buffet",
    "bbq",
    "grill",
    "hotpot",
    "crayfish",
    "cuisine_japanese",
    "sushi",
    "izakaya",
    "western_cuisine",
    "steak",
    "lamb",
    "light_meal",
    "light_dinner",
    "light_food",
    "healthy_light",
    "low_calorie",
}

DINING_BUDGET_HINTS = {
    "western_cuisine": 180.0,
    "steak": 220.0,
    "lamb": 180.0,
    "buffet": 240.0,
    "bbq": 180.0,
    "grill": 180.0,
    "hotpot": 160.0,
    "crayfish": 120.0,
    "cuisine_japanese": 220.0,
    "sushi": 220.0,
    "izakaya": 220.0,
    "light_meal": 110.0,
    "light_food": 110.0,
    "healthy_light": 110.0,
}


TAG_DEFINITIONS: Dict[str, TagDefinition] = {
    "family_parent_child": TagDefinition("family_parent_child", "家庭亲子", "scenario", keywords=("老婆孩子", "孩子", "亲子", "带娃", "5岁")),
    "friend_group": TagDefinition("friend_group", "朋友局", "scenario", keywords=("朋友", "室友", "同学", "聚会")),
    "anniversary_emotion": TagDefinition("anniversary_emotion", "约会/纪念日", "scenario", keywords=("纪念日", "生日", "约会", "用心", "仪式感")),
    "city_light_explore": TagDefinition("city_light_explore", "城市轻探索", "scenario", keywords=("来下沙", "来杭州", "找我玩", "招待")),
    "fallback_unknown": TagDefinition("fallback_unknown", "轻探索", "scenario", user_visible=False),
    "child_friendly": TagDefinition(
        "child_friendly",
        "亲子友好",
        "audience",
        keywords=("亲子", "儿童", "童宇宙", "乐园", "嘉年华", "手作", "手工", "陶艺", "拼豆", "油画", "烘焙"),
    ),
    "kid_safe": TagDefinition(
        "kid_safe",
        "适合孩子",
        "audience",
        keywords=("亲子", "儿童", "童宇宙", "乐园", "嘉年华", "手作", "手工", "陶艺", "拼豆", "油画", "烘焙"),
    ),
    "family_time": TagDefinition("family_time", "家庭时间", "scenario", keywords=("家庭", "亲子", "孩子", "嘉年华")),
    "family_friendly": TagDefinition("family_friendly", "家庭友好", "audience", keywords=("家庭", "亲子", "孩子", "儿童")),
    "adult_family": TagDefinition("adult_family", "成年家人", "audience", keywords=OPEN_TERM_PATTERNS["visiting_family"]),
    "visiting_family": TagDefinition("visiting_family", "家人来访", "scenario", keywords=OPEN_TERM_PATTERNS["visiting_family"]),
    "sibling": TagDefinition("sibling", "兄弟姐妹", "audience", keywords=("姐姐", "我姐", "妹妹", "哥哥", "弟弟")),
    "host_guest": TagDefinition("host_guest", "招待友好", "scenario", keywords=OPEN_TERM_PATTERNS["host_guest"]),
    "visitor_friendly": TagDefinition("visitor_friendly", "到达方便", "scenario", keywords=("来下沙", "来杭州", "金沙湖", "下沙")),
    "showcase_local": TagDefinition("showcase_local", "下沙代表性", "scenario", keywords=("金沙湖", "湖畔", "公园", "剧院", "茶空间", "下沙")),
    "date_friendly": TagDefinition("date_friendly", "适合约会", "relation", keywords=OPEN_TERM_PATTERNS["date_friendly"]),
    "romantic": TagDefinition("romantic", "浪漫氛围", "relation", keywords=("纪念日", "情侣", "约会", "浪漫", "仪式感")),
    "thoughtful": TagDefinition("thoughtful", "用心安排", "relation", keywords=("用心", "纪念日", "仪式感")),
    "low_key": TagDefinition("low_key", "不夸张", "style", keywords=OPEN_TERM_PATTERNS["low_key"]),
    "light_ritual": TagDefinition("light_ritual", "轻仪式感", "style", keywords=("纪念日", "仪式感", "用心", "不夸张")),
    "group_ok": TagDefinition("group_ok", "多人友好", "audience", keywords=("朋友", "室友", "聚会", "多人")),
    "alone": TagDefinition("alone", "适合独处", "audience", keywords=("一个人", "自己", "独处")),
    "mood_relief": TagDefinition("mood_relief", "放松情绪", "scenario", keywords=("散心", "难受", "失恋", "不开心", "放松")),
    "relaxed": TagDefinition("relaxed", "轻松一点", "tempo", keywords=("轻松", "舒服", "不累", "别太赶")),
    "low_pressure": TagDefinition("low_pressure", "低压力", "tempo", keywords=("低压力", "散心", "不累", "别太赶")),
    "quiet": TagDefinition("quiet", "安静放松", "ambience", keywords=("安静", "不要太吵", "不太吵", "别太吵", "不吵")),
    "quiet_alone": TagDefinition("quiet_alone", "安静独处", "ambience", keywords=("一个人", "安静", "独处")),
    "quiet_stay": TagDefinition("quiet_stay", "安静停留", "ambience", keywords=("安静", "坐着聊", "咖啡", "甜品")),
    "conversation": TagDefinition("conversation", "适合聊天", "ambience", keywords=("聊天", "好聊天", "坐着聊", "聊一聊")),
    "nearby": TagDefinition("nearby", "距离较近", "route", keywords=("附近", "别太远", "不远", "就近")),
    "route_simple": TagDefinition("route_simple", "路线简单", "route", keywords=OPEN_TERM_PATTERNS["route_simple"]),
    "low_queue": TagDefinition("low_queue", "少排队", "status", keywords=OPEN_TERM_PATTERNS["low_queue"]),
    "rain_safe": TagDefinition("rain_safe", "雨天可去", "weather", keywords=("下雨", "雨天", "室内", "避雨")),
    "indoor": TagDefinition("indoor", "室内可去", "weather", keywords=("室内", "雨天", "避雨")),
    "mall_walk": TagDefinition("mall_walk", "商场走走", "activity", keywords=("逛商场", "商场", "购物中心")),
    "lake_walk": TagDefinition("lake_walk", "湖边散步", "activity", keywords=("金沙湖", "湖畔", "散步")),
    "light_walk": TagDefinition("light_walk", "轻松走走", "activity", keywords=("散步", "走走", "逛逛", "公园")),
    "photo": TagDefinition("photo", "适合拍照", "activity", keywords=OPEN_TERM_PATTERNS["photo"]),
    "photo_spot": TagDefinition("photo_spot", "适合拍照", "activity", keywords=OPEN_TERM_PATTERNS["photo"]),
    "photo_friendly": TagDefinition("photo_friendly", "适合拍照", "activity", keywords=OPEN_TERM_PATTERNS["photo"]),
    "hands_on": TagDefinition("hands_on", "手作体验", "activity", keywords=("DIY", "diy", "手作", "手工", "手工坊", "陶艺", "拼豆", "油画", "烘焙DIY")),
    "craft": TagDefinition("craft", "手工", "activity", keywords=("DIY", "diy", "手作", "手工", "手工坊", "陶艺", "拼豆", "油画", "烘焙DIY")),
    "amusement": TagDefinition("amusement", "游乐体验", "activity", keywords=OPEN_TERM_PATTERNS["amusement"]),
    "board_game": TagDefinition("board_game", "桌游棋牌", "activity", keywords=OPEN_TERM_PATTERNS["board_game"]),
    "karaoke": TagDefinition("karaoke", "唱歌娱乐", "activity", keywords=OPEN_TERM_PATTERNS["karaoke"]),
    "music": TagDefinition("music", "有音乐", "activity", keywords=OPEN_TERM_PATTERNS["music"]),
    "acoustic_music": TagDefinition("acoustic_music", "轻音乐", "activity", keywords=OPEN_TERM_PATTERNS["music"]),
    "esports": TagDefinition("esports", "电竞游戏", "activity", keywords=OPEN_TERM_PATTERNS["esports"]),
    "low_fit_activity": TagDefinition(
        "low_fit_activity",
        "低适配活动",
        "risk",
        keywords=("棋牌", "麻将", "KTV", "电竞", "网咖", "台球", "健身", "游泳", "PS5", "VR", "剧本杀", "桌游"),
        user_visible=False,
    ),
    "spicy_heavy": TagDefinition(
        "spicy_heavy",
        "重口味",
        "risk",
        keywords=("火锅", "毛肚", "麻辣", "烧烤", "烤肉", "干锅", "地锅", "鸡锅", "锅鸡", "美蛙", "酸辣", "酸菜鱼", "重庆", "烙锅", "串串", "烤鱼", "湖南菜"),
        user_visible=False,
    ),
    "strong_social": TagDefinition("strong_social", "强社交", "risk", keywords=("电竞", "KTV", "桌游", "剧本杀"), user_visible=False),
    "alcohol": TagDefinition("alcohol", "可小酌", "food", keywords=("酒吧", "酒馆", "小酒馆", "酒咖", "精酿", "清吧", "Lounge", "LOUNGE", "Bar", "BAR", "bar")),
    "light_drink": TagDefinition("light_drink", "轻饮", "food", keywords=("酒吧", "酒馆", "小酒馆", "酒咖", "精酿", "清吧", "Lounge", "LOUNGE", "Bar", "BAR", "bar")),
    "coffee": TagDefinition("coffee", "咖啡", "food", keywords=OPEN_TERM_PATTERNS["coffee"]),
    "dessert": TagDefinition("dessert", "甜品", "food", keywords=OPEN_TERM_PATTERNS["dessert"]),
    "dinner": TagDefinition("dinner", "晚餐", "food", keywords=OPEN_TERM_PATTERNS["dinner"]),
    "explicit_dining": TagDefinition("explicit_dining", "明确餐饮", "food", user_visible=False),
    "proper_dining": TagDefinition("proper_dining", "正式用餐", "food", keywords=("餐厅", "料理", "火锅", "烤肉", "烧肉", "烧烤", "小馆", "饭店", "酒楼")),
    "quality_dining": TagDefinition("quality_dining", "品质正餐", "food", keywords=OPEN_TERM_PATTERNS["quality_dining"]),
    "ambience_dining": TagDefinition("ambience_dining", "有氛围", "food", keywords=OPEN_TERM_PATTERNS["beautiful_dining"]),
    "beautiful_dining": TagDefinition("beautiful_dining", "漂亮饭", "food", keywords=OPEN_TERM_PATTERNS["beautiful_dining"]),
    "quiet_dining": TagDefinition("quiet_dining", "安静餐厅", "food", keywords=("安静餐厅", "不吵", "适合聊天")),
    "quiet_restaurant": TagDefinition("quiet_restaurant", "安静餐厅", "food", keywords=("安静餐厅", "不吵", "适合聊天")),
    "buffet": TagDefinition("buffet", "自助餐", "food", keywords=OPEN_TERM_PATTERNS["buffet"]),
    "hotpot": TagDefinition("hotpot", "火锅", "food", keywords=OPEN_TERM_PATTERNS["hotpot"]),
    "crayfish": TagDefinition("crayfish", "小龙虾", "food", keywords=DINING_MATCH_EXPANSIONS["crayfish"]),
    "cuisine_japanese": TagDefinition("cuisine_japanese", "日料", "food", keywords=OPEN_TERM_PATTERNS["cuisine_japanese"]),
    "sushi": TagDefinition("sushi", "寿司", "food", keywords=OPEN_TERM_PATTERNS["sushi"]),
    "izakaya": TagDefinition("izakaya", "居酒屋", "food", keywords=OPEN_TERM_PATTERNS["izakaya"]),
    "bbq": TagDefinition("bbq", "烤肉", "food", keywords=("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "日式烧肉", "韩式烤肉", "自助烤肉", "自助烧烤")),
    "grill": TagDefinition("grill", "烤肉", "food", keywords=("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "日式烧肉", "韩式烤肉", "自助烤肉", "自助烧烤")),
    "western_cuisine": TagDefinition("western_cuisine", "西餐", "food", keywords=("西餐", "西式", "牛排", "意面", "披萨", "比萨", "LOFT", "扒房")),
    "steak": TagDefinition("steak", "牛排", "food", keywords=OPEN_TERM_PATTERNS["steak"]),
    "lamb": TagDefinition("lamb", "羊肉", "food", keywords=OPEN_TERM_PATTERNS["lamb"]),
    "healthy_light": TagDefinition("healthy_light", "低负担", "food", keywords=OPEN_TERM_PATTERNS["healthy_light"]),
    "light_meal": TagDefinition("light_meal", "清淡餐", "food", keywords=DINING_MATCH_EXPANSIONS["light_meal"]),
    "light_dinner": TagDefinition("light_dinner", "清淡晚餐", "food", keywords=OPEN_TERM_PATTERNS["light_dinner"]),
    "light_food": TagDefinition("light_food", "清淡低负担", "food", keywords=DINING_MATCH_EXPANSIONS["light_food"]),
    "low_calorie": TagDefinition("low_calorie", "清淡低负担", "food", keywords=("减脂", "低卡", "低脂", "轻食")),
    "budget_fit": TagDefinition("budget_fit", "预算友好", "budget", keywords=("预算", "别太贵", "不贵", "人均")),
    "budget_sensitive": TagDefinition("budget_sensitive", "预算友好", "budget", keywords=("预算", "别太贵", "不贵", "人均")),
    "restaurant": TagDefinition("restaurant", "餐厅", "raw_poi_tag", keywords=("餐厅", "饭店", "料理")),
    "activity": TagDefinition("activity", "活动", "raw_poi_tag", keywords=("活动", "玩", "体验")),
    "food": TagDefinition("food", "餐饮", "raw_poi_tag", keywords=("餐饮", "吃", "饭")),
    "lake": TagDefinition("lake", "湖边", "place", keywords=("湖畔", "金沙湖", "公园", "茶空间", "沙滩")),
    "park": TagDefinition("park", "公园", "place", keywords=("公园", "湖畔", "散步")),
    "low_end_chain": TagDefinition("low_end_chain", "低仪式感连锁", "risk", keywords=("米村", "拌饭", "麦当劳", "肯德基", "德克士", "老乡鸡", "老娘舅", "萨莉亚", "必胜客", "达美乐", "麻辣烫"), user_visible=False),
}

for _tag_key in CONTROLLED_TAGS:
    TAG_DEFINITIONS.setdefault(
        _tag_key,
        TagDefinition(_tag_key, _tag_key, "unclassified", user_visible=False),
    )


def get_tag_definition(tag: str) -> Optional[TagDefinition]:
    key = controlled_tag(tag) or str(tag or "").strip().lower().replace("-", "_").replace(" ", "_")
    return TAG_DEFINITIONS.get(key)


def get_display_label(tag: str) -> str:
    definition = get_tag_definition(tag)
    return definition.display_label if definition else str(tag or "")


def get_tag_keywords(tag: str) -> tuple[str, ...]:
    definition = get_tag_definition(tag)
    return definition.keywords if definition else ()


def has_any_tag_keyword(text: str, tag: str) -> bool:
    haystack = str(text or "")
    return any(keyword and keyword in haystack for keyword in get_tag_keywords(tag))


def get_user_visible_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for tag in tags or []:
        definition = get_tag_definition(str(tag))
        if definition and definition.user_visible and definition.key not in result:
            result.append(definition.key)
    return result


def get_display_labels(tags: list[str] | tuple[str, ...]) -> list[str]:
    labels: list[str] = []
    for tag in get_user_visible_tags(tags):
        label = get_display_label(tag)
        if label and label not in labels:
            labels.append(label)
    return labels


def controlled_tag(value: Any) -> Optional[str]:
    tag = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    tag = TAG_ALIASES.get(tag, tag)
    return tag if tag in CONTROLLED_TAGS else None


def normalize_tags(values: Iterable[Any]) -> List[str]:
    tags = []
    for value in values:
        tag = controlled_tag(value)
        if tag:
            tags.append(tag)
    return sorted(set(tags))


def extract_dining_preference(raw_text: str, base_tags: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
    """Extract an open-ended dining target without enumerating every dish.

    The returned profile is internal recommendation context. Public APIs still
    expose only PlanContract fields and user-visible tags.
    """

    text = raw_text or ""
    phrases = _dining_phrases(text)
    base_dining_tags = set(normalize_tags(base_tags or [])) & DINING_PROFILE_TAGS
    matched_tags = _dining_tags_from_text(text)

    for phrase in phrases:
        matched_tags.update(_dining_tags_from_text(phrase))
        if "自助" in phrase or "放题" in phrase:
            matched_tags.add("buffet")
        if "烤" in phrase or "炭" in phrase:
            matched_tags.update({"bbq", "grill"})
        if "羊" in phrase:
            matched_tags.add("lamb")
        if "牛排" in phrase:
            matched_tags.update({"western_cuisine", "steak"})
        if any(token in phrase for token in ("清淡", "减脂", "低卡", "轻食", "沙拉")):
            matched_tags.update({"light_food", "light_meal", "healthy_light"})

    if "light_meal" in matched_tags:
        matched_tags.add("light_food")

    has_dining_cue = bool(phrases or any(token in text for token in ("吃", "晚饭", "晚餐", "正餐", "餐厅", "饭店")))
    dietary_explicit = bool(matched_tags & {"light_food", "light_meal", "light_dinner", "healthy_light"}) and has_dining_cue
    explicit = bool(phrases or dietary_explicit or matched_tags & {"buffet", "hotpot", "crayfish", "cuisine_japanese", "sushi", "izakaya", "bbq", "grill", "western_cuisine", "steak", "lamb"})
    if explicit:
        matched_tags.update({"explicit_dining", "proper_dining"})
        if not any(token in text for token in ("早餐", "早饭", "午饭", "午餐", "中午")):
            matched_tags.add("dinner")

    positive_terms = set(phrases)
    for tag in matched_tags:
        positive_terms.update(DINING_MATCH_EXPANSIONS.get(tag, ()))
    for phrase in phrases:
        if len(phrase) >= 3:
            positive_terms.add(phrase)
        if phrase.startswith("烤") and len(phrase) > 2:
            positive_terms.add(phrase[1:])

    normalized_tags = base_dining_tags | matched_tags
    dining_tags = sorted((normalized_tags & CONTROLLED_TAGS & DINING_PROFILE_TAGS) - SCENARIO_TAGS)
    specific_tags = sorted((matched_tags & CONTROLLED_TAGS & DINING_PROFILE_TAGS) - DINING_GENERIC_TAGS)
    budget_hint = extract_budget_max_per_person(text) or _dining_budget_hint(specific_tags)
    if dietary_explicit and not phrases:
        mode = "diet"
    elif "buffet" in matched_tags:
        mode = "format"
    elif matched_tags & {"western_cuisine", "cuisine_japanese", "sushi", "izakaya", "hotpot"}:
        mode = "cuisine"
    elif matched_tags & {"crayfish", "lamb", "steak", "bbq", "grill"}:
        mode = "dish"
    elif explicit:
        mode = "dining"
    else:
        mode = None

    return {
        "explicit": explicit,
        "mode": mode,
        "raw_terms": sorted(term for term in positive_terms if term in phrases),
        "positive_terms": sorted(term for term in positive_terms if len(term) >= 2),
        "normalized_tags": dining_tags,
        "specific_tags": specific_tags,
        "budget_max_per_person_hint": budget_hint,
        "match_available": False,
    }


def area_from_text(raw_text: str, user_location: Optional[Dict[str, Any]] = None) -> Optional[str]:
    for token, area in AREA_KEYWORDS.items():
        if token in raw_text:
            return area
    if user_location:
        area = str(user_location.get("area") or "").strip()
        if area in AREA_TO_MARKER:
            return area
    return None


def area_marker(area: Optional[str]) -> Optional[str]:
    return AREA_TO_MARKER.get(area or "")


def normalize_intent_profile(
    raw_text: str,
    scenario: str,
    *,
    llm_tags: Optional[Iterable[Any]] = None,
    user_location: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = raw_text or ""
    tags = set(normalize_tags(llm_tags or []))
    tags.add(scenario if scenario in SCENARIO_TAGS else "fallback_unknown")
    raw_terms = _open_terms(text)
    alcohol_negated = _negates_alcohol(text)
    board_game_negated = negates_activity_type(text, ("桌游", "棋牌", "狼人杀", "剧本杀", "电竞"))
    karaoke_negated = negates_activity_type(text, OPEN_TERM_PATTERNS["karaoke"])
    if alcohol_negated:
        raw_terms = [term for term in raw_terms if term not in {"alcohol", "light_drink"}]
    if board_game_negated:
        raw_terms = [term for term in raw_terms if term != "board_game"]
    if karaoke_negated:
        raw_terms = [term for term in raw_terms if term != "karaoke"]

    for term in raw_terms:
        mapped = controlled_tag(term)
        if mapped:
            tags.add(mapped)

    if any(token in text for token in ("附近", "别太远", "不远", "就近")):
        tags.update({"nearby", "route_simple"})
    if any(token in text for token in ("路线简单", "路线要简单", "别折腾", "别太折腾", "少转场")):
        tags.update({"route_simple"})
    if any(token in text for token in ("轻松", "舒服", "不累", "别太赶")):
        tags.update({"relaxed", "low_pressure"})
    if any(token in text for token in ("不排队", "少排队", "低排队", "别排队", "不排长队")):
        tags.update({"low_queue"})
    if any(token in text for token in ("下雨", "雨天", "下雨也能去")):
        tags.update({"rain_safe", "indoor"})
    if any(token in text for token in ("逛商场", "商场", "购物中心")):
        tags.update({"mall_walk"})
    if any(token in text for token in ("咖啡", "聊天", "好聊天", "坐着聊", "聊一聊", "聊")):
        tags.update({"coffee", "conversation"})
    if any(token in text for token in ("安静", "不要太吵", "不太吵", "别太吵", "不吵")):
        tags.update({"quiet"})
    if not board_game_negated and any(token in text for token in ("桌游", "棋牌", "狼人杀", "剧本杀")):
        tags.update({"board_game", "group_ok"})
    if not karaoke_negated and any(token in text for token in OPEN_TERM_PATTERNS["karaoke"]):
        tags.update({"karaoke", "group_ok", "indoor"})
    if not board_game_negated and any(token in text for token in OPEN_TERM_PATTERNS["esports"]):
        tags.update({"esports", "group_ok", "indoor"})
    if "正餐" in text:
        tags.update({"proper_dining", "dinner"})
    if any(token in text for token in OPEN_TERM_PATTERNS["amusement"]):
        tags.update({"amusement", "child_friendly", "kid_safe", "family_time"})
    if any(token in text for token in ("别太贵", "不贵", "预算", "人均")):
        tags.update({"budget_sensitive", "budget_fit"})
    if any(token in text for token in ("晚饭", "晚餐", "晚上吃", "晚上我们想去吃")):
        tags.update({"dinner"})
    if any(token in text for token in ("清淡", "轻食", "低卡", "减脂", "椰子鸡", "粥", "蒸菜", "顺德小馆")):
        tags.update({"light_food", "light_meal", "light_dinner"})
    if any(token in text for token in ("火锅", "小火锅", "毛肚", "涮锅", "酸汤火锅")):
        tags.update({"hotpot", "proper_dining", "dinner"})
    if any(token in text for token in OPEN_TERM_PATTERNS["crayfish"]):
        tags.update({"crayfish", "proper_dining", "dinner"})
    if any(token in text for token in ("日料", "日式", "日本料理", "寿司", "刺身", "居酒屋", "烧鸟", "鮨", "和风", "会席", "日式咖喱", "回转寿司")):
        tags.update({"cuisine_japanese", "proper_dining", "dinner"})
    if any(token in text for token in ("寿司", "鮨", "刺身", "回转寿司")):
        tags.update({"sushi", "cuisine_japanese", "proper_dining", "dinner"})
    if any(token in text for token in ("居酒屋", "烧鸟")):
        tags.update({"izakaya", "cuisine_japanese", "proper_dining", "dinner"})
    if any(token in text for token in ("烤肉", "烧烤", "烧肉", "炭烤", "烤串", "烤吧", "自助烤肉", "日式烧肉", "韩式烤肉")):
        tags.update({"bbq", "grill", "proper_dining", "dinner"})
    if any(token in text for token in OPEN_TERM_PATTERNS["buffet"]):
        tags.update({"buffet", "proper_dining", "dinner"})
    if any(token in text for token in ("女朋友", "约会", "情侣", "对象")):
        tags.update({"date_friendly", "romantic", "thoughtful", "route_simple"})
    if any(token in text for token in ("漂亮饭", "有氛围", "氛围感", "精致", "体面", "好一点")):
        tags.update({"beautiful_dining", "quality_dining", "ambience_dining", "proper_dining"})
    if any(token in text for token in ("手工", "手作", "DIY", "diy", "陶艺", "拼豆", "油画")):
        tags.update({"hands_on", "craft", "indoor"})
    if any(token in text for token in ("姐姐", "我姐", "妹妹", "哥哥", "弟弟", "爸妈", "家人", "亲戚", "来下沙", "来找我玩")):
        tags.update({"visiting_family", "adult_family", "sibling", "host_guest", "visitor_friendly", "showcase_local", "conversation"})

    dining_preference = extract_dining_preference(text, tags)
    tags.update(dining_preference["normalized_tags"])

    if scenario == "anniversary_emotion":
        tags.update({"date_friendly", "low_key", "thoughtful", "quiet_dining", "light_ritual", "photo_spot", "route_simple", "ambience_dining"})
    elif scenario == "family_parent_child":
        tags.update({"child_friendly", "family_time", "indoor", "rain_safe", "low_queue", "light_food", "kid_safe"})
    elif scenario == "friend_group":
        tags.update({"group_ok", "budget_sensitive", "relaxed", "low_queue", "route_simple"})
    elif scenario == "city_light_explore":
        tags.update({"visitor_friendly", "host_guest", "showcase_local", "conversation", "relaxed", "route_simple", "photo_spot", "quality_dining"})
    elif scenario == "fallback_unknown" and looks_solo_mood_relief(text):
        tags.update({"alone", "mood_relief", "quiet", "low_pressure", "light_walk", "nearby", "low_queue"})

    if alcohol_negated:
        tags.difference_update({"alcohol", "light_drink"})
    if board_game_negated:
        tags.discard("board_game")
    if karaoke_negated:
        tags.discard("karaoke")

    area = area_from_text(text, user_location)
    weights = {
        "intent_match": 42,
        "route": 26 if "route_simple" in tags or "nearby" in tags else 18,
        "status": 24 if "low_queue" in tags else 18,
        "budget": 20 if "budget_sensitive" in tags or "budget_fit" in tags else 12,
        "area": 18 if area else 8,
        "rating": 8,
        "novelty": 8,
    }
    axes = {
        "scenario": scenario,
        "area": area,
        "tempo": sorted(tags & {"relaxed", "low_pressure", "route_simple", "light_walk"}),
        "relation": sorted(tags & {"date_friendly", "family_time", "group_ok", "alone", "thoughtful", "host_guest", "visiting_family", "adult_family", "sibling"}),
        "place": sorted(tags & {"indoor", "rain_safe", "lake_walk", "mall_walk", "photo_spot", "quiet", "hands_on", "craft", "karaoke", "amusement", "showcase_local"}),
        "consumption": sorted(tags & {"budget_fit", "budget_sensitive", "light_food", "light_meal", "light_dinner", "healthy_light", "coffee", "dessert", "alcohol", "buffet", "hotpot", "cuisine_japanese", "sushi", "izakaya", "bbq", "grill", "western_cuisine", "steak", "lamb", "beautiful_dining", "quality_dining", "ambience_dining", "proper_dining"}),
    }
    return {
        "normalized_tags": sorted(tags & CONTROLLED_TAGS),
        "raw_terms": raw_terms,
        "tag_axes": axes,
        "weights": weights,
        "dining_preference": dining_preference,
    }


def _open_terms(raw_text: str) -> List[str]:
    terms = []
    for tag, patterns in OPEN_TERM_PATTERNS.items():
        if any(pattern in raw_text for pattern in patterns):
            terms.append(tag)
    for match in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,30}", raw_text):
        term = controlled_tag(match)
        if term:
            terms.append(term)
    return sorted(set(terms))


def _negates_alcohol(text: str) -> bool:
    return any(token in text for token in ("不喝酒", "不要喝酒", "别喝酒", "不想喝酒", "不安排酒"))


def negates_activity_type(text: str, terms: Iterable[str]) -> bool:
    joined = "|".join(re.escape(term) for term in terms if term)
    if not joined:
        return False
    return bool(re.search(rf"(?:不要|别安排|别给|不用|不想|不安排|别用)[^，。,.!?；;]{{0,10}}(?:{joined})", text or ""))


def _dining_tags_from_text(text: str) -> set[str]:
    tags: set[str] = set()
    for tag, patterns in DINING_TERM_TAGS.items():
        if any(pattern in text for pattern in patterns):
            tags.add(tag)
    if "烤" in text and any(token in text for token in ("肉", "羊", "牛", "排", "串")):
        tags.update({"bbq", "grill"})
    return tags


def _dining_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    patterns = [
        r"(?:想|想去|想要|准备|打算|要|去)?吃(?:点|些|个|一顿|一下)?([^，。,.!?；;]{1,18})",
        r"(?:晚饭|晚餐|正餐)(?:想|要|安排|吃)?([^，。,.!?；;]{1,14})",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            phrase = _clean_dining_phrase(match)
            if phrase:
                phrases.append(phrase)
    if any(token in text for token in ("减脂", "低卡", "轻食", "清淡")) and any(token in text for token in ("吃", "晚饭", "晚餐", "正餐", "安排")):
        for token in ("减脂", "低卡", "轻食", "清淡"):
            if token in text:
                phrases.append(token)
    return sorted(set(phrases))


def _clean_dining_phrase(value: str) -> str:
    phrase = str(value or "").strip()
    phrase = re.split(r"(?:然后|顺便|但是|但|活动|行程|路线|帮我|安排|你来|之前|以后|再|，|。|,|\\.)", phrase)[0]
    phrase = re.sub(r"^(和|跟)?(女朋友|对象|老婆|男朋友|朋友|家人|孩子|我|我们|一起|去|想|要|来|点|些)+", "", phrase)
    phrase = re.sub(r"(吧|呀|啊|哦|哈|一点|一些|一下|的|餐厅|店|地方|附近|周末|这周末|今天|明天|晚上|晚饭|晚餐)$", "", phrase)
    phrase = phrase.strip(" 的了吧呀啊哦哈")
    if len(phrase) < 2:
        return ""
    if any(token in phrase for token in ("女朋友", "对象", "活动", "安排")):
        return ""
    return phrase[:12]


def _dining_budget_hint(tags: Iterable[str]) -> Optional[float]:
    hints = [DINING_BUDGET_HINTS[tag] for tag in tags if tag in DINING_BUDGET_HINTS]
    if not hints:
        return None
    return max(hints)


def extract_budget_max_per_person(raw_text: str) -> Optional[float]:
    text = str(raw_text or "")
    patterns = (
        r"(?:人均|每人|每个人|一人)[^0-9一二两三四五六七八九十百]{0,10}(?:不超过|不超|不高于|以内|以下|上限|控制在|少于|低于|约|左右|大概|差不多)?\s*([0-9]{1,4}(?:\.\d+)?|[一二两三四五六七八九十百]{1,4})\s*(?:元|块)?",
        r"(?:预算|饭钱|餐费|吃饭)[^0-9一二两三四五六七八九十百]{0,10}(?:人均|每人|每个人)?[^0-9一二两三四五六七八九十百]{0,10}(?:不超过|不超|不高于|以内|以下|上限|控制在|少于|低于|约|左右|大概|差不多)?\s*([0-9]{1,4}(?:\.\d+)?|[一二两三四五六七八九十百]{1,4})\s*(?:元|块)?",
        r"([0-9]{1,4}(?:\.\d+)?|[一二两三四五六七八九十百]{1,4})\s*(?:元|块)?\s*(?:以内|以下|封顶)[^，。,.!?；;]{0,8}(?:人均|每人|每个人|饭|餐)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if _budget_number_is_stop_count(text, match.end(1)):
            continue
        value = _budget_number(match.group(1))
        if value and 1 <= value <= 3000:
            return float(value)
    return None


def _budget_number_is_stop_count(text: str, end: int) -> bool:
    after = text[end : end + 16]
    number = r"(?:[0-9]{1,4}(?:\.\d+)?|[一二两三四五六七八九十百]{1,4})"
    return bool(re.match(rf"\s*(?:[-~到至]\s*{number}\s*)?(?:个)?(?:活动|地点|节点|项目|去处|地方|站)", after))


def _budget_number(value: str) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    numerals = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10.0
    if text == "百":
        return 100.0
    if "百" in text:
        left, _, right = text.partition("百")
        hundreds = numerals.get(left, 1 if not left else 0)
        remainder = _budget_number(right) if right else 0
        return float(hundreds * 100 + (remainder or 0))
    if "十" in text:
        left, _, right = text.partition("十")
        tens = numerals.get(left, 1 if not left else 0)
        ones = numerals.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    if text in numerals:
        return float(numerals[text])
    return None
