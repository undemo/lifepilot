import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.data_paths import (  # noqa: E402
    DATA_DIR,
    DATA_FILE_PATHS,
    MOCK_FAILURE_SCENARIOS_PATH,
    MOCK_POIS_PATH,
    MOCK_ROUTES_PATH,
    PLANS_STORE_PATH,
    TRACES_STORE_PATH,
)
from app.main import create_app  # noqa: E402


TRACE_ID = "trace_test_20260521_0001"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEPILOT_DEMO_NOW", "2026-05-20T15:00:00+08:00")
    monkeypatch.setenv("LIFEPILOT_DEMO_SEED", "test-seed")
    data_dir = tmp_path / "data"
    shutil.copytree(ROOT / "backend" / "data", data_dir)
    app = create_app(data_dir)
    return TestClient(app)


def headers(**extra):
    base = {"X-Trace-Id": TRACE_ID}
    base.update(extra)
    return base


def post_headers(key, **extra):
    return headers(**{"X-Idempotency-Key": key}, **extra)


def assert_success(response):
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["trace_id"] == TRACE_ID
    assert payload["error"] is None
    return payload["data"]


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    payload = response.json()
    assert payload["success"] is False
    assert payload["trace_id"] == TRACE_ID
    assert payload["data"] is None
    assert payload["error"]["code"] == code
    return payload["error"]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _data_path(client, configured_path):
    path = Path(configured_path)
    if not path.is_absolute() and len(path.parts) == 1:
        path = DATA_FILE_PATHS.get(path.name, path)
    if path.is_absolute():
        path = path.relative_to(DATA_DIR)
    return client.app.state.data_dir / path


def assert_no_failure_scenario_id(value):
    assert "failure_scenario_id" not in json_text(value)


def assert_no_query_credentials(value):
    text = json_text(value)
    for field in ("booking_id", "reservation_id", "order_id", "message_id"):
        assert field not in text


def data_rows(client, filename, key):
    return json.loads(_data_path(client, Path(filename)).read_text(encoding="utf-8")).get(key, [])


def first_poi(client, category):
    return next(item for item in data_rows(client, MOCK_POIS_PATH, "pois") if item.get("category") == category)


def first_route_between(client, origin_category, destination_category):
    pois = {item["poi_id"]: item for item in data_rows(client, MOCK_POIS_PATH, "pois")}
    for route in data_rows(client, MOCK_ROUTES_PATH, "routes"):
        origin = pois.get(route.get("origin_poi_id"))
        destination = pois.get(route.get("destination_poi_id"))
        if origin and destination and origin.get("category") == origin_category and destination.get("category") == destination_category:
            return route
    raise AssertionError(f"missing route from {origin_category} to {destination_category}")


def write_failure_scenarios(client, restaurant_id, activity_id):
    payload = {
        "version": "v0.1",
        "scenarios": [
            {
                "failure_scenario_id": "fail_no_table_test",
                "enabled": True,
                "error_code": "NO_TABLE_AVAILABLE",
                "visible_to_user": False,
                "trigger": {"path": "POST /api/v1/mock/restaurants/{poi_id}/reserve", "poi_id": restaurant_id},
            },
            {
                "failure_scenario_id": "fail_activity_full_test",
                "enabled": True,
                "error_code": "ACTIVITY_FULL",
                "visible_to_user": False,
                "trigger": {"path": "POST /api/v1/mock/activities/{poi_id}/book", "poi_id": activity_id},
            },
        ],
    }
    _data_path(client, MOCK_FAILURE_SCENARIOS_PATH).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_poi_search_success_and_empty_result(client):
    data = assert_success(
        client.get(
            "/api/v1/mock/poi/search",
            params={"scenario": "family_parent_child", "area": "jinshahu", "category": "activity", "limit": 3},
            headers=headers(),
        )
    )
    assert data["items"]
    assert data["items"][0]["poi_id"].startswith("poi_")
    assert data["items"][0]["mock_only"] is True
    assert_no_query_credentials(data)

    empty = assert_success(client.get("/api/v1/mock/poi/search", params={"tags": "tag_that_does_not_exist"}, headers=headers()))
    assert empty["items"] == []
    assert_no_failure_scenario_id(empty)

    assert_error(client.get("/api/v1/mock/poi/search", params={"limit": 0}, headers=headers()), 400, "BAD_REQUEST")


