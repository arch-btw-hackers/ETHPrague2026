// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ColdChainShipment} from "../contracts/orderContract.sol";

// Runs the full happy-path flow against a live deployment.
// Since we use one key for all roles (sender = receiver = tracker),
// the flow is: create → start → tracker reports GOOD → receiver confirms → DELIVERED.
contract TestOnChainScript is Script {
    address constant CONTRACT = 0x33B4e4950C14bdad2ec99f0A97ce667E29447213;

    function run() external {
        uint256 key = vm.envUint("PRIVATE_KEY");
        address self = vm.addr(key);

        ColdChainShipment c = ColdChainShipment(CONTRACT);

        console.log("=== ColdChainShipment on-chain test ===");
        console.log("Tester address:", self);
        console.log("Contract:", CONTRACT);
        console.log("nextShipmentId before:", c.nextShipmentId());

        vm.startBroadcast(key);

        // 1. Create shipment — use self for all roles to avoid multi-key complexity
        uint256 id = c.createShipment(self, self, "ipfs://test-package-ref");
        console.log("1. createShipment -> id:", id);

        // 2. Start shipment
        c.startShipment(id);
        console.log("2. startShipment OK");

        // 3. Tracker submits GOOD state
        c.submitTrackerState(id, true, "swarm://telemetry-proof-ok");
        console.log("3. submitTrackerState(good) OK");

        // 4. Receiver confirms
        c.confirmReceived(id);
        console.log("4. confirmReceived OK");

        vm.stopBroadcast();

        // 5. Read final state (no broadcast needed)
        (
            address sender,
            address receiver,
            address trackerService,
            string memory packageRef,
            string memory telemetryProof,
            ColdChainShipment.TrackerState trackerState,
            ColdChainShipment.ShipmentStatus status,
            bool receiverConfirmed,
            uint256 createdAt,
            uint256 deliveredAt
        ) = c.getShipment(id);

        console.log("=== Final shipment state ===");
        console.log("sender:          ", sender);
        console.log("receiver:        ", receiver);
        console.log("trackerService:  ", trackerService);
        console.log("packageRef:      ", packageRef);
        console.log("telemetryProof:  ", telemetryProof);
        console.log("trackerState:    ", uint8(trackerState));  // 1 = GOOD
        console.log("status:          ", uint8(status));        // 2 = DELIVERED
        console.log("receiverConfirmed:", receiverConfirmed);
        console.log("createdAt:       ", createdAt);
        console.log("deliveredAt:     ", deliveredAt);

        require(status == ColdChainShipment.ShipmentStatus.DELIVERED, "FAIL: expected DELIVERED");
        require(trackerState == ColdChainShipment.TrackerState.GOOD, "FAIL: expected GOOD tracker state");
        require(receiverConfirmed, "FAIL: expected receiver confirmed");
        require(deliveredAt > 0, "FAIL: deliveredAt not set");

        console.log("=== ALL CHECKS PASSED ===");
    }
}
