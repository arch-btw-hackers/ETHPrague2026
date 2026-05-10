"""
Auth service — nonce store, JWT issuance/verification, role lookup.

All state is in-process. For a production multi-replica deployment,
replace _nonce_store with Redis or a DB-backed solution.
"""
import json
import base64
import logging
import os
import pathlib
import secrets
import time

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 3600          # 1 hour
NONCE_TTL_SECONDS = 300            # 5 minutes — window to complete SIWE flow

_ROLES_PATH = pathlib.Path(__file__).parent.parent / "config" / "roles.json"

# ---------------------------------------------------------------------------
# Nonce store  (nonce -> expiry unix timestamp)
# ---------------------------------------------------------------------------

_nonce_store: dict[str, float] = {}


def generate_nonce() -> str:
    """Generate a cryptographically random nonce and store it with a TTL."""
    _evict_expired_nonces()
    nonce = secrets.token_hex(16)
    _nonce_store[nonce] = time.time() + NONCE_TTL_SECONDS
    return nonce


def consume_nonce(nonce: str) -> bool:
    """Return True and remove the nonce if it exists and hasn't expired."""
    _evict_expired_nonces()
    expiry = _nonce_store.pop(nonce, None)
    if expiry is None:
        return False
    return time.time() < expiry


def _evict_expired_nonces() -> None:
    now = time.time()
    expired = [k for k, exp in _nonce_store.items() if exp <= now]
    for k in expired:
        del _nonce_store[k]


# ---------------------------------------------------------------------------
# Role lookup
# ---------------------------------------------------------------------------

def get_role(address: str) -> str:
    """Return the role for an Ethereum address (lowercase). Default: 'user'."""
    if not _ROLES_PATH.exists():
        return "user"
    try:
        roles: dict[str, str] = json.loads(_ROLES_PATH.read_text())
        return roles.get(address.lower(), "user")
    except Exception:
        logger.exception("Failed to read roles.json")
        return "user"


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        logger.warning("JWT_SECRET not set — using insecure default (dev mode)")
        return "dev-secret-change-me"
    return secret


