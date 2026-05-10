# GigaService — Architecture & Technical Design

## Overview

GigaService is a Web3-native IoT backend for cold-chain logistics. It bridges physical hardware trackers (SpaceComputer devices) with decentralized infrastructure: **Ethereum Swarm** for tamper-proof telemetry storage, **Ethereum smart contracts** for on-chain enforcement, and **EAS** (Ethereum Attestation Service) for participant credential verification. All authentication is passwordless, based on **Sign-In with Ethereum (SIWE)**.

The service is built with **FastAPI** (async Python) and deployed as a Docker container. It exposes a REST API consumed by tracker hardware, logistics operators, and route-planning clients.

---

## Data Flow

```
 [SpaceComputer Tracker]
         │
         │  POST /sensors/data
         │  { payload: {...}, signature: "<ECDSA-P256 base64>" }
         ▼
 ┌──────────────────────┐
 │   api/sensors.py     │
 │  1. Verify ECDSA sig │◄── DEVICE_PUBLIC_KEY_PEM (env)
 │  2. Load conditions  │◄── Swarm (conditions_hash)
 │  3. Rules engine     │
 │  4. Upload telemetry │──► Swarm /bzz (linked list node)
 │  5. BackgroundTask   │
 └──────────┬───────────┘
            │  violation detected
            ▼
 ┌────────────────────────────────┐
 │     _handle_violation()        │
 │  submit_tracker_state(...)     │──► ColdChainShipment.submitTrackerState()
 │  trigger_contract_refund(...)  │──► ColdChainShipment.cancelShipment()
 │  send_html_alert(...)          │──► SMTP (Gmail)
 └────────────────────────────────┘
```

**Step-by-step:**

1. A SpaceComputer tracker sends a signed telemetry packet to `POST /sensors/data` (`api/sensors.py`). The packet carries sensor readings (temperature, acceleration, optional GPS) and a base64-encoded ECDSA P-256 signature over the canonical JSON payload.

2. **Signature verification** (`verify_spacecomputer_signature`) loads the device's public key from `DEVICE_PUBLIC_KEY_PEM` and validates the signature using `cryptography.hazmat.primitives.asymmetric.ec`. In dev mode (key not set), the check is bypassed with a warning.

3. **Delivery conditions** (`max_temp_c`, `max_acceleration`) are fetched from Swarm by their content hash, cached in-process in `CONDITIONS_CACHE` to avoid per-request Swarm round-trips.

4. The **rules engine** evaluates each reading against conditions and produces a list of `violation_reasons`.

5. The telemetry record is serialised as JSON and uploaded to **Swarm** via `upload_json()` (`storage/swarm.py`). The record carries a `prev_hash` field pointing to the previous upload, forming an **append-only linked list** in content-addressable storage.

6. If a violation occurred, `_handle_violation()` is scheduled as a **FastAPI `BackgroundTask`** — the HTTP response is returned immediately, blockchain latency is invisible to the tracker.

---

## Decentralised Storage — Ethereum Swarm

All persistent data is stored in **Ethereum Swarm** (Bee node, `storage/swarm.py`). The backend communicates with a local or remote Bee API (`BEE_API_URL`).

### Immutable Linked List

Every telemetry record uploaded to Swarm is a JSON document with the following envelope:

```json
{
  "device_id": "tracker-001",
  "timestamp": "2026-05-09T14:00:00+00:00",
  "readings": { "temp_c": 26.4, "acceleration_x": 0.3, "lat": 50.07, "lon": 14.43 },
  "is_valid": false,
  "reason": "temp 26.4°C > 25°C",
  "prev_hash": "<swarm-reference-of-previous-record>"
}
```

`prev_hash` is the Swarm content reference of the chronologically previous record for the same device. Because Swarm references are content-addressed (SHA-3 / Keccak), any retroactive modification of a historical record would change its hash, breaking the chain — providing cryptographic tamper-evidence without a blockchain write per telemetry packet.

A mutable **index file** (`/data/index.json`, Docker volume) maps each `device_id` to `conditions_hash` and `latest_telemetry_hash`. This is the only mutable local state; all historical data is immutable in Swarm.

The `asyncio.Lock`-protected `_read_index` / `_write_index` helpers in `storage/swarm.py` ensure atomic read-modify-write under concurrent async coroutines.

### Key functions

| Function | Purpose |
|---|---|
| `upload_json(data)` | POST to `/bzz`, returns 64-char Swarm reference |
| `download_json(ref)` | GET `/bzz/{ref}`, returns parsed JSON |
| `get_device_entry(device_id)` | Read from the local index |
| `set_device_entry(device_id, **fields)` | Atomic write to local index |
| `list_all_entries()` | Full index snapshot (used by analytics) |

---

## Blockchain Integration — ColdChainShipment Contract

The backend acts as a **trusted oracle**: it observes sensor data, applies the rules engine, and autonomously initiates Ethereum transactions when conditions are violated. No human approves individual transactions.

**Contract:** `ColdChainShipment` at `0x965CdD2a560bab50ce52A826d1431A488C9E9959` on Sepolia testnet.

