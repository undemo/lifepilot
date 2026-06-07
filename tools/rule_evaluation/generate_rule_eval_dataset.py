#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tools" / "rule_evaluation" / "rule_eval_dataset.json"
VERSION = "2026-05-24"


AREAS = {
    "金沙湖": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
    "下沙": {"label": "杭州下沙龙湖天街", "area": "下沙", "lat": 30.310, "lng": 120.329},
    "高教园区": {"label": "杭州高教园区", "area": "高教园区", "lat": 30.315, "lng": 120.355},
}


DINING_TAGS = {
    "自助餐": ["buffet"],
    "自助烤肉": ["buffet", "bbq", "grill"],
    "清淡晚饭": ["light_meal", "light_food"],
    "减脂轻食": ["light_meal", "light_food", "healthy_light"],
    "椰子鸡": ["light_meal", "light_food"],
    "火锅": ["hotpot"],
    "烤肉": ["bbq", "grill"],
    "日料": ["cuisine_japanese"],
    "西餐": ["western_cuisine"],
    "寿司": ["cuisine_japanese", "sushi"],
    "居酒屋": ["cuisine_japanese", "izakaya"],
    "牛排": ["western_cuisine", "steak"],
    "烤羊排": ["lamb", "bbq", "grill"],
    "漂亮饭": ["beautiful_dining", "quality_dining", "ambience_dining"],
}


def case(
    cases: List[Dict[str, Any]],
    group: str,
    input_text: str,
    *,
    expected_scenario: str,
    party_size: int,
    must_have_tags: Optional[List[str]] = None,
    activity_should_match_any: Optional[List[str]] = None,
    restaurant_should_match_any: Optional[List[str]] = None,
    should_exclude_terms: Optional[List[str]] = None,
    user_area: str = "金沙湖",
    preferred_start_time: Optional[str] = None,
    preferred_end_time: Optional[str] = None,
    timeline_order: Optional[str] = None,
    difficulty: str = "medium",
    notes: str = "",
) -> None:
    case_id = f"rule_eval_{len(cases) + 1:03d}"
    body: Dict[str, Any] = {
        "input_text": input_text,
        "use_memory": False,
        "user_location": AREAS[user_area],
    }
    if preferred_start_time:
        body["preferred_start_time"] = preferred_start_time
    if preferred_end_time:
        body["preferred_end_time"] = preferred_end_time
    cases.append(
        {
            "case_id": case_id,
            "group": group,
            "difficulty": difficulty,
            "request_body": body,
            "expected": {
                "scenario": expected_scenario,
                "party_size": party_size,
                "must_have_tags": must_have_tags or [],
                "activity_should_match_any": activity_should_match_any or [],
                "restaurant_should_match_any": restaurant_should_match_any or [],
                "timeline_order": timeline_order or ("dinner_last" if (must_have_tags and "dinner" in must_have_tags) else "flexible"),
                "should_exclude_terms": should_exclude_terms or [],
            },
            "evaluation_notes": notes,
        }
    )


def dining_tags(name: str) -> List[str]:
    tags = list(DINING_TAGS[name])
    if name not in {"漂亮饭"}:
        tags.append("dinner")
    return tags


def build_family_cases(cases: List[Dict[str, Any]]) -> None:
    activities = [
        ("去游乐园玩一会儿", ["amusement"], "游乐园要落到亲子游乐/嘉年华，不应退化为电竞或普通商场。"),
        ("去嘉年华或者儿童乐园", ["amusement"], "嘉年华/儿童乐园是显式活动锚点。"),
        ("做一次手工DIY", ["hands_on", "craft"], "手作需求应命中手工、DIY、陶艺等。"),
        ("找室内亲子活动", ["child_friendly", "kid_safe"], "室内亲子活动不能出现棋牌、酒吧、KTV。"),
        ("孩子5岁，不排长队", ["child_friendly", "kid_safe", "low_queue"], "低排队和儿童安全优先。"),
    ]
    meals = ["自助餐", "自助烤肉", "清淡晚饭", "减脂轻食", "椰子鸡", "火锅", "烤肉", "日料", "西餐"]
    for activity_text, activity_tags, note in activities:
        for meal in meals:
            case(
                cases,
                "family_parent_child",
                f"这周末想和老婆孩子{activity_text}，然后吃一顿{meal}，别太远。",
                expected_scenario="family_parent_child",
                party_size=3,
                must_have_tags=[*activity_tags, *dining_tags(meal)],
                activity_should_match_any=activity_tags,
                restaurant_should_match_any=DINING_TAGS[meal],
                should_exclude_terms=["电竞", "棋牌", "酒吧", "KTV"],
                difficulty="hard" if meal in {"自助餐", "自助烤肉"} else "medium",
                notes=note,
            )