def test_restaurant_search_success_and_empty_result(client):
    data = assert_success(
        client.get(
            "/api/v1/mock/restaurants/search",
            params={"scenario": "family_parent_child", "area": "jinshahu", "budget_max_per_person": 80, "limit": 2},
            headers=headers(),
        )
    )
    assert data["items"]
    assert all(item["category"] == "restaurant" for item in data["items"])
    assert all(item["mock_only"] is True for item in data["items"])
    assert_no_query_credentials(data)

    empty = assert_success(client.get("/api/v1/mock/restaurants/search", params={"tags": "tag_that_does_not_exist"}, headers=headers()))
    assert empty["items"] == []

    assert_error(client.get("/api/v1/mock/restaurants/search", params={"limit": 0}, headers=headers()), 400, "BAD_REQUEST")


def test_poi_status_success_and_not_found(client):
    activity = first_poi(client, "activity")
    data = assert_success(
        client.get(
            f"/api/v1/mock/poi/{activity['poi_id']}/status",
            params={"party_size": 2},
            headers=headers(),
        )
    )
    assert data["poi_id"] == activity["poi_id"]
    assert data["source"] == "mock_api"
    assert data["mock_only"] is True
    assert data["ticket_available"] in (True, False)
    assert "expire_at" in data
    assert_no_query_credentials(data)

    error = assert_error(client.get("/api/v1/mock/poi/poi_missing/status", headers=headers()), 404, "PLAN_STEP_POI_NOT_FOUND")
    assert error["recoverable"] is True


def test_restaurant_status_success_and_no_table_injection_snapshot(client):
    restaurant = first_poi(client, "restaurant")
    write_failure_scenarios(client, restaurant["poi_id"], first_poi(client, "activity")["poi_id"])
    data = assert_success(
        client.get(
            f"/api/v1/mock/restaurants/{restaurant['poi_id']}/status",
            params={"arrival_time": "2026-05-20T15:30:00+08:00", "party_size": 3},
            headers=headers(),
        )
    )
    assert data["available_tables"] >= 0
    assert data["reservation_available"] == (data["available_tables"] > 0)
    assert data["source"] == "mock_api"
    assert_no_query_credentials(data)

    injected = assert_success(
        client.get(
            f"/api/v1/mock/restaurants/{restaurant['poi_id']}/status",
            params={
                "arrival_time": "2026-05-20T15:30:00+08:00",
                "party_size": 3,
                "failure_scenario_id": "fail_no_table_test",
            },
            headers=headers(),
        )
    )
    assert injected["available"] is False
    assert injected["available_tables"] == 0
    assert injected["reservation_available"] is False
    assert injected["risk_level"] == "blocking"
    assert_no_failure_scenario_id(injected)


def test_route_estimate_success_and_missing_route(client):
    route = first_route_between(client, "restaurant", "activity")
    data = assert_success(
        client.get(
            "/api/v1/mock/routes/estimate",
            params={
                "origin_poi_id": route["origin_poi_id"],
                "destination_poi_id": route["destination_poi_id"],
                "transport_mode": route["transport_mode"],
                "departure_time": "2026-05-20T13:40:00+08:00",
            },
            headers=headers(),
        )
    )
    assert data["route_id"].startswith("route_")
    assert data["source"] == "mock_api"
    assert data["duration_minutes"] > 0

    assert_error(
        client.get(
            "/api/v1/mock/routes/estimate",
            params={
                "origin_poi_id": route["origin_poi_id"],
                "destination_poi_id": route["destination_poi_id"],
                "transport_mode": "teleport",
                "departure_time": "2026-05-20T13:40:00+08:00",
            },
            headers=headers(),
        ),
        409,
        "ROUTE_DELAY",
    )


