from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "prompts"

STYLE_DIMENSIONS = {
    "tone": ["朴素", "轻松", "安静", "热闹", "高效", "疗愈", "运动感", "烟火气", "干净清爽", "适合外地人"],
    "price_band": ["免费", "10-30", "30-50", "50-100", "100-150", "150以上"],
    "area": ["下沙", "金沙湖", "高教园区"],
    "time_slot": ["清晨运动前后", "工作日午休", "工作日傍晚", "周六下午", "雨天临时改计划", "深夜前补给", "外地朋友到达后", "情绪低落想散心"],
    "weather_context": ["多云可散步", "小雨偏室内", "天气热需少走路", "湖边风大需备选", "空气闷热想找阴凉", "雨后地面湿滑", "晴天适合运动"],
    "party_context": ["一个人", "两个人", "三五人", "同事临时聚", "外地朋友来访", "带宠物", "带老人", "带孩子", "骑行或跑步后"],
    "mobility": ["少走路", "可步行串联", "地铁口集合", "打车优先", "开车停车优先", "骑行友好", "轮椅或推车友好", "室内连廊动线"],
    "people_segment": ["喜欢小动物的人", "很在意卫生的人", "心情低落想散心的人", "爱运动的人", "压力大想放空的人", "外地来杭州的人", "独处工作的人", "预算敏感学生", "夜间补给人群", "拍照记录人群", "老人同行", "室内避雨人群"],
    "life_need": ["正餐", "咖啡茶饮", "低成本消磨时间", "散步放空", "运动后补给", "宠物友好", "卫生间/更衣/洗手", "停车接驳", "临时买药/便利补给", "安静工作", "外地朋友打卡", "雨天室内备选", "情绪缓冲", "轻娱乐"],
}

MICRO_SCENE_MIX = [
    "衣/整理：雨天临时外套、普通更衣、运动后整理、拍照前补妆、储物点",
    "食/饮：正餐、小吃、轻食、咖啡、茶饮、甜品、夜间补给、运动后补水",
    "停留/放空：短时休息、安静坐一会儿、压力大放空、心情不好散心、看湖或看人流",
    "行/接驳：地铁口、停车点、打车点、骑行停靠、少走路接驳、外地人好找的集合点",
    "娱/学习/工作：展览、书店、运动、桌游、KTV、临时办公、独处阅读、轻量社交",
    "卫生/服务：干净卫生间、洗手、更衣、母婴、宠物友好、便利店、药店、充电、避雨",
    "大众偏好：喜欢小动物、爱干净、外地朋友来玩、爱运动、预算敏感、怕吵、怕晒、怕排队",
]

FILE_CONTRACTS = {
    "mock_pois.json": """
顶层 {"version":"v0.1","area":"杭州下沙/金沙湖/高教园区","pois":[]}
POI字段：poi_id,name,category,sub_category,tags,location,area,address,price_per_person,rating,opening_hours,suitable_scenarios,risk_tags,mock_only,created_at,updated_at。
category只能是 activity / restaurant / walk_spot / service / transport_anchor。
必须覆盖 family_parent_child / friend_group / anniversary_emotion。
""",
    "mock_status.json": """
顶层 {"version":"v0.1","statuses":{poi_id:{query_status,execute_status,debug_failure_ref?}}}
query_status字段包含 available,open_status,queue_minutes,risk_level,status_message,source,updated_at,expire_at；餐厅补 available_tables/reservation_available；活动补 ticket_available/remaining_tickets/booking_available。
source必须是mock_api，debug失败引用只允许内部使用。
""",
    "mock_inventory.json": """
顶层 {"version":"v0.1","restaurant_slots":[],"activity_slots":[]}
restaurant_slots包含 poi_id,slot_start,slot_end,base_tables,reserved_tables,max_party_size。
activity_slots包含 poi_id,slot_start,slot_end,remaining_tickets,booking_available。
""",
    "mock_routes.json": """
顶层 {"version":"v0.1","routes":[]}
Route字段：route_id,origin_poi_id,destination_poi_id,transport_mode,distance_km,duration_minutes,traffic_level,confidence,source,updated_at。
所有起终点必须来自POI列表，source必须是mock_api。
""",
    "mock_weather.json": """
顶层 {"version":"v0.1","weather_snapshots":[]}
Weather字段：weather_id,area,time_range,weather,temperature,rain_probability,outdoor_risk_level,suggested_recovery,source,updated_at。
覆盖下沙、金沙湖、高教园区，source必须是mock_api。
""",
    "mock_failure_scenarios.json": """
顶层 {"version":"v0.1","scenarios":[]}
场景字段：failure_scenario_id,enabled,trigger,error_code,visible_to_user。
error_code只能覆盖 NO_TABLE_AVAILABLE / ACTIVITY_FULL / PLAN_EXECUTABLE_WINDOW_EXPIRED；visible_to_user必须为false。
""",
    "mock_social_signals.json": """
顶层 {"version":"v0.1","signals":[]}
Signal字段：signal_id,poi_id,summary,positive_tags,negative_tags,heat_score,is_mock,source_type,updated_at。
必须包含 confidence 和 mock_sources；mock_sources只能是link1、link2、link3这类占位链接。
is_mock必须为true，source_type必须是mock_social_signal，summary必须写成80-220字口碑Mock归纳段落。
summary必须提到POI名称，并结合POI类别写具体好评和差评，不允许套用固定Demo场景模板。
""",
    "benchmark_samples.json": """
顶层 {"version":"v0.1","samples":[]}
Sample字段：sample_id,scenario,scenario_expected,input_text,expected_constraints,expected_verifier_checks。
必须覆盖家庭亲子、朋友局、纪念日，并包含Recovery、窗口过期、天气风险、预算约束等扩展样例。
""",
}

