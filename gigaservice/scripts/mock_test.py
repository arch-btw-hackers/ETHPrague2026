"""
Manual smoke-test script for POST /sensors/data.

Sends 3 requests with randomly generated telemetry and a fake vault signature.
Run against a locally running server:
    cd gigaservice
    uvicorn server:app --reload
    python scripts/mock_test.py
"""
import secrets
import random
import requests

BASE_URL = "http://localhost:8000"
DEVICE_ID = "cargo_tracker_9000"
NUM_REQUESTS = 3


def _fake_vault_sig() -> str:
    """Return a plausible-looking but fake Vault transit signature."""
    token = secrets.token_hex(32)
    return f"vault:v1:{token}"


def _make_payload(nonce: int) -> dict:
    temp_c = round(random.uniform(18.0, 32.0), 3)
    acceleration_overload = round(random.uniform(0.5, 3.5), 3)
    return {
        "payload": {
            "device_id": DEVICE_ID,
            "nonce": nonce,
            "readings": {
                "temp_c": temp_c,
                "acceleration_overload": acceleration_overload,
            },
        },
        "signature": _fake_vault_sig(),
    }


def main() -> None:
    print(f"Sending {NUM_REQUESTS} telemetry packets to {BASE_URL}/sensors/data\n")

    for i in range(1, NUM_REQUESTS + 1):
        body = _make_payload(nonce=secrets.randbits(32))
        readings = body["payload"]["readings"]
        print(
            f"[{i}/{NUM_REQUESTS}] temp={readings['temp_c']}°C  "
            f"accel_overload={readings['acceleration_overload']}"
        )
        try:
            resp = requests.post(f"{BASE_URL}/sensors/data", json=body, timeout=5)
            print(f"  → HTTP {resp.status_code}  {resp.json()}\n")
        except requests.ConnectionError:
            print("  → Connection refused. Is the server running?\n")
            break


if __name__ == "__main__":
    main()
