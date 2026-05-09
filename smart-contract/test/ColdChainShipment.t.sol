// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ColdChainShipment} from "../contracts/orderContract.sol";

contract ColdChainShipmentTest is Test {
    ColdChainShipment public shipment;

    address sender = makeAddr("sender");
    address receiver = makeAddr("receiver");
    address tracker = makeAddr("tracker");
    address stranger = makeAddr("stranger");

    string constant PKG_REF = "ipfs://QmTest";
    string constant TELEMETRY = "swarm://telemetry-proof-1";

    function setUp() public {
        shipment = new ColdChainShipment();
    }

    // -------------------------------------------------------------------------
    // createShipment
    // -------------------------------------------------------------------------

    function test_CreateShipment() public {
        vm.prank(sender);
        uint256 id = shipment.createShipment(receiver, tracker, PKG_REF);

        assertEq(id, 0);
        assertEq(shipment.nextShipmentId(), 1);

        (
            address s, address r, address t,
            string memory pkg, string memory tel,
            ColdChainShipment.TrackerState ts,
            ColdChainShipment.ShipmentStatus status,
            bool confirmed,
            uint256 createdAt,
            uint256 deliveredAt
        ) = shipment.getShipment(id);

        assertEq(s, sender);
        assertEq(r, receiver);
        assertEq(t, tracker);
        assertEq(pkg, PKG_REF);
        assertEq(tel, "");
        assertEq(uint8(ts), uint8(ColdChainShipment.TrackerState.UNKNOWN));
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.CREATED));
        assertFalse(confirmed);
        assertEq(createdAt, block.timestamp);
        assertEq(deliveredAt, 0);
    }

    function test_CreateShipment_EmitsEvent() public {
        vm.expectEmit(true, true, true, true);
        emit ColdChainShipment.ShipmentCreated(0, sender, receiver, tracker, PKG_REF);

        vm.prank(sender);
        shipment.createShipment(receiver, tracker, PKG_REF);
    }

    function test_CreateShipment_RevertOnZeroReceiver() public {
        vm.prank(sender);
        vm.expectRevert("Invalid receiver");
        shipment.createShipment(address(0), tracker, PKG_REF);
    }

    function test_CreateShipment_RevertOnZeroTracker() public {
        vm.prank(sender);
        vm.expectRevert("Invalid tracker service");
        shipment.createShipment(receiver, address(0), PKG_REF);
    }

    function test_CreateShipment_RevertOnEmptyPackageRef() public {
        vm.prank(sender);
        vm.expectRevert("Missing package ref");
        shipment.createShipment(receiver, tracker, "");
    }

    function test_CreateShipment_IncreasesId() public {
        vm.startPrank(sender);
        uint256 id0 = shipment.createShipment(receiver, tracker, PKG_REF);
        uint256 id1 = shipment.createShipment(receiver, tracker, PKG_REF);
        vm.stopPrank();

        assertEq(id0, 0);
        assertEq(id1, 1);
    }

    // -------------------------------------------------------------------------
    // startShipment
    // -------------------------------------------------------------------------

    function _createShipment() internal returns (uint256) {
        vm.prank(sender);
        return shipment.createShipment(receiver, tracker, PKG_REF);
    }

    function test_StartShipment() public {
        uint256 id = _createShipment();

        vm.expectEmit(true, false, false, false);
        emit ColdChainShipment.ShipmentStarted(id);

        vm.prank(sender);
        shipment.startShipment(id);

        (,,,,, , ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.IN_TRANSIT));
    }

    function test_StartShipment_RevertIfNotSender() public {
        uint256 id = _createShipment();
        vm.prank(stranger);
        vm.expectRevert("Not sender");
        shipment.startShipment(id);
    }

    function test_StartShipment_RevertIfWrongStatus() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(sender);
        vm.expectRevert("Wrong status");
        shipment.startShipment(id);
    }

    function test_StartShipment_RevertIfNonExistent() public {
        vm.prank(sender);
        vm.expectRevert("Shipment does not exist");
        shipment.startShipment(99);
    }

    // -------------------------------------------------------------------------
    // submitTrackerState
    // -------------------------------------------------------------------------

    function test_SubmitTrackerState_Good() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.expectEmit(true, false, false, true);
        emit ColdChainShipment.TrackerStateSubmitted(id, ColdChainShipment.TrackerState.GOOD, TELEMETRY);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);

        (,,,, string memory tel, ColdChainShipment.TrackerState ts, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(tel, TELEMETRY);
        assertEq(uint8(ts), uint8(ColdChainShipment.TrackerState.GOOD));
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.IN_TRANSIT));
    }

    function test_SubmitTrackerState_Bad_CausesBreached() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.expectEmit(true, false, false, false);
        emit ColdChainShipment.ShipmentBreached(id, "Tracker reported bad package state");

        vm.prank(tracker);
        shipment.submitTrackerState(id, false, TELEMETRY);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.BREACHED));
    }

    function test_SubmitTrackerState_RevertIfNotTracker() public {
        uint256 id = _createShipment();
        vm.prank(stranger);
        vm.expectRevert("Not tracker service");
        shipment.submitTrackerState(id, true, TELEMETRY);
    }

    function test_SubmitTrackerState_RevertOnEmptyProof() public {
        uint256 id = _createShipment();
        vm.prank(tracker);
        vm.expectRevert("Missing telemetry proof");
        shipment.submitTrackerState(id, true, "");
    }

    function test_SubmitTrackerState_RevertIfBreached() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, false, TELEMETRY);

        vm.prank(tracker);
        vm.expectRevert("Shipment not active");
        shipment.submitTrackerState(id, true, TELEMETRY);
    }

    // -------------------------------------------------------------------------
    // confirmReceived
    // -------------------------------------------------------------------------

    function test_ConfirmReceived() public {
        uint256 id = _createShipment();

        vm.expectEmit(true, true, false, false);
        emit ColdChainShipment.ReceiverConfirmed(id, receiver);

        vm.prank(receiver);
        shipment.confirmReceived(id);

        (,,,,,, ColdChainShipment.ShipmentStatus status, bool confirmed,, ) = shipment.getShipment(id);
        assertTrue(confirmed);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.IN_TRANSIT));
    }

    function test_ConfirmReceived_RevertIfNotReceiver() public {
        uint256 id = _createShipment();
        vm.prank(stranger);
        vm.expectRevert("Not receiver");
        shipment.confirmReceived(id);
    }

    function test_ConfirmReceived_RevertIfBreached() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);
        vm.prank(tracker);
        shipment.submitTrackerState(id, false, TELEMETRY);

        vm.prank(receiver);
        vm.expectRevert("Shipment not active");
        shipment.confirmReceived(id);
    }

    // -------------------------------------------------------------------------
    // Full delivery flow
    // -------------------------------------------------------------------------

    function test_DeliveryFlow_TrackerThenReceiver() public {
        uint256 id = _createShipment();

        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);

        vm.expectEmit(true, false, false, false);
        emit ColdChainShipment.ShipmentDelivered(id);

        vm.prank(receiver);
        shipment.confirmReceived(id);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, uint256 deliveredAt) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.DELIVERED));
        assertEq(deliveredAt, block.timestamp);
    }

    function test_DeliveryFlow_ReceiverThenTracker() public {
        uint256 id = _createShipment();

        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(receiver);
        shipment.confirmReceived(id);

        vm.expectEmit(true, false, false, false);
        emit ColdChainShipment.ShipmentDelivered(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.DELIVERED));
    }

    function test_DeliveryFlow_NotDeliveredWithoutBothConditions() public {
        uint256 id = _createShipment();

        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.IN_TRANSIT));
    }

    // -------------------------------------------------------------------------
    // cancelShipment
    // -------------------------------------------------------------------------

    function test_CancelShipment_WhenCreated() public {
        uint256 id = _createShipment();

        vm.expectEmit(true, false, false, false);
        emit ColdChainShipment.ShipmentCancelled(id);

        vm.prank(sender);
        shipment.cancelShipment(id);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.CANCELLED));
    }

    function test_CancelShipment_WhenInTransit() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(sender);
        shipment.cancelShipment(id);

        (,,,,,, ColdChainShipment.ShipmentStatus status,,, ) = shipment.getShipment(id);
        assertEq(uint8(status), uint8(ColdChainShipment.ShipmentStatus.CANCELLED));
    }

    function test_CancelShipment_RevertIfNotSender() public {
        uint256 id = _createShipment();
        vm.prank(stranger);
        vm.expectRevert("Not sender");
        shipment.cancelShipment(id);
    }

    function test_CancelShipment_RevertIfAlreadyDeliverable() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);
        vm.prank(receiver);
        shipment.confirmReceived(id);

        vm.prank(sender);
        vm.expectRevert("Cannot cancel");
        shipment.cancelShipment(id);
    }

    function test_CancelShipment_RevertIfTrackerGoodAndReceiverConfirmed() public {
        uint256 id = _createShipment();
        vm.prank(sender);
        shipment.startShipment(id);

        vm.prank(tracker);
        shipment.submitTrackerState(id, true, TELEMETRY);

        vm.prank(receiver);
        shipment.confirmReceived(id);

        // Now DELIVERED — can't cancel
        vm.prank(sender);
        vm.expectRevert("Cannot cancel");
        shipment.cancelShipment(id);
    }
}
