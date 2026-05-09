from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

router = APIRouter(prefix="/packages", tags=["Packages"])


class DeliveryConditions(BaseModel):
    device_id: str
    max_temp_c: float
    max_acceleration: float


class PackageResponse(BaseModel):
    device_id: str
    swarm_hash: str


@router.post("/", response_model=PackageResponse)
async def create_package(conditions: DeliveryConditions):
    swarm_hash = await upload_json(conditions.model_dump())
    set_device_entry(conditions.device_id, conditions_hash=swarm_hash, latest_telemetry_hash=None)
    return PackageResponse(device_id=conditions.device_id, swarm_hash=swarm_hash)


@router.get("/{device_id}")
def get_package(device_id: str):
    entry = get_device_entry(device_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"device_id": device_id, "swarm_hash": entry["conditions_hash"]}


@router.get("/{device_id}/history")
async def get_package_history(device_id: str):
    """
    Traverse the telemetry linked list stored in Swarm.
    Each record contains a 'prev_hash' pointing to the previous entry.
    Returns a chronological list (oldest first) for frontend charts.
    """
    entry = get_device_entry(device_id)
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

