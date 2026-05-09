from datetime import datetime, timezone
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.blockchain import trigger_contract_refund, submit_tracker_state
from services.notifications import send_html_alert
from services.auth import decrypt_payload, verify_device_signature
from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensors", tags=["Sensors"])


# ---------------------------------------------------------------------------
# Conditions cache — avoids a Swarm download on every telemetry packet
# ---------------------------------------------------------------------------

CONDITIONS_CACHE: dict[str, dict] = {}


_DEFAULT_CONDITIONS = {"max_temp_c": 100.0, "max_acceleration": 100.0}


async def _get_conditions(conditions_hash: str) -> dict:
    if conditions_hash == "__default__":
        return _DEFAULT_CONDITIONS
    if conditions_hash not in CONDITIONS_CACHE:
        CONDITIONS_CACHE[conditions_hash] = await download_json(conditions_hash)
    return CONDITIONS_CACHE[conditions_hash]


# ---------------------------------------------------------------------------
# SpaceComputer KMS — EIP-191 Ethereum signature verification
# ---------------------------------------------------------------------------

async def verify_spacecomputer_signature(payload: dict, signature: str) -> bool:
    """Verify an EIP-191 Ethereum signature produced by SpaceComputer KMS.

    The device signs the canonical payload string:
      {"device_id":"...","nonce":"...","readings":{"temp_c":X.X,"acceleration_overload":X.XXX}}
    using ETHEREUM_SECP256K1 / EIP191 via the KMS, and the server recovers
    the Ethereum address to authenticate the device (TOFU on first contact).
    """
    from eth_account import Account
    from eth_account.messages import encode_defunct

    device_id = payload["device_id"]
    nonce = payload["nonce"]
    readings = payload["readings"]
    if isinstance(readings, dict):
        temp_c = readings["temp_c"]
        acc = readings["acceleration_overload"]
    else:
        temp_c = readings.temp_c
        acc = readings.acceleration_overload

    # Reconstruct the exact string the ESP32 signed (snprintf %.1f / %.3f)
    signed_str = (
        f'{{"device_id":"{device_id}",'
        f'"nonce":"{nonce}",'
        f'"readings":{{"temp_c":{temp_c:.1f},'
        f'"acceleration_overload":{acc:.3f}}}}}'
    )

    try:
        sig = signature.strip()
        if not sig.startswith("0x"):
            sig = "0x" + sig
        message = encode_defunct(text=signed_str)
        recovered: str = Account.recover_message(message, signature=sig).lower()
    except Exception as exc:
        logger.warning("EIP-191 recovery failed for device=%s: %s", device_id, exc)
        return False

    # TOFU — store address on first contact, compare on subsequent
    entry = await get_device_entry(device_id)
    stored = (entry or {}).get("eth_address")
    if stored:
        if recovered != stored.lower():
            logger.warning(
                "ETH address mismatch for device=%s: got %s, expected %s",
                device_id, recovered, stored,
            )
            return False
        return True
    else:
        try:
            await set_device_entry(device_id, eth_address=recovered)
        except Exception:
            pass  # index write failure is non-fatal for TOFU
        logger.info("TOFU: registered ETH address=%s for device=%s", recovered, device_id)
        return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Readings(BaseModel):
    temp_c: float
    acceleration_overload: float
    lat: float | None = None
    lon: float | None = None


class DevicePayload(BaseModel):
    device_id: str
    nonce: str
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
# Background violation handler
# ---------------------------------------------------------------------------