def build_date_cases(cases: List[Dict[str, Any]]) -> None:
    dining_targets = ["火锅", "日料", "寿司", "居酒屋", "烤肉", "自助餐", "西餐", "牛排", "烤羊排", "清淡晚饭"]
    modifiers = [
        ("下午活动你来安排", ["date_friendly"]),
        ("路线别太折腾", ["route_simple"]),
        ("预算适中", ["budget_fit"]),
        ("想有点氛围", ["ambience_dining"]),
        ("不想太夸张", ["low_key"]),
    ]
    for dining in dining_targets:
        for modifier, extra_tags in modifiers:
            case(
                cases,
                "date_dining_anchor",
                f"这周末想和女朋友出去放松一下，{modifier}，晚上想吃{dining}。",
                expected_scenario="anniversary_emotion",
                party_size=2,
                must_have_tags=[*extra_tags, *dining_tags(dining), "date_friendly"],
                restaurant_should_match_any=DINING_TAGS[dining],
                should_exclude_terms=["棋牌", "电竞", "快餐", "茶空间替代正餐", "咖啡替代正餐"],
                difficulty="hard" if dining in {"自助餐", "烤羊排", "清淡晚饭"} else "medium",
            )


def build_friend_cases(cases: List[Dict[str, Any]]) -> None:
    activities = [
        ("四个人想桌游聊天", ["board_game", "group_ok"]),
        ("四个人想唱K", ["karaoke", "group_ok"]),
        ("四个人想逛商场顺便吃饭", ["group_ok", "mall_walk"]),
        ("四个人想找地方喝咖啡聊天", ["coffee", "conversation"]),
        ("四个人想吃自助餐再找地方坐坐", ["buffet", "group_ok"]),
        ("四个人想吃烧烤，别太贵", ["bbq", "grill", "budget_sensitive"]),
    ]
    constraints = [
        ("别太远", ["nearby", "route_simple"], "金沙湖"),
        ("别太贵", ["budget_sensitive"], "下沙"),
        ("下雨也能去", ["rain_safe", "indoor"], "下沙"),
        ("不想排长队", ["low_queue"], "金沙湖"),
        ("晚上十点前结束", [], "高教园区"),
    ]
    for activity_text, activity_tags in activities:
        for suffix, constraint_tags, area in constraints:
            meal_tags = [tag for tag in activity_tags if tag in {"buffet", "bbq", "grill"}]
            case(
                cases,
                "friend_group",
                f"今天下午和朋友出去玩，{activity_text}，{suffix}。",
                expected_scenario="friend_group",
                party_size=4,
                must_have_tags=[*activity_tags, *constraint_tags],
                activity_should_match_any=[tag for tag in activity_tags if tag not in {"buffet", "bbq", "grill", "budget_sensitive"}],
                restaurant_should_match_any=meal_tags,
                user_area=area,
                should_exclude_terms=["高价", "长队"],
                difficulty="medium",
            )


def build_solo_cases(cases: List[Dict[str, Any]]) -> None:
    moods = ["有点不开心", "最近很累", "失恋了", "想一个人放松", "心情很烦", "想低压力散心"]
    targets = [
        ("喝点酒", ["alcohol", "light_drink"]),
        ("找有音乐的地方坐坐", ["music", "acoustic_music"]),
        ("去金沙湖附近走走", ["light_walk", "nearby"]),
        ("找安静咖啡店待一会儿", ["coffee", "quiet"]),
        ("晚上十点前到家", []),
    ]
    for mood in moods:
        for target, target_tags in targets:
            case(
                cases,
                "solo_mood_relief",
                f"我{mood}，想一个人{target}，别太折腾。",
                expected_scenario="fallback_unknown",
                party_size=1,
                must_have_tags=["alone", "mood_relief", "low_pressure", *target_tags],
                activity_should_match_any=[tag for tag in target_tags if tag in {"music", "acoustic_music", "light_walk", "nearby", "coffee", "quiet"}],
                restaurant_should_match_any=[tag for tag in target_tags if tag in {"alcohol", "light_drink", "coffee"}],
                should_exclude_terms=["亲子", "多人团建", "强社交"],
                preferred_end_time="2026-05-24T22:00:00+08:00" if "十点" in target else None,
                difficulty="hard" if target_tags else "medium",
            )


