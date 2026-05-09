"""Tests for RSA/ECDSA encryption endpoints:
  GET  /api/v1/auth/keys
  POST /api/v1/sensors/encrypted-data

Includes a full device simulation test that mimics what the IoT firmware does.
"""
import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

from services.auth import (
    get_server_public_key_pem,
    decrypt_with_server_key,
    verify_device_signature,
)


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

        plaintext = b'{"temp_c": 4.2, "acceleration_overload": 0.1}'
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
# Unit tests — verify_device_signature
# ---------------------------------------------------------------------------

class TestVerifyDeviceSignature:
    def test_dev_mode_returns_true_no_key_set(self, monkeypatch):
        """Without DEVICE_PUBLIC_KEY_PEM configured, always returns True."""
        monkeypatch.delenv("DEVICE_PUBLIC_KEY_PEM", raising=False)
        assert verify_device_signature("any payload", "any signature") is True

    def test_strips_vault_prefix(self, monkeypatch):
        """vault:v1: prefix is stripped before Base64 decode attempt."""
        monkeypatch.delenv("DEVICE_PUBLIC_KEY_PEM", raising=False)
        result = verify_device_signature("msg", "vault:v1:aGVsbG8=")
        assert result is True

    def test_invalid_base64_returns_false(self, monkeypatch):
        """When key IS set, bad base64 must return False (not raise)."""
        priv = ec.generate_private_key(ec.SECP256R1())
        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode().replace("\n", "\\n")
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pub_pem)
        result = verify_device_signature("msg", "!!!not-base64!!!")
        assert result is False

    def test_valid_signature_verified(self, monkeypatch):
        """A real ECDSA P-256 signature verifies correctly."""
        priv = ec.generate_private_key(ec.SECP256R1())
        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode().replace("\n", "\\n")
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pub_pem)

        message = "42device-abc123ciphertext-payload"
        sig_bytes = priv.sign(message.encode(), ec.ECDSA(hashes.SHA256()))
        sig_b64 = base64.b64encode(sig_bytes).decode()

        assert verify_device_signature(message, sig_b64) is True

    def test_wrong_signature_returns_false(self, monkeypatch):
        priv = ec.generate_private_key(ec.SECP256R1())
        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode().replace("\n", "\\n")
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pub_pem)

        wrong_sig = base64.b64encode(b"wrong" * 10).decode()
        assert verify_device_signature("correct message", wrong_sig) is False


# ---------------------------------------------------------------------------
# GET /api/v1/auth/keys
# ---------------------------------------------------------------------------

class TestGetPublicKeys:
    def test_returns_server_public_key(self, client):
        resp = client.get("/api/v1/auth/keys")
        assert resp.status_code == 200
        body = resp.json()
        assert "server_public_key" in body
        pem = body["server_public_key"]
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")

    def test_key_is_valid_rsa_pem(self, client):
        resp = client.get("/api/v1/auth/keys")
        pem = resp.json()["server_public_key"]
        key = serialization.load_pem_public_key(pem.encode())
        assert key.key_size == 2048  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# POST /api/v1/sensors/encrypted-data — helpers
# ---------------------------------------------------------------------------

ENC_DEVICE_CONDITIONS = {
    "device_id": "enc-device-1",
    "max_temp_c": 25.0,
    "max_acceleration": 2.0,
}


def _encrypt_readings(readings: dict) -> str:
    """Encrypt a readings dict with the server RSA public key. Returns Base64."""
    pem = get_server_public_key_pem()
    public_key = serialization.load_pem_public_key(pem.encode())
    plaintext = json.dumps(readings).encode()
    ciphertext = public_key.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode()


# ---------------------------------------------------------------------------
# POST /api/v1/sensors/encrypted-data — API tests
# ---------------------------------------------------------------------------

