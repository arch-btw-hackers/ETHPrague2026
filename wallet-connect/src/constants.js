export const API_BASE = 'http://80.211.207.162:8000/api/v1';

export const CONTRACT_ADDRESS = '0x965CdD2a560bab50ce52A826d1431A488C9E9959';
export const STATIC_RECEIVER = '0x9BF33E723997aF32fB187Afd295cB92c105E7e97';
export const TRACKER_SERVICE_WALLET = '0x2A64A82325244de00b0DB9B7Cf1C84D48da80d06';

export const TRACKER_STATE_LABELS = {
    0: 'Unknown',
    1: 'Good',
    2: 'Bad',
};

export const TRACKER_STATE_COLORS = {
    0: 'var(--status-unknown)',
    1: 'var(--status-good)',
    2: 'var(--status-bad)',
};

export const SHIPMENT_STATUS_LABELS = {
    0: 'Created',
    1: 'In Transit',
    2: 'Delivered',
    3: 'Breached',
    4: 'Cancelled',
};

export const SHIPMENT_STATUS_COLORS = {
    0: 'var(--status-created)',
    1: 'var(--status-transit)',
    2: 'var(--status-good)',
    3: 'var(--status-bad)',
    4: 'var(--status-cancelled)',
};

export const CONTRACT_ABI = [
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            }
        ],
        "name": "ReceiverConfirmed",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "string",
                "name": "reason",
                "type": "string"
            }
        ],
        "name": "ShipmentBreached",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "ShipmentCancelled",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "indexed": true,
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "address",
                "name": "trackerService",
                "type": "address"
            },
            {
                "indexed": false,
                "internalType": "string",
                "name": "packageRef",
                "type": "string"
            }
        ],
        "name": "ShipmentCreated",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "ShipmentDelivered",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "ShipmentStarted",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            },
            {
                "indexed": false,
                "internalType": "enum ColdChainShipment.TrackerState",
                "name": "trackerState",
                "type": "uint8"
            },
            {
                "indexed": false,
                "internalType": "string",
                "name": "telemetryProof",
                "type": "string"
            }
        ],
        "name": "TrackerStateSubmitted",
        "type": "event"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "cancelShipment",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "confirmReceived",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "receiverWallet",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "trackerServiceWallet",
                "type": "address"
            },
            {
                "internalType": "string",
                "name": "packageRef",
                "type": "string"
            }
        ],
        "name": "createShipment",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "getShipment",
        "outputs": [
            {
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "trackerService",
                "type": "address"
            },
            {
                "internalType": "string",
                "name": "packageRef",
                "type": "string"
            },
            {
                "internalType": "string",
                "name": "telemetryProof",
                "type": "string"
            },
            {
                "internalType": "enum ColdChainShipment.TrackerState",
                "name": "trackerState",
                "type": "uint8"
            },
            {
                "internalType": "enum ColdChainShipment.ShipmentStatus",
                "name": "status",
                "type": "uint8"
            },
            {
                "internalType": "bool",
                "name": "receiverConfirmed",
                "type": "bool"
            },
            {
                "internalType": "uint256",
                "name": "createdAt",
                "type": "uint256"
            },
            {
                "internalType": "uint256",
                "name": "deliveredAt",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "nextShipmentId",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "name": "shipments",
        "outputs": [
            {
                "internalType": "address",
                "name": "sender",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "receiver",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "trackerService",
                "type": "address"
            },
            {
                "internalType": "string",
                "name": "packageRef",
                "type": "string"
            },
            {
                "internalType": "string",
                "name": "telemetryProof",
                "type": "string"
            },
            {
                "internalType": "enum ColdChainShipment.TrackerState",
                "name": "trackerState",
                "type": "uint8"
            },
            {
                "internalType": "enum ColdChainShipment.ShipmentStatus",
                "name": "status",
                "type": "uint8"
            },
            {
                "internalType": "bool",
                "name": "receiverConfirmed",
                "type": "bool"
            },
            {
                "internalType": "uint256",
                "name": "createdAt",
                "type": "uint256"
            },
            {
                "internalType": "uint256",
                "name": "deliveredAt",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            }
        ],
        "name": "startShipment",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "uint256",
                "name": "shipmentId",
                "type": "uint256"
            },
            {
                "internalType": "bool",
                "name": "isGood",
                "type": "bool"
            },
            {
                "internalType": "string",
                "name": "telemetryProof",
                "type": "string"
            }
        ],
        "name": "submitTrackerState",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }


];