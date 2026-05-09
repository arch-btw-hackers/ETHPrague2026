"""
Unit tests for services/blockchain.py — submit_tracker_state function.

All tests mock AsyncWeb3 so no real RPC connection is made in CI.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_w3_mock(tx_hex: str = "0x" + "ab" * 32) -> MagicMock:
    """Return a minimal AsyncWeb3 mock that simulates a successful tx send."""
    # submitTrackerState(...).build_transaction({...}) → dict
    mock_fn = MagicMock()
    mock_fn.build_transaction = AsyncMock(return_value={"gas": 21000})

    mock_contract = MagicMock()
    mock_contract.functions.submitTrackerState.return_value = mock_fn

    # Signed tx — raw_transaction is bytes-like
    mock_signed = MagicMock()
    mock_signed.raw_transaction = b"\x00" * 32

    # Account mock
    mock_account = MagicMock()
    mock_account.address = "0x" + "de" * 20
    mock_account.sign_transaction = MagicMock(return_value=mock_signed)

    # Return value of send_raw_transaction must have .hex() → tx_hex
    mock_hash = MagicMock()
    mock_hash.hex.return_value = tx_hex

    # w3.eth — gas_price is awaited as a property, NOT called, so use a coroutine object
    async def _gas_price_coro():
        return int(1e9)

    mock_eth = MagicMock()
    mock_eth.get_transaction_count = AsyncMock(return_value=0)
    mock_eth.gas_price = _gas_price_coro()
    mock_eth.send_raw_transaction = AsyncMock(return_value=mock_hash)
    mock_eth.contract.return_value = mock_contract
    mock_eth.account.from_key.return_value = mock_account

    mock_w3 = MagicMock()
    mock_w3.eth = mock_eth

    return mock_w3


# ---------------------------------------------------------------------------
# Dev-mode (missing env vars)
# ---------------------------------------------------------------------------

class TestSubmitTrackerStateDevMode:
    async def test_returns_none_when_rpc_url_missing(self, monkeypatch):
        monkeypatch.delenv("WEB3_RPC_URL", raising=False)
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.setenv("WEB3_PRIVATE_KEY", "0x" + "aa" * 32)

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(1, False, "proof")
        assert result is None

    async def test_returns_none_when_contract_address_missing(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.delenv("CONTRACT_ADDRESS", raising=False)
        monkeypatch.setenv("WEB3_PRIVATE_KEY", "0x" + "aa" * 32)

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(1, False, "proof")
        assert result is None

    async def test_returns_none_when_private_key_missing(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.delenv("WEB3_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("SERVER_PRIVATE_KEY", raising=False)

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(1, False, "proof")
        assert result is None

    async def test_accepts_legacy_server_private_key(self, monkeypatch):
        """SERVER_PRIVATE_KEY is the legacy fallback for WEB3_PRIVATE_KEY."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.delenv("WEB3_PRIVATE_KEY", raising=False)
        monkeypatch.setenv("SERVER_PRIVATE_KEY", "0x" + "bb" * 32)

        mock_w3 = _make_w3_mock()
        monkeypatch.setattr("services.blockchain._get_web3", lambda: mock_w3)
        monkeypatch.setattr(
            "services.blockchain.AsyncWeb3.to_checksum_address",
            lambda addr: addr,
        )

        import services.blockchain as bc
        bc._w3 = None  # reset singleton

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(42, False, "swarm_hash")
        # Any non-None return means the key was picked up
        assert result is not None


# ---------------------------------------------------------------------------
# On-chain success path
# ---------------------------------------------------------------------------

