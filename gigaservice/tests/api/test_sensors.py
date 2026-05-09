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
    def _post_reading(self, client, mock_swarm, temp_c, acc_x, acc_y, conditions=None):
        cond = conditions or {"device_id": "tracker-001", "max_temp_c": 25.0, "max_acceleration": 2.0}
        client.post("/packages/", json=cond)
        req = {
            "payload": {
                "device_id": cond["device_id"],
                "nonce": 1,
                "readings": {"temp_c": temp_c, "acceleration_x": acc_x, "acceleration_y": acc_y},
            },
            "signature": "sig",
        }
        return client.post("/sensors/data", json=req).json()

    def test_temp_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=30.0, acc_x=0.0, acc_y=0.0)
        assert body["is_valid"] is False

    def test_acc_x_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_x=5.0, acc_y=0.0)
        assert body["is_valid"] is False

    def test_acc_y_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_x=0.0, acc_y=5.0)
        assert body["is_valid"] is False

    def test_negative_acc_x_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_x=-5.0, acc_y=0.0)
        assert body["is_valid"] is False

    def test_negative_acc_y_exceeded_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=20.0, acc_x=0.0, acc_y=-5.0)
        assert body["is_valid"] is False

    def test_exact_boundary_is_valid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=25.0, acc_x=2.0, acc_y=2.0)
        assert body["is_valid"] is True

    def test_one_tick_over_temp_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=25.001, acc_x=0.0, acc_y=0.0)
        assert body["is_valid"] is False

    def test_all_violated_is_invalid(self, client, mock_swarm):
        body = self._post_reading(client, mock_swarm, temp_c=99.0, acc_x=99.0, acc_y=99.0)
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
            "payload": {"device_id": "x", "nonce": 1, "readings": {"temp_c": 20.0, "acceleration_x": 0.0, "acceleration_y": 0.0}}
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
                "readings": {"temp_c": "hot", "acceleration_x": 0.0, "acceleration_y": 0.0}
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
