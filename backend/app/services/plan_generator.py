import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.constants import TraceEventType
from app.services.llm_client import LLMClient
from app.services.logging_service import LoggingService


ACTIVITY_REQUEST_TERMS = (
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
    "打游戏",
    "游戏",
    "电竞",
    "网咖",
    "网吧",
    "电玩",
    "KTV",
    "ktv",
    "唱K",
    "K歌",
)


class PlanGenerator:
    def __init__(self, logging_service: LoggingService, llm_client: Optional[LLMClient] = None) -> None:
        self.logging_service = logging_service
        self.llm_client = llm_client

    def generate(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
        candidate_set: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        llm_notes = self._llm_draft_notes(trace_id, user_goal, constraints, candidate_set)
        variants = self._draft_variants(user_goal)
        drafts = [
            {
                "draft_id": draft_id,
                "scenario": user_goal["scenario"],
                "steps": self._steps(user_goal, constraints, time_window, candidate_set, llm_notes, variant_key),
                "messages": self._messages(user_goal, llm_notes),
                "explanation_seed": self._safe_note(llm_notes.get("explanation"), self._explanation(user_goal)),
            }
            for draft_id, variant_key in variants
        ]
        self.logging_service.log(
            trace_id,
            TraceEventType.INTENT_LOG,
            "PlanGenerator",
            {
                "user_visible_message": "已生成内部候选草案，下一步进入结构化校验。",
                "draft_count": len(drafts),
                "step_count": len(drafts[0]["steps"]) if drafts else 0,
            },
            visible_to_user=False,
        )
        return drafts

    def _draft_variants(self, user_goal: Dict[str, Any]) -> list[tuple[str, str]]:
        if user_goal["scenario"] == "friend_group":
            return [
                ("draft_good_food", "good_food"),
                ("draft_budget_relaxed", "budget_relaxed"),
                ("draft_photo_walk", "photo_walk"),
            ]
        return [("draft_primary", "primary")]

    def _llm_draft_notes(
        self,
        trace_id: str,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        candidate_set: Dict[str, Any],
    ) -> Dict[str, str]:
        if not self.llm_client:
            return {}
        selected = candidate_set.get("selected_pois") or {}
        poi_names = {
            role: poi.get("name")
            for role, poi in selected.items()
            if isinstance(poi, dict) and poi.get("name")
        }
        try:
            data = self.llm_client.generate_json(
                system_prompt=(
                    "你是LifePilot的受控计划草案文案模块。只输出JSON对象。"
                    "你只能为已经选定的Mock POI生成用户可读节点说明和模拟消息文案。"
                    "禁止更换POI，禁止判断余位、票务、路线、天气或执行成功，禁止输出Prompt、推理链或API Key。"
                ),
                user_prompt=(
                    "生成JSON字段：activity_note, restaurant_note, tail_note, explanation, group_invite, partner_note, card_title。"
                    "每个字段不超过45个中文字符。不得声称真实订座、真实支付、真实微信或真实票务。"
                    "card_title必须是2到6个中文字符或常见缩写，作为计划总览卡片标题，例如周日韩餐、电竞组队、寿司晚餐；不要标点。"
                    f"用户目标摘要：{user_goal.get('goal_summary')}。"
                    f"场景：{user_goal.get('scenario')}。标签：{user_goal.get('intent_tags')}。"
                    f"约束：party_size={constraints.get('party_size')}, budget_pp={constraints.get('budget_max_per_person')}, "
                    f"walking={constraints.get('walking_tolerance')}, queue={constraints.get('queue_tolerance')}。"
                    f"已选Mock POI：{poi_names}。"
                ),
                temperature=0.35,
                max_tokens=900,
            )
            self.logging_service.log(
                trace_id,
                TraceEventType.INTENT_LOG,
                "LLMPlanDraftAdapter",
                {
                    "user_visible_message": "已使用受控LLM润色内部草案文案。",
                    "fields": sorted(key for key in data.keys() if key in {"activity_note", "restaurant_note", "tail_note", "explanation"}),
                },
                visible_to_user=False,
            )
            return {
                key: self._safe_note(data.get(key), "")
                for key in ("activity_note", "restaurant_note", "tail_note", "explanation", "group_invite", "partner_note", "card_title")
            }
        except Exception as exc:
            self.logging_service.log(
                trace_id,
                TraceEventType.ERROR_LOG,
                "LLMPlanDraftAdapter",
                {
                    "error_code": "INTERNAL_ERROR",
                    "message": f"LLM draft fallback: {exc.__class__.__name__}",
                },
                level="warning",
                visible_to_user=False,
            )
            return {}

    def _steps(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
        candidate_set: Dict[str, Any],
        llm_notes: Dict[str, str],
        variant_key: str,
    ) -> list[Dict[str, Any]]:
        selected = candidate_set["selected_pois"]
        routes = candidate_set.get("routes") or []
        scenario = user_goal["scenario"]
        current = datetime.fromisoformat(time_window["start_time"])
        steps: list[Dict[str, Any]] = []
        restaurant_first = candidate_set.get("planning_order") == "restaurant_first"
        dinner_last = candidate_set.get("planning_order") == "dinner_last"
        if candidate_set.get("itinerary_nodes") and int(constraints.get("target_stop_count") or 0) >= 2:
            multi_steps = self._multi_stop_steps(user_goal, constraints, time_window, candidate_set, llm_notes, variant_key)
            if multi_steps:
                return multi_steps
        single_dining_steps = self._single_dining_steps(user_goal, constraints, time_window, candidate_set, llm_notes, variant_key)
        if single_dining_steps:
            return single_dining_steps

        if restaurant_first:
            markers = set(str(item) for item in constraints.get("must_have") or [])
            wants_music = bool(markers & {"music", "acoustic_music"})
            post_meal_conversation = "post_meal_conversation" in markers
            restaurant_first_request = "restaurant_first_request" in markers
            restaurant = selected.get("restaurant")
            tail = selected.get("tail")
            tail_step_type = self._tail_step_type(tail) if tail else ""
            service_linked_to_restaurant = bool(tail and tail_step_type == "service" and restaurant)
            if service_linked_to_restaurant:
                duration = min(self._tail_duration(scenario, "service"), 20)
                steps.append(
                    self._poi_step(
                        "service",
                        tail,
                        current,
                        duration,
                        self._safe_note(llm_notes.get("tail_note"), self._service_note(tail, restaurant)),
                    )
                )
                current += timedelta(minutes=duration)

            if restaurant:
                duration = self._restaurant_duration(scenario)
                note = (
                    self._restaurant_first_note(scenario, constraints, post_meal_conversation)
                    if post_meal_conversation or restaurant_first_request
                    else "先找个能安静小酌的地方坐一会儿，控制节奏，不把时间拖晚。"
                )
                steps.append(self._poi_step("restaurant", restaurant, current, duration, self._safe_note(llm_notes.get("restaurant_note"), note), reservation_required=True))
                current += timedelta(minutes=duration)

            if len(routes) >= 1:
                steps.append(self._transport_step(routes[0], current))
                current += timedelta(minutes=int(routes[0]["duration_minutes"]))

            activity = selected.get("activity")
            if activity:
                duration = self._activity_duration(scenario)
                if post_meal_conversation:
                    note = "饭后再换到低噪声、方便坐着聊的地方，不把正餐和聊天顺序倒过来。"
                elif restaurant_first_request:
                    note = "饭后再去你明说的活动，顺序按先吃饭、再活动来排。"
                else:
                    note = "再去有轻音乐的室内空间散心，强度低，方便按时收住回家。" if wants_music else "再换到低压力的短停留点，让情绪慢慢落下来，方便按时收住回家。"
                steps.append(self._poi_step("activity", activity, current, duration, self._safe_note(llm_notes.get("activity_note"), note), booking_required=True))
                current += timedelta(minutes=duration)

            if len(routes) >= 2 and not service_linked_to_restaurant:
                steps.append(self._transport_step(routes[1], current))
                current += timedelta(minutes=int(routes[1]["duration_minutes"]))

            if tail and not service_linked_to_restaurant:
                step_type = tail_step_type or self._tail_step_type(tail)
                duration = self._tail_duration(scenario, step_type)
                tail_note = "如果还想多留一会儿，用一个短停留点自然收尾。" if post_meal_conversation else self._tail_note(scenario, step_type, variant_key)
                steps.append(self._poi_step(step_type, tail, current, duration, self._safe_note(llm_notes.get("tail_note"), tail_note)))
            return self._fit_to_window(steps, time_window, scenario)

        if dinner_last:
            first = selected.get("activity")
            if first:
                duration = self._activity_duration(scenario)
                steps.append(self._poi_step("activity", first, current, duration, self._safe_note(llm_notes.get("activity_note"), self._activity_note(scenario, variant_key, constraints)), booking_required=True))
                current += timedelta(minutes=duration)

            tail = selected.get("tail")
            tail_step_type = self._tail_step_type(tail) if tail else ""
            restaurant = selected.get("restaurant")
            service_linked_to_restaurant = bool(tail and tail_step_type == "service" and restaurant)
            if first and tail and not service_linked_to_restaurant and len(routes) >= 1:
                steps.append(self._transport_step(routes[0], current))
                current += timedelta(minutes=int(routes[0]["duration_minutes"]))

            if tail:
                step_type = tail_step_type or self._tail_step_type(tail)
                next_route_minutes = (
                    int(routes[1]["duration_minutes"])
                    if first and len(routes) >= 2 and not service_linked_to_restaurant
                    else int(routes[0]["duration_minutes"])
                    if routes
                    else 10
                )
                duration = (
                    min(self._tail_duration(scenario, step_type), 20)
                    if service_linked_to_restaurant
                    else self._tail_duration_until_dinner(current, time_window, scenario, step_type, next_route_minutes)
                )
                note = (
                    self._service_note(tail, restaurant)
                    if step_type == "service"
                    else self._tail_note(scenario, step_type, variant_key)
                )
                steps.append(self._poi_step(step_type, tail, current, duration, self._safe_note(llm_notes.get("tail_note"), note)))
                current += timedelta(minutes=duration)

            route_index = (
                0
                if service_linked_to_restaurant and routes
                else 1
                if first and tail and len(routes) >= 2
                else 0
                if routes and (tail or first)
                else None
            )
            if route_index is not None and route_index < len(routes):
                steps.append(self._transport_step(routes[route_index], current))
                current += timedelta(minutes=int(routes[route_index]["duration_minutes"]))

            dinner_anchor = self._dinner_anchor(time_window)
            if current < dinner_anchor:
                current = dinner_anchor

            restaurant = selected.get("restaurant")
            if restaurant:
                duration = self._restaurant_duration(scenario)
                steps.append(self._poi_step("restaurant", restaurant, current, duration, self._safe_note(llm_notes.get("restaurant_note"), self._restaurant_note(scenario, variant_key, constraints)), reservation_required=True))
            return self._fit_to_window(steps, time_window, scenario)

        first = selected.get("activity")
        if first:
            duration = self._activity_duration(scenario)
            steps.append(self._poi_step("activity", first, current, duration, self._safe_note(llm_notes.get("activity_note"), self._activity_note(scenario, variant_key, constraints)), booking_required=True))
            current += timedelta(minutes=duration)

        tail = selected.get("tail")
        tail_step_type = self._tail_step_type(tail) if tail else ""
        restaurant = selected.get("restaurant")
        service_linked_to_restaurant = bool(tail and tail_step_type == "service" and restaurant)
        if service_linked_to_restaurant:
            duration = self._tail_duration(scenario, "service")
            steps.append(
                self._poi_step(
                    "service",
                    tail,
                    current,
                    min(duration, 20),
                    self._safe_note(llm_notes.get("tail_note"), self._service_note(tail, restaurant)),
                )
            )
            current += timedelta(minutes=min(duration, 20))

        if len(routes) >= 1:
            steps.append(self._transport_step(routes[0], current))
            current += timedelta(minutes=int(routes[0]["duration_minutes"]))

        if restaurant:
            duration = self._restaurant_duration(scenario)
            steps.append(self._poi_step("restaurant", restaurant, current, duration, self._safe_note(llm_notes.get("restaurant_note"), self._restaurant_note(scenario, variant_key, constraints)), reservation_required=True))
            current += timedelta(minutes=duration)

        if len(routes) >= 2 and not service_linked_to_restaurant:
            steps.append(self._transport_step(routes[1], current))
            current += timedelta(minutes=int(routes[1]["duration_minutes"]))

        if tail and not service_linked_to_restaurant:
            step_type = tail_step_type or self._tail_step_type(tail)
            duration = self._tail_duration(scenario, step_type)
            steps.append(self._poi_step(step_type, tail, current, duration, self._safe_note(llm_notes.get("tail_note"), self._tail_note(scenario, step_type, variant_key))))

        return self._fit_to_window(steps, time_window, scenario)

    def _single_dining_steps(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
        candidate_set: Dict[str, Any],
        llm_notes: Dict[str, str],
        variant_key: str,
    ) -> list[Dict[str, Any]]:
        if not self._is_single_explicit_dining_request(user_goal, constraints, candidate_set):
            return []
        restaurant = self._best_explicit_dining_restaurant(constraints, candidate_set)
        if not restaurant:
            return []
        scenario = user_goal["scenario"]
        current = datetime.fromisoformat(time_window["start_time"])
        duration = max(60, self._restaurant_duration(scenario))
        note = self._safe_note(llm_notes.get("restaurant_note"), self._restaurant_note(scenario, variant_key, constraints))
        return self._fit_to_window(
            [
                self._poi_step(
                    "restaurant",
                    restaurant,
                    current,
                    duration,
                    note,
                    reservation_required=True,
                )
            ],
            time_window,
            scenario,
        )

    def _is_single_explicit_dining_request(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        candidate_set: Dict[str, Any],
    ) -> bool:
        dining_preference = constraints.get("dining_preference") or {}
        try:
            target_stop_count = int(constraints.get("target_stop_count") or 1)
        except (TypeError, ValueError):
            target_stop_count = 1
        target_source = str(constraints.get("target_stop_count_source") or "")
        if not bool(dining_preference.get("explicit")) or target_stop_count > 1:
            return False
        if target_source and target_source != "meal_inferred":
            return False
        if self._has_activity_request(user_goal):
            return False
        selected = candidate_set.get("selected_pois") or {}
        return not bool(selected.get("activity") or selected.get("tail"))

    def _has_activity_request(self, user_goal: Dict[str, Any]) -> bool:
        raw_text = str(user_goal.get("raw_text") or "")
        if any(term in raw_text for term in ACTIVITY_REQUEST_TERMS):
            return True
        return bool(re.search(r"玩\s*(?:几个|[0-9一二两三四五六七八九十]+)\s*(?:小?时|钟头)", raw_text))

    def _best_explicit_dining_restaurant(self, constraints: Dict[str, Any], candidate_set: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates: list[Dict[str, Any]] = []
        seen: set[str] = set()

        def add_candidate(poi: Optional[Dict[str, Any]]) -> None:
            if not isinstance(poi, dict) or poi.get("category") != "restaurant" or not poi.get("poi_id"):
                return
            poi_id = str(poi["poi_id"])
            if poi_id in seen:
                return
            seen.add(poi_id)
            candidates.append(poi)

        selected = candidate_set.get("selected_pois") or {}
        for role in ("activity", "restaurant", "tail"):
            add_candidate(selected.get(role))
        for poi in candidate_set.get("extra_pois") or []:
            add_candidate(poi)
        for node in candidate_set.get("itinerary_nodes") or []:
            add_candidate(node.get("poi") if isinstance(node, dict) else None)

        if not candidates:
            return None
        return max(candidates, key=lambda poi: self._explicit_dining_match_score(poi, constraints))

    def _explicit_dining_match_score(self, poi: Dict[str, Any], constraints: Dict[str, Any]) -> float:
        dining_preference = constraints.get("dining_preference") or {}
        raw_terms = [str(term).strip() for term in dining_preference.get("raw_terms") or [] if str(term).strip()]
        specific_tags = [str(tag).strip() for tag in dining_preference.get("specific_tags") or [] if str(tag).strip()]
        normalized_tags = [str(tag).strip() for tag in dining_preference.get("normalized_tags") or [] if str(tag).strip()]
        tags = {str(tag) for tag in poi.get("tags") or []}
        searchable = " ".join(
            str(value)
            for value in (
                poi.get("name"),
                poi.get("category"),
                poi.get("raw_poi_tag"),
                " ".join(tags),
            )
            if value
        )
        score = 1.0
        for term in raw_terms:
            if term in searchable:
                score += 5.0
        for tag in specific_tags:
            if tag in tags or tag in searchable:
                score += 3.0
        for tag in normalized_tags:
            if tag in tags:
                score += 1.0
        return score

    def _multi_stop_steps(
        self,
        user_goal: Dict[str, Any],
        constraints: Dict[str, Any],
        time_window: Dict[str, Any],
        candidate_set: Dict[str, Any],
        llm_notes: Dict[str, str],
        variant_key: str,
    ) -> list[Dict[str, Any]]:
        scenario = user_goal["scenario"]
        nodes = [node for node in candidate_set.get("itinerary_nodes") or [] if node.get("poi")]
        routes = candidate_set.get("routes") or []
        if len(nodes) < 2:
            return []
        nodes = self._normalize_service_node_order(nodes)
        current = datetime.fromisoformat(time_window["start_time"])
        steps: list[Dict[str, Any]] = []
        dinner_anchor = self._multi_dinner_anchor(time_window)
        target_count = int(constraints.get("target_stop_count") or len(nodes))
        nodes = nodes[:target_count]
        step_types = [self._step_type_for_node(str(node.get("role") or self._node_role_from_poi(node["poi"])), node["poi"]) for node in nodes]
        durations = self._multi_stop_durations(step_types, scenario, time_window, routes)
        route_index = 0
        physical_seen = 0

        for index, node in enumerate(nodes):
            poi = node["poi"]
            role = str(node.get("role") or self._node_role_from_poi(poi))
            step_type = step_types[index]
            if step_type == "restaurant" and scenario == "anniversary_emotion" and current < dinner_anchor:
                current = dinner_anchor
            duration = durations[index]
            if step_type == "service":
                duration = min(duration, 20)
                note = self._service_note(poi, self._restaurant_target_for_service(index, nodes, step_types))
            else:
                note = self._node_note(step_type, role, scenario, constraints, llm_notes, variant_key, index, poi)
            steps.append(
                self._poi_step(
                    step_type,
                    poi,
                    current,
                    duration,
                    note,
                    booking_required=step_type == "activity",
                    reservation_required=step_type == "restaurant",
                )
            )
            current += timedelta(minutes=duration)
            if step_type != "service":
                physical_seen += 1
            next_non_service_index = self._next_non_service_index(step_types, index + 1)
            next_is_service = index + 1 < len(step_types) and step_types[index + 1] == "service"
            if next_non_service_index is not None and not next_is_service and physical_seen > 0 and route_index < len(routes):
                steps.append(self._transport_step(routes[route_index], current))
                current += timedelta(minutes=int(routes[route_index]["duration_minutes"]))
                route_index += 1

        return self._fit_to_window(steps, time_window, scenario)

    def _normalize_service_node_order(self, nodes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        restaurant_index = next(
            (
                index
                for index, node in enumerate(nodes)
                if self._step_type_for_node(str(node.get("role") or self._node_role_from_poi(node["poi"])), node["poi"]) == "restaurant"
            ),
            None,
        )
        if restaurant_index is None:
            return nodes
        service_after_ids = {
            str((node.get("poi") or {}).get("poi_id") or "")
            for node in nodes[restaurant_index + 1 :]
            if self._step_type_for_node(str(node.get("role") or self._node_role_from_poi(node["poi"])), node["poi"]) == "service"
        }
        service_after_ids.discard("")
        if not service_after_ids:
            return nodes
        normalized: list[Dict[str, Any]] = []
        for index, node in enumerate(nodes):
            poi_id = str((node.get("poi") or {}).get("poi_id") or "")
            if index == restaurant_index:
                normalized.extend(
                    item
                    for item in nodes[restaurant_index + 1 :]
                    if str((item.get("poi") or {}).get("poi_id") or "") in service_after_ids
                )
            if poi_id in service_after_ids:
                continue
            normalized.append(node)
        return normalized

    def _next_non_service_index(self, step_types: list[str], start: int) -> Optional[int]:
        for index in range(start, len(step_types)):
            if step_types[index] != "service":
                return index
        return None

    def _restaurant_target_for_service(
        self,
        index: int,
        nodes: list[Dict[str, Any]],
        step_types: list[str],
    ) -> Optional[Dict[str, Any]]:
        for offset in range(index + 1, len(nodes)):
            if step_types[offset] == "restaurant":
                return nodes[offset]["poi"]
        for offset in range(index - 1, -1, -1):
            if step_types[offset] == "restaurant":
                return nodes[offset]["poi"]
        return None

    def _multi_stop_durations(
        self,
        step_types: list[str],
        scenario: str,
        time_window: Dict[str, Any],
        routes: list[Dict[str, Any]],
    ) -> list[int]:
        desired = [self._node_duration(step_type, scenario, len(step_types)) for step_type in step_types]
        if not step_types:
            return desired
        try:
            start = datetime.fromisoformat(time_window["start_time"])
            end = datetime.fromisoformat(time_window["end_time"])
        except (KeyError, TypeError, ValueError):
            return desired
        route_minutes = sum(int(route.get("duration_minutes") or 0) for route in routes[: max(0, len(step_types) - 1)])
        available = int((end - start).total_seconds() // 60) - route_minutes
        if available <= 0 or sum(desired) <= available:
            return desired

        minimums = [self._minimum_node_duration(step_type) for step_type in step_types]
        minimum_total = sum(minimums)
        if minimum_total >= available:
            floor = max(8, available // len(step_types))
            return [max(8, min(minimum, floor)) for minimum in minimums]

        extra = available - minimum_total
        weights = [max(1, desired[index] - minimums[index]) for index in range(len(step_types))]
        total_weight = sum(weights)
        durations = [minimums[index] + int(extra * weights[index] / total_weight) for index in range(len(step_types))]
        remainder = available - sum(durations)
        index = 0
        while remainder > 0 and durations:
            durations[index % len(durations)] += 1
            remainder -= 1
            index += 1
        return durations

    def _minimum_node_duration(self, step_type: str) -> int:
        if step_type == "restaurant":
            return 60
        if step_type == "activity":
            return 35
        if step_type == "walk":
            return 25
        if step_type == "service":
            return 15
        return 20

    def _step_type_for_node(self, role: str, poi: Dict[str, Any]) -> str:
        if role == "restaurant" or poi.get("category") == "restaurant" and role == "restaurant":
            return "restaurant"
        if role == "tail":
            return self._tail_step_type(poi)
        if poi.get("category") == "walk_spot":
            return "walk"
        if poi.get("category") == "service":
            return "service"
        return "activity"

    def _node_role_from_poi(self, poi: Dict[str, Any]) -> str:
        if poi.get("category") == "restaurant":
            return "restaurant"
        if poi.get("category") in {"walk_spot", "service"}:
            return "tail"
        return "activity"

    def _node_duration(self, step_type: str, scenario: str, stop_count: int) -> int:
        if step_type == "service":
            return 20
        if scenario == "anniversary_emotion" and stop_count >= 4:
            if step_type == "restaurant":
                return 90
            if step_type == "activity":
                return 85
            if step_type == "walk":
                return 55
            return 25
        if step_type == "restaurant":
            return self._restaurant_duration(scenario)
        if step_type == "activity":
            return self._activity_duration(scenario)
        return self._tail_duration(scenario, step_type)

    def _multi_dinner_anchor(self, time_window: Dict[str, Any]) -> datetime:
        start = datetime.fromisoformat(time_window["start_time"])
        end = datetime.fromisoformat(time_window["end_time"])
        anchor = start.replace(hour=18, minute=0, second=0, microsecond=0)
        if anchor < start:
            anchor = start + timedelta(hours=2)
        latest = end - timedelta(minutes=100)
        if anchor > latest:
            anchor = max(start, latest)
        return anchor

    def _node_note(
        self,
        step_type: str,
        role: str,
        scenario: str,
        constraints: Dict[str, Any],
        llm_notes: Dict[str, str],
        variant_key: str,
        index: int,
        poi: Optional[Dict[str, Any]] = None,
    ) -> str:
        if step_type == "restaurant":
            return self._safe_note(llm_notes.get("restaurant_note"), self._restaurant_note(scenario, variant_key, constraints))
        if step_type == "walk":
            if scenario == "anniversary_emotion":
                return "留一段湖边慢走和拍照，不制造隆重负担，也让路线自然过渡。"
            return self._tail_note(scenario, step_type, variant_key)
        if step_type == "service":
            return "把鲜花/蛋糕等轻服务提前模拟下单，送到后续节点，不占用太多现场时间。"
        poi_note = self._poi_activity_note(poi or {}, scenario, constraints, variant_key)
        if scenario == "anniversary_emotion" and index == 0:
            return poi_note or self._safe_note(llm_notes.get("activity_note"), self._activity_note(scenario, variant_key, constraints))
        if scenario == "anniversary_emotion":
            return poi_note or "补一个低压力的小体验，让下午到晚饭之间有内容但不赶场。"
        return poi_note or self._safe_note(llm_notes.get("activity_note"), self._activity_note(scenario, variant_key, constraints))

    def _poi_activity_note(
        self,
        poi: Dict[str, Any],
        scenario: str,
        constraints: Dict[str, Any],
        variant_key: str,
    ) -> str:
        name = str(poi.get("name") or "")
        tags = {str(tag) for tag in poi.get("tags") or []}
        text = " ".join(
            str(value)
            for value in (
                name,
                poi.get("sub_category"),
                poi.get("raw_poi_tag"),
                " ".join(tags),
            )
            if value
        )
        is_hands_on = bool(tags & {"hands_on", "craft"} or any(token in text for token in ("手作", "手工", "DIY", "diy", "陶艺", "拼豆", "油画", "烘焙")))
        is_amusement = bool(tags & {"amusement", "child_friendly", "kid_safe", "family_time"} or any(token in text for token in ("嘉年华", "乐园", "游乐", "儿童")))
        is_mall = bool("mall" in tags or any(token in text for token in ("天街", "商场", "购物中心")))
        is_lake = bool("lake" in tags or any(token in text for token in ("金沙湖", "湖畔", "湖边", "公园")))
        is_esports = bool("esports" in tags or any(token in text for token in ("电竞", "网咖", "网吧", "电玩")))
        is_karaoke = bool("karaoke" in tags or any(token in text for token in ("KTV", "ktv", "唱K", "K歌", "唱歌")))
        is_board_game = bool("board_game" in tags or any(token in text for token in ("桌游", "剧本杀", "狼人杀", "密室")))
        is_quiet = bool(tags & {"quiet", "quiet_stay", "coffee", "dessert"})
        is_music = bool(tags & {"music", "acoustic_music"} or any(token in text for token in ("音乐", "民谣")))

        if scenario == "family_parent_child":
            if is_hands_on:
                return "手作体验适合孩子参与，室内安静、强度低，不用赶场。"
            if is_amusement and is_mall:
                return "商场室内游乐节点，孩子参与度高，和后续用餐转场短。"
            if is_amusement:
                return "轻游乐节点适合孩子放电，控制停留时长，后面还能按时吃饭。"
            if is_mall:
                return "商场室内活动受天气影响小，方便休息，也方便接晚饭。"
            if is_lake:
                return "靠近湖边的轻活动，节奏慢，适合亲子边玩边休息。"
            return "这一站按亲子友好的室内活动来排，强度不高，留足转场余量。"

        if scenario == "anniversary_emotion":
            if is_hands_on:
                return "手作体验有参与感，也有可带走的小记忆，约会节奏更自然。"
            if is_lake:
                return "湖边轻停留适合慢走和拍照，不制造隆重负担。"
            if is_quiet:
                return "安静停留点适合放慢节奏，给晚饭前留出自然过渡。"
            return "补一个低压力的小体验，让下午到晚饭之间有内容但不赶场。"

        if scenario == "city_light_explore":
            if is_lake:
                return "用有下沙识别度的湖边节点开场，方便聊天和轻松拍照。"
            if is_mall:
                return "商场室内节点好找、好休息，适合家人到达后慢慢进入状态。"
            return self._activity_note(scenario, variant_key, constraints)

        if scenario == "fallback_unknown":
            if is_lake:
                return "湖边或公园类节点刺激低，适合短距离走走，把情绪放下来。"
            if is_quiet:
                return "安静停留点决策成本低，可以坐一会儿，也方便随时结束。"
            if is_music:
                return "有音乐的低压力空间适合短暂停留，控制节奏不拖晚。"
            return self._activity_note(scenario, variant_key, constraints)

        if is_esports:
            return "电竞/网咖类室内活动适合朋友组队，时间和预算都容易控住。"
        if is_karaoke:
            return "KTV类节点适合朋友组队，把主要互动放在室内完成。"
        if is_board_game:
            return "桌游类节点适合坐着互动，预算可控，也方便后面接饭。"
        if is_hands_on:
            return "手作体验比纯逛更有参与感，适合朋友轻松热身。"
        if is_mall:
            return "商场室内短停留受天气影响小，转场和预算都更好控制。"
        return self._activity_note(scenario, variant_key, constraints)

    def _tail_step_type(self, poi: Dict[str, Any]) -> str:
        if poi.get("category") == "walk_spot":
            return "walk"
        if poi.get("category") == "activity":
            return "activity"
        if poi.get("category") == "service":
            return "service"
        if poi.get("category") == "restaurant" and set(str(tag) for tag in poi.get("tags") or []) & {"coffee", "dessert", "quiet_stay"}:
            return "activity"
        if poi.get("category") == "restaurant":
            return "restaurant"
        return "activity"

    def _poi_step(
        self,
        step_type: str,
        poi: Dict[str, Any],
        start: datetime,
        duration: int,
        note: str,
        booking_required: bool = False,
        reservation_required: bool = False,
    ) -> Dict[str, Any]:
        end = start + timedelta(minutes=duration)
        if step_type == "activity" and poi.get("category") != "activity":
            booking_required = False
        return {
            "type": step_type,
            "title": poi["name"],
            "description": note,
            "start_time": start.replace(microsecond=0).isoformat(),
            "end_time": end.replace(microsecond=0).isoformat(),
            "duration_minutes": duration,
            "poi_id": poi["poi_id"],
            "booking_required": booking_required,
            "reservation_required": reservation_required,
            "display_tags": poi.get("tags", [])[:4],
            "user_visible_notes": note,
        }

    def _transport_step(self, route: Dict[str, Any], start: datetime) -> Dict[str, Any]:
        duration = int(route["duration_minutes"])
        end = start + timedelta(minutes=duration)
        return {
            "type": "transport",
            "title": "转场",
            "description": "路线来自模拟估算，留出短转场缓冲。",
            "start_time": start.replace(microsecond=0).isoformat(),
            "end_time": end.replace(microsecond=0).isoformat(),
            "duration_minutes": duration,
            "from_poi_id": route["origin_poi_id"],
            "to_poi_id": route["destination_poi_id"],
            "transport_mode": route["transport_mode"],
            "estimated_route": route,
            "booking_required": False,
            "reservation_required": False,
            "display_tags": ["nearby"],
            "user_visible_notes": "转场时间按模拟路线估算。",
        }

    def _messages(self, user_goal: Dict[str, Any], llm_notes: Dict[str, str]) -> Dict[str, str]:
        messages = {
            "plan_card_title": self._safe_card_title(llm_notes.get("card_title")) or self._fallback_card_title(user_goal),
        }
        if user_goal["scenario"] == "anniversary_emotion":
            messages["partner_note"] = self._safe_note(llm_notes.get("partner_note"), "今天不用安排得很隆重，就按轻松的节奏走，我想把这段时间留给我们。")
            return messages
        if user_goal["scenario"] == "friend_group":
            messages["group_invite"] = self._safe_note(llm_notes.get("group_invite"), "我先整理了一个不远、不贵、偏轻松的方案，大家可以直接投偏好。")
            return messages
        return messages

    def _safe_card_title(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        stripped = "".join(ch for ch in text if ch not in " \t\r\n，。！？、；;,.!?：:（）()【】[]《》<>“”\"'")
        return stripped if 2 <= len(stripped) <= 6 else ""

    def _fallback_card_title(self, user_goal: Dict[str, Any]) -> str:
        raw_text = str(user_goal.get("raw_text") or "")
        tags = set(str(tag) for tag in user_goal.get("intent_tags") or [])
        text = f"{raw_text} {' '.join(tags)}"
        prefix = self._title_time_prefix(raw_text)
        if any(token in text for token in ("韩国料理", "韩餐", "韩料", "韩式", "部队锅", "泡菜")):
            return self._join_card_title(prefix, "韩餐")
        if "sushi" in tags or any(token in text for token in ("寿司", "鮨", "刺身", "回转寿司")):
            return self._join_card_title(prefix, "寿司")
        if "cuisine_japanese" in tags or any(token in text for token in ("日料", "日式", "日本料理", "居酒屋", "烧鸟")):
            return self._join_card_title(prefix, "日料")
        if "hotpot" in tags or "火锅" in text:
            return self._join_card_title(prefix, "火锅")
        if tags & {"bbq", "grill"} or any(token in text for token in ("烤肉", "烧烤", "烧肉")):
            return self._join_card_title(prefix, "烤肉")
        if "buffet" in tags or any(token in text for token in ("自助", "放题")):
            return self._join_card_title(prefix, "自助餐")
        if "esports" in tags or any(token in text for token in ("电竞", "打游戏", "网咖", "网吧")):
            return self._join_card_title(prefix, "电竞")
        if "karaoke" in tags or any(token in text for token in ("KTV", "ktv", "唱K", "K歌", "唱歌")):
            return self._join_card_title(prefix, "K歌")
        if "board_game" in tags or any(token in text for token in ("桌游", "剧本杀", "狼人杀")):
            return self._join_card_title(prefix, "桌游")
        if user_goal.get("scenario") == "family_parent_child":
            return "亲子下午"
        if user_goal.get("scenario") == "anniversary_emotion":
            return "纪念日约会"
        if user_goal.get("scenario") == "friend_group":
            return self._join_card_title(prefix, "朋友局")
        return "生活计划"

    def _title_time_prefix(self, raw_text: str) -> str:
        if any(token in raw_text for token in ("周六", "星期六", "礼拜六")):
            return "周六"
        if any(token in raw_text for token in ("周日", "星期日", "星期天", "礼拜日", "礼拜天")):
            return "周日"
        if any(token in raw_text for token in ("这周末", "本周末", "周末")):
            return "周末"
        if any(token in raw_text for token in ("今晚", "今天晚上", "晚上")):
            return "今晚"
        if "下午" in raw_text:
            return "下午"
        return ""

    def _join_card_title(self, prefix: str, label: str) -> str:
        joined = f"{prefix}{label}" if prefix else ""
        if 2 <= len(joined) <= 6:
            return joined
        fallback = f"{label}计划"
        return fallback if len(fallback) <= 6 else label[:6]

    def _activity_duration(self, scenario: str) -> int:
        if scenario == "anniversary_emotion":
            return 70
        if scenario == "city_light_explore":
            return 75
        if scenario == "fallback_unknown":
            return 50
        return 75

    def _restaurant_duration(self, scenario: str) -> int:
        if scenario == "anniversary_emotion":
            return 80
        if scenario == "city_light_explore":
            return 75
        if scenario == "fallback_unknown":
            return 40
        return 70

    def _tail_duration(self, scenario: str, step_type: str) -> int:
        if scenario == "fallback_unknown":
            return 35
        return 30 if step_type == "walk" else 25

    def _tail_duration_until_dinner(self, current: datetime, time_window: Dict[str, Any], scenario: str, step_type: str, next_route_minutes: int) -> int:
        base = self._tail_duration(scenario, step_type)
        anchor = self._dinner_anchor(time_window)
        target_end = anchor - timedelta(minutes=next_route_minutes)
        fill = int((target_end - current).total_seconds() // 60)
        if fill <= base:
            return base
        return min(fill, 100)

    def _dinner_anchor(self, time_window: Dict[str, Any]) -> datetime:
        start = datetime.fromisoformat(time_window["start_time"])
        end = datetime.fromisoformat(time_window["end_time"])
        anchor = start.replace(hour=17, minute=30, second=0, microsecond=0)
        if anchor < start:
            anchor = start
        latest = end - timedelta(minutes=70)
        if anchor > latest:
            return max(start, latest)
        return anchor

    def _activity_note(self, scenario: str, variant_key: str = "primary", constraints: Optional[Dict[str, Any]] = None) -> str:
        markers = set(str(item) for item in (constraints or {}).get("must_have") or [])
        if scenario == "family_parent_child":
            return "先安排孩子能参与、强度不高、排队压力低的活动。"
        if scenario == "anniversary_emotion":
            if markers & {"hands_on", "craft"}:
                return "先做一个有参与感的手作体验，约会会更自然，也有可带走的小记忆。"
            return "先用安静的小活动打开节奏，不做夸张仪式。"
        if scenario == "city_light_explore":
            return "先选一个有下沙识别度、方便聊天的轻活动，适合家人刚到后慢慢进入状态。"
        if scenario == "fallback_unknown":
            return "先到低压力的安静空间，不需要被迫互动，适合把情绪放下来。"
        if markers & {"esports"}:
            return "先按你明说的打游戏来选电竞/网咖类室内活动，适合朋友组队。"
        if markers & {"karaoke"}:
            return "先按你明说的唱歌来选KTV类室内活动，适合朋友组队。"
        if variant_key == "budget_relaxed":
            return "先选低预算、轻松坐聊的节点，避免一开始就太赶。"
        if variant_key == "photo_walk":
            return "先安排适合逛逛和拍照的节点，节奏轻一点。"
        return "先安排轻松活动，方便朋友聊天热身。"

    def _restaurant_note(self, scenario: str, variant_key: str = "primary", constraints: Optional[Dict[str, Any]] = None) -> str:
        profile_tags = set(((constraints or {}).get("recommendation_profile") or {}).get("normalized_tags") or [])
        markers = set(str(item) for item in (constraints or {}).get("must_have") or [])
        dining_preference = (constraints or {}).get("dining_preference") or {}
        if scenario == "fallback_unknown" and dining_preference.get("explicit"):
            raw_terms = dining_preference.get("raw_terms") or dining_preference.get("positive_terms") or []
            target = str(raw_terms[0]) if raw_terms else "这顿饭"
            return f"按你明说的{target}来选餐厅，不用其他品类替代。"
        if scenario == "family_parent_child":
            raw_terms = [
                str(term).strip()
                for term in dining_preference.get("raw_terms") or []
                if str(term).strip() and str(term).strip() not in {"清淡", "低负担", "轻食", "低卡", "低脂", "减脂", "健康", "沙拉"}
            ]
            if raw_terms:
                return f"晚饭优先照顾孩子想吃的{raw_terms[0]}，同时避开重口味和长队。"
            if "buffet" in markers:
                return "晚饭按你明说的自助餐来选，兼顾孩子和家庭用餐节奏。"
            if markers & {"light_meal", "light_food"}:
                return "晚饭选清淡、家庭友好的正餐，避开重口味和长队。"
            return "餐饮优先兼顾低负担饮食和家庭友好。"
        if scenario == "anniversary_emotion":
            if "buffet" in markers:
                return "晚饭按你们明说的自助餐来选，不用普通小吃或简餐替代。"
            if "hotpot" in markers:
                return "晚饭按你们明说的火锅来选，同时控制排队和转场。"
            if markers & {"cuisine_japanese", "sushi", "izakaya"}:
                return "晚饭按你们明说的日料来选，同时保留约会感和短转场。"
            if markers & {"bbq", "grill"}:
                raw_terms = dining_preference.get("raw_terms") or []
                target = str(raw_terms[0]) if raw_terms else "烤肉"
                return f"晚饭按你们明说的{target}来选，同时控制排队和转场。"
            if markers & {"western_cuisine", "steak"}:
                raw_terms = dining_preference.get("raw_terms") or []
                target = str(raw_terms[0]) if raw_terms else "西餐"
                return f"晚饭按你们明说的{target}来选，优先保证正餐属性和短转场。"
            if "lamb" in markers:
                raw_terms = dining_preference.get("raw_terms") or []
                target = str(raw_terms[0]) if raw_terms else "羊肉"
                return f"晚饭按你们明说的{target}来选，不用咖啡或茶空间替代。"
            if markers & {"light_meal", "light_food", "healthy_light"}:
                return "晚饭按清淡、低负担方向来选，避开重口味和伪正餐。"
            if profile_tags & {"beautiful_dining", "quality_dining", "ambience_dining"}:
                return "餐厅优先选有氛围和品质感的正餐，不用低价连锁凑数。"
            return "选择安静、不高调但有照顾感的用餐节点。"
        if scenario == "city_light_explore":
            if "buffet" in markers:
                return "吃饭按自助餐来选，避免用普通小吃或简餐替代明确诉求。"
            return "吃饭选体面但不端着的地方，方便边吃边聊，也能体现你在认真招待。"
        if scenario == "fallback_unknown":
            return "把这一站作为低压力短停靠点，方便中途结束。"
        if variant_key == "budget_relaxed":
            return "餐饮优先控制人均预算和排队压力。"
        if variant_key == "photo_walk":
            return "餐饮放在轻松转场后，不抢掉逛逛的时间。"
        return "餐饮控制预算和排队压力，适合4人轻松坐下。"

    def _tail_note(self, scenario: str, step_type: str, variant_key: str = "primary") -> str:
        if scenario == "family_parent_child":
            return "中间留一段短距离休息或轻量收尾，等到晚饭也不累。"
        if scenario == "anniversary_emotion":
            return "最后留一小段散步或服务节点，形成轻仪式感收尾。"
        if scenario == "city_light_explore":
            return "最后留一段轻松收尾，不把家人带得太累，也方便回程。"
        if scenario == "fallback_unknown":
            return "最后留一段短距离走走或室内休息点，让这段散心可以自然收住。"
        if variant_key == "photo_walk":
            return "最后补一个好走、好拍、低成本的收尾节点。"
        if step_type == "walk":
            return "最后用低成本、低强度节点收尾，避免太赶。"
        return "补一个不打扰的服务节点。"

    def _service_note(self, service: Dict[str, Any], restaurant: Optional[Dict[str, Any]] = None) -> str:
        target = restaurant.get("name") if restaurant else None
        if target:
            return f"提前把{service['name']}模拟下单，约送到后面的{target}，不用临时绕路取。"
        return f"提前把{service['name']}模拟下单，和后续节点合并处理，不单独增加取货压力。"

    def _restaurant_first_note(
        self,
        scenario: str,
        constraints: Dict[str, Any],
        post_meal_conversation: bool,
    ) -> str:
        markers = set(str(item) for item in constraints.get("must_have") or [])

        if "buffet" in markers and markers & {"bbq", "grill"}:
            meal = "自助烤肉"
        elif "buffet" in markers:
            meal = "自助餐"
        elif markers & {"bbq", "grill"}:
            meal = "烤肉"
        elif markers & {"western_cuisine", "steak"}:
            meal = "西餐"
        elif "hotpot" in markers:
            meal = "火锅"
        elif markers & {"cuisine_japanese", "sushi", "izakaya"}:
            meal = "日料"
        elif markers & {"light_meal", "light_food", "healthy_light"}:
            meal = "清淡正餐"
        else:
            meal = "正餐"

        if post_meal_conversation:
            return f"先按你明说的{meal}吃饭，饭后再找低噪声地方坐着聊。"
        if scenario == "anniversary_emotion":
            return f"先按你们明说的{meal}吃饭，再接饭后的轻松安排。"
        return f"先按你明说的{meal}吃饭，再接饭后的活动安排。"

    def _explanation(self, user_goal: Dict[str, Any]) -> str:
        return user_goal.get("goal_summary") or "生成一段生活时间线。"

    def _safe_note(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        forbidden = ("真实支付", "真实订座", "真实微信", "真实短信", "真实票务", "真实锁票", "实时抓取", "锁定")
        if not text or any(token in text for token in forbidden):
            return fallback
        return text[:80]

    def _fit_to_window(self, steps: list[Dict[str, Any]], time_window: Dict[str, Any], scenario: str) -> list[Dict[str, Any]]:
        if not steps:
            return steps
        end_limit = datetime.fromisoformat(time_window["end_time"])
        if datetime.fromisoformat(steps[-1]["end_time"]) <= end_limit:
            return steps
        fitted = list(steps)
        if scenario == "fallback_unknown":
            fitted = self._drop_last_poi_segment(fitted)
            if fitted and datetime.fromisoformat(fitted[-1]["end_time"]) > end_limit:
                fitted = self._drop_last_poi_segment(fitted)
        return self._trim_last_step(fitted, end_limit)

    def _drop_last_poi_segment(self, steps: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        if len(steps) <= 1:
            return steps
        result = list(steps)
        while result and result[-1]["type"] == "transport":
            result.pop()
        if result and result[-1]["type"] in {"restaurant", "walk", "service"}:
            result.pop()
        while result and result[-1]["type"] == "transport":
            result.pop()
        return result or steps[:1]

    def _trim_last_step(self, steps: list[Dict[str, Any]], end_limit: datetime) -> list[Dict[str, Any]]:
        if not steps:
            return steps
        last = steps[-1]
        start = datetime.fromisoformat(last["start_time"])
        base_minimum = 20 if last["type"] in {"activity", "restaurant", "walk"} else 5
        available_minutes = int((end_limit - start).total_seconds() // 60)
        minimum = max(1, min(base_minimum, available_minutes))
        if start + timedelta(minutes=minimum) > end_limit:
            if len(steps) == 1:
                duration = max(1, int((end_limit - start).total_seconds() // 60))
                last["duration_minutes"] = duration
                last["end_time"] = (start + timedelta(minutes=duration)).replace(microsecond=0).isoformat()
                return steps
            else:
                return self._trim_last_step(steps[:-1], end_limit)
        duration = max(minimum, int((end_limit - start).total_seconds() // 60))
        last["duration_minutes"] = duration
        last["end_time"] = (start + timedelta(minutes=duration)).replace(microsecond=0).isoformat()
        return steps
