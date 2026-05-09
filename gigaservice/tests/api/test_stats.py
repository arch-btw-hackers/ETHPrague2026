"""
Tests for GET /stats/hotspots and the notification service.
"""
import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    device_id: str,
    is_valid: bool,
    reason: str = "",
    lat: float | None = None,
    lon: float | None = None,
    prev_hash: str | None = None,
) -> dict:
    return {
        "device_id": device_id,
        "nonce": 1,
        "readings": {
            "temp_c": 26.0 if not is_valid else 20.0,
            "acceleration_x": 0.1,
            "acceleration_y": 0.1,
            "lat": lat,
            "lon": lon,
        },
        "is_valid": is_valid,
        "reason": reason,
        "timestamp": "2026-05-09T12:00:00+00:00",
        "prev_hash": prev_hash,
    }


# ---------------------------------------------------------------------------
# /stats/hotspots
# ---------------------------------------------------------------------------

class TestHotspotsEmpty:
    def test_no_devices_returns_empty_list(self, client: TestClient, monkeypatch):
        monkeypatch.setattr("api.stats.list_all_entries", AsyncMock(return_value={}))
        resp = client.get("/stats/hotspots")
        assert resp.status_code == 200
        assert resp.json() == {"hotspots": []}

    def test_device_with_no_telemetry_hash(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"tracker-001": {}}),
        )
        resp = client.get("/stats/hotspots")
        assert resp.status_code == 200
        assert resp.json() == {"hotspots": []}


class TestHotspotsFiltering:
    def test_valid_record_not_included(self, client: TestClient, monkeypatch):
        record = _make_record("t1", is_valid=True, lat=50.0, lon=14.0)
        store = {"hash1": record}
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "hash1"}}),
        )
        monkeypatch.setattr(
            "api.stats.download_json", AsyncMock(side_effect=lambda h: store[h])
        )
        resp = client.get("/stats/hotspots")
        assert resp.json() == {"hotspots": []}

    def test_invalid_without_gps_not_included(self, client: TestClient, monkeypatch):
        record = _make_record("t1", is_valid=False, reason="temp")
        # lat/lon are None — should not appear
        store = {"hash1": record}
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "hash1"}}),
        )
        monkeypatch.setattr(
            "api.stats.download_json", AsyncMock(side_effect=lambda h: store[h])
        )
        resp = client.get("/stats/hotspots")
        assert resp.json() == {"hotspots": []}

    def test_invalid_with_gps_included(self, client: TestClient, monkeypatch):
        record = _make_record(
            "t1", is_valid=False, reason="temp 26.0°C > 25°C", lat=50.07, lon=14.43
        )
        store = {"hash1": record}
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "hash1"}}),
        )
        monkeypatch.setattr(
            "api.stats.download_json", AsyncMock(side_effect=lambda h: store[h])
        )
        resp = client.get("/stats/hotspots")
        data = resp.json()
        assert len(data["hotspots"]) == 1
        h = data["hotspots"][0]
        assert h["lat"] == 50.07
        assert h["lon"] == 14.43
        assert h["device_id"] == "t1"
        assert "temp" in h["reason"]

    def test_multiple_devices(self, client: TestClient, monkeypatch):
        records = {
            "h1": _make_record("t1", is_valid=False, lat=50.0, lon=14.0, reason="temp"),
            "h2": _make_record("t2", is_valid=False, lat=51.0, lon=15.0, reason="accel"),
        }
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(
                return_value={
                    "t1": {"latest_telemetry_hash": "h1"},
                    "t2": {"latest_telemetry_hash": "h2"},
                }
            ),
        )
        monkeypatch.setattr(
            "api.stats.download_json", AsyncMock(side_effect=lambda h: records[h])
        )
        resp = client.get("/stats/hotspots")
        hotspots = resp.json()["hotspots"]
        device_ids = {h["device_id"] for h in hotspots}
        assert device_ids == {"t1", "t2"}

    def test_linked_list_traversal(self, client: TestClient, monkeypatch):
        """Violations in older records (via prev_hash chain) are collected."""
        old_record = _make_record(
            "t1", is_valid=False, lat=48.0, lon=16.0, reason="temp", prev_hash=None
        )
        new_record = _make_record(
            "t1", is_valid=True, prev_hash="old_hash"
        )
        store = {"new_hash": new_record, "old_hash": old_record}
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "new_hash"}}),
        )
        monkeypatch.setattr(
            "api.stats.download_json", AsyncMock(side_effect=lambda h: store[h])
        )
        resp = client.get("/stats/hotspots")
        hotspots = resp.json()["hotspots"]
        assert len(hotspots) == 1
        assert hotspots[0]["lat"] == 48.0

    def test_download_error_skips_device(self, client: TestClient, monkeypatch):
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"broken": {"latest_telemetry_hash": "bad_hash"}}),
        )
        monkeypatch.setattr(
            "api.stats.download_json",
            AsyncMock(side_effect=Exception("Swarm unavailable")),
        )
        resp = client.get("/stats/hotspots")
        assert resp.status_code == 200
        assert resp.json() == {"hotspots": []}


