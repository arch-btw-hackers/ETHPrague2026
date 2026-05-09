"""
Blockchain integration — smart-contract interaction via AsyncWeb3.

Environment variables (all required in production):
  WEB3_RPC_URL       — JSON-RPC endpoint (Infura, Alchemy, or local Anvil)
  CONTRACT_ADDRESS   — deployed DeliveryEscrow contract address
  SERVER_PRIVATE_KEY — hex private key used to sign and pay for transactions

The contract is expected to expose at minimum:
  function cancelDelivery(string calldata deviceId) external
"""
import logging
import os

from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal ABI — only the function we actually call
# ---------------------------------------------------------------------------

_CANCEL_DELIVERY_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "deviceId", "type": "string"}],
        "name": "cancelDelivery",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

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

async def trigger_contract_refund(device_id: str) -> str | None:
    """
    Send a cancelDelivery(deviceId) transaction to the smart contract.

    Returns the transaction hash on success, or None if a recoverable error
    occurred (e.g. RPC unreachable). Non-recoverable exceptions propagate.

    This function is designed to be called as a FastAPI BackgroundTask so
    that telemetry responses are not delayed by blockchain latency.
    """
    rpc_url = os.environ.get("WEB3_RPC_URL")
    contract_address = os.environ.get("CONTRACT_ADDRESS")
    private_key = os.environ.get("SERVER_PRIVATE_KEY")

    if not rpc_url or not contract_address or not private_key:
        logger.warning(
            "Web3 environment variables not configured — skipping refund for device %s",
            device_id,
        )
        return None

    try:
        w3 = _get_web3()

        checksum_address = AsyncWeb3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=checksum_address, abi=_CANCEL_DELIVERY_ABI)

        account = w3.eth.account.from_key(private_key)
        sender = account.address

        nonce = await w3.eth.get_transaction_count(sender)
        gas_price = await w3.eth.gas_price

        tx = await contract.functions.cancelDelivery(device_id).build_transaction(
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
            "cancelDelivery sent for device %s — tx %s", device_id, hex_hash
        )
        return hex_hash

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to trigger contract refund for device %s: %s",
            device_id,
            exc,
            exc_info=True,
        )
        return None