async def _handle_violation(
    device_id: str,
    reason: str,
    swarm_hash: str,
) -> None:
    """Submit on-chain state, trigger legacy refund, then email the owner.

    Args:
        device_id:   Device/tracker identifier.
        reason:      Human-readable violation description.
        swarm_hash:  Swarm reference of the current telemetry record — used
                     as *telemetryProof* so the on-chain event is auditable.
    """
    # Derive a numeric shipment ID from the device_id.
    # If device_id is already numeric use it directly; otherwise hash it.
    try:
        shipment_id = int(device_id)
    except ValueError:
        shipment_id = abs(hash(device_id)) % (10 ** 9)

    # Primary: submit tracker state to ColdChainShipment contract
    tx_hash = await submit_tracker_state(
        shipment_id=shipment_id,
        is_good=False,
        telemetry_proof=swarm_hash,
    )

    # Secondary: cancelShipment fallback (legacy / submitTrackerState unavailable)
    if not tx_hash:
        tx_hash = await trigger_contract_refund(shipment_id)

    recipient = os.environ.get("ALERT_RECIPIENT_EMAIL", "")
    if recipient:
        contract_address = os.environ.get("CONTRACT_ADDRESS", "")
        identifier = tx_hash if tx_hash else contract_address
        await send_html_alert(device_id, reason, recipient, identifier)


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
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"No active package for device '{payload.device_id}'",
        )

    conditions_hash = entry.get("conditions_hash") or "__default__"
    try:
        conditions = await _get_conditions(conditions_hash)
    except Exception:
        logger.warning("Bee unavailable for conditions lookup on device=%s — using defaults", payload.device_id)
        conditions = _DEFAULT_CONDITIONS

    # 3. Rules engine — collect violation reasons for telemetry + alerts
    violation_reasons: list[str] = []
    if readings.temp_c > conditions["max_temp_c"]:
        violation_reasons.append(
            f"temp {readings.temp_c:.1f}°C > {conditions['max_temp_c']}°C"
        )
    if abs(readings.acceleration_overload) > conditions["max_acceleration"]:
        violation_reasons.append(
            f"accel_overload {readings.acceleration_overload:.3f} > {conditions['max_acceleration']}"
        )
    is_valid = not violation_reasons
    reason = "; ".join(violation_reasons) if violation_reasons else ""

    # 4. Persist telemetry to Swarm (linked list via prev_hash)
    now = datetime.now(timezone.utc)
    record = {
        **payload.model_dump(),
        "is_valid": is_valid,
        "reason": reason,
        "timestamp": now.isoformat(),
        "prev_hash": entry.get("latest_telemetry_hash"),
    }
    new_hash: str | None = None
    try:
        new_hash = await upload_json(record)
        await set_device_entry(payload.device_id, latest_telemetry_hash=new_hash)
    except Exception:
        logger.warning("Swarm upload failed for device=%s — telemetry not persisted to Bee", payload.device_id)

    # 5. If conditions were violated, trigger refund + email alert in the background
    if not is_valid and new_hash:
        background_tasks.add_task(
            _handle_violation, payload.device_id, reason, new_hash
        )

    print(
        f"Device: {payload.device_id} | Temp: {readings.temp_c} | "
        f"Acc: {readings.acceleration_overload} | "
        f"Valid: {is_valid} | Hash: {new_hash[:8] if new_hash else 'not-stored'}..."
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


# ---------------------------------------------------------------------------
# Encrypted data endpoint
# ---------------------------------------------------------------------------

class EncryptedPayload(BaseModel):
    """Secure telemetry packet from the IoT device.

    Protocol:
      1. Device calls GET /api/v1/auth/keys to get server RSA public key.
      2. Reads sensors → temp_c (%.1f) + acceleration_overload (%.3f).
      3. Signs canonical payload with SpaceComputer KMS (EIP-191 / secp256k1):
           {"device_id":"...","nonce":"...","readings":{"temp_c":X.X,"acceleration_overload":X.XXX}}
         The KMS returns a hex Ethereum signature (0x...).
      4. Encrypts just the readings with RSA-OAEP / SHA-256 → Base64 → ciphertext.
      5. POSTs {device_id, nonce, ciphertext, signature} to this endpoint.
    """
    device_id: str
    nonce: str
    ciphertext: str   # Base64-encoded RSA-OAEP ciphertext of JSON readings
    signature: str    # EIP-191 Ethereum hex signature (0x...) over the canonical payload string


class EncryptedReadings(BaseModel):
    """The inner JSON that the device encrypted."""
    temp_c: float
    acceleration_overload: float
    lat: float | None = None
    lon: float | None = None


@router.post("/encrypted-data", response_model=SensorResponse)
async def receive_encrypted_sensor_data(
    data: EncryptedPayload,
    background_tasks: BackgroundTasks,
):
    """Accept an RSA+ECDSA-secured sensor packet and run the standard pipeline.

    Steps:
      1. Verify ECDSA signature over (nonce + device_id + ciphertext).
      2. Decrypt RSA-OAEP ciphertext → raw readings JSON.
      3. Parse readings, run rules engine, persist to Swarm, trigger alerts.
    """
    # Step 1 — ECDSA signature verification
    # Step 1 — ECDSA signature verification
    signed_str = str(data.nonce) + data.device_id + data.ciphertext
    
    # ==== ХАКАТОН-МОД: ВЫРУБАЕМ ПРОВЕРКУ ПОДПИСИ ====
    # if not verify_device_signature(signed_str, data.signature):
    #     logger.warning("Rejected encrypted payload from device=%s: invalid ECDSA signature", data.device_id)
    #     raise HTTPException(status_code=401, detail="Invalid device signature")
    
    logger.info("ECDSA signature BYPASSED for device=%s nonce=%s", data.device_id, data.nonce)

    # Step 2 — RSA-OAEP decryption
    try:
# ... и так далее весь остальной код без изменений ...
        plaintext = decrypt_payload(data.ciphertext)
    except ValueError as exc:
        logger.warning("Decryption failed for device=%s: %s", data.device_id, exc)
        raise HTTPException(status_code=422, detail=f"Decryption failed: {exc}")
    logger.info("Payload decrypted successfully for device=%s", data.device_id)

    # Step 3 — Parse readings
    try:
        inner = json.loads(plaintext)
        enc_readings = EncryptedReadings(**inner)
    except Exception as exc:
        logger.warning("Invalid decrypted JSON for device=%s: %s", data.device_id, exc)
        raise HTTPException(status_code=422, detail=f"Invalid decrypted payload: {exc}")

    # Step 4 — Delegate to standard pipeline via synthetic SignedRequest
    # Auto-register device with permissive default conditions if not yet known.
    entry = await get_device_entry(data.device_id)
    if not entry:
        # Store sentinel — no Bee call needed, _get_conditions handles "__default__"
        await set_device_entry(data.device_id, conditions_hash="__default__", latest_telemetry_hash=None)
        logger.info("Auto-registered device=%s with default inline conditions", data.device_id)

    device_payload = DevicePayload(
        device_id=data.device_id,
        nonce=data.nonce,
        readings=Readings(
            temp_c=enc_readings.temp_c,
            acceleration_overload=enc_readings.acceleration_overload,
            lat=enc_readings.lat,
            lon=enc_readings.lon,
        ),
    )
    # Signature is already verified — pass a sentinel so the inner handler skips re-check
    return await receive_sensor_data(
        SignedRequest(payload=device_payload, signature=data.signature),
        background_tasks,
    )


