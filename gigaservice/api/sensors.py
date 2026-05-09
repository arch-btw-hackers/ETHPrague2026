from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

router = APIRouter(prefix="/sensors", tags=["Sensors"])


# ---------------------------------------------------------------------------
# Conditions cache — avoids a Swarm download on every telemetry packet
# ---------------------------------------------------------------------------

CONDITIONS_CACHE: dict[str, dict] = {}


async def _get_conditions(conditions_hash: str) -> dict:
    if conditions_hash not in CONDITIONS_CACHE:
        CONDITIONS_CACHE[conditions_hash] = await download_json(conditions_hash)
    return CONDITIONS_CACHE[conditions_hash]


# ---------------------------------------------------------------------------
# SpaceComputer KMS — signature verification stub
# ---------------------------------------------------------------------------

async def verify_spacecomputer_signature(payload: dict, signature: str) -> bool:
    """
    TODO: call SpaceComputer KMS.
    Stub: always returns True.
    """
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Readings(BaseModel):
    temp_c: float
    acceleration_x: float
    acceleration_y: float


class DevicePayload(BaseModel):
    device_id: str
    nonce: int
    readings: Readings


class SignedRequest(BaseModel):
    payload: DevicePayload
    signature: str


class SensorResponse(BaseModel):
    received: bool
    device_id: str
    is_valid: bool
    timestamp: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/data", response_model=SensorResponse)
async def receive_sensor_data(data: SignedRequest):
    payload = data.payload
    readings = payload.readings

    # 1. Signature check via SpaceComputer KMS
    if not await verify_spacecomputer_signature(payload.model_dump(), data.signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Load package conditions — from cache or Swarm
    entry = await get_device_entry(payload.device_id)
    if not entry or not entry.get("conditions_hash"):
        raise HTTPException(
            status_code=404,
            detail=f"No active package for device '{payload.device_id}'",
        )

    conditions = await _get_conditions(entry["conditions_hash"])

    # 3. Rules engine
    is_valid = True
    if readings.temp_c > conditions["max_temp_c"]:
        is_valid = False
    if abs(readings.acceleration_x) > conditions["max_acceleration"]:
        is_valid = False
    if abs(readings.acceleration_y) > conditions["max_acceleration"]:
        is_valid = False

    # 4. Persist telemetry to Swarm (linked list via prev_hash)
    now = datetime.now(timezone.utc)
    record = {
        **payload.model_dump(),
        "is_valid": is_valid,
        "timestamp": now.isoformat(),
        "prev_hash": entry.get("latest_telemetry_hash"),
    }
    new_hash = await upload_json(record)

    # 5. Update index atomically.
    #    If this fails after the Swarm write, the linked list is inconsistent.
    #    Return 500 so the tracker can retry with the same nonce.
    try:
        await set_device_entry(payload.device_id, latest_telemetry_hash=new_hash)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Index write failed after Swarm upload. Please retry.",
        ) from exc

    print(
        f"Device: {payload.device_id} | Temp: {readings.temp_c} | "
        f"AccX: {readings.acceleration_x} | AccY: {readings.acceleration_y} | "
        f"Valid: {is_valid} | Hash: {new_hash[:8]}..."
    )

    return SensorResponse(
        received=True,
        device_id=payload.device_id,
        is_valid=is_valid,
        timestamp=now,
    )


@router.get("/latest/{device_id}")
async def get_latest(device_id: str):
    entry = await get_device_entry(device_id)
    if not entry or not entry.get("latest_telemetry_hash"):
        raise HTTPException(status_code=404, detail="No telemetry found")
    return await download_json(entry["latest_telemetry_hash"])


