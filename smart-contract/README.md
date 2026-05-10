# ColdChainShipment Smart Contract

A Solidity smart contract for trustless cold-chain logistics tracking, built with [Foundry](https://book.getfoundry.sh/). Shipments are marked **DELIVERED** only when both the tracker service reports good conditions **and** the receiver confirms receipt — neither party alone can complete the delivery.

## Overview

Three roles participate in each shipment:

| Role | Responsibility |
|---|---|
| **Sender** | Creates and starts the shipment, can cancel it |
| **Tracker Service** | Submits signed telemetry proofs (temperature, humidity, etc.) stored on Swarm/IPFS |
| **Receiver** | Confirms physical receipt of the package |

### Shipment lifecycle

```
CREATED → IN_TRANSIT → DELIVERED
                     ↘ BREACHED   (tracker reports bad conditions)
         ↘ CANCELLED              (sender cancels before delivery)
```

Delivery requires **both** conditions to be true:
- Tracker submitted a `GOOD` state with a telemetry proof
- Receiver called `confirmReceived`

Either condition can arrive first; the contract auto-completes the shipment when both are met.

## Contract

`contracts/orderContract.sol` — `ColdChainShipment`

### Key functions

| Function | Caller | Description |
|---|---|---|
| `createShipment(receiver, trackerService, packageRef)` | Sender | Creates a new shipment; `packageRef` is a Swarm/IPFS link to package metadata |
| `startShipment(shipmentId)` | Sender | Transitions status from `CREATED` to `IN_TRANSIT` |
| `submitTrackerState(shipmentId, isGood, telemetryProof)` | Tracker Service | Submits telemetry; a bad state immediately sets status to `BREACHED` |
| `confirmReceived(shipmentId)` | Receiver | Confirms physical receipt |
| `cancelShipment(shipmentId)` | Sender | Cancels if not yet deliverable |
| `getShipment(shipmentId)` | Anyone | Returns full shipment state |

### Events

- `ShipmentCreated` — emitted on creation
- `ShipmentStarted` — emitted when sender starts transit
- `TrackerStateSubmitted` — emitted on each tracker update (includes telemetry proof URI)
- `ReceiverConfirmed` — emitted when receiver acknowledges receipt
- `ShipmentDelivered` — emitted when both conditions are satisfied
- `ShipmentBreached` — emitted when tracker reports bad package state
- `ShipmentCancelled` — emitted on cancellation

## Setup

### Prerequisites

- [Foundry](https://book.getfoundry.sh/getting-started/installation) (`forge`, `cast`, `anvil`)

### Install

```bash
make install
```

Or manually:

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
forge install foundry-rs/forge-std
```

### Environment

Copy the example env file and fill in your values:

```bash
cp .example.env .dev.env
```

`.dev.env` variables:

| Variable | Description |
|---|---|
| `PRIVATE_KEY` | Deployer/tester private key (no `0x` prefix) |
| `SEPOLIA_RPC_URL` | Alchemy/Infura Sepolia endpoint |
| `MAINNET_RPC_URL` | Alchemy/Infura mainnet endpoint |
| `ETHERSCAN_API_KEY` | For contract verification |
| `CONTRACT_ADDRESS` | Auto-populated by `make deploy-sepolia` |

## Usage

### Build

```bash
make build
# or: forge build
```

### Test (local)

```bash
make test
# or: forge test -vvv
```

### Deploy to Sepolia

```bash
make deploy-sepolia
```

The contract address is automatically written to `CONTRACT_ADDRESS` in `.dev.env` after deployment.

### Deploy to Mainnet

```bash
make deploy-mainnet
```

### On-chain integration test

Runs the full happy-path flow (`create → start → tracker GOOD → receiver confirms → DELIVERED`) against the deployed contract:

```bash
forge script scripts/TestOnChain.s.sol:TestOnChainScript \
  --rpc-url $SEPOLIA_RPC_URL \
  --private-key $PRIVATE_KEY \
  --broadcast -vvvv
```

### Clean

```bash
make clean
```

## Project Structure

```
smart-contract/
├── contracts/
│   └── orderContract.sol     # ColdChainShipment contract
├── scripts/
│   ├── Deploy.s.sol          # Deployment script
│   └── TestOnChain.s.sol     # On-chain integration test
├── test/
│   └── ColdChainShipment.t.sol  # Forge unit tests
├── ts-test/
│   └── index.ts              # TypeScript integration tests
├── foundry.toml              # Foundry configuration
└── Makefile                  # Common commands
```

## Configuration

`foundry.toml`:
- Solidity `0.8.24`
- Optimizer enabled, 200 runs
- Sources: `contracts/`, tests: `test/`, scripts: `scripts/`
