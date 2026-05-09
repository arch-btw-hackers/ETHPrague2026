"""
Shared fixtures for the GigaService test suite.

All external dependencies (Swarm Bee node, filesystem index) are mocked
so tests run in CI without any infrastructure.
"""
import json
import os
import sys
import pytest

from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Make the gigaservice root importable when running pytest from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# App fixture — single shared TestClient per session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    from server import app as _app
    return _app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# In-memory index — replaces the filesystem index.json
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_index(tmp_path, monkeypatch):
    """
    Redirect the persistent index to a temp file so tests are isolated
    and never touch the real /data/index.json.
    """
    index_file = tmp_path / "index.json"
    monkeypatch.setenv("INDEX_FILE", str(index_file))

    # Re-import with the patched env so the module picks up the new path
    import importlib
    import storage.swarm as swarm_mod
    monkeypatch.setattr(swarm_mod, "INDEX_FILE", str(index_file))
    return index_file


# ---------------------------------------------------------------------------
# Swarm stubs — keep unit/API tests free of real HTTP calls
# ---------------------------------------------------------------------------

FAKE_HASH = "a" * 64  # valid-looking 64-char hex reference


@pytest.fixture()
def mock_swarm(monkeypatch):
    """
    Patch upload_json / download_json / get_device_entry / set_device_entry
    at the api layer so endpoint tests never hit a real Bee node.
    """
    store: dict[str, dict] = {}
    counter = [0]

    async def _upload(data: dict) -> str:
        counter[0] += 1
        h = format(counter[0], "064x")  # unique 64-char hex per call
        store[h] = data
        return h

    async def _download(ref: str) -> dict:
        if ref not in store:
            raise Exception(f"Reference {ref} not found in mock store")
        return store[ref]

    index: dict[str, dict] = {}

    async def _get_entry(device_id: str):
        return index.get(device_id)

    async def _set_entry(device_id: str, **fields):
        index.setdefault(device_id, {}).update(fields)

    monkeypatch.setattr("api.packages.upload_json", _upload)
    monkeypatch.setattr("api.packages.download_json", _download)
    monkeypatch.setattr("api.packages.get_device_entry", _get_entry)
    monkeypatch.setattr("api.packages.set_device_entry", _set_entry)

    monkeypatch.setattr("api.sensors.upload_json", _upload)
    monkeypatch.setattr("api.sensors.download_json", _download)
    monkeypatch.setattr("api.sensors.get_device_entry", _get_entry)
    monkeypatch.setattr("api.sensors.set_device_entry", _set_entry)

    return {"store": store, "index": index}


# ---------------------------------------------------------------------------
# Conditions cache — cleared before every test for isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_conditions_cache():
    import api.sensors as sensors_mod
    sensors_mod.CONDITIONS_CACHE.clear()
    yield


# ---------------------------------------------------------------------------
# Blockchain stub — prevent real Web3 calls in CI
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_blockchain(monkeypatch):
    """Replace trigger_contract_refund with a no-op async stub for all tests."""
    async def _noop(device_id: str):
        return None

    monkeypatch.setattr("api.sensors.trigger_contract_refund", _noop)


# ---------------------------------------------------------------------------
# Canonical request payloads
# ---------------------------------------------------------------------------

@pytest.fixture()
def delivery_conditions():
    return {
        "device_id": "tracker-001",
        "max_temp_c": 25.0,
        "max_acceleration": 2.0,
    }


@pytest.fixture()
def signed_request():
    return {
        "payload": {
            "device_id": "tracker-001",
            "nonce": 1,
            "readings": {
                "temp_c": 20.0,
                "acceleration_x": 0.5,
                "acceleration_y": 0.3,
            },
        },
        "signature": "valid-sig",
    }