**ABI surface used** (`services/blockchain.py`):

```solidity
function submitTrackerState(uint256 shipmentId, bool isGood, string calldata telemetryProof) external;
function cancelShipment(uint256 shipmentId) external;
```

### Transaction flow

1. `submit_tracker_state(shipment_id, is_good, telemetry_proof)` — primary path. Called on every violation. `telemetry_proof` is the Swarm reference of the just-uploaded telemetry record, making the on-chain event fully auditable: anyone can retrieve the raw sensor data from Swarm using the hash emitted in the transaction.

2. `trigger_contract_refund(shipment_id)` — fallback. If `submitTrackerState` fails (e.g. RPC unreachable), `cancelShipment` is attempted separately.

Both functions build and sign a raw transaction in-process:
- `AsyncWeb3` with `AsyncHTTPProvider` + `ExtraDataToPOAMiddleware` (PoA chain support)
- Gas price read from `w3.eth.gas_price` (awaited directly as a coroutine)
- Lazy singleton `_w3` instance to avoid connection setup cost on every telemetry packet

Credentials (`WEB3_RPC_URL`, `WEB3_PRIVATE_KEY`, `CONTRACT_ADDRESS`) are injected via environment variables — never committed to the repository.

---

## Authentication — Sign-In with Ethereum (SIWE) + JWT + RBAC

The service uses **no passwords**. Authentication is performed by signing an EIP-4361 SIWE message with the user's Ethereum wallet (`api/auth.py`).

### Auth flow

```
Client                              Server
  │  GET /auth/nonce                  │
  │──────────────────────────────────►│
  │  ← { nonce: "a3f7..." }           │  (single-use, stored in memory)
  │                                   │
  │  Sign SIWE message in wallet      │
  │                                   │
  │  POST /auth/verify                │
  │  { message: "...", signature: "..."} │
  │──────────────────────────────────►│
  │                                   │  1. Parse EIP-4361 message
  │                                   │  2. Verify nonce (consume)
  │                                   │  3. eth_account.recover_message()
  │                                   │  4. Compare recovered address
  │                                   │  5. Assign role from RBAC table
  │                                   │  6. Issue JWT (HS256, 24h)
  │  ← { token, address, role }       │
```

SIWE message parsing is implemented natively with `eth_account` (bundled in `web3`) — no C-extension dependencies (`siwe` library avoided for build portability). The EIP-4361 format is parsed with a lightweight regex helper in `api/auth.py`.

### RBAC

Each JWT payload carries a `role` field. The `RoleChecker` dependency (`api/deps.py`) enforces access:

| Role | Permitted endpoints |
|---|---|
| `provider` | `POST /packages/`, full tracker CRUD |
| `courier` | `GET /packages/{id}`, sensor data submission |
| `admin` | All endpoints |

### ENS integration

`reverse_resolve_ens(address)` (`services/blockchain.py`) resolves Ethereum addresses to ENS names for display purposes (e.g. in JWT payloads and audit logs). `resolve_ens(name)` converts ENS names to `0x` addresses, allowing providers to register packages using `tracker.eth` instead of raw hex identifiers.

---

## Trust Protocol — Ethereum Attestation Service (EAS)

Sensitive endpoints require participants to hold an **on-chain attestation** from a trusted attester, verified through the EAS contract (`services/attestations.py`).

The `RequiresAttestation(schema_uid)` FastAPI dependency:

1. Decodes the Bearer JWT to obtain the user's Ethereum address.
2. Queries `Attested(recipient, schema)` event logs on the EAS contract.
3. Calls `isRevoked(uid)` for each matching attestation.
4. Returns 403 Forbidden if no live attestation exists.

Results are **cached in-process** (`_ATTESTATION_CACHE`) with a configurable TTL. Only `True` (attested) results are cached — revocations take effect within one TTL window. `False` results bypass the cache so a freshly-issued attestation grants access immediately.

Example: the `GET /packages/{device_id}/history` endpoint is gated behind `RequiresAttestation(COURIER_SCHEMA_ID)` — only couriers certified on-chain can retrieve shipment history.

In dev mode (EAS env vars not set), `verify_attestation` returns `True` unconditionally so local development requires no blockchain node.

---

## Notifications — Async SMTP Alerts

When a violation is detected, `send_html_alert()` (`services/notifications.py`) sends an HTML email to the configured recipient.

- Transport: **Gmail SMTP on port 587 with STARTTLS** (`smtplib`)
- The blocking SMTP handshake runs inside `loop.run_in_executor(None, _send_sync, ...)` — the event loop is never blocked
- The email body is rendered from `templates/alert_email.html` — a dark-mode responsive template with a purple CTA button linking to the transaction or contract on Etherscan
- The explorer link is built by `_build_explorer_link(val)`: 66-char strings → `/tx/`, 42-char strings → `/address/`
- `SMTP_PASSWORD` is read exclusively from the environment at send time — never stored as a module-level constant

---

## Geo-Analytics — Route Risk Analysis

