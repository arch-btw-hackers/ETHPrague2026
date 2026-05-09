import json
import os
import httpx

BEE_API_URL = os.getenv("BEE_API_URL", "http://localhost:1633")
POSTAGE_BATCH_ID = os.getenv("BEE_POSTAGE_BATCH_ID", "")


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
        # amount=10000000, depth=17 — minimal batch for devnet
        response = await client.post(f"{BEE_API_URL}/stamps/10000000/17")
        response.raise_for_status()
        return response.json()["batchID"]
