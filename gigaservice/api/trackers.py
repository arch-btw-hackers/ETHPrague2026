"""
CRUD API for tracker management.

A tracker represents a physical hardware device.
Its metadata (name, description, owner) is stored in Swarm.
The persistent index maps tracker_id -> {meta_hash}.

Endpoints:
  POST   /trackers/               — register a new tracker
  GET    /trackers/               — list all trackers
  GET    /trackers/{tracker_id}   — get tracker details
  PUT    /trackers/{tracker_id}   — update tracker metadata
  DELETE /trackers/{tracker_id}   — remove tracker
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from storage.swarm import (
    upload_json,
    download_json,
    get_device_entry,
    set_device_entry,
    delete_device_entry,
    _read_index,
)

router = APIRouter(prefix="/trackers", tags=["Trackers"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TrackerCreate(BaseModel):
    tracker_id: str
    name: str
    description: str = ""
    owner: str = ""


class TrackerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    owner: str | None = None


class TrackerResponse(BaseModel):
    tracker_id: str
    name: str
    description: str
    owner: str
    meta_hash: str


# ---------------------------------------------------------------------------
# Helpers — all async to stay consistent with the async index layer
# ---------------------------------------------------------------------------

def _tracker_key(tracker_id: str) -> str:
    """Namespace tracker entries to avoid collision with device packages."""
    return f"__tracker__{tracker_id}"


async def _get_tracker(tracker_id: str) -> dict | None:
    return await get_device_entry(_tracker_key(tracker_id))


async def _set_tracker(tracker_id: str, **fields) -> None:
    await set_device_entry(_tracker_key(tracker_id), **fields)


async def _delete_tracker(tracker_id: str) -> None:
    await delete_device_entry(_tracker_key(tracker_id))


async def _list_trackers() -> list[str]:
    index = await _read_index()
    prefix = "__tracker__"
    return [k[len(prefix):] for k in index if k.startswith(prefix)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=TrackerResponse, status_code=201)
async def create_tracker(data: TrackerCreate):
    if await _get_tracker(data.tracker_id):
        raise HTTPException(status_code=409, detail=f"Tracker '{data.tracker_id}' already exists")

    meta = {
        "tracker_id": data.tracker_id,
        "name": data.name,
        "description": data.description,
        "owner": data.owner,
    }
    meta_hash = await upload_json(meta)
    await _set_tracker(data.tracker_id, meta_hash=meta_hash)

    return TrackerResponse(**meta, meta_hash=meta_hash)


@router.get("/", response_model=list[TrackerResponse])
async def list_trackers():
    ids = await _list_trackers()
    results = []
    for tid in ids:
        entry = await _get_tracker(tid)
        if not entry:
            continue
        meta = await download_json(entry["meta_hash"])
        results.append(TrackerResponse(**meta, meta_hash=entry["meta_hash"]))
    return results


@router.get("/{tracker_id}", response_model=TrackerResponse)
async def get_tracker(tracker_id: str):
    entry = await _get_tracker(tracker_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Tracker '{tracker_id}' not found")
    meta = await download_json(entry["meta_hash"])
    return TrackerResponse(**meta, meta_hash=entry["meta_hash"])


@router.put("/{tracker_id}", response_model=TrackerResponse)
async def update_tracker(tracker_id: str, data: TrackerUpdate):
    entry = await _get_tracker(tracker_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Tracker '{tracker_id}' not found")

    meta = await download_json(entry["meta_hash"])

    if data.name is not None:
        meta["name"] = data.name
    if data.description is not None:
        meta["description"] = data.description
    if data.owner is not None:
        meta["owner"] = data.owner

    new_hash = await upload_json(meta)
    await _set_tracker(tracker_id, meta_hash=new_hash)

    return TrackerResponse(**meta, meta_hash=new_hash)


@router.delete("/{tracker_id}", status_code=204)
async def delete_tracker(tracker_id: str):
    if not await _get_tracker(tracker_id):
        raise HTTPException(status_code=404, detail=f"Tracker '{tracker_id}' not found")
    await _delete_tracker(tracker_id)

