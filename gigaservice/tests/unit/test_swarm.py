"""
Unit tests for storage/swarm.py

External HTTP (Bee node) is intercepted by respx so tests are deterministic
and run with no infrastructure.
The persistent index is redirected to tmp via mock_index fixture.
All index functions are now async — tests use async def + await.
"""
import json
import pytest
import httpx
import respx

from storage.swarm import (
    upload_json,
    download_json,
    get_postage_batch_id,
    get_device_entry,
    set_device_entry,
    delete_device_entry,
    _read_index,
    _write_index,
    set_http_client,
    _client,
)

BEE = "http://localhost:1633"
FAKE_REF = "b" * 64


# ---------------------------------------------------------------------------
# _read_index / _write_index
# ---------------------------------------------------------------------------

class TestReadWriteIndex:
    async def test_read_empty_index(self, mock_index):
        assert await _read_index() == {}

    async def test_write_and_read_roundtrip(self, mock_index):
        data = {"tracker-1": {"conditions_hash": "abc", "latest_telemetry_hash": None}}
        await _write_index(data)
        assert await _read_index() == data

    async def test_write_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep_path = tmp_path / "a" / "b" / "index.json"
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "INDEX_FILE", str(deep_path))
        await _write_index({"k": "v"})
        assert deep_path.exists()

    async def test_read_returns_dict_from_disk(self, mock_index):
        mock_index.write_text(json.dumps({"x": {"y": 1}}))
        result = await _read_index()
        assert result == {"x": {"y": 1}}


# ---------------------------------------------------------------------------
# get_device_entry / set_device_entry / delete_device_entry
# ---------------------------------------------------------------------------

class TestGetSetDeviceEntry:
    async def test_get_nonexistent_returns_none(self, mock_index):
        assert await get_device_entry("ghost") is None

    async def test_set_creates_entry(self, mock_index):
        await set_device_entry("dev-1", conditions_hash="abc123")
        entry = await get_device_entry("dev-1")
        assert entry == {"conditions_hash": "abc123"}

    async def test_set_merges_fields(self, mock_index):
        await set_device_entry("dev-2", conditions_hash="hash1")
        await set_device_entry("dev-2", latest_telemetry_hash="hash2")
        entry = await get_device_entry("dev-2")
        assert entry["conditions_hash"] == "hash1"
        assert entry["latest_telemetry_hash"] == "hash2"

    async def test_set_overwrites_existing_field(self, mock_index):
        await set_device_entry("dev-3", conditions_hash="old")
        await set_device_entry("dev-3", conditions_hash="new")
        assert (await get_device_entry("dev-3"))["conditions_hash"] == "new"

    async def test_multiple_devices_isolated(self, mock_index):
        await set_device_entry("a", conditions_hash="hash-a")
        await set_device_entry("b", conditions_hash="hash-b")
        assert (await get_device_entry("a"))["conditions_hash"] == "hash-a"
        assert (await get_device_entry("b"))["conditions_hash"] == "hash-b"

    async def test_empty_device_id(self, mock_index):
        await set_device_entry("", conditions_hash="x")
        assert (await get_device_entry(""))["conditions_hash"] == "x"


class TestDeleteDeviceEntry:
    async def test_delete_existing_entry(self, mock_index):
        await set_device_entry("dev-del", conditions_hash="h")
        await delete_device_entry("dev-del")
        assert await get_device_entry("dev-del") is None

    async def test_delete_nonexistent_is_noop(self, mock_index):
        # Should not raise
        await delete_device_entry("ghost")

    async def test_delete_only_removes_target(self, mock_index):
        await set_device_entry("keep", conditions_hash="k")
        await set_device_entry("remove", conditions_hash="r")
        await delete_device_entry("remove")
        assert await get_device_entry("keep") is not None
        assert await get_device_entry("remove") is None


# ---------------------------------------------------------------------------
# HTTP client initialization
# ---------------------------------------------------------------------------

class TestHttpClient:
    def test_raises_if_client_not_set(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "_http_client", None)
        with pytest.raises(RuntimeError, match="not initialized"):
            _client()

    def test_set_http_client_stores_instance(self, monkeypatch):
        import storage.swarm as swarm_mod
        fake = httpx.AsyncClient()
        set_http_client(fake)
        assert swarm_mod._http_client is fake


# ---------------------------------------------------------------------------
# upload_json
# ---------------------------------------------------------------------------

class TestUploadJson:
    @respx.mock
    async def test_happy_path_returns_reference(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "deadbeef")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        ref = await upload_json({"key": "value"})
        assert ref == FAKE_REF

    @respx.mock
    async def test_sends_correct_content_type(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        route = respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        await upload_json({"x": 1})
        assert route.called
        assert route.calls[0].request.headers["content-type"] == "application/json"

    @respx.mock
    async def test_sends_postage_batch_header(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "mybatch")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        route = respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        await upload_json({"x": 1})
        assert route.calls[0].request.headers["swarm-postage-batch-id"] == "mybatch"

    @respx.mock
    async def test_raises_on_4xx(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(return_value=httpx.Response(402))
        with pytest.raises(httpx.HTTPStatusError):
            await upload_json({"x": 1})

    @respx.mock
    async def test_uploads_empty_dict(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        assert await upload_json({}) == FAKE_REF

    @respx.mock
    async def test_uploads_nested_dict(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        assert await upload_json({"nested": {"a": [1, 2, 3]}}) == FAKE_REF


# ---------------------------------------------------------------------------
# download_json
# ---------------------------------------------------------------------------

class TestDownloadJson:
    @respx.mock
    async def test_happy_path_returns_dict(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        payload = {"device_id": "x", "temp_c": 22.0}
        respx.get(f"{BEE}/bzz/{FAKE_REF}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await download_json(FAKE_REF)
        assert result == payload

    @respx.mock
    async def test_raises_on_404(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.get(f"{BEE}/bzz/{FAKE_REF}").mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await download_json(FAKE_REF)

    @respx.mock
    async def test_raises_on_500(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.get(f"{BEE}/bzz/{FAKE_REF}").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await download_json(FAKE_REF)


# ---------------------------------------------------------------------------
# get_postage_batch_id
# ---------------------------------------------------------------------------

class TestGetPostageBatchId:
    @respx.mock
    async def test_returns_batch_id(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/stamps/10000000/17").mock(
            return_value=httpx.Response(201, json={"batchID": "mybatch"})
        )
        result = await get_postage_batch_id()
        assert result == "mybatch"

    @respx.mock
    async def test_raises_on_error(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/stamps/10000000/17").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await get_postage_batch_id()

