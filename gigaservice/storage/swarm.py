import json
import os
import httpx

BEE_API_URL = os.getenv("BEE_API_URL", "http://localhost:1633")
POSTAGE_BATCH_ID = os.getenv("BEE_POSTAGE_BATCH_ID", "")

# Персистентный индекс: device_id -> {conditions_hash, latest_telemetry_hash}
# Монтируется как Docker volume, переживает перезапуски
INDEX_FILE = os.getenv("INDEX_FILE", "/data/index.json")


# ---------------------------------------------------------------------------
# Swarm upload / download
# ---------------------------------------------------------------------------

async def upload_json(data: dict) -> str:
    """Upload JSON to Swarm via /bzz. Returns the Swarm reference (hash)."""
    payload = json.dumps(data).encode()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BEE_API_URL}/bzz",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "swarm-postage-batch-id": POSTAGE_BATCH_ID,
                "swarm-deferred-upload": "false",
            },
        )
        response.raise_for_status()
        return response.json()["reference"]


async def download_json(reference: str) -> dict:
    """Download JSON from Swarm by reference hash."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BEE_API_URL}/bzz/{reference}")
        response.raise_for_status()
        return response.json()


async def get_postage_batch_id() -> str:
    """Buy a minimal postage batch and return its ID (for dev/testing)."""
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BEE_API_URL}/stamps/10000000/17")
        response.raise_for_status()
        return response.json()["batchID"]


# ---------------------------------------------------------------------------
# Persistent index (survives container restarts via Docker volume)
# ---------------------------------------------------------------------------

def _read_index() -> dict:
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            return json.load(f)
    return {}


def _write_index(index: dict) -> None:
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f)


def get_device_entry(device_id: str) -> dict | None:
    """Return stored index entry for a device or None."""
    return _read_index().get(device_id)


def set_device_entry(device_id: str, **fields) -> None:
    """Update (merge) fields for a device in the persistent index."""
    index = _read_index()
    index.setdefault(device_id, {}).update(fields)
    _write_index(index)
