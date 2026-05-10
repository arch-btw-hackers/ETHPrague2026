import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import RequiresAttestation, RoleChecker, get_current_user
from services.blockchain import resolve_ens, create_shipment_on_chain
from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

router = APIRouter(prefix="/packages", tags=["Packages"])

# Schema UID for "Certified Courier" attestation.
# Override via EAS_COURIER_SCHEMA env var. Falls back to zero UID when not set
# (EAS returns no logs for zero UID — attestation gate is effectively open).
_raw_schema = os.environ.get("EAS_COURIER_SCHEMA")
if not _raw_schema:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "EAS_COURIER_SCHEMA is not set — using zero UID (attestation gate disabled)"
    )
COURIER_SCHEMA_ID: str = _raw_schema or ("0x" + "00" * 32)


class DeliveryConditions(BaseModel):
    device_id: str
    max_temp_c: float
    max_acceleration: float


class PackageResponse(BaseModel):
    device_id: str
    swarm_hash: str


class PackageContractInit(BaseModel):
    """Internal model passed to create_shipment_on_chain."""
    package_ref: str
    receiver_wallet: str
    tracker_service_wallet: str


class ShipmentInitRequest(BaseModel):
    """What the caller sends to POST /initialize."""
    temp_c: float
    acceleration: float
    receiver_wallet: str | None = None       # Ethereum address of the receiver
    tracker_service_wallet: str | None = None  # Ethereum address of tracker service


class ShipmentInitResponse(BaseModel):
    """What the server returns after registering the shipment on-chain."""
    package_ref: str
    tx_hash: str
    shipment_id: int | None = None


@router.post("/", response_model=PackageResponse)
async def create_package(
    conditions: DeliveryConditions,
    user: dict = Depends(RoleChecker(["provider", "admin"])),
):
    # Auto-resolve ENS names (e.g. "tracker.eth") to a 0x address.
    # Non-ENS identifiers are returned unchanged by resolve_ens.
    try:
        device_id = await resolve_ens(conditions.device_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    swarm_hash = await upload_json(conditions.model_dump())
    await set_device_entry(device_id, conditions_hash=swarm_hash, latest_telemetry_hash=None)
    return PackageResponse(device_id=device_id, swarm_hash=swarm_hash)


@router.post("/initialize", response_model=ShipmentInitResponse)
async def initialize_package_on_chain(req: ShipmentInitRequest):
    """Register a new shipment on-chain. No auth required."""
    package_ref = str(uuid.uuid4())

    # Default wallets: use the server's own address for both if not provided
    server_address = os.environ.get("SERVER_ADDRESS", "0x0000000000000000000000000000000000000000")
    receiver = req.receiver_wallet or server_address
    tracker_svc = req.tracker_service_wallet or server_address

    data = PackageContractInit(
        package_ref=package_ref,
        receiver_wallet=receiver,
        tracker_service_wallet=tracker_svc,
    )
    try:
        tx_hash = await create_shipment_on_chain(data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Blockchain error: {exc}")
    return ShipmentInitResponse(
        package_ref=package_ref,
        tx_hash=tx_hash,
    )


@router.get("/{device_id}")
async def get_package(device_id: str):
    entry = await get_device_entry(device_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"device_id": device_id, "swarm_hash": entry["conditions_hash"]}


@router.get("/{device_id}/history")
async def get_package_history(
    device_id: str,
    user: dict = Depends(RequiresAttestation(COURIER_SCHEMA_ID)),
):
    """
    Traverse the telemetry linked list stored in Swarm.
    Each record contains a 'prev_hash' pointing to the previous entry.
    Returns a chronological list (oldest first) for frontend charts.
    """
    entry = await get_device_entry(device_id)
    if not entry or not entry.get("latest_telemetry_hash"):
        raise HTTPException(status_code=404, detail="No telemetry found for this device")

    records = []
    current_hash = entry["latest_telemetry_hash"]

    while current_hash:
        record = await download_json(current_hash)
        records.append(record)
        current_hash = record.get("prev_hash")

    records.reverse()  # oldest first
    return {"device_id": device_id, "count": len(records), "history": records}