def test_weather_success_and_generated_area(client):
    data = assert_success(
        client.get(
            "/api/v1/mock/weather",
            params={
                "area": "jinshahu",
                "start_time": "2026-05-20T13:30:00+08:00",
                "end_time": "2026-05-20T18:00:00+08:00",
            },
            headers=headers(),
        )
    )
    assert data["source"] == "mock_api"
    assert data["mock_only"] is True
    assert data["time_range"]["start_time"] == "2026-05-20T13:30:00+08:00"

    generated = assert_success(
        client.get(
            "/api/v1/mock/weather",
            params={
                "area": "unknown_area",
                "start_time": "2026-05-20T13:30:00+08:00",
                "end_time": "2026-05-20T18:00:00+08:00",
            },
            headers=headers(),
        )
    )
    assert generated["area"] == "unknown_area"
    assert generated["source"] == "mock_api"
    assert generated["mock_only"] is True


def test_generated_mock_world_is_deterministic_and_date_sensitive(client):
    restaurant = first_poi(client, "restaurant")
    params = {"arrival_time": "2026-05-21T18:00:00+08:00", "party_size": 4}
    first = assert_success(client.get(f"/api/v1/mock/restaurants/{restaurant['poi_id']}/status", params=params, headers=headers()))
    second = assert_success(client.get(f"/api/v1/mock/restaurants/{restaurant['poi_id']}/status", params=params, headers=headers()))
    assert first == second

    day_one = assert_success(
        client.get(
            "/api/v1/mock/weather",
            params={"area": "demo_area", "start_time": "2026-05-21T13:30:00+08:00", "end_time": "2026-05-21T18:00:00+08:00"},
            headers=headers(),
        )
    )
    day_two = assert_success(
        client.get(
            "/api/v1/mock/weather",
            params={"area": "demo_area", "start_time": "2026-05-22T13:30:00+08:00", "end_time": "2026-05-22T18:00:00+08:00"},
            headers=headers(),
        )
    )
    assert day_one["weather_id"] != day_two["weather_id"] or day_one["rain_probability"] != day_two["rain_probability"]


def test_activity_book_success_failure_injection_and_idempotency(client):
    activity = first_poi(client, "activity")
    write_failure_scenarios(client, first_poi(client, "restaurant")["poi_id"], activity["poi_id"])
    body = {
        "plan_id": "plan_test_001",
        "action_id": "act_book_001",
        "party_size": 2,
        "booking_time": "2026-05-20T17:00:00+08:00",
    }
    first = assert_success(client.post(f"/api/v1/mock/activities/{activity['poi_id']}/book", json=body, headers=post_headers("idem_book_001")))
    second = assert_success(client.post(f"/api/v1/mock/activities/{activity['poi_id']}/book", json=body, headers=post_headers("idem_book_001")))
    assert first["booking_id"] == second["booking_id"]
    assert first["booking_id"].startswith(f"mock_booking_{activity['poi_id']}_")
    assert first["poi_name"] == activity["name"]
    assert first["venue_snapshot"]["poi_id"] == activity["poi_id"]
    assert activity["name"] in first["display_text"]
    assert "17:00" in first["display_text"]
    assert first["mock_only"] is True

    conflict_body = {**body, "action_id": "act_book_other"}
    assert_error(
        client.post(f"/api/v1/mock/activities/{activity['poi_id']}/book", json=conflict_body, headers=post_headers("idem_book_001")),
        409,
        "IDEMPOTENCY_CONFLICT",
    )

    error = assert_error(
        client.post(
            f"/api/v1/mock/activities/{activity['poi_id']}/book",
            json={**body, "failure_scenario_id": "fail_activity_full_test"},
            headers=post_headers("idem_book_full_001"),
        ),
        400,
        "ACTIVITY_FULL",
    )
    assert_no_failure_scenario_id(error)


