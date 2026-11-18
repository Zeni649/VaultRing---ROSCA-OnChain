// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {YieldAdapter} from "../src/YieldAdapter.sol";

/**
 * Deploy YieldAdapter cho một dây hụi (Part 2 — Idle Funds Yield + HITL).
 *
 * Địa chỉ Aave v3 trên Avalanche Fuji:
 *   Pool     : 0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951
 *   aUSDC    : 0x57F1c63497AEe0bE305B8852b354CEc793da43bB
 *   (Nếu Aave Fuji không có thanh khoản USDC, dùng MockYieldAdapter bên dưới.)
 *
 * forge script script/Deploy.s.sol:DeployYieldAdapter \
 *   --rpc-url $FUJI_RPC --broadcast --private-key $PRIVATE_KEY \
 *   --sig "run(address,address,address,address)" $USDC $AAVE_POOL $AUSDC $CIRCLE
 */
contract DeployYieldAdapter is Script {
    function run(
        address usdc,
        address aavePool,
        address ausdc,
        address circle
    ) external returns (YieldAdapter adapter) {
        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        adapter = new YieldAdapter(usdc, aavePool, ausdc, circle);
        console2.log("YieldAdapter", address(adapter));
        vm.stopBroadcast();
    }
}
