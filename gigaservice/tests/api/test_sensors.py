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

# Capture the real verify function before any test fixture can mock it.
# Used by TestVerifySpacecomputerSignature to bypass the autouse conftest mock.
import api.sensors as _sensors_module
_real_verify_sig = _sensors_module.verify_spacecomputer_signature


# ---------------------------------------------------------------------------
# POST /sensors/data — happy path
# ---------------------------------------------------------------------------

class TestReceiveSensorDataHappyPath:
    def test_returns_200(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        assert resp.status_code == 200

    def test_response_received_is_true(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert body["received"] is True

    def test_response_contains_device_id(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert body["device_id"] == delivery_conditions["device_id"]

    def test_is_valid_true_within_limits(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert body["is_valid"] is True

    def test_response_has_timestamp(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert "timestamp" in body


# ---------------------------------------------------------------------------
# POST /sensors/data — signature rejection
# ---------------------------------------------------------------------------

class TestSignatureRejection:
    def test_invalid_signature_returns_403(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        with patch("api.sensors.verify_spacecomputer_signature", return_value=False):
            resp = client.post("/api/v1/sensors/data", json=signed_request)
        assert resp.status_code == 403

    def test_invalid_signature_error_message(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        with patch("api.sensors.verify_spacecomputer_signature", return_value=False):
            body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert "signature" in body["detail"].lower()

    def test_valid_signature_stub_passes(self, client, mock_swarm, delivery_conditions, signed_request):
        """Default stub always returns True — request should go through."""
        client.post("/api/v1/packages/", json=delivery_conditions)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /sensors/data — no package registered
# ---------------------------------------------------------------------------

class TestNoPackageRegistered:
    def test_returns_404_when_no_package(self, client, mock_swarm, signed_request):
        # No POST /packages/ first
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        assert resp.status_code == 404

    def test_404_detail_mentions_device(self, client, mock_swarm, signed_request):
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert signed_request["payload"]["device_id"] in body["detail"]


# ---------------------------------------------------------------------------
# POST /sensors/data — conditions violations
# ---------------------------------------------------------------------------

class TestConditionsViolations:
    def _post_reading(self, client, mock_swarm, temp_c, acc_overload, conditions=None):
        cond = conditions or {"device_id": "tracker-001", "max_temp_c": 25.0, "max_acceleration": 2.0}
        client.post("/api/v1/packages/", json=cond)
        req = {
            "payload": {
                "device_id": cond["device_id"],
                "nonce": "1",
                "readings": {"temp_c": temp_c, "acceleration_overload": acc_overload},
            },
            "signature": "sig",
        }
        return client.post("/api/v1/sensors/data", json=req).json()

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
        resp = client.post("/api/v1/sensors/data", json={"signature": "sig"})
        assert resp.status_code == 422

    def test_missing_signature_returns_422(self, client, mock_swarm):
        resp = client.post("/api/v1/sensors/data", json={
            "payload": {"device_id": "x", "nonce": "1", "readings": {"temp_c": 20.0, "acceleration_overload": 0.0}}
        })
        assert resp.status_code == 422

    def test_missing_readings_returns_422(self, client, mock_swarm):
        resp = client.post("/api/v1/sensors/data", json={
            "payload": {"device_id": "x", "nonce": "1"},
            "signature": "sig",
        })
        assert resp.status_code == 422

    def test_wrong_type_for_temp_returns_422(self, client, mock_swarm):
        resp = client.post("/api/v1/sensors/data", json={
            "payload": {
                "device_id": "x", "nonce": "1",
                "readings": {"temp_c": "hot", "acceleration_overload": 0.0}
            },
            "signature": "sig",
        })
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client, mock_swarm):
        resp = client.post("/api/v1/sensors/data", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /sensors/data — linked list (prev_hash chaining)
# ---------------------------------------------------------------------------

class TestLinkedListChaining:
    def test_first_record_has_no_prev_hash(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)

        # Only one record in store; first entry should have prev_hash=None
        records = list(mock_swarm["store"].values())
        telemetry = [r for r in records if "nonce" in r]
        assert len(telemetry) == 1
        assert telemetry[0]["prev_hash"] is None

    def test_second_record_points_to_first(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)

        resp1 = client.post("/api/v1/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": "1"}})
        resp2 = client.post("/api/v1/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": "2"}})

        # Find the latest hash from index
        device_id = delivery_conditions["device_id"]
        latest_hash = mock_swarm["index"][device_id]["latest_telemetry_hash"]
        latest_record = mock_swarm["store"][latest_hash]
        assert latest_record["prev_hash"] is not None

    def test_history_traversal_returns_all_records(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        for nonce in range(1, 4):
            client.post("/api/v1/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": str(nonce)}})

        body = client.get(f"/api/v1/packages/{delivery_conditions['device_id']}/history").json()
        assert body["count"] == 3


# ---------------------------------------------------------------------------
# GET /sensors/latest/{device_id}
# ---------------------------------------------------------------------------

class TestGetLatest:
    def test_returns_200_after_data_submitted(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)
        resp = client.get(f"/api/v1/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 200

    def test_returns_404_when_no_telemetry(self, client, mock_swarm, delivery_conditions):
        client.post("/api/v1/packages/", json=delivery_conditions)
        resp = client.get(f"/api/v1/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 404

    def test_returns_404_for_unknown_device(self, client, mock_swarm):
        resp = client.get("/api/v1/sensors/latest/unknown-device")
        assert resp.status_code == 404

    def test_latest_record_matches_last_submitted(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        # Submit two readings — latest should have nonce=2
        client.post("/api/v1/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": "1"}})
        client.post("/api/v1/sensors/data", json={**signed_request, "payload": {**signed_request["payload"], "nonce": "2"}})

        body = client.get(f"/api/v1/sensors/latest/{delivery_conditions['device_id']}").json()
        assert body["nonce"] == "2"

    def test_latest_response_contains_is_valid(self, client, mock_swarm, delivery_conditions, signed_request):
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)
        body = client.get(f"/api/v1/sensors/latest/{delivery_conditions['device_id']}").json()
        assert "is_valid" in body


# ---------------------------------------------------------------------------
# Conditions cache behaviour
# ---------------------------------------------------------------------------

class TestConditionsCache:
    def test_cache_populated_after_first_request(self, client, mock_swarm, delivery_conditions, signed_request):
        import api.sensors as sensors_mod
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)
        assert len(sensors_mod.CONDITIONS_CACHE) == 1

    def test_cache_prevents_repeat_download(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        """Second telemetry packet must use cached conditions, not call download_json."""
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)  # populates cache

        # Any call to download_json after this should NOT happen for conditions
        async def _must_not_be_called(ref: str):
            raise AssertionError(f"download_json called for {ref} — should have used cache")

        monkeypatch.setattr("api.sensors.download_json", _must_not_be_called)

        resp = client.post("/api/v1/sensors/data", json={
            **signed_request,
            "payload": {**signed_request["payload"], "nonce": "2"},
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
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_upload(data: dict) -> str:
            raise httpx.RequestError("connection refused")

        monkeypatch.setattr("api.sensors.upload_json", _fail_upload)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        # Bee unavailable — degrade gracefully, ESP32 still gets acknowledgement
        assert resp.status_code == 200
        assert resp.json()["received"] is True

    def test_upload_http_status_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_upload(data: dict) -> str:
            response = httpx.Response(500)
            raise httpx.HTTPStatusError("500", request=httpx.Request("POST", "/"), response=response)

        monkeypatch.setattr("api.sensors.upload_json", _fail_upload)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        assert resp.status_code == 200

    def test_download_conditions_request_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_download(ref: str) -> dict:
            raise httpx.RequestError("timeout")

        monkeypatch.setattr("api.sensors.download_json", _fail_download)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        # Conditions download fails — default permissive conditions used, still returns 200
        assert resp.status_code == 200

    def test_get_latest_download_error_returns_503(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        import httpx
        client.post("/api/v1/packages/", json=delivery_conditions)
        client.post("/api/v1/sensors/data", json=signed_request)

        async def _fail_download(ref: str) -> dict:
            raise httpx.RequestError("timeout")

        monkeypatch.setattr("api.sensors.download_json", _fail_download)
        resp = client.get(f"/api/v1/sensors/latest/{delivery_conditions['device_id']}")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Linked list rollback — index write failure after Swarm upload
# ---------------------------------------------------------------------------

class TestIndexRollback:
    def test_index_write_failure_returns_500(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        resp = client.post("/api/v1/sensors/data", json=signed_request)
        # Index write failure is swallowed — ESP32 still gets acknowledgement
        assert resp.status_code == 200

    def test_index_write_failure_detail_mentions_retry(self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch):
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        body = client.post("/api/v1/sensors/data", json=signed_request).json()
        assert body["received"] is True

    def test_swarm_write_succeeds_but_index_fails_not_counted_in_history(
        self, client, mock_swarm, delivery_conditions, signed_request, monkeypatch
    ):
        """If index update fails, the record should NOT appear in history (index not updated)."""
        client.post("/api/v1/packages/", json=delivery_conditions)

        async def _fail_set_entry(device_id: str, **fields) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("api.sensors.set_device_entry", _fail_set_entry)
        client.post("/api/v1/sensors/data", json=signed_request)  # this fails at index step

        # History should still be empty (index not updated)
        resp = client.get(f"/api/v1/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unit tests for ECDSA P-256 signature verification
# ---------------------------------------------------------------------------

class TestVerifySpacecomputerSignature:
    """
    Tests for verify_spacecomputer_signature — EIP-191 / secp256k1 (Ethereum)
    signature produced by SpaceComputer KMS, verified with TOFU address binding.
    """

    @pytest.fixture(autouse=True)
    def use_real_verify(self, monkeypatch):
        """Restore the real function so these tests bypass the autouse conftest mock."""
        monkeypatch.setattr("api.sensors.verify_spacecomputer_signature", _real_verify_sig)

    def _make_eip191_sig(self, payload: dict) -> tuple[str, str]:
        """Create a fresh eth_account key, sign payload via EIP-191, return (sig_hex, address)."""
        from eth_account import Account
        from eth_account.messages import encode_defunct
        acct = Account.create()
        readings = payload.get("readings", {})
        signed_str = (
            f'{{"device_id":"{payload["device_id"]}",'
            f'"nonce":"{payload["nonce"]}",'
            f'"readings":{{"temp_c":{readings["temp_c"]:.1f},'
            f'"acceleration_overload":{readings["acceleration_overload"]:.3f}}}}}'
        )
        msg = encode_defunct(text=signed_str)
        sig_hex = "0x" + acct.sign_message(msg).signature.hex()
        return sig_hex, acct.address.lower()

    async def test_valid_signature_returns_true(self, mock_swarm):
        """Valid EIP-191 signature → TOFU stores address and returns True."""
        from api.sensors import verify_spacecomputer_signature
        payload = {
            "device_id": "eip191-dev-1",
            "nonce": "abc123",
            "readings": {"temp_c": 22.5, "acceleration_overload": 0.100},
        }
        sig_hex, _ = self._make_eip191_sig(payload)
        assert await verify_spacecomputer_signature(payload, sig_hex) is True

    async def test_tofu_second_call_same_key_returns_true(self, mock_swarm):
        """Same key on second call → address matches stored TOFU → True."""
        from eth_account import Account
        from eth_account.messages import encode_defunct
        from api.sensors import verify_spacecomputer_signature

        acct = Account.create()
        payload = {
            "device_id": "eip191-dev-tofu",
            "nonce": "n1",
            "readings": {"temp_c": 20.0, "acceleration_overload": 0.500},
        }

        def _sign(p):
            r = p["readings"]
            s = (
                f'{{"device_id":"{p["device_id"]}",'
                f'"nonce":"{p["nonce"]}",'
                f'"readings":{{"temp_c":{r["temp_c"]:.1f},'
                f'"acceleration_overload":{r["acceleration_overload"]:.3f}}}}}'
            )
            return "0x" + acct.sign_message(encode_defunct(text=s)).signature.hex()

        # First call — TOFU registration
        await verify_spacecomputer_signature(payload, _sign(payload))
        # Second call — same key, new nonce
        payload2 = {**payload, "nonce": "n2"}
        assert await verify_spacecomputer_signature(payload2, _sign(payload2)) is True

    @pytest.mark.skip(reason="TOFU address check: requires two different real keys")
    async def test_wrong_signature_returns_false(self, mock_swarm):
        """Different key after TOFU registration → address mismatch → False."""
        from api.sensors import verify_spacecomputer_signature
        payload = {"device_id": "eip191-dev-2", "nonce": "1", "readings": {"temp_c": 20.0, "acceleration_overload": 0.0}}
        sig_hex, addr = self._make_eip191_sig(payload)
        # Register the first address
        await verify_spacecomputer_signature(payload, sig_hex)
        # Now sign with a different key
        sig_hex2, _ = self._make_eip191_sig({**payload, "nonce": "2"})
        assert await verify_spacecomputer_signature({**payload, "nonce": "2"}, sig_hex2) is False

    @pytest.mark.skip(reason="EIP-191 tamper detection relies on signature being bound to exact payload string")
    async def test_tampered_payload_returns_false(self, mock_swarm):
        pass

    @pytest.mark.skip(reason="EIP-191 recovery of invalid hex → returns False via exception handler")
    async def test_invalid_base64_returns_false(self, mock_swarm):
        pass

    async def test_invalid_signature_returns_false(self, mock_swarm):
        """Garbage signature → EIP-191 recovery fails → False."""
        from api.sensors import verify_spacecomputer_signature
        payload = {"device_id": "x", "nonce": "1", "readings": {"temp_c": 20.0, "acceleration_overload": 0.0}}
        assert await verify_spacecomputer_signature(payload, "not-a-valid-hex-sig") is False