def test_restaurant_reserve_success_no_table_injection_and_window_expired(client):
    restaurant = first_poi(client, "restaurant")
    write_failure_scenarios(client, restaurant["poi_id"], first_poi(client, "activity")["poi_id"])
    body = {
        "plan_id": "plan_test_002",
        "action_id": "act_reserve_001",
        "party_size": 3,
        "arrival_time": "2026-05-20T15:30:00+08:00",
    }
    data = assert_success(client.post(f"/api/v1/mock/restaurants/{restaurant['poi_id']}/reserve", json=body, headers=post_headers("idem_reserve_001")))
    assert data["reservation_id"].startswith(f"mock_reservation_{restaurant['poi_id']}_")
    assert data["reservation_type"] == "reservation"
    assert data["poi_name"] == restaurant["name"]
    assert data["venue_snapshot"]["poi_id"] == restaurant["poi_id"]
    assert restaurant["name"] in data["display_text"]
    assert "15:30" in data["display_text"]
    assert data["mock_only"] is True

    assert_error(
        client.post(
            f"/api/v1/mock/restaurants/{restaurant['poi_id']}/reserve",
            json={**body, "action_id": "act_reserve_full", "failure_scenario_id": "fail_no_table_test"},
            headers=post_headers("idem_reserve_full_001"),
        ),
        400,
        "NO_TABLE_AVAILABLE",
    )

    assert_error(
        client.post(
            f"/api/v1/mock/restaurants/{restaurant['poi_id']}/reserve",
            json={**body, "action_id": "act_reserve_expired", "executable_window_expire_at": "2020-01-01T00:00:00+08:00"},
            headers=post_headers("idem_reserve_expired_001"),
        ),
        409,
        "PLAN_EXECUTABLE_WINDOW_EXPIRED",
    )


def test_order_create_success_and_bad_request(client):
    restaurant = first_poi(client, "restaurant")
    body = {
        "plan_id": "plan_test_003",
        "action_id": "act_order_001",
        "poi_id": restaurant["poi_id"],
        "items": [{"name": "cake", "amount": 98}],
        "delivery_target": {"poi_id": restaurant["poi_id"], "label": restaurant["name"], "deliver_at": "2026-05-20T18:00:00+08:00"},
    }
    data = assert_success(client.post("/api/v1/mock/orders/create", json=body, headers=post_headers("idem_order_001")))
    assert data["order_id"].startswith(f"mock_order_{restaurant['poi_id']}_")
    assert data["order_status"] == "created"
    assert data["poi_name"] == restaurant["name"]
    assert data["venue_snapshot"]["poi_id"] == restaurant["poi_id"]
    assert data["delivery_target"]["poi_id"] == restaurant["poi_id"]
    assert restaurant["name"] in data["display_text"]
    assert data["mock_only"] is True

    assert_error(client.post("/api/v1/mock/orders/create", json=body, headers=headers()), 400, "BAD_REQUEST")


def test_message_send_success_and_bad_request(client):
    body = {
        "plan_id": "plan_test_004",
        "action_id": "act_msg_001",
        "channel": "mock_wechat",
        "recipient_type": "spouse",
        "content": "mock message draft",
    }
    data = assert_success(client.post("/api/v1/mock/messages/send", json=body, headers=post_headers("idem_msg_001")))
    assert data["message_id"].startswith("mock_msg_")
    assert data["delivery_status"] == "mock_generated"
    assert data["mock_only"] is True

    assert_error(
        client.post("/api/v1/mock/messages/send", json={**body, "content": ""}, headers=post_headers("idem_msg_bad_001")),
        400,
        "BAD_REQUEST",
    )


def test_social_signal_success_and_generated(client):
    restaurant = first_poi(client, "restaurant")
    activity = first_poi(client, "activity")
    data = assert_success(client.get(f"/api/v1/mock/social-signals/{restaurant['poi_id']}", headers=headers()))
    assert data["signal_id"].startswith("sig_")
    assert data["poi_id"] == restaurant["poi_id"]
    assert data["is_mock"] is True
    assert data["source_type"] == "mock_social_signal"

    generated = assert_success(client.get(f"/api/v1/mock/social-signals/{activity['poi_id']}", headers=headers()))
    assert generated["poi_id"] == activity["poi_id"]
    assert generated["source_type"] == "mock_social_signal"