FILE_GOALS = {
    "mock_pois.json": "生成面向大众生活需求的地点骨架，强调不同兴趣、情绪、卫生、运动、预算、动线和人群约束，不生成可执行状态。",
    "mock_status.json": "生成Mock状态快照，让Verifier能判断营业、排队、桌位、票务和窗口。",
    "mock_inventory.json": "生成分时段库存，让查询和执行存在合理动态变化。",
    "mock_routes.json": "生成路线矩阵，覆盖本地生活常见串联动线。",
    "mock_weather.json": "生成区域天气风险，驱动户外到室内的PlanB。",
    "mock_failure_scenarios.json": "生成可复现失败脚本，服务Executor失败和Recovery演示。",
    "mock_social_signals.json": "生成口碑Mock摘要，展示模拟社交反馈但不阻断主流程。",
    "benchmark_samples.json": "生成评测样例，覆盖P0主路径、失败恢复、隐私和Mock边界。",
}


def compose_prompt(file_name: str, *, seed: int | None = None, batch_size: int = 15, start_index: int = 1, pois: list[dict[str, Any]] | None = None) -> str:
    if file_name not in FILE_CONTRACTS:
        raise ValueError(f"unsupported file: {file_name}")
    rng = random.Random(seed)
    context = {key: rng.choice(values) for key, values in STYLE_DIMENSIONS.items()}
    scenario = rng.choice(
        [
            "喜欢小动物，想找不排斥宠物或能看到动物元素的地方",
            "很在意卫生，优先干净、明亮、洗手间和桌面维护好的地点",
            "最近有点难过，想一个人散散心，不想被打扰",
            "爱运动，想把跑步、骑行、拉伸和补给串起来",
            "压力大，想找能短暂停留、放空、喝点东西的地方",
            "外地朋友来玩，希望地点好找、能代表下沙日常、不要太游客化",
            "预算有限，但希望吃喝、休息、娱乐都有选择",
            "下雨临时改计划，需要室内、少走路、好等车的备选",
            "晚上临时出门，需要安全、明亮、补给方便的地点",
            "想独处办公或阅读，重视安静、插座、桌面和停留舒适度",
        ]
    )
    prompt_path = PROMPTS_DIR / f"{file_name.removesuffix('.json')}.md"
    template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (PROMPTS_DIR / "generate_dataset.md").read_text(encoding="utf-8")
    poi_limit = min(batch_size, 15) if file_name == "mock_social_signals.json" else 30
    pois_json = json.dumps((pois or [])[:poi_limit], ensure_ascii=False, indent=2)
    replacements = {
        "{{file_name}}": file_name,
        "{{file_goal}}": FILE_GOALS[file_name],
        "{{file_contract}}": FILE_CONTRACTS[file_name].strip(),
        "{{batch_size}}": str(batch_size),
        "{{start_index}}": str(start_index),
        "{{scenario_context}}": scenario,
        "{{tone}}": context["tone"],
        "{{price_band}}": context["price_band"],
        "{{area}}": context["area"],
        "{{time_slot}}": context["time_slot"],
        "{{weather_context}}": context["weather_context"],
        "{{party_context}}": context["party_context"],
        "{{mobility}}": context["mobility"],
        "{{people_segment}}": context["people_segment"],
        "{{life_need}}": context["life_need"],
        "{{micro_scene_mix}}": "\n".join(f"- {item}" for item in MICRO_SCENE_MIX),
        "{{pois_json}}": pois_json,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose varied LifePilot Qwen prompts for each mock data file.")
    parser.add_argument("--file", default="mock_pois.json", choices=sorted(FILE_CONTRACTS))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--start-index", type=int, default=1)
    args = parser.parse_args()
    print(compose_prompt(args.file, seed=args.seed, batch_size=args.batch_size, start_index=args.start_index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
