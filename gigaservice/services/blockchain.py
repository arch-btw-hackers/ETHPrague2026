"""
Blockchain integration — smart-contract interaction via AsyncWeb3.

Environment variables (all required in production):
  WEB3_RPC_URL        — JSON-RPC endpoint (Infura, Alchemy, or local Anvil)
  CONTRACT_ADDRESS    — deployed ColdChainShipment contract address
  WEB3_PRIVATE_KEY    — hex private key used to sign and pay for transactions
  SERVER_PRIVATE_KEY  — alias for WEB3_PRIVATE_KEY (legacy, fallback)

The ColdChainShipment contract (0x965CdD2a560bab50ce52A826d1431A488C9E9959) exposes:
  function cancelShipment(uint256 shipmentId) external
  function submitTrackerState(uint256 shipmentId, bool isGood, string calldata telemetryProof) external
"""
import logging
import os

from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal ABI — only the function we actually call
# ---------------------------------------------------------------------------

_CANCEL_SHIPMENT_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "shipmentId", "type": "uint256"}],
        "name": "cancelShipment",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

_SUBMIT_TRACKER_STATE_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "shipmentId", "type": "uint256"},
            {"internalType": "bool", "name": "isGood", "type": "bool"},
            {"internalType": "string", "name": "telemetryProof", "type": "string"},
        ],
        "name": "submitTrackerState",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# Combined ABI used for the ColdChainShipment contract
_CONTRACT_ABI = _CANCEL_SHIPMENT_ABI + _SUBMIT_TRACKER_STATE_ABI

# ---------------------------------------------------------------------------
# Lazy singleton — built once on first call, reused afterwards
# ---------------------------------------------------------------------------

_w3: AsyncWeb3 | None = None


def _get_web3() -> AsyncWeb3:
    global _w3
    if _w3 is None:
        rpc_url = os.environ["WEB3_RPC_URL"]
        _w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
        # Inject PoA middleware for networks like Polygon/BSC/Anvil
        _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return _w3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def trigger_contract_refund(shipment_id: int) -> str | None:
    """
    Send a cancelShipment(shipmentId) transaction to the ColdChainShipment contract.

    Returns the transaction hash on success, or None if a recoverable error
    occurred (e.g. RPC unreachable).

    This function is designed to be called as a FastAPI BackgroundTask so
    that telemetry responses are not delayed by blockchain latency.
    """
    rpc_url = os.environ.get("WEB3_RPC_URL")
    contract_address = os.environ.get("CONTRACT_ADDRESS")
    private_key = os.environ.get("WEB3_PRIVATE_KEY") or os.environ.get("SERVER_PRIVATE_KEY")

    if not rpc_url or not contract_address or not private_key:
        logger.warning(
            "Web3 environment variables not configured — skipping cancelShipment "
            "(shipmentId=%s)",
            shipment_id,
        )
        return None

    try:
        w3 = _get_web3()

        checksum_address = AsyncWeb3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum_address, abi=_CONTRACT_ABI)

        account = w3.eth.account.from_key(private_key)
        sender = account.address

        nonce = await w3.eth.get_transaction_count(sender)
        gas_price = await w3.eth.gas_price

        tx = await contract.functions.cancelShipment(shipment_id).build_transaction(
            {
                "from": sender,
                "nonce": nonce,
                "gasPrice": gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_hash = tx_hash.hex()

        logger.info(
            "cancelShipment sent — shipmentId=%s tx=%s", shipment_id, hex_hash
        )
        return hex_hash

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "cancelShipment failed — shipmentId=%s: %s",
            shipment_id,
            exc,
            exc_info=True,
        )
        return None


async def submit_tracker_state(
    shipment_id: int,
    is_good: bool,
    telemetry_proof: str,
) -> str | None:
    """
    Call submitTrackerState(shipmentId, isGood, telemetryProof) on the
    ColdChainShipment contract.

    Returns the transaction hash on success, or None when env vars are
    missing (dev mode) or a recoverable error occurs.

    Errors are logged and swallowed so a single RPC hiccup does not crash
    the background task and delay the HTTP response.
    """
    rpc_url = os.environ.get("WEB3_RPC_URL")
    contract_address = os.environ.get("CONTRACT_ADDRESS")
    private_key = os.environ.get("WEB3_PRIVATE_KEY") or os.environ.get("SERVER_PRIVATE_KEY")

    if not rpc_url or not contract_address or not private_key:
        logger.warning(
            "Web3 environment variables not configured — skipping submitTrackerState "
            "(shipmentId=%s, isGood=%s)",
            shipment_id,
            is_good,
        )
        return None

    try:
        w3 = _get_web3()

        checksum_address = AsyncWeb3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum_address, abi=_CONTRACT_ABI)

        account = w3.eth.account.from_key(private_key)
        sender = account.address

        nonce = await w3.eth.get_transaction_count(sender)
        gas_price = await w3.eth.gas_price

        tx = await contract.functions.submitTrackerState(
            shipment_id, is_good, telemetry_proof
        ).build_transaction(
            {
                "from": sender,
                "nonce": nonce,
                "gasPrice": gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_hash = tx_hash.hex()

        logger.info(
            "submitTrackerState sent — shipmentId=%s isGood=%s tx=%s",
            shipment_id,
            is_good,
            hex_hash,
        )
        return hex_hash

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "submitTrackerState failed — shipmentId=%s isGood=%s: %s",
            shipment_id,
            is_good,
            exc,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# ENS helpers
# ---------------------------------------------------------------------------

async def resolve_ens(name: str) -> str:
    """
    Forward-resolve an ENS name to a checksummed Ethereum address.

    If *name* does not end with '.eth' it is returned unchanged, making
    this function safe to call unconditionally on any identifier.

    Raises ValueError if the name ends with '.eth' but cannot be resolved
    (no resolver registered, ENS node unavailable, or WEB3_RPC_URL not set).
    """
    if not name.endswith(".eth"):
        return name

    rpc_url = os.environ.get("WEB3_RPC_URL")
    if not rpc_url:
        raise ValueError(
            f"Cannot resolve ENS name '{name}': WEB3_RPC_URL is not configured"
        )

    try:
        w3 = _get_web3()
        address = await w3.ens.address(name)
        if address is None:
            raise ValueError(f"ENS name '{name}' has no registered address")
        logger.info("Resolved ENS %s \u2192 %s", name, address)
        return address
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"ENS resolution failed for '{name}': {exc}") from exc


async def reverse_resolve_ens(address: str) -> str | None:
    """
    Reverse-resolve an Ethereum address to its primary ENS name.

    Returns None on any error (RPC unavailable, no reverse record, etc.).
    Intended for best-effort logging only — never blocks the request path.
    """
    rpc_url = os.environ.get("WEB3_RPC_URL")
    if not rpc_url:
        return None

    try:
        w3 = _get_web3()
        name = await w3.ens.name(address)
        return name  # None if no reverse record
    except Exception as exc:  # noqa: BLE001
        logger.debug("Reverse ENS lookup failed for %s: %s", address, exc)
        return None
