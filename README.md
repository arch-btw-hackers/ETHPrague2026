# GigaService — Cold Chain IoT Platform

> **ETHPrague 2026 hackathon project.**
> A Web3-native microservice that connects physical IoT shipment trackers to decentralised infrastructure: tamper-proof telemetry on **Ethereum Swarm**, on-chain enforcement via a **Solidity smart contract** on Sepolia, and passwordless authentication through **Sign-In with Ethereum**.

---

## What it does

A SpaceComputer hardware tracker signs sensor readings (temperature, acceleration, GPS) with an ECDSA P-256 key and submits them to this backend. The backend verifies the signature, stores an immutable linked-list record in Swarm, runs a rules engine, and — on any violation — autonomously fires a blockchain transaction and sends an HTML alert email. Route planners can query historical violation hotspots and get a Haversine-based risk score for any proposed route.

---

## Roadmap & Features

### Core 1 — Foundation

| | Feature | Implementation |
|---|---|---|
| ✅ | **Smart contract integration** | `services/blockchain.py` — `AsyncWeb3` with `AsyncHTTPProvider` talks to `ColdChainShipment` (Sepolia: `0x965CdD2a560bab50ce52A826d1431A488C9E9959`). Calls `submitTrackerState` and `cancelShipment` as background tasks, signing transactions with the server's private key. |
| ✅ | **Tracker hardware & SpaceComputer connection** | `api/sensors.py` — `POST /sensors/data` receives telemetry packets from the tracker. Every packet is verified before processing; unverifiable requests are rejected with HTTP 403. |
| ✅ | **Signed telemetry** | `verify_spacecomputer_signature()` in `api/sensors.py` validates ECDSA P-256 / SHA-256 signatures using `cryptography.hazmat`. The canonical message is the alphabetically-sorted JSON of the payload, making the signature deterministic and replay-resistant. |
| ✅ | **Swarm storage** | `storage/swarm.py` — each telemetry record is uploaded to Swarm (`/bzz`) as an immutable JSON blob. Records carry a `prev_hash` field pointing to the previous upload, forming a cryptographically linked list. A local `index.json` (Docker volume) maps `device_id → latest_telemetry_hash`. |
| ✅ | **Setup conditions for packages** | `api/packages.py` — `POST /packages/` stores `max_temp_c` and `max_acceleration` thresholds in Swarm and writes the content hash to the index. The sensor endpoint loads conditions by hash on first read and caches them in-process. |
| ✅ | **Alza / Amazon integration** | Marketplace integration is handled on the frontend; the backend exposes the package and tracker CRUD API that marketplace webhooks can call. |
| ✅ | **Wallet integration** | `api/auth.py` — full EIP-4361 SIWE flow: nonce issuance → wallet signing → `eth_account.recover_message()` → JWT. No passwords, no email accounts — only an Ethereum wallet is required. |
| 🔧 | **PQC algorithms (SpaceComputer)** | The signature verification path in `api/sensors.py` is abstracted behind `verify_spacecomputer_signature()`. The current ECDSA P-256 implementation can be swapped for a hybrid classical/post-quantum scheme (e.g. Dilithium) by replacing the verifier without touching any other module. |

### Core 2 — Identity & Access

| | Feature | Implementation |
|---|---|---|
| ✅ | **ENS service** | `services/blockchain.py` — `resolve_ens(name)` converts `.eth` names to `0x` addresses (used in `POST /packages/` so providers can register packages with `tracker.eth`). `reverse_resolve_ens(address)` looks up the primary ENS name for any address and is embedded in the JWT payload for display. |
| ✅ | **Provider / Courier / Tracker / Agent identity** | Every authenticated session carries a `role` field in its JWT. Roles (`provider`, `courier`, `admin`) are assigned at login based on a configurable RBAC table in `services/auth.py`. |
| ✅ | **Access control** | `api/deps.py` — `RoleChecker(["provider"])` is a FastAPI dependency injected directly into route signatures. Unauthorised roles receive HTTP 403 before any business logic runs. |
| ✅ | **Attestations (EAS)** | `services/attestations.py` + `api/deps.py` — `RequiresAttestation(schema_uid)` queries `Attested` event logs on the EAS contract and calls `isRevoked(uid)` to confirm the attestation is live. Results are cached with a TTL; only positive attestations are cached so revocations propagate promptly. |
| ✅ | **Dashboards API** | `api/stats.py` — `GET /stats/hotspots` traverses all devices' telemetry chains and returns every geo-tagged violation record. The frontend consumes this to render heatmaps and analytics dashboards. |
| ✅ | **CI/CD pipeline** | `.github/workflows/test.yml` — GitHub Actions runs **270 pytest tests** on every push and pull request. Coverage is reported with `pytest-cov`. All external I/O (Swarm, Web3, SMTP) is mocked so the suite runs in seconds without any infrastructure. |

### Core 3 & 4 — Analytics, Notifications, Demo

