from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from storage.swarm import upload_json, download_json
from api.packages import ACTIVE_PACKAGES

router = APIRouter(prefix="/sensors", tags=["Sensors"])


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
    # base64_payload: str  # раскомментируй, если трекер шлёт JSON в base64


class SensorResponse(BaseModel):
    received: bool
    device_id: str
    is_valid: bool
    timestamp: datetime


@router.post("/data", response_model=SensorResponse)
async def receive_sensor_data(data: SignedRequest):
    payload = data.payload
    readings = payload.readings

    # 1. Проверка подписи через SpaceComputer KMS
    # is_valid_sig = await verify_with_spacecomputer(data.payload, data.signature)
    # if not is_valid_sig:
    #     raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. Загружаем условия доставки из Swarm
    conditions_hash = ACTIVE_PACKAGES.get(payload.device_id)
    if not conditions_hash:
        raise HTTPException(status_code=404, detail=f"No active package for device '{payload.device_id}'")

    conditions = await download_json(conditions_hash)

    # 3. Анализ условий
    is_valid = True
    if readings.temp_c > conditions["max_temp_c"]:
        is_valid = False
    if abs(readings.acceleration_x) > conditions["max_acceleration"]:
        is_valid = False
    if abs(readings.acceleration_y) > conditions["max_acceleration"]:
        is_valid = False

    # 4. Сохраняем результат в Swarm
    record = {
        **payload.model_dump(),
        "is_valid": is_valid,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await upload_json(record)

    print(
        f"Device: {payload.device_id} | "
        f"Temp: {readings.temp_c} | "
        f"AccX: {readings.acceleration_x} | "
        f"AccY: {readings.acceleration_y} | "
        f"Valid: {is_valid}"
    )

    return SensorResponse(
        received=True,
        device_id=payload.device_id,
        is_valid=is_valid,
        timestamp=datetime.utcnow(),
    )


@router.get("/latest/{device_id}")
def get_latest(device_id: str):
    # TODO: достать последнее значение из Swarm
    return {"device_id": device_id, "data": None, "message": "not implemented yet"}
