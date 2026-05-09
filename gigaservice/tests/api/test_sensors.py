"""
API contract tests for /sensors endpoints.

Covers:
  - POST /sensors/data  — happy path, signature rejection, unknown device,
                          conditions violations, boundary values, linked list
  - GET  /sensors/latest/{device_id} — happy path, unknown device
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Capture the real function at module level (before any test fixtures can mock it).
# Used by TestVerifySpacecomputerSignature to bypass the autouse conftest mock.
import api.sensors as _sensors_module
_real_verify_sig = _sensors_module.verify_spacecomputer_signature


# ---------------------------------------------------------------------------
# POST /sensors/data — happy path
# ---------------------------------------------------------------------------

class TestReceiveSensorDataHappyPath:
    def test_returns_200(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 200

    def test_response_received_is_true(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        body = client.post("/sensors/data", json=signed_request).json()
        assert body["received"] is True

    def test_response_contains_device_id(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        body = client.post("/sensors/data", json=signed_request).json()
        assert body["device_id"] == delivery_conditions["device_id"]

    def test_is_valid_true_within_limits(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        body = client.post("/sensors/data", json=signed_request).json()
        assert body["is_valid"] is True

    def test_response_has_timestamp(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        body = client.post("/sensors/data", json=signed_request).json()
        assert "timestamp" in body


# ---------------------------------------------------------------------------
# POST /sensors/data — signature rejection
# ---------------------------------------------------------------------------

class TestSignatureRejection:
    def test_invalid_signature_returns_403(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        with patch("api.sensors.verify_spacecomputer_signature", return_value=False):
            resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 403

    def test_invalid_signature_error_message(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        with patch("api.sensors.verify_spacecomputer_signature", return_value=False):
            body = client.post("/sensors/data", json=signed_request).json()
        assert "signature" in body["detail"].lower()

    def test_valid_signature_stub_passes(self, client, mock_swarm, delivery_conditions, signed_request):
        """Default stub always returns True — request should go through."""
        client.post("/packages/", json=delivery_conditions)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /sensors/data — no package registered
# ---------------------------------------------------------------------------

class TestNoPackageRegistered:
    def test_returns_404_when_no_package(self, client, mock_swarm, signed_request):
        # No POST /packages/ first
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 404

    def test_404_detail_mentions_device(self, client, mock_swarm, signed_request):
        body = client.post("/sensors/data", json=signed_request).json()
        assert signed_request["payload"]["device_id"] in body["detail"]


# ---------------------------------------------------------------------------
# POST /sensors/data — conditions violations
# ---------------------------------------------------------------------------

class TestConditionsViolations:
    def _post_reading(self, client, mock_swarm, temp_c, acc_overload, conditions=None):
        cond = conditions or {"device_id": "tracker-001", "max_temp_c": 25.0, "max_acceleration": 2.0}
        client.post("/packages/", json=cond)
        req = {
            "payload": {
                "device_id": cond["device_id"],
                "nonce": 1,
                "readings": {"temp_c": temp_c, "acceleration_overload": acc_overload},
            },
            "signature": "sig",
        }
        return client.post("/sensors/data", json=req).json()

    def test_temp_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=30.0, acc_overload=0.0)
        assert body["is_valid"] is False

    def test_acc_overload_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_overload=5.0)
        assert body["is_valid"] is False

    def test_negative_acc_overload_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_overload=-5.0)
        assert body["is_valid"] is False

    def test_exact_boundary_is_valid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=25.0, acc_overload=2.0)
        assert body["is_valid"] is True

    def test_one_tick_over_temp_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=25.001, acc_overload=0.0)
        assert body["is_valid"] is False

    def test_all_violated_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=99.0, acc_overload=99.0)
        assert body["is_valid"] is False


# ---------------------------------------------------------------------------
# POST /sensors/data — validation errors
# ---------------------------------------------------------------------------

class TestSensorDataValidation:
    def test_missing_payload_returns_422(self, client, mock_swarm):
        resp = client.post("/sensors/data", json={"signature": "sig"})
        assert resp.status_code == 422

    def test_missing_signature_returns_422(self, client, mock_swarm):
        resp = client.post("/sensors/data", json={
            "payload": {"device_id": "x", "nonce": 1, "readings": {"temp_c": 20.0, "acceleration_overload": 0.0}}
        })
        assert resp.status_code == 422

    def test_missing_readings_returns_422(self, client, mock_swarm):
        resp = client.post("/sensors/data", json={
            "payload": {"device_id": "x", "nonce": 1},
            "signature": "sig",
        })
        assert resp.status_code == 422

    def test_wrong_type_for_temp_returns_422(self, client, mock_swarm):
        resp = client.post("/sensors/data", json={
            "payload": {
                "device_id": "x", "nonce": 1,
                "readings": {"temp_c": "hot", "acceleration_overload": 0.0}
            },
            "signature": "sig",
        })
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client, mock_swarm):
        resp = client.post("/sensors/data", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /sensors/data — linked list (prev_hash chaining)
# ---------------------------------------------------------------------------

class TestLinkedListChaining:
    def test_first_record_has_no_prev_hash(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)

        # Only one record in store; first entry should have prev_hash=None
        records = list(mock_swarm["store"].values())
        telemetry = [r for r in records if "nonce" in r]
        assert len(telemetry) == 1
        assert telemetry[0]["prev_hash"] is None

    def test_second_record_points_to_first(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)

        resp1 = client.post("/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": 1}})
        resp2 = client.post("/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": 2}})

        # Find the latest hash from index
        device_id = delivery_conditions["device_id"]
        latest_hash = mock_swarm["index"][device_id]["latest_telemetry_hash"]
        latest_record = mock_swarm["store"][latest_hash]
        assert latest_record["prev_hash"] is not None

    def test_history_traversal_returns_all_records(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        for nonce in range(1, 4):
            client.post("/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": nonce}})

        body = client.get(f"/packages/{delivery_conditions['device_id']}/history").json()
        assert body["count"] == 3


# ---------------------------------------------------------------------------
# GET /sensors/latest/{device_id}
# ---------------------------------------------------------------------------

class TestGetLatest:
    def test_returns_200_after_data_submitted(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)
        resp = client.get(f"/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 200

    def test_returns_404_when_no_telemetry(self, client, mock_swarm, delivery_conditions):
        client.post("/packages/", json=delivery_conditions)
        resp = client.get(f"/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 404

    def test_returns_404_for_unknown_device(self, client, mock_swarm):
        resp = client.get("/sensors/latest/unknown-device")
        assert resp.status_code == 404

    def test_latest_record_matches_last_submitted(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        # Submit two readings — latest should have nonce=2
        client.post("/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": 1}})
        client.post("/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": 2}})

        body = client.get(f"/sensors/latest/{delivery_conditions['device_id']}").json()
        assert body["nonce"] == 2

    def test_latest_response_contains_is_valid(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)
        body = client.get(f"/sensors/latest/{delivery_conditions['device_id']}").json()
        assert "is_valid" in body


# ---------------------------------------------------------------------------
# Conditions cache behaviour
# ---------------------------------------------------------------------------

class TestConditionsCache:
    def test_cache_populated_after_first_request(self, client, mock_swarm, delivery_conditions, signed_request):
        import api.sensors as sensors_mod
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)
        assert len(sensors_mod.CONDITIONS_CACHE) == 1

    def test_cache_prevents_repeat_download(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        """Second telemetry packet must use cached conditions, not call download_json."""
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)  # populates cache

        # Any call to download_json after this should NOT happen for conditions
        async def _must_not_be_called(ref: str):
            raise AssertionError(f"download_json called for {ref} — should have used cache")

        monkeypatch.setattr("api.sensors.download_json", _must_not_be_called)

        resp = client.post("/sensors/data", json={
            **signed_request,
            "payload": {**signed_request["payload"], "nonce": 2},
        })
        assert resp.status_code == 200

    def test_cache_cleared_between_tests(self):
        import api.sensors as sensors_mod
        # The clear_conditions_cache autouse fixture guarantees this
        assert sensors_mod.CONDITIONS_CACHE == {}


# ---------------------------------------------------------------------------
# 503 — Swarm node unavailable
# ---------------------------------------------------------------------------

class TestSwarmUnavailable503:
    def test_upload_request_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/packages/", json=delivery_conditions)

        async def _fail_upload(data: dict) -> str:
            raise httpx.RequestError("connection refused")

        monkeypatch.setattr("api.sensors.upload_json", _fail_upload)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Swarm storage unavailable"

    def test_upload_http_status_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/packages/", json=delivery_conditions)

        async def _fail_upload(data: dict) -> str:
            response = httpx.Response(500)
            raise httpx.HTTPStatusError("500", request=httpx.Request("POST", "/"), response=response)

        monkeypatch.setattr("api.sensors.upload_json", _fail_upload)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 503

    def test_download_conditions_request_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/packages/", json=delivery_conditions)

        async def _fail_download(ref: str) -> dict:
            raise httpx.RequestError("timeout")

        monkeypatch.setattr("api.sensors.download_json", _fail_download)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 503

    def test_get_latest_download_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)

        async def _fail_download(ref: str) -> dict:
            raise httpx.RequestError("timeout")

        monkeypatch.setattr("api.sensors.download_json", _fail_download)
        resp = client.get(f"/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Linked list rollback — index write failure after Swarm upload
# ---------------------------------------------------------------------------

class TestIndexRollback:
    def test_index_write_failure_returns_500(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        client.post("/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        resp = client.post("/sensors/data", json=signed_request)
        assert resp.status_code == 500

    def test_index_write_failure_detail_mentions_retry(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        client.post("/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        body = client.post("/sensors/data", json=signed_request).json()
        assert "retry" in body["detail"].lower()

    def test_swarm_write_succeeds_but_index_fails_not_counted_in_history(
        self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch
    ):
        """If index update fails, the record should NOT appear in history (index not updated)."""
        client.post("/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        client.post("/sensors/data", json=signed_request)  # this fails at index step

        # History should still be empty (index not updated)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for ECDSA P-256 signature verification
# ---------------------------------------------------------------------------

class TestVerifySpacecomputerSignature:
    """
    Tests for verify_spacecomputer_signature using a freshly generated
    ephemeral P-256 key pair — no external infrastructure needed.
    """

    @pytest.fixture(autouse=True)
    def use_real_verify(self, monkeypatch):
        """Restore the real function, overriding the conftest autouse mock."""
        monkeypatch.setattr("api.sensors.verify_spacecomputer_signature", _real_verify_sig)

    @pytest.fixture()
    def key_pair(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        return private_key, public_key

    @pytest.fixture()
    def pem_env(self, key_pair, monkeypatch):
        from cryptography.hazmat.primitives import serialization
        _, public_key = key_pair
        pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pem)
        # Reset cached key loader between tests
        return pem

    def _make_signature(self, private_key, payload: dict) -> str:
        import json, base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        sig = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(sig).decode()

    async def test_valid_signature_returns_true(self, key_pair, pem_env):
        from api.sensors import verify_spacecomputer_signature
        private_key, _ = key_pair
        payload = {"device_id": "dev-1", "nonce": 42, "readings": {"temp_c": 20.0, "acceleration_overload": 0.1}}
        sig = self._make_signature(private_key, payload)
        assert await verify_spacecomputer_signature(payload, sig) is True

    async def test_wrong_signature_returns_false(self, key_pair, pem_env):
        from api.sensors import verify_spacecomputer_signature
        from cryptography.hazmat.primitives.asymmetric import ec as ec_mod
        _, _ = key_pair
        other_key = ec_mod.generate_private_key(ec_mod.SECP256R1())
        payload = {"device_id": "dev-1", "nonce": 1, "readings": {}}
        sig = self._make_signature(other_key, payload)
        assert await verify_spacecomputer_signature(payload, sig) is False

    async def test_tampered_payload_returns_false(self, key_pair, pem_env):
        from api.sensors import verify_spacecomputer_signature
        private_key, _ = key_pair
        original = {"device_id": "dev-1", "nonce": 1, "readings": {"temp_c": 20.0}}
        sig = self._make_signature(private_key, original)
        tampered = {**original, "nonce": 99}
        assert await verify_spacecomputer_signature(tampered, sig) is False

    async def test_invalid_base64_returns_false(self, pem_env):
        from api.sensors import verify_spacecomputer_signature
        assert await verify_spacecomputer_signature({"x": 1}, "!!!not-base64!!!") is False

    async def test_no_env_var_returns_false(self, monkeypatch):
        from api.sensors import verify_spacecomputer_signature
        monkeypatch.delenv("DEVICE_PUBLIC_KEY_PEM", raising=False)
        # No key configured → rejected (returns False, logs an error)
        assert await verify_spacecomputer_signature({"x": 1}, "anysig") is False
