// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title  MockYieldAdapter
 * @notice Adapter giả cho demo — thay vì gửi Aave, nó chỉ track số tiền
 *         và tạo yield giả (0.5% mỗi lần withdraw) để quay video demo được.
 *
 * Dùng khi Aave Fuji không có thanh khoản USDC hoặc để test HITL flow.
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IRoscaCircle {
    function noteYield(uint256 amount) external;
}

contract MockYieldAdapter {
    address public immutable USDC;
    address public immutable ROSCA;

    uint256 public amountSent;  // Track gốc
    uint256 public mockBalance; // Giả aUSDC balance (gốc + lãi giả)

    event SuppliedToAave(uint256 amount);
    event WithdrewFromAave(uint256 usdcReceived, uint256 yieldEarned);

    constructor(address usdc_, address rosca_) {
        USDC = usdc_;
        ROSCA = rosca_;
    }

    /**
     * @notice Giả gửi USDC vào Aave.
     *         Thực tế chỉ track và cập nhật mockBalance.
     */
    function supplyToAave(uint256 amount) external {
        require(msg.sender == ROSCA, "only_rosca");
        require(amount > 0, "zero_amount");

        amountSent += amount;
        mockBalance += amount;  // Giả: aUSDC = gốc (chưa accrual lãi)

        emit SuppliedToAave(amount);
    }

    /**
     * @notice Giả rút từ Aave.
     *         Tạo yield giả (0.5%) và gửi lại Rosca + báo lãi.
     */
    function withdrawAndReport() external {
        require(msg.sender == ROSCA, "only_rosca");
        require(mockBalance > 0, "no_ausdc");

        // Tạo yield giả: 0.5% của gốc
        uint256 fakeYield = (amountSent * 5) / 1000;  // 0.5%
        uint256 usdcReceived = amountSent + fakeYield;

        // Gửi lại Rosca (mock: chỉ log, không transfer thực)
        // Trong thực tế cần transfer từ USDC
        require(IERC20(USDC).transfer(ROSCA, usdcReceived), "transfer_failed");

        // Báo lại Rosca
        IRoscaCircle(ROSCA).noteYield(fakeYield);

        emit WithdrewFromAave(usdcReceived, fakeYield);

        // Reset
        amountSent = 0;
        mockBalance = 0;
    }

    /**
     * @notice Giả aUSDC balance.
     */
    function ausdc_balance() external view returns (uint256) {
        return mockBalance;
    }
}
