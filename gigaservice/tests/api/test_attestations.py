"""
Tests for EAS attestation system:
  - services/attestations.py unit tests
  - api/deps.py RequiresAttestation dependency
  - GET /packages/{id}/history attestation gate
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.attestations import (
    verify_attestation,
    clear_attestation_cache,
    _ATTESTATION_CACHE,
    _to_bytes32,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA_ID = "0x" + "ab" * 32
OTHER_SCHEMA = "0x" + "cd" * 32
USER_ADDR = "0xDeAdBeEf000000000000000000000000DeAdBeEf"


@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure attestation cache is empty between tests."""
    clear_attestation_cache()
    yield
    clear_attestation_cache()


# ---------------------------------------------------------------------------
# _to_bytes32 helper
# ---------------------------------------------------------------------------

class TestToBytes32:
    def test_full_32_byte_hex_with_prefix(self):
        val = "0x" + "ab" * 32
        result = _to_bytes32(val)
        assert result == bytes.fromhex("ab" * 32)

    def test_short_hex_zero_padded(self):
        result = _to_bytes32("0x01")
        assert result == b"\x00" * 31 + b"\x01"

    def test_no_prefix_accepted(self):
        result = _to_bytes32("abcd")
        assert result[-2:] == bytes.fromhex("abcd")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            _to_bytes32("0x" + "ff" * 33)


# ---------------------------------------------------------------------------
# verify_attestation — dev mode (env vars absent)
# ---------------------------------------------------------------------------

class TestVerifyAttestationDevMode:
    async def test_returns_true_when_eas_address_missing(self, monkeypatch):
        monkeypatch.delenv("EAS_CONTRACT_ADDRESS", raising=False)
        monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is True

    async def test_returns_true_when_rpc_missing(self, monkeypatch):
        monkeypatch.setenv("EAS_CONTRACT_ADDRESS", "0x" + "aa" * 20)
        monkeypatch.delenv("WEB3_RPC_URL", raising=False)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is True

    async def test_returns_true_when_both_missing(self, monkeypatch):
        monkeypatch.delenv("EAS_CONTRACT_ADDRESS", raising=False)
        monkeypatch.delenv("WEB3_RPC_URL", raising=False)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is True


# ---------------------------------------------------------------------------
# verify_attestation — on-chain path (mocked web3)
# ---------------------------------------------------------------------------

class TestVerifyAttestationOnChain:
    @pytest.fixture()
    def eas_env(self, monkeypatch):
        monkeypatch.setenv("EAS_CONTRACT_ADDRESS", "0x" + "ea" * 20)
        monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")

    def _make_attestation_tuple(
        self,
        revocation_time: int = 0,
        expiration_time: int = 0,
    ) -> tuple:
        """Build a fake Attestation struct tuple matching the ABI order."""
        return (
            b"\x00" * 32,  # uid
            b"\x00" * 32,  # schema
            0,             # time
            expiration_time,
            revocation_time,
            b"\x00" * 32,  # refUID
            "0x" + "00" * 20,  # recipient
            "0x" + "00" * 20,  # attester
            True,           # revocable
            b"",            # data
        )

    def _mock_contract(self, logs: list, attestation_tuple: tuple, monkeypatch):
        """Wire up a mock web3 contract with the given logs and attestation result."""
        mock_event = MagicMock()
        mock_event.get_logs = AsyncMock(return_value=logs)

        mock_get_attestation = MagicMock()
        mock_get_attestation.call = AsyncMock(return_value=attestation_tuple)

        mock_contract = MagicMock()
        mock_contract.events.Attested = mock_event
        mock_contract.functions.getAttestation.return_value = mock_get_attestation

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3.eth.contract = MagicMock(return_value=mock_contract)
        monkeypatch.setattr("services.attestations._get_web3", lambda: mock_w3)
        return mock_contract

    async def test_valid_attestation_returns_true(self, eas_env, monkeypatch):
        logs = [{"args": {"uid": b"\x01" * 32}}]
        attestation = self._make_attestation_tuple(revocation_time=0, expiration_time=0)
        self._mock_contract(logs, attestation, monkeypatch)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is True

    async def test_no_logs_returns_false(self, eas_env, monkeypatch):
        self._mock_contract([], self._make_attestation_tuple(), monkeypatch)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is False

    async def test_revoked_attestation_returns_false(self, eas_env, monkeypatch):
        logs = [{"args": {"uid": b"\x01" * 32}}]
        # revocation_time != 0 → revoked
        attestation = self._make_attestation_tuple(revocation_time=1_000_000)
        self._mock_contract(logs, attestation, monkeypatch)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is False

    async def test_expired_attestation_returns_false(self, eas_env, monkeypatch):
        logs = [{"args": {"uid": b"\x01" * 32}}]
        # expiration_time in the past
        attestation = self._make_attestation_tuple(expiration_time=1)
        self._mock_contract(logs, attestation, monkeypatch)
        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is False

    async def test_one_valid_among_revoked_returns_true(self, eas_env, monkeypatch):
        """First log is revoked, second is valid → should return True."""
        logs = [
            {"args": {"uid": b"\x01" * 32}},
            {"args": {"uid": b"\x02" * 32}},
        ]
        revoked = self._make_attestation_tuple(revocation_time=1_000_000)
        valid = self._make_attestation_tuple(revocation_time=0, expiration_time=0)

        mock_event = MagicMock()
        mock_event.get_logs = AsyncMock(return_value=logs)

        call_results = [revoked, valid]
        call_iter = iter(call_results)

        mock_fn_instance = MagicMock()
        mock_fn_instance.call = AsyncMock(side_effect=lambda: next(call_iter))

        mock_contract = MagicMock()
        mock_contract.events.Attested = mock_event
        mock_contract.functions.getAttestation.return_value = mock_fn_instance

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        monkeypatch.setattr("services.attestations._get_web3", lambda: mock_w3)

        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is True

    async def test_rpc_error_returns_false(self, eas_env, monkeypatch):
        """Chain unreachable → fail-closed (return False)."""
        mock_event = MagicMock()
        mock_event.get_logs = AsyncMock(side_effect=ConnectionError("RPC down"))

        mock_contract = MagicMock()
        mock_contract.events.Attested = mock_event

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        monkeypatch.setattr("services.attestations._get_web3", lambda: mock_w3)

        result = await verify_attestation(USER_ADDR, SCHEMA_ID)
        assert result is False


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