# ---------------------------------------------------------------------------
# Sensor data with GPS coordinates
# ---------------------------------------------------------------------------

class TestSensorDataWithGPS:
    """Verify that lat/lon in the payload round-trips correctly."""

    def test_gps_coords_stored_in_record(
        self, client: TestClient, mock_swarm, monkeypatch
    ):
        monkeypatch.setattr(
            "api.sensors.verify_spacecomputer_signature", AsyncMock(return_value=True)
        )
        mock_swarm["index"]["gps-dev"] = {
            "conditions_hash": "cond_hash",
            "latest_telemetry_hash": None,
        }
        mock_swarm["store"]["cond_hash"] = {
            "max_temp_c": 25.0,
            "max_acceleration": 2.0,
        }
        payload = {
            "payload": {
                "device_id": "gps-dev",
                "nonce": 1,
                "readings": {
                    "temp_c": 20.0,
                    "acceleration_x": 0.1,
                    "acceleration_y": 0.1,
                    "lat": 50.07,
                    "lon": 14.43,
                },
            },
            "signature": "sig",
        }
        resp = client.post("/sensors/data", json=payload)
        assert resp.status_code == 200
        # Find the stored telemetry record
        stored = [
            v for v in mock_swarm["store"].values()
            if isinstance(v, dict) and v.get("device_id") == "gps-dev"
            and "is_valid" in v
        ]
        assert stored, "Telemetry record not found in mock store"
        readings = stored[0]["readings"]
        assert readings["lat"] == 50.07
        assert readings["lon"] == 14.43


# ---------------------------------------------------------------------------
# Notifications — smtplib must be mocked in CI
# ---------------------------------------------------------------------------

class TestSendHtmlAlert:
    async def test_sends_email_when_password_set(self, monkeypatch, tmp_path):
        from services.notifications import send_html_alert, _TEMPLATE_PATH

        # Create a minimal template in tmp dir
        template = tmp_path / "alert_email.html"
        template.write_text(
            "<html>{device_id} {reason} {timestamp} {explorer_link}</html>",
            encoding="utf-8",
        )
        monkeypatch.setattr("services.notifications._TEMPLATE_PATH", template)
        monkeypatch.setenv("SMTP_PASSWORD", "test-password")

        mock_smtp_instance = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_cls:
            mock_smtp_instance.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp_instance.__exit__ = MagicMock(return_value=False)
            await send_html_alert(
                device_id="t1",
                reason="temp violation",
                recipient_email="owner@example.com",
                tx_hash_or_address="0x" + "ab" * 20,
            )
        mock_smtp_cls.assert_called_once()
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.sendmail.assert_called_once()

    async def test_skips_email_when_no_password(self, monkeypatch, tmp_path):
        from services.notifications import send_html_alert

        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        with patch("smtplib.SMTP") as mock_smtp_cls:
            await send_html_alert(
                device_id="t1",
                reason="temp",
                recipient_email="owner@example.com",
                tx_hash_or_address="0x" + "00" * 20,
            )
        mock_smtp_cls.assert_not_called()

    async def test_tx_hash_builds_tx_link(self, monkeypatch, tmp_path):
        from services.notifications import _build_explorer_link

        link = _build_explorer_link("0x" + "ab" * 32)  # 66 chars → /tx/
        assert "/tx/" in link

    async def test_address_builds_address_link(self, monkeypatch):
        from services.notifications import _build_explorer_link

        link = _build_explorer_link("0x" + "ab" * 20)  # 42 chars → /address/
        assert "/address/" in link

    async def test_smtp_failure_does_not_raise(self, monkeypatch, tmp_path):
        """Email errors are logged but never propagate to the caller."""
        from services.notifications import send_html_alert

        template = tmp_path / "alert_email.html"
        template.write_text(
            "<html>{device_id} {reason} {timestamp} {explorer_link}</html>",
            encoding="utf-8",
        )
        monkeypatch.setattr("services.notifications._TEMPLATE_PATH", template)
        monkeypatch.setenv("SMTP_PASSWORD", "pw")

        with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("connect failed")):
            # Must not raise
            await send_html_alert("t1", "reason", "a@b.com", "0x" + "aa" * 20)


