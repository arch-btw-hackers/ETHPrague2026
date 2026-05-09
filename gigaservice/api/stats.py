"""
Stats API — analytics derived from the telemetry linked-list in Swarm.

GET /stats/hotspots
  Traverses all devices' telemetry histories, collects records where
  is_valid == False and GPS coordinates are present, and returns them
  as a structured list for route-analytics / heatmap rendering.
"""
import logging

from fastapi import APIRouter

from storage.swarm import download_json, list_all_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["Stats"])

# Maximum number of telemetry nodes to traverse per device to bound latency.
_MAX_DEPTH = 200


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

    return {"hotspots": hotspots}
