from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from storage.swarm import upload_json

router = APIRouter(prefix="/sensors", tags=["Sensors"])


class Readings(BaseModel):
    temp_c: float
    humidity_pct: float
    shock_detected: bool
    door_open: bool


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
    timestamp: datetime


@router.post("/data", response_model=SensorResponse)
async def receive_sensor_data(data: SignedRequest):
    payload = data.payload

    # 1. Проверка подписи через SpaceComputer KMS
    # is_valid = await verify_with_spacecomputer(data.payload, data.signature)
    # if not is_valid:
    #     raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. Анализ условий
    # if payload.readings.shock_detected:
    #     ... фиксируем нарушение
    # if payload.readings.temp_c > MAX_TEMP:
    #     ... фиксируем нарушение

    # 3. Сохранение в Swarm
    # swarm_hash = await upload_json(payload.model_dump())

    print(
        f"Device: {payload.device_id} | "
        f"Temp: {payload.readings.temp_c} | "
        f"Shock: {payload.readings.shock_detected}"
    )

    return SensorResponse(
        received=True,
        device_id=payload.device_id,
        timestamp=datetime.utcnow(),
    )


@router.get("/latest/{device_id}")
def get_latest(device_id: str):
    # TODO: достать последнее значение из Swarm
    return {"device_id": device_id, "data": None, "message": "not implemented yet"}
