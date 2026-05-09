"""
Stats API — analytics derived from the telemetry linked-list in Swarm.

GET  /stats/hotspots       — all geo-tagged delivery violations (heatmap data)
POST /stats/analyze-route  — risk analysis for a proposed delivery route
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.geo import haversine_km
from storage.swarm import download_json, list_all_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["Stats"])

# Maximum number of telemetry nodes to traverse per device to bound latency.
_MAX_DEPTH = 200

# Radius (km) within which a waypoint is considered "near" a violation hotspot.
_RISK_RADIUS_KM = 2.0


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Waypoint(BaseModel):
    lat: float
    lon: float


class RouteRequest(BaseModel):
    waypoints: list[Waypoint]


class RouteAnalysisResponse(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    warnings: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _collect_hotspots() -> list[dict]:
    """Traverse all devices' telemetry and return violation hotspot records."""
    hotspots: list[dict] = []
    all_entries = await list_all_entries()

    for device_id, entry in all_entries.items():
        current_hash: str | None = entry.get("latest_telemetry_hash")
        depth = 0

        while current_hash and depth < _MAX_DEPTH:
            depth += 1
            try:
                record = await download_json(current_hash)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to fetch telemetry %s for device %s: %s",
                    current_hash, device_id, exc,
                )
                break

            if not record.get("is_valid", True):
                readings = record.get("readings", {})
                lat = readings.get("lat")
                lon = readings.get("lon")
                if lat is not None and lon is not None:
                    hotspots.append(
                        {
                            "lat": lat,
                            "lon": lon,
                            "device_id": record.get("device_id", device_id),
                            "reason": record.get("reason", ""),
                        }
                    )

            current_hash = record.get("prev_hash")

    return hotspots


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/hotspots")
async def get_hotspots():
    """
    Return all geo-tagged delivery violations across all tracked devices.

    Response shape::

        {
          "hotspots": [
            {"lat": 50.07, "lon": 14.43, "device_id": "tracker-001", "reason": "..."},
            ...
          ]
        }
    """
    return {"hotspots": await _collect_hotspots()}


@router.post("/analyze-route", response_model=RouteAnalysisResponse)
async def analyze_route(body: RouteRequest) -> RouteAnalysisResponse:
    """
    Evaluate risk level of a proposed delivery route.

    Loads all historical violation hotspots and checks whether any waypoint
    falls within ``_RISK_RADIUS_KM`` km of a known hotspot. Returns a risk
    summary and a list of human-readable warnings.

    Risk levels:
      - ``LOW``    — 0 waypoints near a hotspot
      - ``MEDIUM`` — 1–2 waypoints near a hotspot
      - ``HIGH``   — 3 or more waypoints near a hotspot
    """
    hotspots = await _collect_hotspots()
    warnings: list[str] = []

    for wp in body.waypoints:
        for hs in hotspots:
            dist = haversine_km(wp.lat, wp.lon, hs["lat"], hs["lon"])
            if dist <= _RISK_RADIUS_KM:
                warnings.append(
                    f"Route passes near a historical violation zone at "
                    f"[{hs['lat']}, {hs['lon']}]"
                )
                # Count each waypoint at most once per hotspot match to avoid
                # duplicate warnings from the same hs appearing multiple times
                break

    hit_count = len(warnings)
    if hit_count == 0:
        risk_level = "LOW"
    elif hit_count <= 2:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return RouteAnalysisResponse(risk_level=risk_level, warnings=warnings)