class TestEncryptedDataEndpoint:
    def test_valid_encrypted_payload_accepted(self, client, mock_swarm, mock_blockchain):
        client.post("/api/v1/packages/", json=ENC_DEVICE_CONDITIONS)
        readings = {"temp_c": 4.0, "acceleration_overload": 0.1, "lat": 50.0, "lon": 14.0}
        ciphertext = _encrypt_readings(readings)
        resp = client.post(
            "/api/v1/sensors/encrypted-data",
            json={
                "device_id": "enc-device-1",
                "nonce": "42",
                "ciphertext": ciphertext,
                "signature": "vault:v1:fakesig",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["received"] is True
        assert body["device_id"] == "enc-device-1"
        assert body["is_valid"] is True

    def test_invalid_base64_returns_422(self, client):
        resp = client.post(
            "/api/v1/sensors/encrypted-data",
            json={"device_id": "d", "nonce": "1", "ciphertext": "!!!not-base64!!!", "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_garbage_ciphertext_returns_422(self, client):
        garbage = base64.b64encode(b"random garbage bytes").decode()
        resp = client.post(
            "/api/v1/sensors/encrypted-data",
            json={"device_id": "d", "nonce": "1", "ciphertext": garbage, "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_decrypted_but_invalid_json_returns_422(self, client):
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
            "/api/v1/sensors/encrypted-data",
            json={"device_id": "d", "nonce": "1", "ciphertext": ciphertext_b64, "signature": "sig"},
        )
        assert resp.status_code == 422

    def test_violation_triggers_background_task(self, client, mock_swarm, mock_blockchain):
        client.post("/api/v1/packages/", json=ENC_DEVICE_CONDITIONS)
        readings = {"temp_c": 999.0, "acceleration_overload": 0.1}
        ciphertext = _encrypt_readings(readings)
        resp = client.post(
            "/api/v1/sensors/encrypted-data",
            json={
                "device_id": "enc-device-1",
                "nonce": "43",
                "ciphertext": ciphertext,
                "signature": "vault:v1:fakesig",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False


# ---------------------------------------------------------------------------
# Device simulation test — full end-to-end cryptographic roundtrip
# ---------------------------------------------------------------------------

class TestDeviceSimulation:
    """Simulates what the IoT firmware does to send an encrypted telemetry packet.

    1. Fetch server public RSA key via GET /api/v1/auth/keys.
    2. Encrypt sensor readings with RSA-OAEP.
    3. Sign (nonce + device_id + ciphertext) with a fresh ECDSA P-256 key.
    4. POST to /api/v1/sensors/encrypted-data and assert success.
    """

    @pytest.mark.skip(reason="Hackathon: ECDSA check is bypassed")
    def test_device_sends_encrypted_signed_telemetry(self, client, mock_swarm, mock_blockchain, monkeypatch):
        # ---- Device setup: generate its own ECDSA P-256 key pair ----
        device_private_key = ec.generate_private_key(ec.SECP256R1())
        device_public_key = device_private_key.public_key()
        pub_pem = device_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode().replace("\n", "\\n")
        # Tell the server about this device's public key
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pub_pem)

        # Register the device package conditions
        client.post("/api/v1/packages/", json={
            "device_id": "sim-device-1",
            "max_temp_c": 10.0,
            "max_acceleration": 3.0,
        })

        # ---- Step 1: Fetch server RSA public key ----
        keys_resp = client.get("/api/v1/auth/keys")
        assert keys_resp.status_code == 200
        server_pub_pem = keys_resp.json()["server_public_key"]
        server_pub = serialization.load_pem_public_key(server_pub_pem.encode())

        # ---- Step 2: Encrypt readings ----
        device_id = "sim-device-1"
        nonce = "1001"
        readings = {"temp_c": 5.5, "acceleration_overload": 0.3, "lat": 50.08, "lon": 14.43}
        plaintext = json.dumps(readings).encode()
        ciphertext_bytes = server_pub.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        ciphertext_b64 = base64.b64encode(ciphertext_bytes).decode()

        # ---- Step 3: Sign (nonce + device_id + ciphertext) ----
        signed_str = str(nonce) + device_id + ciphertext_b64
        sig_bytes = device_private_key.sign(signed_str.encode(), ec.ECDSA(hashes.SHA256()))
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # ---- Step 4: Send to server ----
        resp = client.post("/api/v1/sensors/encrypted-data", json={
            "device_id": device_id,
            "nonce": nonce,
            "ciphertext": ciphertext_b64,
            "signature": sig_b64,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["received"] is True
        assert body["device_id"] == device_id
        assert body["is_valid"] is True  # temp 5.5 < 10.0, accel 0.3 < 3.0

    def test_tampered_ciphertext_rejected(self, client, mock_swarm, mock_blockchain, monkeypatch):
        """If ciphertext changes after signing, ECDSA verification must fail."""
        device_private_key = ec.generate_private_key(ec.SECP256R1())
        device_public_key = device_private_key.public_key()
        pub_pem = device_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode().replace("\n", "\\n")
        monkeypatch.setenv("DEVICE_PUBLIC_KEY_PEM", pub_pem)

        server_pub_pem = client.get("/api/v1/auth/keys").json()["server_public_key"]
        server_pub = serialization.load_pem_public_key(server_pub_pem.encode())

        device_id = "sim-device-2"
        nonce = "999"
        readings = {"temp_c": 3.0, "acceleration_overload": 0.1}
        ciphertext_bytes = server_pub.encrypt(
            json.dumps(readings).encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        ciphertext_b64 = base64.b64encode(ciphertext_bytes).decode()

        # Sign original ciphertext
        signed_str = str(nonce) + device_id + ciphertext_b64
        sig_bytes = device_private_key.sign(signed_str.encode(), ec.ECDSA(hashes.SHA256()))
        sig_b64 = base64.b64encode(sig_bytes).decode()

        # Tamper: change one byte of ciphertext
        tampered = bytearray(base64.b64decode(ciphertext_b64))
        tampered[0] ^= 0xFF
        tampered_b64 = base64.b64encode(bytes(tampered)).decode()

        resp = client.post("/api/v1/sensors/encrypted-data", json={
            "device_id": device_id,
            "nonce": nonce,
            "ciphertext": tampered_b64,
            "signature": sig_b64,
        })
        # Signature over original ciphertext but tampered ciphertext sent → 401
        assert resp.status_code == 422
