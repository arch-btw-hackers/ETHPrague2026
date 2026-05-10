"""
Ethereum Attestation Service (EAS) integration.

Checks whether a given Ethereum address holds a valid (non-revoked) attestation
for a particular schema by querying the on-chain EAS contract directly.

Environment variables:
  EAS_CONTRACT_ADDRESS — address of the deployed EAS contract
  WEB3_RPC_URL         — JSON-RPC endpoint (shared with blockchain.py)

Reference ABI
-------------
The EAS contract exposes `getAttestation(bytes32 uid)` and an indexed event
store, but the most practical on-chain path is to call the EASIndexer
`getAttestationCount` + `getAttestationByIndex`, or to filter
`Attested(address indexed recipient, ...)` logs.

We use the minimal approach: query `Attested` logs for (recipient, schema)
and then call `isRevoked(uid)` for each to find at least one live attestation.

If EAS_CONTRACT_ADDRESS or WEB3_RPC_URL is not set the function returns True
so local development works without a blockchain node.
"""
import asyncio
import logging
import os
from typing import Any

from web3 import AsyncWeb3

from services.blockchain import _get_web3

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal EAS ABI — only the parts we need
# ---------------------------------------------------------------------------

_EAS_ABI: list[dict[str, Any]] = [
    # getAttestation(bytes32 uid) → Attestation struct
    {
        "inputs": [{"internalType": "bytes32", "name": "uid", "type": "bytes32"}],
        "name": "getAttestation",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "uid", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "schema", "type": "bytes32"},
                    {"internalType": "uint64", "name": "time", "type": "uint64"},
                    {"internalType": "uint64", "name": "expirationTime", "type": "uint64"},
                    {"internalType": "uint64", "name": "revocationTime", "type": "uint64"},
                    {"internalType": "bytes32", "name": "refUID", "type": "bytes32"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "address", "name": "attester", "type": "address"},
                    {"internalType": "bool", "name": "revocable", "type": "bool"},
                    {"internalType": "bytes", "name": "data", "type": "bytes"},
                ],
                "internalType": "struct Attestation",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # Attested event — emitted when a new attestation is created
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "recipient", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "attester", "type": "address"},
            {"indexed": False, "internalType": "bytes32", "name": "uid", "type": "bytes32"},
            {"indexed": True, "internalType": "bytes32", "name": "schemaUID", "type": "bytes32"},
        ],
        "name": "Attested",
        "type": "event",
    },
]

# ---------------------------------------------------------------------------
# In-process cache — avoids redundant RPC calls for the same address+schema
# ---------------------------------------------------------------------------

# Key: (lowercase_address, schema_id)  Value: bool result
_ATTESTATION_CACHE: dict[tuple[str, str], bool] = {}

# TTL for positive results (seconds).  Negative results are not cached so
# a freshly issued attestation takes effect immediately on next request.
_CACHE_TTL_SECONDS = 300

# (key → expiry unix timestamp) — stored separately to keep the logic simple
_CACHE_EXPIRY: dict[tuple[str, str], float] = {}


def clear_attestation_cache() -> None:
    """Remove all cached attestation results (used in tests)."""
    _ATTESTATION_CACHE.clear()
    _CACHE_EXPIRY.clear()


def _cache_get(key: tuple[str, str]) -> bool | None:
    import time
    expiry = _CACHE_EXPIRY.get(key)
    if expiry is None:
        return None
    if time.time() > expiry:
        _ATTESTATION_CACHE.pop(key, None)
        _CACHE_EXPIRY.pop(key, None)
        return None
    return _ATTESTATION_CACHE.get(key)


def _cache_set(key: tuple[str, str], value: bool) -> None:
    import time
    # Only cache positive results — negative ones re-checked on next request
    if value:
        _ATTESTATION_CACHE[key] = value
        _CACHE_EXPIRY[key] = time.time() + _CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# Core verification function
# ---------------------------------------------------------------------------

async def verify_attestation(user_address: str, schema_id: str) -> bool:
    """
    Return True if *user_address* has at least one valid (non-revoked,
    non-expired) attestation for *schema_id* on-chain.

    Falls back to True (permissive) when EAS_CONTRACT_ADDRESS or
    WEB3_RPC_URL is not configured, so local dev works without a node.

    Results are cached in-process for _CACHE_TTL_SECONDS seconds to avoid
    hammering the RPC endpoint on every request.
    """
    eas_address = os.environ.get("EAS_CONTRACT_ADDRESS", "").strip()
    rpc_url = os.environ.get("WEB3_RPC_URL", "").strip()

    if not eas_address or not rpc_url:
        logger.warning(
            "EAS_CONTRACT_ADDRESS or WEB3_RPC_URL not configured — "
            "attestation check skipped (dev mode), granting access"
        )
        return True

    address_lower = user_address.lower()
    cache_key = (address_lower, schema_id)

    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(
            "Attestation cache hit for address=%s schema=%s result=%s",
            address_lower, schema_id, cached,
        )
        return cached

    try:
        result = await _check_on_chain(eas_address, rpc_url, user_address, schema_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "EAS attestation check failed for address=%s schema=%s: %s",
            address_lower, schema_id, exc, exc_info=True,
        )
        # Fail-closed: deny access when the chain is unreachable
        return False

    _cache_set(cache_key, result)
    logger.info(
        "Attestation %s for address=%s schema=%s",
        "GRANTED" if result else "DENIED",
        address_lower, schema_id,
    )
    return result


async def _check_on_chain(
    eas_address: str,
    rpc_url: str,
    user_address: str,
    schema_id: str,
) -> bool:
    """
    Query the EAS contract for Attested events, then verify none are revoked.

    The schemaUID and recipient are indexed event topics so the filter is
    executed server-side on the RPC node (O(log n) in practice).
    """
    import time as _time

    w3 = _get_web3()
    checksum_eas = AsyncWeb3.to_checksum_address(eas_address)
    checksum_user = AsyncWeb3.to_checksum_address(user_address)

    # Normalise schema_id to bytes32 hex
    schema_bytes32 = _to_bytes32(schema_id)

    contract = w3.eth.contract(address=checksum_eas, abi=_EAS_ABI)

    # Fetch all Attested logs for this (recipient, schema) pair
    logs = await contract.events.Attested.get_logs(  # type: ignore[attr-defined]
        argument_filters={
            "recipient": checksum_user,
            "schemaUID": schema_bytes32,
        },
        fromBlock=0,
    )

    if not logs:
        return False

    now = int(_time.time())

    # Check each attestation — return True on the first live one
    for log in logs:
        uid: bytes = log["args"]["uid"]
        attestation = await contract.functions.getAttestation(uid).call()

        # attestation is a tuple matching the Attestation struct order:
        # uid, schema, time, expirationTime, revocationTime, refUID,
        # recipient, attester, revocable, data
        revocation_time: int = attestation[4]   # 0 = not revoked
        expiration_time: int = attestation[3]   # 0 = never expires

        revoked = revocation_time != 0
        expired = expiration_time != 0 and now > expiration_time

        if not revoked and not expired:
            return True

    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bytes32(value: str) -> bytes:
    """Normalise a hex string (with or without 0x prefix) to a 32-byte value."""
    hex_str = value.removeprefix("0x")
    if len(hex_str) > 64:
        raise ValueError(f"Schema ID too long for bytes32: {value!r}")
    padded = hex_str.zfill(64)
    return bytes.fromhex(padded)
