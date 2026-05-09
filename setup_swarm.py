#!/usr/bin/env python3
"""
Run once after `docker compose up` to buy a postage batch and save it to .env
Usage: python setup_swarm.py
"""
import httpx
import time
import os

BEE_URL = os.getenv("BEE_API_URL", "http://localhost:1633")
ENV_FILE = os.path.join(os.path.dirname(__file__), "gigaservice", ".env")


def wait_for_bee(timeout=60):
    print("Waiting for Bee node...")
    for _ in range(timeout):
        try:
            r = httpx.get(f"{BEE_URL}/health", timeout=2)
            if r.json().get("status") == "ok":
                print("Bee is ready.")
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("Bee node did not start in time.")


def buy_batch():
    print("Buying postage batch...")
    r = httpx.post(f"{BEE_URL}/stamps/10000000/17", timeout=10)
    r.raise_for_status()
    batch_id = r.json()["batchID"]
    print(f"Batch ID: {batch_id}")
    return batch_id


def write_env(batch_id: str):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            lines = [l for l in f.readlines() if not l.startswith("BEE_POSTAGE_BATCH_ID")]
    lines.append(f"BEE_POSTAGE_BATCH_ID={batch_id}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    print(f"Saved to {ENV_FILE}")


if __name__ == "__main__":
    wait_for_bee()
    batch_id = buy_batch()
    write_env(batch_id)