class TestSubmitTrackerStateOnChain:
    async def test_returns_tx_hash_on_success(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.setenv("WEB3_PRIVATE_KEY", "0x" + "aa" * 32)

        expected_hex = "0x" + "ab" * 32
        mock_w3 = _make_w3_mock(tx_hex=expected_hex)
        monkeypatch.setattr("services.blockchain._get_web3", lambda: mock_w3)
        monkeypatch.setattr(
            "services.blockchain.AsyncWeb3.to_checksum_address",
            lambda addr: addr,
        )

        import services.blockchain as bc
        bc._w3 = None

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(99, False, "0xdeadbeef")
        assert result == expected_hex

    async def test_calls_submitTrackerState_with_correct_args(self, monkeypatch):
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.setenv("WEB3_PRIVATE_KEY", "0x" + "aa" * 32)

        mock_w3 = _make_w3_mock()
        monkeypatch.setattr("services.blockchain._get_web3", lambda: mock_w3)
        monkeypatch.setattr(
            "services.blockchain.AsyncWeb3.to_checksum_address",
            lambda addr: addr,
        )

        import services.blockchain as bc
        bc._w3 = None

        from services.blockchain import submit_tracker_state
        await submit_tracker_state(7, False, "abc123")

        mock_w3.eth.contract.return_value.functions.submitTrackerState.assert_called_once_with(
            7, False, "abc123"
        )

    async def test_rpc_error_returns_none(self, monkeypatch):
        """Network / gas errors are swallowed and return None instead of raising."""
        monkeypatch.setenv("WEB3_RPC_URL", "http://localhost:8545")
        monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "cc" * 20)
        monkeypatch.setenv("WEB3_PRIVATE_KEY", "0x" + "aa" * 32)

        mock_w3 = _make_w3_mock()
        # Override send_raw_transaction to raise
        mock_w3.eth.send_raw_transaction = AsyncMock(
            side_effect=Exception("insufficient funds for gas")
        )
        monkeypatch.setattr("services.blockchain._get_web3", lambda: mock_w3)
        monkeypatch.setattr(
            "services.blockchain.AsyncWeb3.to_checksum_address",
            lambda addr: addr,
        )

        import services.blockchain as bc
        bc._w3 = None

        from services.blockchain import submit_tracker_state
        result = await submit_tracker_state(1, False, "proof")
        assert result is None


# ---------------------------------------------------------------------------
# _handle_violation integration — verify submit_tracker_state is called
# ---------------------------------------------------------------------------

class TestHandleViolationCallsSubmitTrackerState:
    def test_submit_tracker_state_called_on_violation(
        self, client, mock_swarm, monkeypatch
    ):
        monkeypatch.setattr(
            "api.sensors.verify_spacecomputer_signature", AsyncMock(return_value=True)
        )
        submit_mock = AsyncMock(return_value="0x" + "cd" * 32)
        monkeypatch.setattr("api.sensors.submit_tracker_state", submit_mock)

        mock_swarm["index"]["ship-1"] = {
            "conditions_hash": "cond",
            "latest_telemetry_hash": None,
        }
        mock_swarm["store"]["cond"] = {"max_temp_c": 25.0, "max_acceleration": 2.0}

        payload = {
            "payload": {
                "device_id": "ship-1",
                "nonce": 1,
                "readings": {
                    "temp_c": 35.0,  # violation
                    "acceleration_x": 0.1,
                    "acceleration_y": 0.1,
                },
            },
            "signature": "sig",
        }
        resp = client.post("/sensors/data", json=payload)
        assert resp.status_code == 200
        submit_mock.assert_called_once()
        args = submit_mock.call_args[1]  # kwargs
        assert args["is_good"] is False
        assert "temp" in args.get("telemetry_proof", "") or isinstance(args.get("telemetry_proof"), str)

    def test_swarm_hash_used_as_telemetry_proof(
        self, client, mock_swarm, monkeypatch
    ):
        """The Swarm reference of the stored record is passed as telemetryProof."""
        monkeypatch.setattr(
            "api.sensors.verify_spacecomputer_signature", AsyncMock(return_value=True)
        )
        submit_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("api.sensors.submit_tracker_state", submit_mock)

        mock_swarm["index"]["ship-2"] = {
            "conditions_hash": "ch2",
            "latest_telemetry_hash": None,
        }
        mock_swarm["store"]["ch2"] = {"max_temp_c": 25.0, "max_acceleration": 2.0}

        payload = {
            "payload": {
                "device_id": "ship-2",
                "nonce": 1,
                "readings": {"temp_c": 40.0, "acceleration_x": 0.1, "acceleration_y": 0.1},
            },
            "signature": "sig",
        }
        client.post("/sensors/data", json=payload)

        # telemetry_proof should be a non-empty string (the Swarm hash)
        proof = submit_mock.call_args[1].get("telemetry_proof", "")
        assert isinstance(proof, str) and len(proof) > 0
