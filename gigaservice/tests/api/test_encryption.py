"""
Tests for RSA encryption endpoints:
  GET  /auth/keys
  POST /sensors/encrypted-data
"""
import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from services.auth import get_server_public_key_pem, decrypt_with_server_key


# ---------------------------------------------------------------------------
# Unit tests — services/auth RSA helpers
# ---------------------------------------------------------------------------

class TestRsaKeyHelpers:
    def test_get_server_public_key_pem_returns_pem(self):
        pem = get_server_public_key_pem()
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert "-----END PUBLIC KEY-----" in pem

    def test_roundtrip_encrypt_decrypt(self):
        """Encrypt with the public key, decrypt with the private key helper."""
        pem = get_server_public_key_pem()
        public_key = serialization.load_pem_public_key(pem.encode())

        plaintext = b'{"device_id": "test", "nonce": 1}'
        ciphertext = public_key.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        ciphertext_b64 = base64.b64encode(ciphertext).decode()

        recovered = decrypt_with_server_key(ciphertext_b64)
        assert recovered == plaintext

    def test_decrypt_invalid_base64_raises(self):
        with pytest.raises(ValueError, match="Base64"):
            decrypt_with_server_key("not-valid-base64!!!")

    def test_decrypt_garbage_ciphertext_raises(self):
        garbage = base64.b64encode(b"not-a-real-ciphertext").decode()
        with pytest.raises(ValueError, match="RSA decryption failed"):
            decrypt_with_server_key(garbage)


# ---------------------------------------------------------------------------
# GET /auth/keys
# ---------------------------------------------------------------------------

class TestGetPublicKeys:
    def test_returns_server_public_key(self, client):
        resp = client.get("/auth/keys")
        assert resp.status_code == 200
        body = resp.json()
        assert "server_public_key" in body
        pem = body["server_public_key"]
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")

    def test_key_is_valid_rsa_pem(self, client):
        resp = client.get("/auth/keys")
        pem = resp.json()["server_public_key"]
        key = serialization.load_pem_public_key(pem.encode())
        assert key.key_size == 2048  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# POST /sensors/encrypted-data
# ---------------------------------------------------------------------------

def _encrypt_payload(payload_dict: dict) -> str:
    """Helper: encrypt a dict with the server public key, return Base64."""
    pem = get_server_public_key_pem()
    public_key = serialization.load_pem_public_key(pem.encode())
    plaintext = json.dumps(payload_dict).encode()
    ciphertext = public_key.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode()


VALID_PAYLOAD = {
    "device_id": "enc-device-1",
    "nonce": 42,
    "readings": {
        "temp_c": 4.0,
        "acceleration_overload": 0.1,
        "lat": 50.0,
        "lon": 14.0,
    },
}

ENC_DEVICE_CONDITIONS = {
    "device_id": "enc-device-1",
    "max_temp_c": 25.0,
    "max_acceleration": 2.0,
}


class TestEncryptedDataEndpoint:
    def test_valid_encrypted_payload_accepted(self, client, mock_swarm, mock_blockchain):
        client.post("/packages/", json=ENC_DEVICE_CONDITIONS)
        ciphertext = _encrypt_payload(VALID_PAYLOAD)
        resp = client.post(
            "/sensors/encrypted-data",
            json={"ciphertext": ciphertext, "signature": "vault:v1:fakesig"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["received"] is True
        assert body["device_id"] == "enc-device-1"

    def test_invalid_base64_returns_422(self, client):
        resp = client.post(
            "/sensors/encrypted-data",
            json={"ciphertext": "!!!not-base64!!!", "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_garbage_ciphertext_returns_422(self, client):
        garbage = base64.b64encode(b"random garbage bytes").decode()
        resp = client.post(
            "/sensors/encrypted-data",
            json={"ciphertext": garbage, "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_decrypted_but_invalid_json_returns_422(self, client):
        """Encrypt something that decrypts fine but isn't a valid DevicePayload."""
        pem = get_server_public_key_pem()
        public_key = serialization.load_pem_public_key(pem.encode())
        ciphertext = public_key.encrypt(
            b"this is not json",
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        ciphertext_b64 = base64.b64encode(ciphertext).decode()
        resp = client.post(
            "/sensors/encrypted-data",
            json={"ciphertext": ciphertext_b64, "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_violation_triggers_background_task(self, client, mock_swarm, mock_blockchain):
        """Payload with high temp should still be accepted (violation handled async)."""
        client.post("/packages/", json=ENC_DEVICE_CONDITIONS)
        hot_payload = {**VALID_PAYLOAD, "readings": {**VALID_PAYLOAD["readings"], "temp_c": 999.0}}
        ciphertext = _encrypt_payload(hot_payload)
        resp = client.post(
            "/sensors/encrypted-data",
            json={"ciphertext": ciphertext, "signature": "vault:v1:fakesig"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False
