"""
Tests for /auth endpoints and JWT/role-based access control.

SIWE signature generation is mocked at the service layer — we test the HTTP
contract and role enforcement logic, not the cryptographic internals of siwe.
"""
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from services.auth import create_jwt, generate_nonce, consume_nonce, get_role


# ---------------------------------------------------------------------------
# services/auth unit tests — nonce store
# ---------------------------------------------------------------------------

class TestNonceStore:
    def test_generate_returns_hex_string(self):
        nonce = generate_nonce()
        assert isinstance(nonce, str)
        assert len(nonce) == 32  # 16 bytes → 32 hex chars

    def test_consume_valid_nonce(self):
        nonce = generate_nonce()
        assert consume_nonce(nonce) is True

    def test_consume_removes_nonce(self):
        nonce = generate_nonce()
        consume_nonce(nonce)
        assert consume_nonce(nonce) is False  # already consumed

    def test_consume_unknown_nonce(self):
        assert consume_nonce("nonexistent-nonce") is False

    def test_nonces_are_unique(self):
        n1 = generate_nonce()
        n2 = generate_nonce()
        assert n1 != n2


# ---------------------------------------------------------------------------
# services/auth unit tests — JWT
# ---------------------------------------------------------------------------

class TestJwt:
    def test_create_and_decode(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        from services import auth as auth_mod
        token = create_jwt("0xabc", "provider")
        payload = auth_mod.decode_jwt(token)
        assert payload["sub"] == "0xabc"
        assert payload["role"] == "provider"

    def test_address_stored_lowercase(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        from services import auth as auth_mod
        token = create_jwt("0xABC", "user")
        payload = auth_mod.decode_jwt(token)
        assert payload["sub"] == "0xabc"

    def test_expired_token_raises(self, monkeypatch):
        import jwt
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        payload = {"sub": "0x1", "role": "user", "exp": int(time.time()) - 1}
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        from services import auth as auth_mod
        with pytest.raises(jwt.ExpiredSignatureError):
            auth_mod.decode_jwt(token)


# ---------------------------------------------------------------------------
# services/auth unit tests — role lookup
# ---------------------------------------------------------------------------

class TestGetRole:
    def test_unknown_address_returns_user(self):
        assert get_role("0xunknown") == "user"

    def test_known_admin_address(self):
        # The bundled roles.json maps this address to admin
        assert get_role("0x0000000000000000000000000000000000000001") == "admin"

    def test_case_insensitive_lookup(self):
        assert get_role("0X0000000000000000000000000000000000000001") == "admin"


# ---------------------------------------------------------------------------
# GET /auth/nonce
# ---------------------------------------------------------------------------

class TestGetNonce:
    def test_returns_200(self, client):
        resp = client.get("/auth/nonce")
        assert resp.status_code == 200

    def test_response_has_nonce_field(self, client):
        body = client.get("/auth/nonce").json()
        assert "nonce" in body

    def test_nonce_is_32_chars(self, client):
        body = client.get("/auth/nonce").json()
        assert len(body["nonce"]) == 32

    def test_nonces_are_unique(self, client):
        n1 = client.get("/auth/nonce").json()["nonce"]
        n2 = client.get("/auth/nonce").json()["nonce"]
        assert n1 != n2


# ---------------------------------------------------------------------------
# POST /auth/verify — mocking SIWE at the service layer
# ---------------------------------------------------------------------------

class TestVerifyEndpoint:
    def test_invalid_siwe_message_returns_401(self, client):
        resp = client.post("/auth/verify", json={
            "message": "not a valid siwe message",
            "signature": "0x" + "a" * 130,
        })
        assert resp.status_code == 401

    def test_valid_flow_returns_token(self, client, monkeypatch):
        """Mock SIWE verification so we test the HTTP contract, not siwe internals."""
        nonce = client.get("/auth/nonce").json()["nonce"]

        mock_msg = MagicMock()
        mock_msg.address = "0xDeAdBeEf000000000000000000000000DeAdBeEf"
        mock_msg.nonce = nonce
        mock_msg.verify.return_value = None
        monkeypatch.setattr("api.auth.SiweMessage", lambda message: mock_msg)

        resp = client.post("/auth/verify", json={
            "message": "fake siwe message",
            "signature": "0x" + "a" * 130,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["address"] == "0xdeadbeef000000000000000000000000deadbeef"

    def test_replayed_nonce_returns_401(self, client, monkeypatch):
        """Consuming the same nonce twice must be rejected."""
        nonce = client.get("/auth/nonce").json()["nonce"]
        consume_nonce(nonce)  # pre-consume so it's gone

        mock_msg = MagicMock()
        mock_msg.address = "0x1111111111111111111111111111111111111111"
        mock_msg.nonce = nonce
        mock_msg.verify.return_value = None
        monkeypatch.setattr("api.auth.SiweMessage", lambda message: mock_msg)

        resp = client.post("/auth/verify", json={
            "message": "fake", "signature": "0x" + "a" * 130
        })
        assert resp.status_code == 401

    def test_role_returned_in_response(self, client, monkeypatch):
        nonce = client.get("/auth/nonce").json()["nonce"]
        admin_addr = "0x0000000000000000000000000000000000000001"

        mock_msg = MagicMock()
        mock_msg.address = admin_addr
        mock_msg.nonce = nonce
        mock_msg.verify.return_value = None
        monkeypatch.setattr("api.auth.SiweMessage", lambda message: mock_msg)

        body = client.post("/auth/verify", json={"message": "x", "signature": "0x"}).json()
        assert body["role"] == "admin"


# ---------------------------------------------------------------------------
# Role-based access control on protected endpoints
# ---------------------------------------------------------------------------

class TestRoleBasedAccess:
    """These tests use a fresh TestClient WITHOUT the session-level auth override."""

    @pytest.fixture()
    def raw_client(self, app):
        """Client with no dependency overrides — real auth enforced."""
        app.dependency_overrides.clear()
        yield TestClient(app)
        # Restore the session-level override for other tests
        from api.deps import get_current_user
        from tests.conftest import MOCK_PROVIDER_USER
        app.dependency_overrides[get_current_user] = lambda: MOCK_PROVIDER_USER

    def _bearer(self, address: str, role: str) -> dict:
        token = create_jwt(address, role)
        return {"Authorization": f"Bearer {token}"}

    def test_no_token_returns_403_on_create_package(self, raw_client):
        resp = raw_client.post("/packages/", json={
            "device_id": "x", "max_temp_c": 25.0, "max_acceleration": 2.0
        })
        # HTTPBearer returns 403 when no credentials at all
        assert resp.status_code == 403

    def test_user_role_forbidden_on_create_package(self, raw_client, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        headers = self._bearer("0xuser", "user")
        resp = raw_client.post("/packages/", json={
            "device_id": "x", "max_temp_c": 25.0, "max_acceleration": 2.0
        }, headers=headers)
        assert resp.status_code == 403

    def test_provider_role_allowed_on_create_package(self, raw_client, mock_swarm, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        headers = self._bearer("0xprovider", "provider")
        resp = raw_client.post("/packages/", json={
            "device_id": "auth-dev-1", "max_temp_c": 25.0, "max_acceleration": 2.0
        }, headers=headers)
        assert resp.status_code == 200

    def test_admin_role_allowed_on_create_package(self, raw_client, mock_swarm, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        headers = self._bearer("0xadmin", "admin")
        resp = raw_client.post("/packages/", json={
            "device_id": "auth-dev-2", "max_temp_c": 25.0, "max_acceleration": 2.0
        }, headers=headers)
        assert resp.status_code == 200

    def test_expired_token_returns_401(self, raw_client, monkeypatch):
        import jwt as pyjwt
        monkeypatch.setenv("JWT_SECRET", "test-secret")
        payload = {"sub": "0x1", "role": "provider", "exp": int(time.time()) - 1}
        token = pyjwt.encode(payload, "test-secret", algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}
        resp = raw_client.post("/packages/", json={
            "device_id": "x", "max_temp_c": 25.0, "max_acceleration": 2.0
        }, headers=headers)
        assert resp.status_code == 401

    def test_garbage_token_returns_401(self, raw_client):
        headers = {"Authorization": "Bearer not.a.jwt"}
        resp = raw_client.post("/packages/", json={
            "device_id": "x", "max_temp_c": 25.0, "max_acceleration": 2.0
        }, headers=headers)
        assert resp.status_code == 401