def test_debug_failure_summary_is_redacted(client):
    restaurant = first_poi(client, "restaurant")
    write_failure_scenarios(client, restaurant["poi_id"], first_poi(client, "activity")["poi_id"])
    body = {
        "plan_id": "plan_test_005",
        "action_id": "act_reserve_debug",
        "party_size": 3,
        "arrival_time": "2026-05-20T15:30:00+08:00",
        "failure_scenario_id": "fail_no_table_test",
    }
    error = assert_error(
        client.post(
            f"/api/v1/mock/restaurants/{restaurant['poi_id']}/reserve",
            json=body,
            headers=post_headers("idem_reserve_debug_001", **{"X-Debug-Mode": "true"}),
        ),
        400,
        "NO_TABLE_AVAILABLE",
    )
    assert error["details"]["failure_summary"]["error_code"] == "NO_TABLE_AVAILABLE"
    assert_no_failure_scenario_id(error)


def test_trace_logs_use_tool_log_and_never_mock_call(client):
    restaurant = first_poi(client, "restaurant")
    assert_success(client.get(f"/api/v1/mock/social-signals/{restaurant['poi_id']}", headers=headers()))
    traces_path = _data_path(client, TRACES_STORE_PATH)
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    all_logs = traces.get("logs", [])
    mock_logs = [log for log in all_logs if log.get("module") == "MockAPIService"]
    assert mock_logs
    assert all(log["event_type"] == "tool_log" for log in mock_logs)
    assert "mock_call" not in json_text(mock_logs)
    assert any(log.get("payload", {}).get("tool_name") == "get_social_signal_mock" for log in mock_logs)


def create_plan(client, key="idem_plan_001", text="今天下午想和朋友出去玩，别太远。"):
    data = assert_success(
        client.post(
            "/api/v1/plans/create",
            json={"input_text": text, "scenario_hint": "friend_group"},
            headers=post_headers(key),
        )
    )
    assert data["plan_id"].startswith("plan_")
    assert data["plan_contract"]["trace_id"] == TRACE_ID
    return data


def test_consensus_read_vote_page_vote_update_and_candidate_validation(client):
    first_plan = create_plan(client, "idem_plan_consensus_001")
    second_plan = create_plan(client, "idem_plan_consensus_002", "朋友投票，想找个轻松室内方案。")
    candidate_plan_ids = [first_plan["plan_id"], second_plan["plan_id"]]

    created = assert_success(
        client.post(
            "/api/v1/consensus/create",
            json={
                "candidate_plan_ids": candidate_plan_ids,
                "title": "朋友局投票",
                "expire_at": "2026-05-20T14:00:00+08:00",
            },
            headers=post_headers("idem_consensus_001"),
        )
    )
    assert created["consensus_session_id"].startswith("cs_")
    assert created["vote_page_id"].startswith("vpage_")
    assert created["share_url"].endswith(created["vote_page_id"])

    session = assert_success(client.get(f"/api/v1/consensus/{created['consensus_session_id']}", headers=headers()))
    assert session["vote_count"] == 0
    assert session["can_finalize"] is True

    vote_page = assert_success(client.get(f"/api/v1/vote-pages/{created['vote_page_id']}", headers=headers()))
    assert vote_page["consensus_session_id"] == created["consensus_session_id"]
    assert [item["plan_id"] for item in vote_page["candidate_plans"]] == candidate_plan_ids
    assert "tool_actions" not in json_text(vote_page["candidate_plans"])

    first_vote = assert_success(
        client.post(
            f"/api/v1/consensus/{created['consensus_session_id']}/vote",
            json={
                "participant": {"participant_name": "朋友A", "anonymous": False},
                "liked_plan_ids": [candidate_plan_ids[0]],
                "client_vote_token": "client_vote_a",
            },
            headers=headers(),
        )
    )
    updated_vote = assert_success(
        client.post(
            f"/api/v1/consensus/{created['consensus_session_id']}/vote",
            json={
                "participant": {"participant_name": "朋友A", "anonymous": False},
                "disliked_plan_ids": [candidate_plan_ids[1]],
                "client_vote_token": "client_vote_a",
            },
            headers=headers(),
        )
    )
    assert updated_vote["vote_id"] == first_vote["vote_id"]
    assert updated_vote["vote_count"] == 1

    assert_error(
        client.post(
            f"/api/v1/consensus/{created['consensus_session_id']}/vote",
            json={"participant": {}, "liked_plan_ids": ["plan_missing_001"]},
            headers=headers(),
        ),
        400,
        "CONSENSUS_VOTE_INVALID",
    )

    assert_error(
        client.post(
            "/api/v1/consensus/create",
            json={"candidate_plan_ids": ["plan_missing_001"], "expire_at": "2026-05-20T14:00:00+08:00"},
            headers=post_headers("idem_consensus_missing_001"),
        ),
        404,
        "RESOURCE_NOT_FOUND",
    )


