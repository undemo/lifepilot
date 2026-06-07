from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query

from app.core.context import RequestContext, get_context
from app.core.responses import success_response
from app.services.mock_api_service import MockAPIService


def create_mock_router(service: MockAPIService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/mock", tags=["mock"])

    @router.get("/poi/search")
    def search_pois(
        scenario: Optional[str] = None,
        area: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = Query(default=10, ge=1, le=100),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.search_pois(ctx.trace_id, scenario=scenario, area=area, category=category, tags=tags, limit=limit, debug=ctx.debug)
        return success_response(ctx.trace_id, data)

    @router.get("/restaurants/search")
    def search_restaurants(
        scenario: Optional[str] = None,
        area: Optional[str] = None,
        dietary_preference: Optional[str] = None,
        budget_max_per_person: Optional[float] = None,
        tags: Optional[str] = None,
        limit: int = Query(default=10, ge=1, le=100),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.search_restaurants(
            ctx.trace_id,
            scenario=scenario,
            area=area,
            dietary_preference=dietary_preference,
            budget_max_per_person=budget_max_per_person,
            tags=tags,
            limit=limit,
            debug=ctx.debug,
        )
        return success_response(ctx.trace_id, data)

    @router.get("/poi/{poi_id}/status")
    def poi_status(
        poi_id: str,
        party_size: Optional[int] = None,
        failure_scenario_id: Optional[str] = None,
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.poi_status(ctx.trace_id, poi_id, party_size=party_size, failure_scenario_id=failure_scenario_id, debug=ctx.debug)
        return success_response(ctx.trace_id, data)

    @router.get("/restaurants/{poi_id}/status")
    def restaurant_status(
        poi_id: str,
        arrival_time: str,
        party_size: int,
        failure_scenario_id: Optional[str] = None,
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.restaurant_status(
            ctx.trace_id,
            poi_id,
            arrival_time=arrival_time,
            party_size=party_size,
            failure_scenario_id=failure_scenario_id,
            debug=ctx.debug,
        )
        return success_response(ctx.trace_id, data)

    @router.get("/routes/estimate")
    def estimate_route(
        origin_poi_id: str,
        destination_poi_id: str,
        transport_mode: str,
        departure_time: str,
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.estimate_route(
            ctx.trace_id,
            origin_poi_id=origin_poi_id,
            destination_poi_id=destination_poi_id,
            transport_mode=transport_mode,
            departure_time=departure_time,
        )
        return success_response(ctx.trace_id, data)

    @router.get("/weather")
    def weather(
        area: str,
        start_time: str,
        end_time: str,
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.weather(ctx.trace_id, area=area, start_time=start_time, end_time=end_time, debug=ctx.debug)
        return success_response(ctx.trace_id, data)

    @router.get("/social-signals/{poi_id}")
    def social_signal(poi_id: str, ctx: RequestContext = Depends(get_context)) -> Dict[str, Any]:
        data = service.social_signal(ctx.trace_id, poi_id)
        return success_response(ctx.trace_id, data)

    @router.post("/activities/{poi_id}/book")
    def book_activity(
        poi_id: str,
        body: Dict[str, Any] = Body(default_factory=dict),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.book_activity(ctx.trace_id, poi_id, body, ctx.idempotency_key, debug=ctx.debug)
        return success_response(ctx.trace_id, data)

    @router.post("/restaurants/{poi_id}/reserve")
    def reserve_restaurant(
        poi_id: str,
        body: Dict[str, Any] = Body(default_factory=dict),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.reserve_restaurant(ctx.trace_id, poi_id, body, ctx.idempotency_key, debug=ctx.debug)
        return success_response(ctx.trace_id, data)

    @router.post("/orders/create")
    def order_item(
        body: Dict[str, Any] = Body(default_factory=dict),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.order_item(ctx.trace_id, body, ctx.idempotency_key)
        return success_response(ctx.trace_id, data)

    @router.post("/messages/send")
    def send_message(
        body: Dict[str, Any] = Body(default_factory=dict),
        ctx: RequestContext = Depends(get_context),
    ) -> Dict[str, Any]:
        data = service.send_message(ctx.trace_id, body, ctx.idempotency_key)
        return success_response(ctx.trace_id, data)

    return router
