"""
Unit tests for storage/swarm.py

External HTTP (Bee node) is mocked with respx so tests are deterministic
and run with no infrastructure. The persistent index is redirected to tmp.
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
    _read_index,
    _write_index,
)

BEE = "http://localhost:1633"
FAKE_REF = "b" * 64


# ---------------------------------------------------------------------------
# Index helpers (pure, no I/O mocking needed — uses tmp_path via mock_index)
# ---------------------------------------------------------------------------

class TestReadWriteIndex:
    def test_read_empty_index(self, mock_index):
        result = _read_index()
        assert result == {}

    def test_write_and_read_roundtrip(self, mock_index):
        data = {"tracker-1": {"conditions_hash": "abc", "latest_telemetry_hash": None}}
        _write_index(data)
        assert _read_index() == data

    def test_write_creates_parent_dirs(self, tmp_path, monkeypatch):
        deep_path = tmp_path / "a" / "b" / "index.json"
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "INDEX_FILE", str(deep_path))
        _write_index({"k": "v"})
        assert deep_path.exists()


class TestGetSetDeviceEntry:
    def test_get_nonexistent_returns_none(self, mock_index):
        assert get_device_entry("ghost") is None

    def test_set_creates_entry(self, mock_index):
        set_device_entry("dev-1", conditions_hash="abc123")
        entry = get_device_entry("dev-1")
        assert entry == {"conditions_hash": "abc123"}

    def test_set_merges_fields(self, mock_index):
        set_device_entry("dev-2", conditions_hash="hash1")
        set_device_entry("dev-2", latest_telemetry_hash="hash2")
        entry = get_device_entry("dev-2")
        assert entry["conditions_hash"] == "hash1"
        assert entry["latest_telemetry_hash"] == "hash2"

    def test_set_overwrites_existing_field(self, mock_index):
        set_device_entry("dev-3", conditions_hash="old")
        set_device_entry("dev-3", conditions_hash="new")
        assert get_device_entry("dev-3")["conditions_hash"] == "new"

    def test_multiple_devices_isolated(self, mock_index):
        set_device_entry("a", conditions_hash="hash-a")
        set_device_entry("b", conditions_hash="hash-b")
        assert get_device_entry("a")["conditions_hash"] == "hash-a"
        assert get_device_entry("b")["conditions_hash"] == "hash-b"

    def test_empty_device_id(self, mock_index):
        # Edge case: empty string as key — should work without crashing
        set_device_entry("", conditions_hash="x")
        assert get_device_entry("")["conditions_hash"] == "x"


# ---------------------------------------------------------------------------
# upload_json
# ---------------------------------------------------------------------------

class TestUploadJson:
    @respx.mock
    @pytest.mark.asyncio
    async def test_happy_path_returns_reference(self, monkeypatch):
        monkeypatch.setenv("BEE_POSTAGE_BATCH_ID", "deadbeef")
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "deadbeef")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        ref = await upload_json({"key": "value"})
        assert ref == FAKE_REF

    @respx.mock
    @pytest.mark.asyncio
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
    @pytest.mark.asyncio
    async def test_raises_on_4xx(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(return_value=httpx.Response(402))
        with pytest.raises(httpx.HTTPStatusError):
            await upload_json({"x": 1})

    @respx.mock
    @pytest.mark.asyncio
    async def test_uploads_empty_dict(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        ref = await upload_json({})
        assert ref == FAKE_REF

    @respx.mock
    @pytest.mark.asyncio
    async def test_uploads_nested_dict(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "POSTAGE_BATCH_ID", "batch1")
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/bzz").mock(
            return_value=httpx.Response(201, json={"reference": FAKE_REF})
        )
        ref = await upload_json({"nested": {"a": [1, 2, 3]}})
        assert ref == FAKE_REF


# ---------------------------------------------------------------------------
# download_json
# ---------------------------------------------------------------------------

class TestDownloadJson:
    @respx.mock
    @pytest.mark.asyncio
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
    @pytest.mark.asyncio
    async def test_raises_on_404(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.get(f"{BEE}/bzz/{FAKE_REF}").mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await download_json(FAKE_REF)

    @respx.mock
    @pytest.mark.asyncio
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
    @pytest.mark.asyncio
    async def test_returns_batch_id(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/stamps/10000000/17").mock(
            return_value=httpx.Response(201, json={"batchID": "mybatch"})
        )
        result = await get_postage_batch_id()
        assert result == "mybatch"

    @respx.mock
    @pytest.mark.asyncio
    async def test_raises_on_error(self, monkeypatch):
        import storage.swarm as swarm_mod
        monkeypatch.setattr(swarm_mod, "BEE_API_URL", BEE)

        respx.post(f"{BEE}/stamps/10000000/17").mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await get_postage_batch_id()