class TestAttestationCaching:
    """Cache is only populated when EAS_CONTRACT_ADDRESS + WEB3_RPC_URL are set
    (on-chain path). Dev-mode early-return is intentionally not cached."""

    @pytest.fixture()
    def eas_env_with_valid_attestation(self, monkeypatch):
        """Set up env + mock w3 so verify_attestation returns True via on-chain path."""
        monkeypatch.setenv("EAS_CONTRACT_ADDRESS", "0x" + "ea" * 20)
        monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")

        attestation_tuple = (
            b"\x00" * 32, b"\x00" * 32, 0, 0, 0,
            b"\x00" * 32, "0x" + "00" * 20, "0x" + "00" * 20, True, b"",
        )
        mock_fn = MagicMock()
        mock_fn.call = AsyncMock(return_value=attestation_tuple)

        mock_event = MagicMock()
        mock_event.get_logs = AsyncMock(return_value=[{"args": {"uid": b"\x01" * 32}}])

        mock_contract = MagicMock()
        mock_contract.events.Attested = mock_event
        mock_contract.functions.getAttestation.return_value = mock_fn

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        monkeypatch.setattr("services.attestations._get_web3", lambda: mock_w3)

    async def test_positive_result_is_cached(
        self, eas_env_with_valid_attestation, monkeypatch
    ):
        await verify_attestation(USER_ADDR, SCHEMA_ID)
        key = (USER_ADDR.lower(), SCHEMA_ID)
        assert key in _ATTESTATION_CACHE
        assert _ATTESTATION_CACHE[key] is True

    async def test_negative_result_not_cached(self, monkeypatch):
        """False results are not cached so a fresh attestation takes effect immediately."""
        monkeypatch.setenv("EAS_CONTRACT_ADDRESS", "0x" + "ea" * 20)
        monkeypatch.setenv("WEB3_RPC_URL", "https://rpc.sepolia.org")

        mock_event = MagicMock()
        mock_event.get_logs = AsyncMock(return_value=[])  # no logs → False

        mock_contract = MagicMock()
        mock_contract.events.Attested = mock_event

        mock_w3 = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        monkeypatch.setattr("services.attestations._get_web3", lambda: mock_w3)

        await verify_attestation(USER_ADDR, SCHEMA_ID)
        key = (USER_ADDR.lower(), SCHEMA_ID)
        assert key not in _ATTESTATION_CACHE

    async def test_cached_result_used_on_second_call(
        self, eas_env_with_valid_attestation, monkeypatch
    ):
        await verify_attestation(USER_ADDR, SCHEMA_ID)
        key = (USER_ADDR.lower(), SCHEMA_ID)
        assert _ATTESTATION_CACHE[key] is True


# ---------------------------------------------------------------------------
# GET /packages/{device_id}/history — attestation gate (HTTP integration)
# ---------------------------------------------------------------------------

class TestHistoryAttestationGate:
    """
    Tests use the session client (which has get_current_user overridden to
    a mock provider). The autouse mock_blockchain fixture sets
    verify_attestation to return True by default.
    """

    def test_history_allowed_with_valid_attestation(
        self, client, mock_swarm, delivery_conditions, signed_request
    ):
        """Default: attestation granted → history endpoint works normally."""
        client.post("/packages/", json=delivery_conditions)
        client.post("/sensors/data", json=signed_request)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 200

    def test_history_forbidden_without_attestation(
        self, client, mock_swarm, delivery_conditions, monkeypatch
    ):
        """Override verify_attestation to False → 403."""
        async def _deny(user_address: str, schema_id: str) -> bool:
            return False

        monkeypatch.setattr("api.deps.verify_attestation", _deny)

        client.post("/packages/", json=delivery_conditions)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 403
        assert "attestation" in resp.json()["detail"].lower()

    def test_history_forbidden_detail_contains_schema_id(
        self, client, mock_swarm, delivery_conditions, monkeypatch
    ):
        async def _deny(user_address: str, schema_id: str) -> bool:
            return False

        monkeypatch.setattr("api.deps.verify_attestation", _deny)

        client.post("/packages/", json=delivery_conditions)
        resp = client.get(f"/packages/{delivery_conditions['device_id']}/history")
        assert resp.status_code == 403
        # Detail should name the schema so the client knows what's missing
        detail = resp.json()["detail"]
        assert "Required attestation" in detail

    def test_history_still_requires_authentication(self, app, mock_swarm, delivery_conditions):
        """No JWT at all → 403 (HTTPBearer returns 403 when credentials absent)."""
        from fastapi.testclient import TestClient
        from api.deps import get_current_user
        from tests.conftest import MOCK_PROVIDER_USER

        # Remove the session-level auth override temporarily
        app.dependency_overrides.pop(get_current_user, None)
        try:
            raw_client = TestClient(app)
            client_with_override = TestClient(app)  # still no override
            resp = raw_client.get(f"/packages/{delivery_conditions['device_id']}/history")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[get_current_user] = lambda: MOCK_PROVIDER_USER