def build_host_cases(cases: List[Dict[str, Any]]) -> None:
    guests = ["我姐", "爸妈", "哥哥", "亲戚", "妹妹"]
    goals = [
        ("来下沙找我玩，想有代表性一点", ["host_guest", "showcase_local"], []),
        ("想去金沙湖附近逛逛再吃饭", ["host_guest", "showcase_local", "route_simple"], []),
        ("想吃一顿体面但不端着的正餐", ["host_guest", "quality_dining"], ["quality_dining", "proper_dining"]),
        ("想找好聊天的地方，不要太吵", ["conversation", "quiet"], []),
        ("想吃自助餐，路线别太折腾", ["buffet", "route_simple"], ["buffet"]),
    ]
    for guest in guests:
        for goal, tags, restaurant_tags in goals:
            case(
                cases,
                "city_light_explore",
                f"这周末{guest}{goal}，帮我安排一下。",
                expected_scenario="city_light_explore",
                party_size=2,
                must_have_tags=tags,
                restaurant_should_match_any=restaurant_tags,
                should_exclude_terms=["棋牌", "电竞", "健身", "低价快餐", "奶茶替代正餐"],
                user_area="下沙" if "下沙" in goal else "金沙湖",
                difficulty="medium",
            )


def build_edge_cases(cases: List[Dict[str, Any]]) -> None:
    specs: List[Dict[str, Any]] = [
        {
            "text": "老婆孩子想去游乐园，但孩子怕吵，晚饭想清淡一点，别排长队。",
            "scenario": "family_parent_child",
            "party": 3,
            "tags": ["amusement", "child_friendly", "low_queue", "light_meal"],
            "activity": ["amusement"],
            "restaurant": ["light_meal", "light_food"],
            "exclude": ["电竞", "酒吧", "麻辣", "烧烤"],
        },
        {
            "text": "想和女朋友吃自助餐，不要给我普通包子面馆，也不要咖啡当正餐。",
            "scenario": "anniversary_emotion",
            "party": 2,
            "tags": ["buffet", "dinner", "date_friendly"],
            "restaurant": ["buffet"],
            "exclude": ["包子", "牛肉汤", "咖啡"],
        },
        {
            "text": "想和女朋友吃点清淡的，但不要沙拉外卖，想坐下来吃晚饭。",
            "scenario": "anniversary_emotion",
            "party": 2,
            "tags": ["light_meal", "light_food", "dinner"],
            "restaurant": ["light_meal", "light_food"],
            "exclude": ["咖啡", "奶茶", "火锅", "烧烤"],
        },
        {
            "text": "我姐来下沙，别安排棋牌和KTV，吃饭想有杭州这边的体面感。",
            "scenario": "city_light_explore",
            "party": 2,
            "tags": ["host_guest", "quality_dining"],
            "restaurant": ["quality_dining", "proper_dining"],
            "exclude": ["棋牌", "KTV", "电竞"],
        },
        {
            "text": "一个人想喝杯酒听点音乐，九点半前回家，路线要简单。",
            "scenario": "fallback_unknown",
            "party": 1,
            "tags": ["alcohol", "light_drink", "music", "route_simple"],
            "restaurant": ["alcohol", "light_drink"],
            "activity": ["music", "acoustic_music"],
            "exclude": ["亲子", "团建"],
        },
        {
            "text": "四个人晚上想吃自助烤肉，预算别太高，饭后找地方坐着聊。",
            "scenario": "friend_group",
            "party": 4,
            "tags": ["buffet", "bbq", "grill", "budget_sensitive", "conversation", "post_meal_conversation"],
            "restaurant": ["buffet", "bbq", "grill"],
            "timeline_order": "restaurant_first",
            "exclude": ["高价", "长队"],
        },
        {
            "text": "四个人晚上先吃自助烤肉，饭后去KTV唱歌，别太远。",
            "scenario": "friend_group",
            "party": 4,
            "tags": ["buffet", "bbq", "grill", "karaoke", "restaurant_first_request"],
            "activity": ["karaoke"],
            "restaurant": ["buffet", "bbq", "grill"],
            "timeline_order": "restaurant_first",
            "exclude": ["包子", "牛肉汤", "影院", "酒吧"],
        },
        {
            "text": "和女朋友先吃西餐，吃完想在附近散步，不想再喝咖啡。",
            "scenario": "anniversary_emotion",
            "party": 2,
            "tags": ["western_cuisine", "dinner", "light_walk", "restaurant_first_request"],
            "activity": ["lake", "park", "light_walk"],
            "restaurant": ["western_cuisine"],
            "timeline_order": "restaurant_first",
            "exclude": ["咖啡", "瑞幸", "星巴克", "烘焙"],
        },
        {
            "text": "周末和老婆孩子去嘉年华，晚饭明确要自助餐，不要包子牛肉汤这种。",
            "scenario": "family_parent_child",
            "party": 3,
            "tags": ["amusement", "buffet", "dinner"],
            "activity": ["amusement"],
            "restaurant": ["buffet"],
            "exclude": ["包子", "牛肉汤", "电竞", "棋牌"],
        },
        {
            "text": "女朋友想吃日料，但不要日式快餐和咖啡，想像正式约会晚饭。",
            "scenario": "anniversary_emotion",
            "party": 2,
            "tags": ["cuisine_japanese", "date_friendly", "dinner"],
            "restaurant": ["cuisine_japanese", "sushi", "izakaya"],
            "exclude": ["咖啡", "日式咖喱", "蛋包饭"],
        },
        {
            "text": "爸妈来金沙湖，想少走路，吃饭不要麦当劳肯德基，找能聊天的正餐。",
            "scenario": "city_light_explore",
            "party": 2,
            "tags": ["host_guest", "route_simple", "proper_dining"],
            "restaurant": ["proper_dining", "quality_dining"],
            "exclude": ["麦当劳", "肯德基", "奶茶"],
        },
        {
            "text": "今天一个人很烦，只想附近走走，不喝酒，也别安排强互动项目。",
            "scenario": "fallback_unknown",
            "party": 1,
            "tags": ["alone", "mood_relief", "light_walk", "nearby"],
            "activity": ["light_walk", "nearby", "quiet"],
            "exclude": ["酒吧", "剧本杀", "团建"],
        },
    ]
    expanded = [*specs, *specs[: max(0, 20 - len(specs))]]
    for index, spec in enumerate(expanded):
        suffix = "" if index < len(specs) else "，如果附近没有就给备选但说明是模拟。"
        case(
            cases,
            "edge_constraints",
            spec["text"] + suffix,
            expected_scenario=spec["scenario"],
            party_size=spec["party"],
            must_have_tags=spec.get("tags", []),
            activity_should_match_any=spec.get("activity", []),
            restaurant_should_match_any=spec.get("restaurant", []),
            should_exclude_terms=spec.get("exclude", []),
            timeline_order=spec.get("timeline_order"),
            difficulty="hard",
        )


