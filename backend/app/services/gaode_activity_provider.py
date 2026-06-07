from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

from app.core.data_paths import GAODE_POI_REVIEW_CANDIDATES_PATH, RUNTIME_ACTIVITY_POIS_PATH


class GaodeActivityProvider:
    """Optional activity candidate supplementer.

    It first reuses local Gaode-derived review data. If `AMAP_KEY` is present,
    it may call Gaode place text search for activity terms and persists converted
    mock POIs into runtime_activity_pois.json so downstream MockAPI status/route
    checks still see a normal mock POI. Failure returns an empty list.
    """

    def __init__(self, store: Any, city: str = "杭州") -> None:
        self.store = store
        self.city = city

    def supplement(
        self,
        *,
        trace_id: str,
        activity_match: Dict[str, Any],
        constraints: Dict[str, Any],
        scenario: Optional[str],
        existing_ids: Iterable[str],
        limit: int = 12,
    ) -> list[Dict[str, Any]]:
        if not activity_match:
            return []
        existing = {str(item) for item in existing_ids or []}
        query_terms = self._query_terms(activity_match)
        if not query_terms:
            return []
        local = self._local_candidates(query_terms, activity_match, constraints, scenario, existing, limit)
        if len(local) >= min(3, limit):
            return local[:limit]
        remote = self._remote_candidates(query_terms, activity_match, constraints, existing | {str(item.get("poi_id")) for item in local}, limit - len(local))
        if remote:
            self._persist_runtime(remote)
        return [*local, *remote][:limit]

    def _query_terms(self, activity_match: Dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("raw_terms", "facility_types"):
            for value in activity_match.get(key) or []:
                text = str(value).strip()
                if text and text not in values:
                    values.append(text)
        type_fallback = {
            "ACTIVITY_BADMINTON": "羽毛球馆",
            "ACTIVITY_TENNIS": "网球中心",
            "ACTIVITY_FOOTBALL": "足球场",
            "ACTIVITY_BASKETBALL": "篮球馆",
            "ACTIVITY_ESPORTS": "电竞馆",
            "ACTIVITY_SCRIPT_MURDER": "剧本杀",
            "ACTIVITY_BOARD_GAME": "桌游",
            "ACTIVITY_KARAOKE": "KTV",
            "ACTIVITY_MOVIE": "电影院",
            "ACTIVITY_THEATER": "剧院",
            "ACTIVITY_HANDS_ON": "手工坊",
            "ACTIVITY_AMUSEMENT": "游乐园",
            "ACTIVITY_SCENIC": "景点",
            "ACTIVITY_PARK_WALK": "公园",
        }
        for type_id in activity_match.get("activity_type_ids") or []:
            term = type_fallback.get(str(type_id))
            if term and term not in values:
                values.append(term)
        if not values:
            for key in ("genres", "styles"):
                for value in activity_match.get(key) or []:
                    text = str(value).strip()
                    if text and text not in values:
                        values.append(text)
        return values[:4]

    def _local_candidates(
        self,
        query_terms: list[str],
        activity_match: Dict[str, Any],
        constraints: Dict[str, Any],
        scenario: Optional[str],
        existing: set[str],
        limit: int,
    ) -> list[Dict[str, Any]]:
        source = self.store.read(GAODE_POI_REVIEW_CANDIDATES_PATH, {"candidates": []}).get("candidates", [])
        if not isinstance(source, list):
            return []
        preferred_area = constraints.get("preferred_area") or constraints.get("area")
        results: list[tuple[float, Dict[str, Any]]] = []
        for row in source:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get(key) or "") for key in ("name", "category", "gaode_type", "semantic_summary", "address"))
            if not any(term in text for term in query_terms):
                continue
            poi_id = str(row.get("poi_id") or self._runtime_id(row.get("name") or text))
            if poi_id in existing:
                continue
            item = self._to_mock_poi(row, activity_match, preferred_area, scenario, poi_id)
            score = 1.0 + sum(0.3 for term in query_terms if term in text)
            results.append((score, item))
        return [item for _, item in sorted(results, key=lambda pair: -pair[0])[:limit]]

    def _remote_candidates(
        self,
        query_terms: list[str],
        activity_match: Dict[str, Any],
        constraints: Dict[str, Any],
        existing: set[str],
        limit: int,
    ) -> list[Dict[str, Any]]:
        key = os.getenv("AMAP_KEY", "").strip()
        if not key or limit <= 0:
            return []
        results: list[Dict[str, Any]] = []
        for term in query_terms:
            if len(results) >= limit:
                break
            try:
                params = urlencode({"key": key, "keywords": term, "city": self.city, "citylimit": "true", "offset": min(10, limit), "page": 1, "extensions": "base"})
                with urlopen(f"https://restapi.amap.com/v3/place/text?{params}", timeout=4.0) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            for row in payload.get("pois") or []:
                name = str(row.get("name") or "")
                if not name:
                    continue
                poi_id = self._runtime_id(name)
                if poi_id in existing:
                    continue
                existing.add(poi_id)
                results.append(self._to_mock_poi(row, activity_match, constraints.get("preferred_area") or constraints.get("area"), None, poi_id))
                if len(results) >= limit:
                    break
        return results

    def _to_mock_poi(
        self,
        row: Dict[str, Any],
        activity_match: Dict[str, Any],
        preferred_area: Optional[str],
        scenario: Optional[str],
        poi_id: str,
    ) -> Dict[str, Any]:
        name = str(row.get("name") or "高德补充活动候选")
        tags = ["gaode_runtime", "activity_supplement", "indoor"]
        if set(activity_match.get("parent_categories") or []) & {"SPORTS"}:
            tags.append("sports")
        if set(activity_match.get("parent_categories") or []) & {"GAME", "SOCIAL_ENTERTAINMENT"}:
            tags.extend(["group_ok", "low_fit_activity"])
        if activity_match.get("child_suitable_required"):
            tags.append("needs_child_review")
        area = str(row.get("business_area") or preferred_area or "下沙")
        location_value = str(row.get("location") or "")
        lng, lat = self._parse_location(location_value)
        return {
            "poi_id": poi_id,
            "name": name,
            "category": "activity",
            "sub_category": str(row.get("type") or row.get("gaode_type") or "活动场馆"),
            "tags": tags,
            "location": {"lat": lat, "lng": lng, "area": area},
            "area": area,
            "address": str(row.get("address") or ""),
            "suitable_scenarios": _dedupe([scenario or "friend_group", "fallback_unknown", "city_light_explore"]),
            "price_per_person": 80,
            "rating": 4.2,
            "opening_hours": "10:00-22:00",
            "risk_tags": ["mock_generated"],
            "mock_only": True,
            "source": "gaode_activity_provider",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "activity_features": {
                "raw_activity_terms": activity_match.get("raw_terms") or [],
                "activity_type_ids": activity_match.get("activity_type_ids") or [],
                "parent_categories": activity_match.get("parent_categories") or [],
                "facility_types": activity_match.get("facility_types") or [],
                "genres": activity_match.get("genres") or [],
                "styles": activity_match.get("styles") or [],
                "scenes": activity_match.get("scenes") or [],
                "intensity": activity_match.get("intensity") or "unknown",
                "physical_intensity": 0.55,
                "indoor": True,
                "booking_required": True,
                "child_activity_score": 0.35 if activity_match.get("child_suitable_required") else 0.5,
                "elderly_activity_score": 0.25 if activity_match.get("elderly_suitable_required") else 0.45,
                "noise_level": 0.6,
                "quiet_score": 0.3,
            },
        }

    def _persist_runtime(self, items: list[Dict[str, Any]]) -> None:
        document = self.store.read(RUNTIME_ACTIVITY_POIS_PATH, {"version": "runtime_activity_pois.v1", "pois": []})
        existing = document.get("pois") if isinstance(document, dict) else []
        if not isinstance(existing, list):
            existing = []
        seen = {str(item.get("poi_id")) for item in existing if isinstance(item, dict)}
        merged = list(existing)
        for item in items:
            poi_id = str(item.get("poi_id") or "")
            if poi_id and poi_id not in seen:
                merged.append(item)
                seen.add(poi_id)
        self.store.write(RUNTIME_ACTIVITY_POIS_PATH, {"version": "runtime_activity_pois.v1", "pois": merged[-80:]})

    def _runtime_id(self, text: str) -> str:
        digest = hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:10]
        return f"poi_runtime_activity_{digest}"

    def _parse_location(self, value: str) -> tuple[float, float]:
        if "," in value:
            try:
                lng, lat = value.split(",", 1)
                return float(lng), float(lat)
            except ValueError:
                pass
        return 120.319, 30.309


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
