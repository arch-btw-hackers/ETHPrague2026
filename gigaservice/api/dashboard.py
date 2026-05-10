"""
Dashboard API — aggregated live view of all devices for the frontend.

GET /dashboard/devices           — all devices with latest telemetry snapshot
GET /dashboard/devices/{id}      — single device + last N telemetry records
GET /dashboard/stream            — Server-Sent Events live stream (2 s interval)
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
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


async def _fetch_latest(hash_: str) -> dict | None:
    try:
        return await download_json(hash_)
    except Exception as exc:
        logger.warning("Could not fetch telemetry %s from Swarm: %s", hash_, exc)
        return None


def _summary_from_index(device_id: str, entry: dict) -> DeviceSummary:
    """Build a DeviceSummary from the index entry (no Swarm call needed)."""
    lr = entry.get("last_reading") or {}
    reading = LatestReading(
        temp_c=lr.get("temp_c"),
        acceleration_overload=lr.get("acceleration_overload"),
        lat=lr.get("lat"),
        lon=lr.get("lon"),
    ) if lr else None
    return DeviceSummary(
        device_id=device_id,
        conditions_hash=entry.get("conditions_hash"),
        latest_telemetry_hash=entry.get("latest_telemetry_hash"),
        latest_reading=reading,
        is_valid=lr.get("is_valid"),
        reason=lr.get("reason"),
        timestamp=lr.get("timestamp"),
        nonce=lr.get("nonce"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/devices", response_model=list[DeviceSummary])
async def list_devices():
    """Return all registered devices with their latest telemetry snapshot.

    Uses last_reading cached in the index — works even when Swarm is down.
    """
    index = await list_all_entries()
    return [
        _summary_from_index(device_id, entry)
        for device_id, entry in index.items()
        if not device_id.startswith(_TRACKER_PREFIX)
    ]


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


@router.get("/stream")
async def stream_devices(
    request: Request,
    interval: float = Query(default=0.5, ge=0.5, le=60.0, description="Push interval in seconds"),
):
    """Server-Sent Events stream — pushes all device snapshots every `interval` seconds.

    Frontend usage:
        const es = new EventSource('/api/v1/dashboard/stream');
        es.onmessage = e => {
            const devices = JSON.parse(e.data);
            // devices is the same shape as GET /dashboard/devices
        };
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                index = await list_all_entries()
                devices = [
                    _summary_from_index(device_id, entry).model_dump()
                    for device_id, entry in index.items()
                    if not device_id.startswith(_TRACKER_PREFIX)
                ]
                yield f"data: {json.dumps(devices)}\n\n"
            except Exception as exc:
                logger.warning("SSE push error: %s", exc)
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