# ---------------------------------------------------------------------------
# Violation background task integration
# ---------------------------------------------------------------------------

class TestViolationTriggersAlert:
    """When a sensor reading is invalid, the background task should call
    send_html_alert (mocked via mock_blockchain autouse fixture)."""

    def test_violation_calls_handle_violation_bg_task(
        self, client: TestClient, mock_swarm, monkeypatch
    ):
        monkeypatch.setattr(
            "api.sensors.verify_spacecomputer_signature", AsyncMock(return_value=True)
        )
        alert_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("api.sensors.send_html_alert", alert_mock)
        monkeypatch.setenv("ALERT_RECIPIENT_EMAIL", "owner@example.com")

        mock_swarm["index"]["vdev"] = {
            "conditions_hash": "ch",
            "latest_telemetry_hash": None,
        }
        mock_swarm["store"]["ch"] = {"max_temp_c": 25.0, "max_acceleration": 2.0}

        # Temp is too high → violation
        payload = {
            "payload": {
                "device_id": "vdev",
                "nonce": 1,
                "readings": {
                    "temp_c": 30.0,
                    "acceleration_x": 0.1,
                    "acceleration_y": 0.1,
                },
            },
            "signature": "sig",
        }
        resp = client.post("/sensors/data", json=payload)
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False
        # send_html_alert is called in a background task; TestClient runs them synchronously
        alert_mock.assert_called_once()
        _, kwargs = alert_mock.call_args
        call_args = alert_mock.call_args[0]
        assert call_args[0] == "vdev"  # device_id
        assert "temp" in call_args[1]  # reason


# ---------------------------------------------------------------------------
# POST /stats/analyze-route
# ---------------------------------------------------------------------------

class TestAnalyzeRouteLow:
    """No waypoints fall within 2 km of any hotspot → LOW risk."""

    def test_empty_waypoints_returns_low(self, client: TestClient, monkeypatch):
        monkeypatch.setattr("api.stats.list_all_entries", AsyncMock(return_value={}))
        resp = client.post("/stats/analyze-route", json={"waypoints": []})
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "LOW"
        assert body["warnings"] == []

    def test_no_hotspots_returns_low(self, client: TestClient, monkeypatch):
        monkeypatch.setattr("api.stats.list_all_entries", AsyncMock(return_value={}))
        payload = {"waypoints": [{"lat": 50.0, "lon": 14.0}]}
        resp = client.post("/stats/analyze-route", json=payload)
        assert resp.status_code == 200
        assert resp.json()["risk_level"] == "LOW"

    def test_waypoint_far_from_hotspot_returns_low(self, client: TestClient, monkeypatch):
        # Hotspot at 50.0, 14.0 — waypoint 50 km away
        record = _make_record("t1", is_valid=False, lat=50.0, lon=14.0, reason="temp")
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        # ~55 km north
        payload = {"waypoints": [{"lat": 50.5, "lon": 14.0}]}
        resp = client.post("/stats/analyze-route", json=payload)
        assert resp.json()["risk_level"] == "LOW"
        assert resp.json()["warnings"] == []


class TestAnalyzeRouteMedium:
    """1–2 waypoints fall within 2 km of a hotspot → MEDIUM risk."""

    def _hotspot_at(self, lat, lon):
        return _make_record("t1", is_valid=False, lat=lat, lon=lon, reason="temp")

    def test_one_hit_returns_medium(self, client: TestClient, monkeypatch):
        record = self._hotspot_at(50.0, 14.0)
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        # Waypoint ~1.1 km away (0.01° lat ≈ 1.11 km)
        payload = {"waypoints": [{"lat": 50.01, "lon": 14.0}]}
        resp = client.post("/stats/analyze-route", json=payload)
        body = resp.json()
        assert body["risk_level"] == "MEDIUM"
        assert len(body["warnings"]) == 1
        assert "50.0" in body["warnings"][0]

    def test_two_hits_returns_medium(self, client: TestClient, monkeypatch):
        hs = {"lat": 50.0, "lon": 14.0}
        records = {
            "h1": _make_record("t1", is_valid=False, lat=hs["lat"], lon=hs["lon"], reason="temp"),
        }
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect=records.get))
        # Two waypoints both ~1.1 km from hotspot
        payload = {
            "waypoints": [
                {"lat": 50.01, "lon": 14.0},
                {"lat": 49.99, "lon": 14.0},
            ]
        }
        resp = client.post("/stats/analyze-route", json=payload)
        body = resp.json()
        assert body["risk_level"] == "MEDIUM"
        assert len(body["warnings"]) == 2

    def test_warning_contains_hotspot_coordinates(self, client: TestClient, monkeypatch):
        record = self._hotspot_at(51.5, 0.1)
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        payload = {"waypoints": [{"lat": 51.505, "lon": 0.1}]}
        resp = client.post("/stats/analyze-route", json=payload)
        warning = resp.json()["warnings"][0]
        assert "51.5" in warning
        assert "0.1" in warning


