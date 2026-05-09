from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage.swarm import upload_json

router = APIRouter(prefix="/packages", tags=["Packages"])

# device_id -> swarm_hash условий доставки
ACTIVE_PACKAGES: dict[str, str] = {}


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
    ACTIVE_PACKAGES[conditions.device_id] = swarm_hash
    return PackageResponse(device_id=conditions.device_id, swarm_hash=swarm_hash)


@router.get("/{device_id}")
def get_package(device_id: str):
    swarm_hash = ACTIVE_PACKAGES.get(device_id)
    if not swarm_hash:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"device_id": device_id, "swarm_hash": swarm_hash}