`GET /stats/hotspots` and `POST /stats/analyze-route` (`api/stats.py`) provide spatial analytics over historical violation data.

### Hotspot collection

`_collect_hotspots()` traverses the telemetry linked-list for every device (up to `_MAX_DEPTH = 200` nodes each). Records where `is_valid == False` and GPS coordinates (`lat`, `lon`) are present are collected as hotspots. The traversal is fully async — each Swarm download is awaited without blocking the event loop.

### Route risk scoring (`POST /stats/analyze-route`)

The request body carries a list of `Waypoint(lat, lon)` objects representing a proposed delivery route. The algorithm:

1. Loads current hotspots via `_collect_hotspots()`.
2. For each waypoint, computes the **Haversine great-circle distance** to every hotspot using `haversine_km()` from `services/geo.py`.
3. If any hotspot falls within `_RISK_RADIUS_KM = 2.0` km, a warning is added: `"Route passes near a historical violation zone at [lat, lon]"`.
4. Risk level is derived from the count of flagged waypoints:

| Flagged waypoints | Risk level |
|---|---|
| 0 | `LOW` |
| 1 – 2 | `MEDIUM` |
| ≥ 3 | `HIGH` |

The Haversine formula (`services/geo.py`) uses only Python's standard `math` library:

$$d = 2r \arcsin\!\left(\sqrt{\sin^2\!\frac{\Delta\varphi}{2} + \cos\varphi_1\cos\varphi_2\sin^2\!\frac{\Delta\lambda}{2}}\right)$$

where $r = 6371$ km (mean Earth radius). Accuracy is within ±0.5% for all terrestrial distances.

---

## API Surface Summary

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Liveness probe |
| `GET` | `/auth/nonce` | — | Issue single-use SIWE nonce |
| `POST` | `/auth/verify` | — | Verify SIWE signature, return JWT |
| `POST` | `/packages/` | Provider | Register shipment conditions in Swarm |
| `GET` | `/packages/{id}` | Any | Retrieve conditions by device ID |
| `POST` | `/sensors/data` | — | Ingest signed telemetry packet |
| `GET` | `/sensors/latest/{id}` | Any | Latest telemetry record |
| `GET` | `/stats/hotspots` | — | All geo-tagged violation hotspots |
| `POST` | `/stats/analyze-route` | — | Risk analysis for a proposed route |
| `POST` | `/trackers/` | Any | Register hardware tracker |
| `GET` | `/trackers/` | Any | List all trackers |
| `GET` | `/trackers/{id}` | Any | Tracker details |
| `PUT` | `/trackers/{id}` | Any | Update tracker metadata |
| `DELETE` | `/trackers/{id}` | Any | Remove tracker |

---

## Environment Variables

| Variable | Module | Purpose |
|---|---|---|
| `WEB3_RPC_URL` | `services/blockchain.py` | Sepolia JSON-RPC endpoint |
| `CONTRACT_ADDRESS` | `services/blockchain.py` | ColdChainShipment address |
| `WEB3_PRIVATE_KEY` | `services/blockchain.py` | Transaction signing key |
| `EAS_CONTRACT_ADDRESS` | `services/attestations.py` | EAS contract address |
| `EAS_COURIER_SCHEMA` | `api/packages.py` | Courier attestation schema UID |
| `DEVICE_PUBLIC_KEY_PEM` | `api/sensors.py` | SpaceComputer ECDSA P-256 public key |
| `JWT_SECRET` | `services/auth.py` | HMAC-SHA256 JWT signing secret |
| `BEE_API_URL` | `storage/swarm.py` | Bee node API endpoint |
| `BEE_POSTAGE_BATCH_ID` | `storage/swarm.py` | Swarm postage batch |
| `SMTP_SENDER_EMAIL` | `services/notifications.py` | Gmail sender address |
| `SMTP_PASSWORD` | `services/notifications.py` | Gmail App Password |
| `ALERT_RECIPIENT_EMAIL` | `api/sensors.py` | Alert destination address |
| `EXPLORER_BASE_URL` | `services/notifications.py` | Block explorer base URL |

All credentials are injected at runtime — the repository contains no secrets.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12+, FastAPI, Uvicorn |
| Async I/O | `asyncio`, `httpx.AsyncClient` (connection pooling) |
| Blockchain | `web3==7.9.0`, `AsyncWeb3`, `AsyncHTTPProvider` |
| Cryptography | `eth_account` (SIWE + tx signing), `cryptography` (ECDSA P-256) |
| Decentralised storage | Ethereum Swarm / Bee node (`/bzz` API) |
| Authentication | EIP-4361 SIWE + HS256 JWT |
| Authorisation | Role-based (`RoleChecker`) + on-chain attestations (`RequiresAttestation`) |
| Email | `smtplib` + STARTTLS, run in thread executor |
| Geospatial | Haversine formula (`services/geo.py`, stdlib `math` only) |
| Containerisation | Docker (`Dockerfile`) |
| Testing | pytest, pytest-asyncio, respx, 270 tests, GitHub Actions CI |
