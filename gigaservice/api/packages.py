import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import RequiresAttestation, RoleChecker, get_current_user
from services.blockchain import resolve_ens
from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

router = APIRouter(prefix="/packages", tags=["Packages"])

# Schema UID for "Certified Courier" attestation.
# EAS_COURIER_SCHEMA must be set — the service refuses to start without it.
COURIER_SCHEMA_ID: str = os.environ["EAS_COURIER_SCHEMA"]


class DeliveryConditions(BaseModel):
    device_id: str
    max_temp_c: float
    max_acceleration: float


class PackageResponse(BaseModel):
    device_id: str
    swarm_hash: str


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

