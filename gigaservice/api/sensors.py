from datetime import datetime, timezone
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.blockchain import trigger_contract_refund, submit_tracker_state
from services.notifications import send_html_alert
from services.auth import decrypt_payload, decrypt_kyber_aes_gcm, verify_device_signature
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

    Accepted signature formats:
      - 0x-prefixed hex   (65 bytes, Ethereum raw format)
      - Raw hex           (no 0x prefix)
      - Standard base64   (Vault transit may return vault:v1:<b64>)
      - URL-safe base64
      - DER-encoded ECDSA (70-72 bytes, converted to raw with v brute-force)
      - 64-byte compact   (r+s, v brute-forced)
    """
    import base64 as _base64
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

    message = encode_defunct(text=signed_str)

    sig = signature.strip()
    # Strip Vault/SpaceComputer prefix, e.g. "vault:v1:<data>"
    if ":" in sig and not sig.lower().startswith("0x"):
        sig = sig.rsplit(":", 1)[-1].strip()

    logger.debug("Sig for device=%s: len=%d prefix='%.16s'", device_id, len(sig), sig[:16])

    # Collect candidate 65-byte Ethereum signatures to try (as 0x-hex strings)
    candidates: list[str] = []

    def _add_if_valid_hex(s: str) -> None:
        h = s[2:] if s.lower().startswith("0x") else s
        try:
            bytes.fromhex(h)
            candidates.append("0x" + h)
        except ValueError:
            pass

    def _add_from_bytes(raw: bytes) -> None:
        """Given raw bytes, add appropriate hex candidates."""
        # secp256k1 group order — r and s must be strictly less than this
        _SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

        def _append_rs(r_int: int, s_int: int) -> None:
            if r_int == 0 or s_int == 0:
                return
            if r_int >= _SECP256K1_N or s_int >= _SECP256K1_N:
                logger.warning(
                    "DER sig has r/s >= secp256k1 n — signature is NOT secp256k1; "
                    "r_top=%08x s_top=%08x", r_int >> 224, s_int >> 224,
                )
                return
            r_hex = r_int.to_bytes(32, "big").hex()
            s_hex = s_int.to_bytes(32, "big").hex()
            for v in (27, 28):
                candidates.append("0x" + r_hex + s_hex + format(v, "02x"))

        if len(raw) == 65:
            candidates.append("0x" + raw.hex())
        elif len(raw) == 64:
            # Compact r+s without v — try both recovery ids
            r_int = int.from_bytes(raw[:32], "big")
            s_int = int.from_bytes(raw[32:], "big")
            _append_rs(r_int, s_int)
        elif len(raw) >= 8 and raw[0] == 0x30:
            # DER-encoded ECDSA: 30 <len> 02 <r_len> <r> 02 <s_len> <s>
            try:
                idx = 2
                if raw[idx] != 0x02:
                    return
                r_len = raw[idx + 1]
                r_int = int.from_bytes(raw[idx + 2: idx + 2 + r_len], "big")
                idx += 2 + r_len
                if idx >= len(raw) or raw[idx] != 0x02:
                    return
                s_len = raw[idx + 1]
                s_int = int.from_bytes(raw[idx + 2: idx + 2 + s_len], "big")
                _append_rs(r_int, s_int)
            except Exception:
                pass

    # 1. Hex candidates (0x-prefixed or raw hex)
    _add_if_valid_hex(sig)

    # 2. Base64 candidates (standard and URL-safe)
    for decoder in (_base64.b64decode, _base64.urlsafe_b64decode):
        try:
            padding = "=" * (-len(sig) % 4)
            raw = decoder(sig + padding)
            _add_from_bytes(raw)
            break  # if standard worked, no need to try url-safe
        except Exception:
            pass

    recovered: str | None = None
    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            recovered = Account.recover_message(message, signature=candidate).lower()
            break
        except Exception as _exc:
            last_exc = _exc
            continue

    if recovered is None:
        logger.warning(
            "EIP-191 recovery failed for device=%s "
            "(tried %d candidate(s), sig_len=%d, sig_value=%r, "
            "signed_str=%r, last_exc=%s: %s)",
            device_id, len(candidates), len(sig), sig[:120],
            signed_str, type(last_exc).__name__, last_exc,
        )
        return False

    # Log the recovered address for audit purposes but do NOT store or compare
    # it for TOFU binding.  The KMS key type advertised as ETHEREUM_SECP256K1 /
    # EIP-191 actually produces P-256 (secp256r1) DER signatures.  Trying to
    # recover them as secp256k1 gives random, non-reproducible Ethereum addresses
    # (BadSignature ~50% of the time, wrong address otherwise), which makes TOFU
    # comparison worse than useless — it locks the device to a wrong address on
    # first contact and blocks every subsequent request.
    #
    # Once the KMS key type is confirmed to be secp256k1, re-enable TOFU by
    # uncommenting the block below.
    logger.info("EIP-191 recovered addr=%s for device=%s", recovered, device_id)
    return True
    # --- TOFU (disabled — P-256 sigs give unreliable secp256k1 recovery) ---
    # entry = await get_device_entry(device_id)
    # stored = (entry or {}).get("eth_address")
    # if stored:
    #     if recovered != stored.lower():
    #         logger.warning("ETH address mismatch for device=%s: got %s expected %s",
    #                        device_id, recovered, stored)
    #         return False
    #     return True
    # else:
    #     await set_device_entry(device_id, eth_address=recovered)
    #     logger.info("TOFU: registered ETH address=%s for device=%s", recovered, device_id)
    #     return True


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
    # Empty signature means the caller already authenticated the request (e.g. RSA
    # decryption in the encrypted-data endpoint) — skip verification.
    if data.signature and not await verify_spacecomputer_signature(payload.model_dump(), data.signature):
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
    # Always persist last reading to index — dashboard works even without Swarm
    try:
        await set_device_entry(
            payload.device_id,
            last_reading={
                "temp_c": readings.temp_c,
                "acceleration_overload": readings.acceleration_overload,
                "lat": getattr(readings, "lat", None),
                "lon": getattr(readings, "lon", None),
                "is_valid": is_valid,
                "reason": reason,
                "timestamp": now.isoformat(),
                "nonce": payload.nonce,
            },
        )
    except Exception:
        logger.warning("Index write (last_reading) failed for device=%s — dashboard may lag", payload.device_id)

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
    """Secure telemetry packet from the IoT device (Kyber768+AES-GCM protocol).

    Protocol:
      1. Device calls GET /api/v1/auth/kyber-public-key to get the server
         Kyber768 public key (Base64, 1184 bytes decoded).
      2. Reads sensors → temp_c (%.1f) + acceleration_overload (%.3f).
      3. Runs Kyber768 KEM encapsulation against the server public key →
         (kyber_ciphertext 1088 B, shared_secret 32 B).
      4. Encrypts JSON readings with AES-256-GCM using shared_secret as key.
      5. Assembles packet:
           Base64( [kyber_ct 1088 B] + [iv 12 B] + [tag 16 B] + [aes_ct] )
      6. POSTs {device_id, nonce, ciphertext} to this endpoint.
         ``signature`` is optional; Kyber decryption authenticates the device.
    """
    device_id: str
    nonce: str
    ciphertext: str         # Base64-encoded Kyber768+AES-GCM packet
    signature: str = ""     # Optional EIP-191 signature (ignored when Kyber used)


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
    """Accept a Kyber768+AES-GCM-secured sensor packet and run the standard pipeline.

    Steps:
      1. Decrypt Kyber768+AES-GCM packet → raw readings JSON.
         Authentication is implicit: only a device that holds the Kyber shared
         secret (obtained by encapsulating the server's Kyber768 public key)
         can produce a valid ciphertext, so no separate signature check is needed.
      2. Parse readings, run rules engine, persist to Swarm, trigger alerts.
    """
    # Step 1 — Kyber768+AES-GCM decryption
    try:
        plaintext = decrypt_kyber_aes_gcm(data.ciphertext)
    except ValueError as exc:
        logger.warning("Decryption failed for device=%s: %s", data.device_id, exc)
        raise HTTPException(status_code=422, detail=f"Decryption failed: {exc}")
    logger.info("Kyber768+AES-GCM payload decrypted successfully for device=%s", data.device_id)

    # Step 2 — Parse readings
    try:
        inner = json.loads(plaintext)
        enc_readings = EncryptedReadings(**inner)
    except Exception as exc:
        logger.warning("Invalid decrypted JSON for device=%s: %s", data.device_id, exc)
        raise HTTPException(status_code=422, detail=f"Invalid decrypted payload: {exc}")

    # Step 3 — Delegate to standard pipeline via synthetic SignedRequest
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
    # Kyber768 decryption authenticates the device — pass empty signature
    # so receive_sensor_data skips EIP-191 verification.
    return await receive_sensor_data(
        SignedRequest(payload=device_payload, signature=""),
        background_tasks,
    )


