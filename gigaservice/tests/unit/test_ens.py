"""
Unit tests for ENS resolution helpers in services/blockchain.py.

All tests mock the AsyncWeb3 instance so no live RPC node is needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.blockchain import resolve_ens, reverse_resolve_ens, _get_web3


# ---------------------------------------------------------------------------
# resolve_ens
# ---------------------------------------------------------------------------

class TestResolveEns:
    """Forward ENS resolution: name.eth → 0x address."""

    def test_non_ens_string_returned_unchanged(self):
        """Regular identifiers (device IDs, addresses) pass through as-is."""
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(resolve_ens("tracker-001"))
        assert result == "tracker-001"

    def test_hex_address_returned_unchanged(self):
        import asyncio
        addr = "0xDeAdBeEf000000000000000000000000DeAdBeEf"
        result = asyncio.get_event_loop().run_until_complete(resolve_ens(addr))
        assert result == addr

    def test_eth_name_raises_when_rpc_not_configured(self, monkeypatch):
        """ENS resolution must fail loudly when WEB3_RPC_URL is absent."""
        monkeypatch.delenv("WEB3_RPC_URL", raising=False)
        import asyncio
        with pytest.raises(ValueError, match="WEB3_RPC_URL"):
            asyncio.get_event_loop().run_until_complete(resolve_ens("vitalik.eth"))

    def test_eth_name_resolved_via_w3_ens(self, monkeypatch):
        """Happy path: w3.ens.address returns an address."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        expected = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

        mock_w3 = MagicMock()
        mock_w3.ens.address = AsyncMock(return_value=expected)
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(resolve_ens("vitalik.eth"))
        assert result == expected
        mock_w3.ens.address.assert_called_once_with("vitalik.eth")

    def test_unregistered_eth_name_raises(self, monkeypatch):
        """w3.ens.address returning None must raise ValueError."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")

        mock_w3 = MagicMock()
        mock_w3.ens.address = AsyncMock(return_value=None)
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        with pytest.raises(ValueError, match="has no registered address"):
            asyncio.get_event_loop().run_until_complete(resolve_ens("nobody.eth"))

    def test_rpc_error_raises_value_error(self, monkeypatch):
        """RPC-level exceptions are re-raised as ValueError."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")

        mock_w3 = MagicMock()
        mock_w3.ens.address = AsyncMock(side_effect=ConnectionError("RPC down"))
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        with pytest.raises(ValueError, match="ENS resolution failed"):
            asyncio.get_event_loop().run_until_complete(resolve_ens("fail.eth"))


# ---------------------------------------------------------------------------
# reverse_resolve_ens
# ---------------------------------------------------------------------------

class TestReverseResolveEns:
    """Reverse ENS resolution: 0x address → name.eth (or None)."""

    def test_returns_none_when_rpc_not_configured(self, monkeypatch):
        monkeypatch.delenv("WEB3_RPC_URL", raising=False)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            reverse_resolve_ens("0xdeadbeef")
        )
        assert result is None

    def test_returns_ens_name_when_found(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")

        mock_w3 = MagicMock()
        mock_w3.ens.name = AsyncMock(return_value="vitalik.eth")
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            reverse_resolve_ens("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
        )
        assert result == "vitalik.eth"

    def test_returns_none_when_no_reverse_record(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")

        mock_w3 = MagicMock()
        mock_w3.ens.name = AsyncMock(return_value=None)
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            reverse_resolve_ens("0xdeadbeef")
        )
        assert result is None

    def test_returns_none_on_rpc_error(self, monkeypatch):
        """RPC errors are swallowed — never raises."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")

        mock_w3 = MagicMock()
        mock_w3.ens.name = AsyncMock(side_effect=ConnectionError("RPC down"))
        monkeypatch.setattr("services.blockchain._w3", mock_w3)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            reverse_resolve_ens("0xdeadbeef")
        )
        assert result is None


# ---------------------------------------------------------------------------
# ENS resolution integrated into POST /packages/
# ---------------------------------------------------------------------------

class TestEnsResolutionInPackagesEndpoint:
    def test_ens_device_id_resolved_before_storage(self, client, mock_swarm, monkeypatch):
        """When device_id is an ENS name it should be stored as the resolved address."""
        resolved_addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        monkeypatch.setattr(
            "api.packages.resolve_ens",
            AsyncMock(return_value=resolved_addr),
        )

        resp = client.post("/packages/", json={
            "device_id": "tracker.eth",
            "max_temp_c": 20.0,
            "max_acceleration": 1.5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["device_id"] == resolved_addr
        # Resolved address used as index key
        assert resolved_addr in mock_swarm["index"]

    def test_unresolvable_ens_name_returns_400(self, client, mock_swarm, monkeypatch):
        """If ENS resolution fails the endpoint returns 400 Bad Request."""
        monkeypatch.setattr(
            "api.packages.resolve_ens",
            AsyncMock(side_effect=ValueError("ENS name 'bad.eth' has no registered address")),
        )

        resp = client.post("/packages/", json={
            "device_id": "bad.eth",
            "max_temp_c": 20.0,
            "max_acceleration": 1.5,
        })
        assert resp.status_code == 400
        assert "bad.eth" in resp.json()["detail"]

    def test_regular_device_id_unaffected(self, client, mock_swarm):
        """Non-ENS identifiers go through resolve_ens unchanged — no mock needed."""
        resp = client.post("/packages/", json={
            "device_id": "plain-tracker-99",
            "max_temp_c": 22.0,
            "max_acceleration": 3.0,
        })
        assert resp.status_code == 200
        assert resp.json()["device_id"] == "plain-tracker-99"