def create_jwt(address: str, role: str) -> str:
    payload = {
        "sub": address.lower(),
        "role": role,
        "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.PyJWTError on any failure."""
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# RSA-2048 server key pair — used for device payload encryption
# ---------------------------------------------------------------------------

_rsa_private_key: rsa.RSAPrivateKey | None = None
_rsa_public_key: rsa.RSAPublicKey | None = None


_RSA_KEY_FILE = pathlib.Path("/data/gigaservice_rsa_key.pem")
_RSA_KEY_FILE_FALLBACK = pathlib.Path("/tmp/gigaservice_rsa_key.pem")


def _load_or_generate_rsa_keys() -> None:
    """Load RSA keys from env vars, a persisted file, or generate a fresh pair.

    Priority:
      1. SERVER_RSA_PRIVATE_KEY env var (production)
      2. /data/gigaservice_rsa_key.pem  (Docker volume — survives container recreations)
      3. /tmp/gigaservice_rsa_key.pem   (legacy path, survives uvicorn restarts only)
      4. Generate a new pair and save it to /data (or /tmp as fallback)
    """
    global _rsa_private_key, _rsa_public_key

    priv_pem = os.environ.get("SERVER_RSA_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    pub_pem = os.environ.get("SERVER_RSA_PUBLIC_KEY", "").replace("\\n", "\n").strip()

    if priv_pem and pub_pem:
        _rsa_private_key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
        _rsa_public_key = serialization.load_pem_public_key(pub_pem.encode())
        logger.info("RSA keys loaded from environment variables")
        return

    for candidate in (_RSA_KEY_FILE, _RSA_KEY_FILE_FALLBACK):
        if candidate.exists():
            try:
                _rsa_private_key = serialization.load_pem_private_key(
                    candidate.read_bytes(), password=None
                )
                _rsa_public_key = _rsa_private_key.public_key()
                logger.info("RSA keys loaded from %s", candidate)
                return
            except Exception:
                logger.warning("Failed to load RSA key from %s — trying next", candidate)

    logger.warning(
        "SERVER_RSA_PRIVATE_KEY / SERVER_RSA_PUBLIC_KEY not set — "
        "generating RSA-2048 key pair"
    )
    _rsa_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    _rsa_public_key = _rsa_private_key.public_key()

    key_pem = _rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    for target in (_RSA_KEY_FILE, _RSA_KEY_FILE_FALLBACK):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(key_pem)
            logger.info("RSA key pair persisted to %s (survives container recreations)", target)
            break
        except Exception as exc:
            logger.warning("Could not persist RSA key to %s: %s", target, exc)


def get_server_public_key_pem() -> str:
    """Return the server RSA public key in PEM format."""
    if _rsa_public_key is None:
        _load_or_generate_rsa_keys()
    return _rsa_public_key.public_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def decrypt_with_server_key(ciphertext_b64: str) -> bytes:
    """Decrypt a Base64-encoded RSA-OAEP ciphertext using the server private key.

    Raises ValueError if the key is unavailable or decryption fails.
    """
    if _rsa_private_key is None:
        _load_or_generate_rsa_keys()
    import base64
    try:
        ciphertext = base64.b64decode(ciphertext_b64)
    except Exception as exc:
        raise ValueError("ciphertext is not valid Base64") from exc
    try:
        return _rsa_private_key.decrypt(  # type: ignore[union-attr]
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:
        raise ValueError("RSA decryption failed") from exc


# Alias for API clarity
decrypt_payload = decrypt_with_server_key


# ---------------------------------------------------------------------------
# Kyber768 server key pair — post-quantum KEM for device payload encryption
# ---------------------------------------------------------------------------

_KYBER_KEY_FILE = pathlib.Path("/data/gigaservice_kyber_key.bin")
_KYBER_KEY_FILE_FALLBACK = pathlib.Path("/tmp/gigaservice_kyber_key.bin")

_kyber_public_key_bytes: bytes | None = None
_kyber_secret_key_bytes: bytes | None = None


def _load_or_generate_kyber_keys() -> None:
    """Load or generate a Kyber768 keypair and persist it to the data volume."""
    global _kyber_public_key_bytes, _kyber_secret_key_bytes

    try:
        import oqs  # type: ignore[import]
    except ImportError:
        logger.warning("liboqs/oqs not installed — Kyber768 unavailable")
        return

    # Check env vars first (base64-encoded)
    sk_b64 = os.environ.get("KYBER_SECRET_KEY_B64", "").strip()
    pk_b64 = os.environ.get("KYBER_PUBLIC_KEY_B64", "").strip()
    if sk_b64 and pk_b64:
        import base64
        _kyber_secret_key_bytes = base64.b64decode(sk_b64)
        _kyber_public_key_bytes = base64.b64decode(pk_b64)
        logger.info("Kyber768 keys loaded from environment variables")
        return

    # Try to load from persisted binary file: [32-byte length prefix][SK][PK]
    for candidate in (_KYBER_KEY_FILE, _KYBER_KEY_FILE_FALLBACK):
        if candidate.exists():
            try:
                raw = candidate.read_bytes()
                sk_len = int.from_bytes(raw[:4], "big")
                sk = raw[4: 4 + sk_len]
                pk = raw[4 + sk_len:]
                _kyber_secret_key_bytes = sk
                _kyber_public_key_bytes = pk
                logger.info("Kyber768 keys loaded from %s", candidate)
                return
            except Exception:
                logger.warning("Failed to load Kyber key from %s", candidate)

    # Generate fresh keypair
    with oqs.KeyEncapsulation("Kyber768") as kem:
        _kyber_public_key_bytes = kem.generate_keypair()
        _kyber_secret_key_bytes = kem.export_secret_key()

    logger.info("Kyber768 keypair generated")

    # Persist: [4-byte SK length][SK][PK]
    sk_len_bytes = len(_kyber_secret_key_bytes).to_bytes(4, "big")
    payload_bin = sk_len_bytes + _kyber_secret_key_bytes + _kyber_public_key_bytes
    for target in (_KYBER_KEY_FILE, _KYBER_KEY_FILE_FALLBACK):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload_bin)
            logger.info("Kyber768 keypair persisted to %s", target)
            break
        except Exception as exc:
            logger.warning("Could not persist Kyber key to %s: %s", target, exc)


def get_kyber_public_key_bytes() -> bytes:
    """Return the Kyber768 public key bytes (1184 bytes for Kyber768)."""
    if _kyber_public_key_bytes is None:
        _load_or_generate_kyber_keys()
    if _kyber_public_key_bytes is None:
        raise RuntimeError("Kyber768 not available — install liboqs")
    return _kyber_public_key_bytes


def decrypt_kyber_aes_gcm(packet_b64: str) -> bytes:
    """Decrypt a Kyber768+AES-GCM packet from the ESP32.

    Packet layout (Base64-encoded):
      [Kyber ciphertext (1088 bytes)] [AES-GCM IV (12 bytes)]
      [AES-GCM tag (16 bytes)] [AES ciphertext (variable)]

    The Kyber ciphertext is decapsulated to recover the shared secret,
    which is used directly as the 32-byte AES-256-GCM key.
    """
    import base64
    try:
        import oqs  # type: ignore[import]
    except ImportError:
        raise ValueError("liboqs not installed — Kyber768 decryption unavailable")

    if _kyber_secret_key_bytes is None:
        _load_or_generate_kyber_keys()
    if _kyber_secret_key_bytes is None:
        raise ValueError("Kyber768 secret key not loaded")

    try:
        packet = base64.b64decode(packet_b64)
    except Exception as exc:
        raise ValueError("packet is not valid Base64") from exc

    KYBER_CT_LEN = 1088
    AES_IV_LEN = 12
    AES_TAG_LEN = 16
    MIN_LEN = KYBER_CT_LEN + AES_IV_LEN + AES_TAG_LEN + 1

    if len(packet) < MIN_LEN:
        raise ValueError(
            f"packet too short: got {len(packet)} bytes, need at least {MIN_LEN}"
        )

    kyber_ct = packet[:KYBER_CT_LEN]
    aes_iv = packet[KYBER_CT_LEN: KYBER_CT_LEN + AES_IV_LEN]
    aes_tag = packet[KYBER_CT_LEN + AES_IV_LEN: KYBER_CT_LEN + AES_IV_LEN + AES_TAG_LEN]
    aes_ct = packet[KYBER_CT_LEN + AES_IV_LEN + AES_TAG_LEN:]

    # Decapsulate: Kyber ciphertext → 32-byte shared secret
    try:
        with oqs.KeyEncapsulation("Kyber768", secret_key=_kyber_secret_key_bytes) as kem:
            shared_secret = kem.decap_secret(kyber_ct)
    except Exception as exc:
        raise ValueError("Kyber768 decapsulation failed") from exc

    # AES-256-GCM decrypt using the shared secret as the key
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        aes_key = shared_secret[:32]   # Kyber768 shared secret is 32 bytes
        aesgcm = AESGCM(aes_key)
        # cryptography library expects ciphertext+tag concatenated
        plaintext = aesgcm.decrypt(aes_iv, aes_ct + aes_tag, associated_data=None)
    except Exception as exc:
        raise ValueError("AES-GCM decryption failed (wrong key or corrupted data)") from exc

    return plaintext


# ---------------------------------------------------------------------------
# ECDSA P-256 device signature verification (Orbitport KMS compatible)
# ---------------------------------------------------------------------------

def _load_device_public_key():
    """Load the IoT device ECDSA P-256 public key from env (same as api.sensors)."""
    pem = os.environ.get("DEVICE_PUBLIC_KEY_PEM", "").replace("\\n", "\n").strip()
    if not pem:
        return None
    try:
        return serialization.load_pem_public_key(pem.encode())
    except Exception:
        logger.warning(
            "DEVICE_PUBLIC_KEY_PEM is set but could not be parsed — "
            "ECDSA verification running in dev mode (always allow)"
        )
        return None


def verify_device_signature(payload_str: str, signature: str) -> bool:
    """Verify an Orbitport KMS ECDSA P-256 / SHA-256 signature.

    Args:
        payload_str: The raw string that was signed (e.g. nonce + device_id + ciphertext).
        signature:   Raw signature value — may have a ``vault:v1:`` prefix which is
                     stripped before Base64 decoding.

    Returns:
        True when the signature is valid.
        True (with a warning) when DEVICE_PUBLIC_KEY_PEM is not configured (dev mode).
        False when the signature is invalid or malformed.
    """
    # Strip Orbitport KMS prefix if present
    if signature.startswith("vault:v1:"):
        signature = signature[len("vault:v1:"):]

    public_key = _load_device_public_key()
    if public_key is None:
        logger.warning(
            "DEV MODE: ECDSA verification skipped — "
            "DEVICE_PUBLIC_KEY_PEM is not configured"
        )
        return True

    message = payload_str.encode()

    try:
        sig_bytes = base64.b64decode(signature, validate=True)
    except Exception:
        logger.debug("Device signature is not valid Base64")
        return False

    try:
        public_key.verify(sig_bytes, message, ec.ECDSA(hashes.SHA256()))
        logger.debug("Device signature verified OK")
        return True
    except InvalidSignature:
        logger.warning("Device signature verification FAILED")
        return False


# Initialise keys at import time so the public keys are ready before first request
_load_or_generate_rsa_keys()
_load_or_generate_kyber_keys()
