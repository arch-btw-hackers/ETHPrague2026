"""
Auth service — nonce store, JWT issuance/verification, role lookup.

All state is in-process. For a production multi-replica deployment,
replace _nonce_store with Redis or a DB-backed solution.
"""
import json
import logging
import os
import pathlib
import secrets
import time

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

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


def _load_or_generate_rsa_keys() -> None:
    """Load RSA keys from env vars or generate a fresh ephemeral pair.

    Environment variables (PEM, \\n-escaped):
      SERVER_RSA_PRIVATE_KEY — PKCS#8 private key (no passphrase)
      SERVER_RSA_PUBLIC_KEY  — SubjectPublicKeyInfo public key

    If neither is set a new 2048-bit pair is generated in-process.
    The generated pair is ephemeral (lost on restart) — set the env vars
    in production to keep a stable identity.
    """
    global _rsa_private_key, _rsa_public_key

    priv_pem = os.environ.get("SERVER_RSA_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    pub_pem = os.environ.get("SERVER_RSA_PUBLIC_KEY", "").replace("\\n", "\n").strip()

    if priv_pem and pub_pem:
        _rsa_private_key = serialization.load_pem_private_key(priv_pem.encode(), password=None)
        _rsa_public_key = serialization.load_pem_public_key(pub_pem.encode())
        logger.info("RSA keys loaded from environment variables")
    else:
        logger.warning(
            "SERVER_RSA_PRIVATE_KEY / SERVER_RSA_PUBLIC_KEY not set — "
            "generating ephemeral RSA-2048 key pair (dev mode)"
        )
        _rsa_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        _rsa_public_key = _rsa_private_key.public_key()


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


# Initialise keys at import time so the public key is ready before first request
_load_or_generate_rsa_keys()
