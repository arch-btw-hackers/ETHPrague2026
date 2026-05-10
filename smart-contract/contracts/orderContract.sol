// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract ColdChainShipment {
    enum TrackerState {
        UNKNOWN,
        GOOD,
        BAD
    }

    enum ShipmentStatus {
        CREATED,
        IN_TRANSIT,
        DELIVERED,
        BREACHED,
        CANCELLED
    }

    struct Shipment {
        address sender;
        address receiver;
        address trackerService;

        string packageRef;      // Swarm/IPFS/backend ссылка с информацией о package
        string telemetryProof;  // Swarm ссылка с подписанными tracker данными

        TrackerState trackerState;
        ShipmentStatus status;

        bool receiverConfirmed;

        uint256 createdAt;
        uint256 deliveredAt;
    }

    uint256 public nextShipmentId;

    mapping(uint256 => Shipment) public shipments;

    event ShipmentCreated(
        uint256 indexed shipmentId,
        address indexed sender,
        address indexed receiver,
        address trackerService,
        string packageRef
    );

    event ShipmentStarted(uint256 indexed shipmentId);

    event TrackerStateSubmitted(
        uint256 indexed shipmentId,
        TrackerState trackerState,
        string telemetryProof
    );

    event ReceiverConfirmed(uint256 indexed shipmentId, address indexed receiver);

    event ShipmentDelivered(uint256 indexed shipmentId);

    event ShipmentBreached(uint256 indexed shipmentId, string reason);

    event ShipmentCancelled(uint256 indexed shipmentId);

    modifier onlySender(uint256 shipmentId) {
        require(msg.sender == shipments[shipmentId].sender, "Not sender");
        _;
    }

    modifier onlyReceiver(uint256 shipmentId) {
        require(msg.sender == shipments[shipmentId].receiver, "Not receiver");
        _;
    }

    modifier onlyTrackerService(uint256 shipmentId) {
        require(msg.sender == shipments[shipmentId].trackerService, "Not tracker service");
        _;
    }

    modifier shipmentExists(uint256 shipmentId) {
        require(shipmentId < nextShipmentId, "Shipment does not exist");
        _;
    }

    function createShipment(
        address receiverWallet,
        address trackerServiceWallet,
        string calldata packageRef
    ) external returns (uint256 shipmentId) {
        require(receiverWallet != address(0), "Invalid receiver");
        require(trackerServiceWallet != address(0), "Invalid tracker service");
        require(bytes(packageRef).length > 0, "Missing package ref");

        shipmentId = nextShipmentId++;

        shipments[shipmentId] = Shipment({
            sender: msg.sender,
            receiver: receiverWallet,
            trackerService: trackerServiceWallet,
            packageRef: packageRef,
            telemetryProof: "",
            trackerState: TrackerState.UNKNOWN,
            status: ShipmentStatus.CREATED,
            receiverConfirmed: false,
            createdAt: block.timestamp,
            deliveredAt: 0
        });

        emit ShipmentCreated(
            shipmentId,
            msg.sender,
            receiverWallet,
            trackerServiceWallet,
            packageRef
        );
    }

    function startShipment(
        uint256 shipmentId
    ) external shipmentExists(shipmentId) onlySender(shipmentId) {
        Shipment storage shipment = shipments[shipmentId];

        require(shipment.status == ShipmentStatus.CREATED, "Wrong status");

        shipment.status = ShipmentStatus.IN_TRANSIT;

        emit ShipmentStarted(shipmentId);
    }

    function submitTrackerState(
        uint256 shipmentId,
        bool isGood,
        string calldata telemetryProof
    ) external shipmentExists(shipmentId) onlyTrackerService(shipmentId) {
        Shipment storage shipment = shipments[shipmentId];

        require(
            shipment.status == ShipmentStatus.CREATED ||
            shipment.status == ShipmentStatus.IN_TRANSIT,
            "Shipment not active"
        );

        require(bytes(telemetryProof).length > 0, "Missing telemetry proof");

        shipment.telemetryProof = telemetryProof;

        if (isGood) {
            shipment.trackerState = TrackerState.GOOD;

            if (shipment.status == ShipmentStatus.CREATED) {
                shipment.status = ShipmentStatus.IN_TRANSIT;
            }

            emit TrackerStateSubmitted(
                shipmentId,
                TrackerState.GOOD,
                telemetryProof
            );

            _tryCompleteShipment(shipmentId);
        } else {
            shipment.trackerState = TrackerState.BAD;
            shipment.status = ShipmentStatus.BREACHED;

            emit TrackerStateSubmitted(
                shipmentId,
                TrackerState.BAD,
                telemetryProof
            );

            emit ShipmentBreached(shipmentId, "Tracker reported bad package state");
        }
    }

    function confirmReceived(
        uint256 shipmentId
    ) external shipmentExists(shipmentId) onlyReceiver(shipmentId) {
        Shipment storage shipment = shipments[shipmentId];

        require(
            shipment.status == ShipmentStatus.CREATED ||
            shipment.status == ShipmentStatus.IN_TRANSIT,
            "Shipment not active"
        );

        shipment.receiverConfirmed = true;

        if (shipment.status == ShipmentStatus.CREATED) {
            shipment.status = ShipmentStatus.IN_TRANSIT;
        }

        emit ReceiverConfirmed(shipmentId, msg.sender);

        _tryCompleteShipment(shipmentId);
    }

    function cancelShipment(
        uint256 shipmentId
    ) external shipmentExists(shipmentId) onlySender(shipmentId) {
        Shipment storage shipment = shipments[shipmentId];

        require(
            shipment.status == ShipmentStatus.CREATED ||
            shipment.status == ShipmentStatus.IN_TRANSIT,
            "Cannot cancel"
        );

        require(
            shipment.trackerState != TrackerState.GOOD || !shipment.receiverConfirmed,
            "Already deliverable"
        );

        shipment.status = ShipmentStatus.CANCELLED;

        emit ShipmentCancelled(shipmentId);
    }

    function _tryCompleteShipment(uint256 shipmentId) internal {
        Shipment storage shipment = shipments[shipmentId];

        if (
            shipment.receiverConfirmed &&
            shipment.trackerState == TrackerState.GOOD &&
            shipment.status == ShipmentStatus.IN_TRANSIT
        ) {
            shipment.status = ShipmentStatus.DELIVERED;
            shipment.deliveredAt = block.timestamp;

            emit ShipmentDelivered(shipmentId);
        }
    }

    function getShipment(
        uint256 shipmentId
    )
        external
        view
        shipmentExists(shipmentId)
        returns (
            address sender,
            address receiver,
            address trackerService,
            string memory packageRef,
            string memory telemetryProof,
            TrackerState trackerState,
            ShipmentStatus status,
            bool receiverConfirmed,
            uint256 createdAt,
            uint256 deliveredAt
        )
    {
        Shipment memory shipment = shipments[shipmentId];

        return (
            shipment.sender,
            shipment.receiver,
            shipment.trackerService,
            shipment.packageRef,
            shipment.telemetryProof,
            shipment.trackerState,
            shipment.status,
            shipment.receiverConfirmed,
            shipment.createdAt,
            shipment.deliveredAt
        );
    }
}