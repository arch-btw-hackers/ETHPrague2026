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
