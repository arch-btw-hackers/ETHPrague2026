"""Swarm Bee API client + persistent index management.

Changes vs v1:
- Global httpx.AsyncClient (connection pooling) — injected via set_http_client()
- asyncio.Lock + aiofiles — race-condition-free, atomic read-modify-write
- All index functions are now async
- New: delete_device_entry() for atomic key removal
"""
import asyncio
import json
import os

import aiofiles
import httpx

BEE_API_URL = os.getenv("BEE_API_URL", "http://localhost:1633")
POSTAGE_BATCH_ID = os.getenv("BEE_POSTAGE_BATCH_ID", "")

# Persistent index: device_id -> {conditions_hash, latest_telemetry_hash}
# Mounted as Docker volume — survives restarts
INDEX_FILE = os.getenv("INDEX_FILE", "/data/index.json")


# ---------------------------------------------------------------------------
# Global HTTP client — injected by FastAPI lifespan (server.py)
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def set_http_client(client: httpx.AsyncClient) -> None:
    global _http_client
    _http_client = client


def _client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError(
            "HTTP client not initialized. Ensure the FastAPI lifespan is running."
        )
    return _http_client


# ---------------------------------------------------------------------------
# Swarm upload / download — use pooled client, no per-call client creation
# ---------------------------------------------------------------------------

async def upload_json(data: dict) -> str:
    """Upload JSON to Swarm via /bzz. Returns the Swarm reference (hash)."""
    payload = json.dumps(data).encode()
    response = await _client().post(
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
    response = await _client().get(f"{BEE_API_URL}/bzz/{reference}")
    response.raise_for_status()
    return response.json()


async def get_postage_batch_id() -> str:
    """Buy a minimal postage batch and return its ID (for dev/testing)."""
    response = await _client().post(f"{BEE_API_URL}/stamps/10000000/17")
    response.raise_for_status()
    return response.json()["batchID"]


# ---------------------------------------------------------------------------
# Persistent index — async, lock-protected, atomic read-modify-write
# ---------------------------------------------------------------------------

_index_lock = asyncio.Lock()


async def _raw_read() -> dict:
    """Read index from disk. Caller MUST hold _index_lock."""
    if not os.path.exists(INDEX_FILE):
        return {}
    async with aiofiles.open(INDEX_FILE) as f:
        return json.loads(await f.read())


async def _raw_write(index: dict) -> None:
    """Write index to disk. Caller MUST hold _index_lock."""
    dir_ = os.path.dirname(INDEX_FILE)
    if dir_:
        os.makedirs(dir_, exist_ok=True)
    async with aiofiles.open(INDEX_FILE, "w") as f:
        await f.write(json.dumps(index))


async def _read_index() -> dict:
    async with _index_lock:
        return await _raw_read()


async def _write_index(index: dict) -> None:
    async with _index_lock:
        await _raw_write(index)


async def get_device_entry(device_id: str) -> dict | None:
    """Return stored index entry for a device or None."""
    async with _index_lock:
        return (await _raw_read()).get(device_id)


async def set_device_entry(device_id: str, **fields) -> None:
    """Atomically update (merge) fields for a device in the persistent index."""
    async with _index_lock:
        index = await _raw_read()
        index.setdefault(device_id, {}).update(fields)
        await _raw_write(index)


async def delete_device_entry(device_id: str) -> None:
    """Atomically remove an entry from the index."""
    async with _index_lock:
        index = await _raw_read()
        index.pop(device_id, None)
        await _raw_write(index)


async def list_all_entries() -> dict[str, dict]:
    """Return the full index as {device_id: entry_dict}."""
    return await _read_index()
