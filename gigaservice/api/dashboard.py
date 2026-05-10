"""
Dashboard API — aggregated live view of all devices for the frontend.

GET /dashboard/devices           — all devices with latest telemetry snapshot
GET /dashboard/devices/{id}      — single device + last N telemetry records
"""
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from storage.swarm import download_json, list_all_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

_TRACKER_PREFIX = "__tracker__"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class LatestReading(BaseModel):
    temp_c: float | None = None
    acceleration_overload: float | None = None
    lat: float | None = None
    lon: float | None = None


class DeviceSummary(BaseModel):
    device_id: str
    conditions_hash: str | None = None
    latest_telemetry_hash: str | None = None
    latest_reading: LatestReading | None = None
    is_valid: bool | None = None
    reason: str | None = None
    timestamp: str | None = None
    nonce: str | None = None


class TelemetryRecord(BaseModel):
    device_id: str
    nonce: str | None = None
    temp_c: float | None = None
    acceleration_overload: float | None = None
    lat: float | None = None
    lon: float | None = None
    is_valid: bool | None = None
    reason: str | None = None
    timestamp: str | None = None
    swarm_hash: str | None = None


class DeviceDetail(BaseModel):
    device_id: str
    conditions_hash: str | None = None
    latest_telemetry_hash: str | None = None
    history: list[TelemetryRecord]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_reading(record: dict) -> tuple[LatestReading, bool | None, str | None, str | None, str | None]:
    readings = record.get("readings") or {}
    return (
        LatestReading(
            temp_c=readings.get("temp_c"),
            acceleration_overload=readings.get("acceleration_overload"),
            lat=readings.get("lat"),
            lon=readings.get("lon"),
        ),
        record.get("is_valid"),
        record.get("reason"),
        record.get("timestamp"),
        record.get("nonce"),
    )


async def _fetch_latest(hash_: str) -> dict | None:
    try:
        return await download_json(hash_)
    except Exception as exc:
        logger.warning("Could not fetch telemetry %s from Swarm: %s", hash_, exc)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/devices", response_model=list[DeviceSummary])
async def list_devices():
    """Return all registered devices with their latest telemetry snapshot.

    Works even when Swarm is unavailable — in that case latest_reading will
    be null but the device_id and hash are still returned.
    """
    index = await list_all_entries()
    result: list[DeviceSummary] = []

    for device_id, entry in index.items():
        # Skip tracker metadata entries (registered via /trackers/)
        if device_id.startswith(_TRACKER_PREFIX):
            continue

        latest_hash: str | None = entry.get("latest_telemetry_hash")
        reading: LatestReading | None = None
        is_valid: bool | None = None
        reason: str | None = None
        timestamp: str | None = None
        nonce: str | None = None

        if latest_hash:
            record = await _fetch_latest(latest_hash)
            if record:
                reading, is_valid, reason, timestamp, nonce = _extract_reading(record)

        result.append(DeviceSummary(
            device_id=device_id,
            conditions_hash=entry.get("conditions_hash"),
            latest_telemetry_hash=latest_hash,
            latest_reading=reading,
            is_valid=is_valid,
            reason=reason,
            timestamp=timestamp,
            nonce=nonce,
        ))

    return result


@router.get("/devices/{device_id}", response_model=DeviceDetail)
async def get_device(
    device_id: str,
    limit: int = Query(default=20, ge=1, le=200, description="Max telemetry records to return"),
):
    """Return a single device with its last `limit` telemetry records (newest first).

    Telemetry is stored as a linked list in Swarm — each record has a
    prev_hash pointing to the previous entry.
    """
    index = await list_all_entries()
    entry = index.get(device_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    history: list[TelemetryRecord] = []
    current_hash: str | None = entry.get("latest_telemetry_hash")
    depth = 0

    while current_hash and depth < limit:
        record = await _fetch_latest(current_hash)
        if not record:
            break

        readings = record.get("readings") or {}
        history.append(TelemetryRecord(
            device_id=record.get("device_id", device_id),
            nonce=record.get("nonce"),
            temp_c=readings.get("temp_c"),
            acceleration_overload=readings.get("acceleration_overload"),
            lat=readings.get("lat"),
            lon=readings.get("lon"),
            is_valid=record.get("is_valid"),
            reason=record.get("reason"),
            timestamp=record.get("timestamp"),
            swarm_hash=current_hash,
        ))

        current_hash = record.get("prev_hash")
        depth += 1

    return DeviceDetail(
        device_id=device_id,
        conditions_hash=entry.get("conditions_hash"),
        latest_telemetry_hash=entry.get("latest_telemetry_hash"),
        history=history,
    )
