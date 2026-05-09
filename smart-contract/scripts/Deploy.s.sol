// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ColdChainShipment} from "../contracts/orderContract.sol";

contract DeployScript is Script {
    function run() external returns (ColdChainShipment) {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");

        vm.startBroadcast(deployerKey);
        ColdChainShipment shipment = new ColdChainShipment();
        vm.stopBroadcast();

        console.log("ColdChainShipment deployed at:", address(shipment));
        return shipment;
    }
}
