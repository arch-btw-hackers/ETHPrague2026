from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from storage.swarm import upload_json, download_json, get_device_entry, set_device_entry

router = APIRouter(prefix="/sensors", tags=["Sensors"])


# ---------------------------------------------------------------------------
# SpaceComputer KMS — signature verification stub
# ---------------------------------------------------------------------------

async def verify_spacecomputer_signature(payload: dict, signature: str) -> bool:
    """
    TODO: реализовать вызов SpaceComputer KMS.
    Отправить payload + signature в расширение SpaceComputer для верификации.
    Пока всегда возвращает True (заглушка).
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
    # base64_payload: str  # раскомментируй, если трекер шлёт JSON в base64


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

    # 1. Проверка подписи через SpaceComputer KMS
    is_valid_sig = await verify_spacecomputer_signature(
        payload.model_dump(), data.signature
    )
    if not is_valid_sig:
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 2. Загружаем условия доставки из персистентного индекса + Swarm
    entry = get_device_entry(payload.device_id)
    if not entry or not entry.get("conditions_hash"):
        raise HTTPException(
            status_code=404,
            detail=f"No active package for device '{payload.device_id}'",
        )

    conditions = await download_json(entry["conditions_hash"])

    # 3. Анализ условий
    is_valid = True
    if readings.temp_c > conditions["max_temp_c"]:
        is_valid = False
    if abs(readings.acceleration_x) > conditions["max_acceleration"]:
        is_valid = False
    if abs(readings.acceleration_y) > conditions["max_acceleration"]:
        is_valid = False

    # 4. Сохраняем запись в Swarm (связный список через prev_hash)
    record = {
        **payload.model_dump(),
        "is_valid": is_valid,
        "timestamp": datetime.utcnow().isoformat(),
        "prev_hash": entry.get("latest_telemetry_hash"),  # ссылка на предыдущий
    }
    new_hash = await upload_json(record)

    # 5. Обновляем индекс: latest_telemetry_hash -> новый хэш
    set_device_entry(payload.device_id, latest_telemetry_hash=new_hash)

    print(
        f"Device: {payload.device_id} | "
        f"Temp: {readings.temp_c} | "
        f"AccX: {readings.acceleration_x} | "
        f"AccY: {readings.acceleration_y} | "
        f"Valid: {is_valid} | Hash: {new_hash[:8]}..."
    )

    return SensorResponse(
        received=True,
        device_id=payload.device_id,
        is_valid=is_valid,
        timestamp=datetime.utcnow(),
    )


@router.get("/latest/{device_id}")
async def get_latest(device_id: str):
    entry = get_device_entry(device_id)
    if not entry or not entry.get("latest_telemetry_hash"):
        raise HTTPException(status_code=404, detail="No telemetry found")
    data = await download_json(entry["latest_telemetry_hash"])
    return data

