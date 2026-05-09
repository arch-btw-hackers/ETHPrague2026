from datetime import datetime, timezone
import base64
import json
import logging
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.blockchain import trigger_contract_refund
from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

logger = logging.getLogger(__name__)

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
# SpaceComputer KMS — ECDSA P-256 signature verification
# ---------------------------------------------------------------------------

def _load_public_key():
    """Load the device's ECDSA P-256 public key from the environment.

    Returns the key object, or None when the env var is not set (dev mode).
    """
    pem = os.environ.get("DEVICE_PUBLIC_KEY_PEM", "").strip()
    if not pem:
        return None
    # Allow \\n escapes so the key fits on a single .env line
    pem = pem.replace("\\n", "\n")
    return serialization.load_pem_public_key(pem.encode())


async def verify_spacecomputer_signature(payload: dict, signature: str) -> bool:
    """Verify an ECDSA P-256 / SHA-256 signature from the IoT tracker.

    The message is the canonical JSON of the payload dict (keys sorted
    alphabetically, no whitespace) encoded as UTF-8.

    Returns True on valid signature.
    Returns True (with a warning) when DEVICE_PUBLIC_KEY_PEM is not set.
    Returns False when the signature is invalid or malformed.
    """
    public_key = _load_public_key()
    if public_key is None:
        logger.warning(
            "DEVICE_PUBLIC_KEY_PEM not set — skipping signature verification (dev mode)"
        )
        return True

    # Canonical message: alphabetically sorted keys, no whitespace
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    try:
        sig_bytes = base64.b64decode(signature, validate=True)
    except Exception:
        logger.debug("Signature is not valid Base64")
        return False

    try:
        public_key.verify(sig_bytes, message, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


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
async def receive_sensor_data(data: SignedRequest, background_tasks: BackgroundTasks):
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

    # 6. If conditions were violated, trigger contract refund in the background
    if not is_valid:
        background_tasks.add_task(trigger_contract_refund, payload.device_id)

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