| | Feature | Implementation |
|---|---|---|
| ✅ | **Route recommendation & risk scoring** | `api/stats.py` — `POST /stats/analyze-route` accepts a list of `Waypoint(lat, lon)` objects. It loads current hotspots from Swarm history, computes the **Haversine great-circle distance** (`services/geo.py`) from each waypoint to each hotspot, and returns `LOW` / `MEDIUM` / `HIGH` risk with per-waypoint warnings. Risk radius: 2 km. |
| ✅ | **Notification service** | `services/notifications.py` — HTML alert emails are sent over Gmail SMTP (port 587, STARTTLS) via `loop.run_in_executor` so the event loop is never blocked. Emails render from `templates/alert_email.html` (dark-mode, responsive) and include a direct Etherscan link to the violation transaction. |
| ✅ | **Demo-ready & error handling** | All endpoints return structured JSON errors. Swarm connectivity failures are caught globally and converted to HTTP 503. Blockchain and SMTP errors are logged and swallowed in background tasks — a network hiccup never delays the sensor HTTP response. The service starts with a single `docker compose up`. |

---

## Local Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for running tests locally without Docker)

### 1. Configure environment variables

```bash
cp gigaservice/.env.example gigaservice/.env
```

Edit `gigaservice/.env` and fill in the required values:

```env
# Swarm (auto-configured by docker-compose)
BEE_API_URL=http://localhost:1633
BEE_POSTAGE_BATCH_ID=

# Sepolia blockchain
WEB3_RPC_URL=https://rpc.sepolia.org
CONTRACT_ADDRESS=0x965CdD2a560bab50ce52A826d1431A488C9E9959
WEB3_PRIVATE_KEY=0x<your-sepolia-private-key>

# JWT signing secret
JWT_SECRET=<long-random-string>

# EAS (Ethereum Attestation Service) on Sepolia
EAS_CONTRACT_ADDRESS=0xC2679fBD37d54388Ce493F1DB75320D236e1815e
EAS_COURIER_SCHEMA=0x<your-schema-uid>

# IoT tracker ECDSA P-256 public key (PEM, \n-escaped)
DEVICE_PUBLIC_KEY_PEM=

# Email alerts (Gmail App Password)
SMTP_SENDER_EMAIL=you@gmail.com
SMTP_PASSWORD=<gmail-app-password>
ALERT_RECIPIENT_EMAIL=alerts@example.com
EXPLORER_BASE_URL=https://sepolia.etherscan.io
```

### 2. Start with Docker Compose

```bash
docker compose up --build
```

This starts:
- **`bee`** — Ethereum Swarm node (ports 1633, 1635)
- **`gigaservice`** — FastAPI backend (port 8000)

Telemetry data is persisted in a named Docker volume (`gigaservice_data`).

### 3. Verify the service is running

```bash
curl http://localhost:8000/health
# → {"healthy": true}
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Run the test suite

```bash
cd gigaservice
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

All 270 tests run entirely with mocks — no Bee node or Sepolia RPC required.

```
270 passed in ~24s
```

---

## Project Structure

```
ETHPrague2026/
├── ARCHITECTURE.md          # Deep technical design document
├── docker-compose.yml       # Bee + GigaService stack
└── gigaservice/
    ├── api/
    │   ├── auth.py          # SIWE login, nonce, JWT issuance
    │   ├── deps.py          # RoleChecker, RequiresAttestation
    │   ├── packages.py      # Delivery conditions CRUD
    │   ├── sensors.py       # Telemetry ingestion + violation handler
    │   ├── stats.py         # Hotspots, route risk analysis
    │   └── trackers.py      # Hardware tracker registry
    ├── services/
    │   ├── attestations.py  # EAS on-chain credential verification
    │   ├── auth.py          # JWT, nonce store, role assignment
    │   ├── blockchain.py    # AsyncWeb3, contract calls, ENS
    │   ├── geo.py           # Haversine distance formula
    │   └── notifications.py # HTML email alerts via SMTP
    ├── storage/
    │   └── swarm.py         # Bee API client, linked-list index
    ├── templates/
    │   └── alert_email.html # Dark-mode violation alert template
    ├── tests/               # 270 pytest tests (unit + API)
    ├── Dockerfile
    ├── .env.example
    └── requirements.txt
```

---

## Key Design Decisions

- **No centralised database** — all historical telemetry lives in Swarm; the local index only stores the chain head hash.
- **Backend as oracle** — the server autonomously signs and submits Ethereum transactions when violations occur, with the Swarm hash as on-chain proof.
- **Zero-infrastructure tests** — every external call (Swarm, Web3, SMTP, EAS) is mocked; CI requires no secrets beyond `JWT_SECRET`.
- **Background tasks for latency** — blockchain and email calls are queued as FastAPI `BackgroundTask`s; the tracker receives its HTTP 200 before any network I/O happens.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical deep-dive.