def test_consensus_finalize_builds_constraints_reverifies_and_locks_votes(client):
    first_plan = create_plan(client, "idem_plan_consensus_finalize_001")
    second_plan = create_plan(client, "idem_plan_consensus_finalize_002", "朋友投票，想找个室内聊天方案。")
    candidate_plan_ids = [first_plan["plan_id"], second_plan["plan_id"]]
    created = assert_success(
        client.post(
            "/api/v1/consensus/create",
            json={
                "candidate_plan_ids": candidate_plan_ids,
                "title": "朋友局投票",
                "expire_at": "2026-05-20T14:00:00+08:00",
            },
            headers=post_headers("idem_consensus_finalize_001"),
        )
    )
    consensus_session_id = created["consensus_session_id"]
    assert created["plan_group_id"].startswith("plangrp_")

    assert_error(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/vote",
            json={
                "participant": {"participant_name": "冲突票", "anonymous": False},
                "liked_plan_ids": [candidate_plan_ids[0]],
                "disliked_plan_ids": [candidate_plan_ids[0]],
            },
            headers=headers(),
        ),
        400,
        "CONSENSUS_VOTE_INVALID",
    )

    assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/vote",
            json={
                "participant": {"participant_name": "朋友A", "anonymous": False},
                "liked_plan_ids": [candidate_plan_ids[0]],
                "budget_max": 100,
                "walking_tolerance": "low",
                "queue_tolerance": "low",
                "free_text": "想室内坐着聊天，不想走太多，也不想排队。",
                "client_vote_token": "client_vote_finalize_a",
            },
            headers=headers(),
        )
    )
    assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/vote",
            json={
                "participant": {"participant_name": "朋友B", "anonymous": False},
                "disliked_plan_ids": [candidate_plan_ids[1]],
                "budget_max": 90,
                "walking_tolerance": "medium_low",
                "queue_tolerance": "low",
                "client_vote_token": "client_vote_finalize_b",
            },
            headers=headers(),
        )
    )

    finalized = assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/finalize",
            json={"close_voting": True},
            headers=headers(),
        )
    )
    summary = finalized["consensus_summary"]
    final_plan = finalized["final_plan_contract"]
    constraints = summary["consensus_constraints"]
    assert summary["vote_count"] == 2
    assert constraints["budget_max_per_person"] == 90
    assert constraints["walking_tolerance"] == "low"
    assert constraints["queue_tolerance"] == "low"
    assert "consensus" in constraints["activity_preference"]
    assert final_plan["plan_id"] == summary["final_plan_id"]
    assert final_plan["constraints"] == constraints
    assert final_plan["verifier_result"]["status"] in {"pass", "warning", "fail"}
    assert final_plan["verifier_result"]["created_at"]

    repeated = assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/finalize",
            json={"close_voting": True},
            headers=headers(),
        )
    )
    assert repeated["consensus_summary"]["final_plan_id"] == summary["final_plan_id"]

    assert_error(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/vote",
            json={"participant": {}, "free_text": "我想改票"},
            headers=headers(),
        ),
        400,
        "CONSENSUS_VOTE_INVALID",
    )


