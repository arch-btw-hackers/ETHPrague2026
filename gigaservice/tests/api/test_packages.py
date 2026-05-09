"""
API contract tests for /packages endpoints.

All Swarm I/O and the persistent index are replaced by the mock_swarm fixture
from conftest so tests never touch a real Bee node or the filesystem.
"""
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# POST /packages/
# ---------------------------------------------------------------------------

class TestCreatePackage:
    def test_happy_path_returns_201(self, client, mock_swarm, delivery_conditions):
        resp = client.post("/packages/", json=delivery_conditions)
        assert resp.status_code == 200  # FastAPI default for POST without status_code arg

    def test_response_contains_device_id(self, client, mock_swarm, delivery_conditions):
        resp = client.post("/packages/", json=delivery_conditions)
        body = resp.json()
        assert body["device_id"] == delivery_conditions["device_id"]

    def test_response_contains_swarm_hash(self, client, mock_swarm, delivery_conditions):
        resp = client.post("/packages/", json=delivery_conditions)
        body = resp.json()
        assert "swarm_hash" in body
        assert len(body["swarm_hash"]) > 0

    def test_conditions_stored_in_index(self, client, mock_swarm, delivery_conditions):
        client.post("/packages/", json=delivery_conditions)
        entry = mock_swarm["index"].get(delivery_conditions["device_id"])
        assert entry is not None
        assert "conditions_hash" in entry

    def test_conditions_stored_in_swarm(self, client, mock_swarm, delivery_conditions):
        resp = client.post("/packages/", json=delivery_conditions)
        h = resp.json()["swarm_hash"]
        stored = mock_swarm["store"].get(h)
        assert stored is not None
        assert stored["max_temp_c"] == delivery_conditions["max_temp_c"]

    def test_missing_device_id_returns_422(self, client, mock_swarm):
        resp = client.post("/packages/", json={"max_temp_c": 25.0, "max_acceleration": 2.0})
        assert resp.status_code == 422

    def test_missing_max_temp_c_returns_422(self, client, mock_swarm):
        resp = client.post("/packages/", json={"device_id": "x", "max_acceleration": 2.0})
        assert resp.status_code == 422

    def test_missing_max_acceleration_returns_422(self, client, mock_swarm):
        resp = client.post("/packages/", json={"device_id": "x", "max_temp_c": 25.0})
        assert resp.status_code == 422

    def test_wrong_type_for_temp_returns_422(self, client, mock_swarm):
        resp = client.post("/packages/", json={
            "device_id": "x", "max_temp_c": "hot", "max_acceleration": 2.0
        })
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client, mock_swarm):
        resp = client.post("/packages/", json={})
        assert resp.status_code == 422

    def test_creating_same_device_twice_overwrites(self, client, mock_swarm, delivery_conditions):
        # Second POST should not error; it overwrites the index entry
        client.post("/packages/", json=delivery_conditions)
        resp = client.post("/packages/", json={**delivery_conditions, "max_temp_c": 30.0})
        assert resp.status_code == 200

    def test_negative_limits_accepted(self, client, mock_swarm):
        # Pydantic allows negative floats — no business-layer restriction
        resp = client.post("/packages/", json={
            "device_id": "cold-chain", "max_temp_c": -10.0, "max_acceleration": 0.5
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /packages/{device_id}
# ---------------------------------------------------------------------------

class TestGetPackage:
    def test_returns_200_after_create(self, client, mock_swarm, delivery_conditions):
        client.post("/packages/", json=delivery_conditions)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}")
        assert resp.status_code == 200

    def test_response_shape(self, client, mock_swarm, delivery_conditions):
        client.post("/packages/", json=delivery_conditions)
        body = client.get(f"/packages/{delivery_conditions['device_id']}").json()
        assert "device_id" in body
        assert "swarm_hash" in body

    def test_unknown_device_returns_404(self, client, mock_swarm):
        resp = client.get("/packages/ghost-device")
        assert resp.status_code == 404

    def test_device_id_echoed_correctly(self, client, mock_swarm, delivery_conditions):
        client.post("/packages/", json=delivery_conditions)
        body = client.get(f"/packages/{delivery_conditions['device_id']}").json()
        assert body["device_id"] == delivery_conditions["device_id"]


# ---------------------------------------------------------------------------
# GET /packages/{device_id}/history
# ---------------------------------------------------------------------------

class TestGetPackageHistory:
    def test_no_telemetry_returns_404(self, client, mock_swarm, delivery_conditions):
        # Package exists but no sensor data submitted yet
        client.post("/packages/", json=delivery_conditions)
        # latest_telemetry_hash is set to None on creation
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 404

    def test_unknown_device_returns_404(self, client, mock_swarm):
        resp = client.get("/packages/no-such-device/history")
        assert resp.status_code == 404

    def test_single_telemetry_record(self, client, mock_swarm, delivery_conditions, signed_request):
        # Create package first
        client.post("/packages/", json=delivery_conditions)
        # Submit one sensor reading
        client.post("/sensors/data", json=signed_request)

        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert len(body["history"]) == 1

    def test_multiple_records_returned_oldest_first(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)

        # Submit 3 readings
        for nonce in range(1, 4):
            payload = {**signed_request, "payload": {**signed_request["payload"], "nonce": nonce}}
            client.post("/sensors/data", json=payload)

        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        # Ensure oldest (nonce=1) comes before newest (nonce=3)
        nonces = [r["nonce"] for r in body["history"]]
        assert nonces == sorted(nonces)

    def test_history_response_shape(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)
        body = client.get(f"/packages/{delivery_conditions['device_id']}/history").json()
        assert "device_id" in body
        assert "count" in body
        assert "history" in body
        assert isinstance(body["history"], list)


# ---------------------------------------------------------------------------
# 503 — Swarm node unavailable
# ---------------------------------------------------------------------------

class TestPackagesSwarmUnavailable:
    def test_create_package_upload_error_returns_503(self, client, mock_swarm, delivery_conditions, monkeypatch):
        import httpx

        async def _fail_upload(data: dict) -> str:
            raise httpx.RequestError("connection refused")

        monkeypatch.setattr("api.packages.upload_json", _fail_upload)
        resp = client.post("/packages/", json=delivery_conditions)
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Swarm storage unavailable"

    def test_create_package_http_status_error_returns_503(self, client, mock_swarm, delivery_conditions, monkeypatch):
        import httpx

        async def _fail_upload(data: dict) -> str:
            response = httpx.Response(503)
            raise httpx.HTTPStatusError("503", request=httpx.Request("POST", "/"), response=response)

        monkeypatch.setattr("api.packages.upload_json", _fail_upload)
        resp = client.post("/packages/", json=delivery_conditions)
        assert resp.status_code == 503

    def test_history_download_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)

        async def _fail_download(ref: str) -> dict:
            raise httpx.RequestError("timeout")

        monkeypatch.setattr("api.packages.download_json", _fail_download)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 503