class TestAnalyzeRouteHigh:
    """3+ waypoints fall within 2 km of hotspots → HIGH risk."""

    def test_three_hits_returns_high(self, client: TestClient, monkeypatch):
        # One hotspot; three close waypoints, one far
        record = _make_record("t1", is_valid=False, lat=50.0, lon=14.0, reason="temp")
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        payload = {
            "waypoints": [
                {"lat": 50.005, "lon": 14.0},   # ~0.55 km — HIT
                {"lat": 50.01, "lon": 14.0},    # ~1.11 km — HIT
                {"lat": 49.99, "lon": 14.0},    # ~1.11 km — HIT
                {"lat": 50.5,  "lon": 14.0},    # ~55 km  — miss
            ]
        }
        resp = client.post("/stats/analyze-route", json=payload)
        body = resp.json()
        assert body["risk_level"] == "HIGH"
        assert len(body["warnings"]) == 3

    def test_multiple_hotspots_accumulate_warnings(self, client: TestClient, monkeypatch):
        records = {
            "h1": _make_record("t1", is_valid=False, lat=50.0, lon=14.0, reason="temp"),
            "h2": _make_record("t2", is_valid=False, lat=51.0, lon=15.0, reason="accel"),
            "h3": _make_record("t3", is_valid=False, lat=52.0, lon=16.0, reason="temp"),
        }
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(
                return_value={
                    "t1": {"latest_telemetry_hash": "h1"},
                    "t2": {"latest_telemetry_hash": "h2"},
                    "t3": {"latest_telemetry_hash": "h3"},
                }
            ),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect=records.get))
        # One waypoint near each hotspot
        payload = {
            "waypoints": [
                {"lat": 50.005, "lon": 14.0},
                {"lat": 51.005, "lon": 15.0},
                {"lat": 52.005, "lon": 16.0},
            ]
        }
        resp = client.post("/stats/analyze-route", json=payload)
        body = resp.json()
        assert body["risk_level"] == "HIGH"
        assert len(body["warnings"]) == 3


class TestAnalyzeRouteEdgeCases:
    def test_waypoint_exactly_on_hotspot_is_hit(self, client: TestClient, monkeypatch):
        record = _make_record("t1", is_valid=False, lat=48.8566, lon=2.3522, reason="temp")
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        payload = {"waypoints": [{"lat": 48.8566, "lon": 2.3522}]}
        resp = client.post("/stats/analyze-route", json=payload)
        assert resp.json()["risk_level"] == "MEDIUM"

    def test_valid_records_dont_create_hotspots(self, client: TestClient, monkeypatch):
        # A valid record with GPS must NOT count as a hotspot
        record = _make_record("t1", is_valid=True, lat=50.0, lon=14.0)
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        # Waypoint right on top of the non-hotspot
        payload = {"waypoints": [{"lat": 50.0, "lon": 14.0}]}
        resp = client.post("/stats/analyze-route", json=payload)
        assert resp.json()["risk_level"] == "LOW"
        assert resp.json()["warnings"] == []

    def test_invalid_record_without_gps_not_a_hotspot(self, client: TestClient, monkeypatch):
        # Violation with no GPS coords — must not appear as a hotspot
        record = _make_record("t1", is_valid=False, reason="temp")
        monkeypatch.setattr(
            "api.stats.list_all_entries",
            AsyncMock(return_value={"t1": {"latest_telemetry_hash": "h1"}}),
        )
        monkeypatch.setattr("api.stats.download_json", AsyncMock(side_effect={"h1": record}.get))
        payload = {"waypoints": [{"lat": 0.0, "lon": 0.0}]}
        resp = client.post("/stats/analyze-route", json=payload)
        assert resp.json()["risk_level"] == "LOW"