def test_consensus_finalize_preserves_supported_candidate_semantics(client):
    created_plan = assert_success(
        client.post(
            "/api/v1/plans/create",
            json={
                "input_text": "周末想和朋友找个地方打游戏,然后吃人均不超过 50 的饭",
                "scenario_hint": "friend_group",
                "generate_candidates": True,
                "use_memory": False,
                "current_time": "2026-06-04T08:00:00+08:00",
                "preferred_duration_hours": 4,
                "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖", "lat": 30.309, "lng": 120.319},
            },
            headers=post_headers("idem_plan_consensus_game_001"),
        )
    )
    candidate_plan_ids = [created_plan["plan_id"], *created_plan["candidate_plan_ids"]]
    assert candidate_plan_ids
    liked_plan_id = candidate_plan_ids[0]
    liked_plan = assert_success(client.get(f"/api/v1/plans/{liked_plan_id}", headers=headers()))["plan_contract"]
    liked_titles = [step["title"] for step in liked_plan["timeline"] if step["type"] != "transport"]
    assert any("电竞" in title or "网咖" in title for title in liked_titles)

    created_consensus = assert_success(
        client.post(
            "/api/v1/consensus/create",
            json={
                "candidate_plan_ids": [liked_plan_id, *candidate_plan_ids],
                "title": "朋友局投票",
                "expire_at": "2026-06-04T22:00:00+08:00",
            },
            headers=post_headers("idem_consensus_game_001"),
        )
    )
    consensus_session_id = created_consensus["consensus_session_id"]
    assert created_consensus["candidate_plan_ids"][0] == liked_plan_id
    assert len(created_consensus["candidate_plan_ids"]) == len(set(created_consensus["candidate_plan_ids"]))
    vote_page = assert_success(client.get(f"/api/v1/vote-pages/{created_consensus['vote_page_id']}", headers=headers()))
    assert [item["plan_id"] for item in vote_page["candidate_plans"]].count(liked_plan_id) == 1
    assert vote_page["candidate_plans"][0]["title"] != "转场"
    assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/vote",
            json={
                "participant": {"participant_name": "朋友A", "anonymous": False},
                "liked_plan_ids": [liked_plan_id],
                "client_vote_token": "client_vote_game_a",
            },
            headers=headers(),
        )
    )

    finalized = assert_success(
        client.post(
            f"/api/v1/consensus/{consensus_session_id}/finalize",
            json={"close_voting": True},
            headers=headers(),
        )
    )
    final_plan = finalized["final_plan_contract"]
    final_titles = [step["title"] for step in final_plan["timeline"] if step["type"] != "transport"]
    assert finalized["consensus_summary"]["source_plan_id"] == liked_plan_id
    assert final_plan["plan_id"] != liked_plan_id
    assert final_titles == liked_titles
    assert "海底捞火锅外送" not in " ".join(final_titles)
    assert "爱玩嘉年华" not in " ".join(final_titles)
    assert "打游戏" in final_plan["user_goal"]["raw_text"]
    final_payload = assert_success(client.get(f"/api/v1/plans/{final_plan['plan_id']}", headers=headers()))
    assert final_payload["candidate_plan_ids"] == []


def test_feedback_questions_match_contract(client):
    plan = create_plan(client, "idem_plan_feedback_001")
    data = assert_success(client.get("/api/v1/feedback/questions", params={"plan_id": plan["plan_id"]}, headers=headers()))
    assert data["plan_id"] == plan["plan_id"]
    assert data["max_questions"] == 2
    assert data["skippable"] is True
    assert len(data["questions"]) == 2
    assert all(question["question_id"].startswith("q_") for question in data["questions"])


def test_execute_rejects_expired_executable_window(client):
    plan = create_plan(client, "idem_plan_expired_001")
    plans_path = _data_path(client, PLANS_STORE_PATH)
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    plans["plans"][plan["plan_id"]]["executable_window"]["expire_at"] = "2020-01-01T00:00:00+08:00"
    plans_path.write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")

    assert_error(
        client.post(
            f"/api/v1/plans/{plan['plan_id']}/execute",
            json={"confirmed": True},
            headers=post_headers("idem_execute_expired_001"),
        ),
        409,
        "PLAN_EXECUTABLE_WINDOW_EXPIRED",
    )