BUILDERS: List[Callable[[List[Dict[str, Any]]], None]] = [
    build_family_cases,
    build_date_cases,
    build_friend_cases,
    build_solo_cases,
    build_host_cases,
    build_edge_cases,
]


def main() -> None:
    cases: List[Dict[str, Any]] = []
    for builder in BUILDERS:
        builder(cases)
    if len(cases) != 200:
        raise SystemExit(f"expected 200 cases, got {len(cases)}")
    dataset = {
        "version": VERSION,
        "schema_version": "rule_eval.v1",
        "purpose": "LifePilot internal rule recall and slot-alignment evaluation dataset. Mock-only; not a public API contract.",
        "case_count": len(cases),
        "groups": {
            group: sum(1 for item in cases if item["group"] == group)
            for group in sorted({item["group"] for item in cases})
        },
        "evaluation_contract": {
            "request_body": "POST /api/v1/plans/create body fragment.",
            "expected.scenario": "Expected user_goal.scenario.",
            "expected.must_have_tags": "Tags that should be present in user_goal.intent_tags or constraints.must_have.",
            "expected.activity_should_match_any": "At least one should appear in activity step display_tags/title/semantic evaluation.",
            "expected.restaurant_should_match_any": "At least one should appear in restaurant step display_tags/title/semantic evaluation.",
            "expected.should_exclude_terms": "Terms that should not appear in selected POI titles or user-visible notes.",
        },
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
