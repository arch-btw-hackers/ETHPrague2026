"""
Sign-In with Ethereum (SIWE) authentication endpoints.

Flow:
  1. GET  /auth/nonce          → {"nonce": "<hex>"}
  2. POST /auth/verify         → {"token": "<JWT>", "address": "0x...", "role": "..."}

The SIWE message must include the nonce returned by step 1.

SIWE verification is implemented directly with eth_account (bundled with web3)
to avoid the siwe library's C-extension build requirements (bitarray, cytoolz).
The EIP-4361 message format is parsed via a lightweight helper and the Ethereum
personal_sign-style signature is verified with Account.recover_message.
"""
import logging
import re

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.auth import consume_nonce, create_jwt, generate_nonce, get_role, get_server_public_key_pem
from services.blockchain import reverse_resolve_ens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# Minimal EIP-4361 parser
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"^([A-Za-z ]+):\s*(.+)$")


def _parse_siwe_message(message: str) -> dict:
    """
    Extract {address, nonce, domain} from an EIP-4361 SIWE text message.

    The format is:
        <domain> wants you to sign in with your Ethereum account:
        <0x-address>
        ...
        Nonce: <hex>
        ...
    """
    lines = [l.rstrip() for l in message.strip().splitlines()]
    if len(lines) < 2:
        raise ValueError("Malformed SIWE message: too short")

    # line[0] = "<domain> wants you to sign in..."
    domain_match = re.match(r"^(.+?) wants you to sign in", lines[0])
    domain = domain_match.group(1) if domain_match else lines[0]

    # line[1] = checksummed Ethereum address
    address = lines[1].strip()
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        raise ValueError(f"Malformed SIWE message: invalid address '{address}'")

    fields: dict[str, str] = {}
    for line in lines[2:]:
        m = _FIELD_RE.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()

    nonce = fields.get("Nonce", "")
    if not nonce:
        raise ValueError("Malformed SIWE message: missing Nonce field")

    return {"address": address, "nonce": nonce, "domain": domain}


class SiweMessage:  # noqa: N801 — named to match the original siwe import in tests
    """Thin wrapper so tests can monkeypatch 'api.auth.SiweMessage' unchanged."""

    def __init__(self, message: str):
        self._raw = message
        parsed = _parse_siwe_message(message)  # raises ValueError on bad format
        self.address: str = parsed["address"]
        self.nonce: str = parsed["nonce"]
        self.domain: str = parsed["domain"]

    def verify(self, signature: str) -> None:
        """Recover signer from EIP-191 personal_sign and compare to self.address."""
        signable = encode_defunct(text=self._raw)
        try:
            recovered = Account.recover_message(signable, signature=signature)
        except Exception as exc:
            raise ValueError(f"Cannot recover signer: {exc}") from exc

        if recovered.lower() != self.address.lower():
            raise ValueError(
                f"Signature mismatch: expected {self.address}, got {recovered}"
            )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    message: str      # Raw EIP-4361 SIWE message text
    signature: str    # 0x-prefixed hex signature from the wallet


class AuthResponse(BaseModel):
    token: str
    address: str
    role: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/nonce")
async def get_nonce():
    """Issue a one-time nonce to include in the SIWE message."""
    return {"nonce": generate_nonce()}


@router.post("/verify", response_model=AuthResponse)
async def verify(data: VerifyRequest):
    """
    Verify a SIWE message + wallet signature, then issue a JWT.

    Returns 401 on any signature/nonce error so callers cannot distinguish
    between invalid signature and expired nonce (prevents oracle attacks).
    """
    try:
        siwe_msg = SiweMessage(message=data.message)
        siwe_msg.verify(data.signature)
    except ValueError as exc:
        logger.debug("SIWE verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired SIWE message")
    except Exception as exc:
        logger.warning("Unexpected SIWE error: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired SIWE message")

    # Validate nonce was issued by us and hasn't been replayed
    if not consume_nonce(siwe_msg.nonce):
        raise HTTPException(status_code=401, detail="Invalid or expired SIWE message")

    address = siwe_msg.address.lower()
    role = get_role(address)
    token = create_jwt(address, role)

    # Best-effort ENS reverse-lookup for server-side audit logging.
    # Never blocks the response — errors are silently swallowed inside reverse_resolve_ens.
    ens_name = await reverse_resolve_ens(address)
    if ens_name:
        logger.info("Authenticated address=%s ens=%s role=%s", address, ens_name, role)
    else:
        logger.info("Authenticated address=%s role=%s", address, role)

    return AuthResponse(token=token, address=address, role=role)


@router.get("/keys")
async def get_public_keys():
    """Return the server RSA public key in PEM format.

    Devices call this once at startup to obtain the key they use to encrypt
    their sensor payloads before sending to POST /sensors/encrypted-data.
    """
    return {"server_public_key": get_server_public_key_pem()}
