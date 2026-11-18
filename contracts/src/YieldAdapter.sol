// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title  YieldAdapter
 * @notice Gửi USDC vào Aave v3 trên Avalanche Fuji để kiếm lãi.
 *         Rosca quản lý: chọn pool, bấm nút, adapter gửi, báo lại yield.
 *
 * HITL (Human in the Loop): Rosca dashboard gợi ý pool → organizer bấm nút
 * → Rosca transfer USDC tới adapter → adapter gửi Aave → yield được tích lũy
 * → organizer bấm "rút" → adapter withdraw + noteYield() để báo lại.
 *
 * Kế toán:
 *   - Rosca track amountSent (tổng USDC chuyển sang adapter)
 *   - Adapter track amountSent cũng
 *   - Khi withdraw: yield = (USDC nhận từ Aave) - amountSent
 *   - Gửi lại Rosca toàn bộ USDC (gốc + lãi)
 *   - Báo Rosca chỉ mỗi lãi (yield)
 *
 * Rủi ro: Aave có thể gặp sự cố, IL từ LP, hay token mất giá. Rosca chỉ gợi ý,
 * không tự động hoá.
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IAavePool {
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);
}

interface IRoscaCircle {
    function noteYield(uint256 amount) external;
}

contract YieldAdapter {
    address public immutable USDC;
    address public immutable AAVE_POOL;
    address public immutable AUSDC;
    address public immutable ROSCA;

    uint256 public amountSent;  // Track tổng USDC đã gửi vào Aave

    event SuppliedToAave(uint256 amount);
    event WithdrewFromAave(uint256 usdcReceived, uint256 yieldEarned);

    constructor(
        address usdc_,
        address aavePool_,
        address ausdc_,
        address rosca_
    ) {
        USDC = usdc_;
        AAVE_POOL = aavePool_;
        AUSDC = ausdc_;
        ROSCA = rosca_;

        // Approve Aave to spend USDC
        IERC20(USDC).approve(AAVE_POOL, type(uint256).max);
    }

    /**
     * @notice Gửi USDC vào Aave. Rosca gọi sau khi transfer USDC tới adapter.
     *
     * Flow:
     *   1. Rosca.transfer(adapter, amount)
     *   2. Adapter.supplyToAave(amount)
     *   3. Adapter cập nhật amountSent, supply vào Aave
     */
    function supplyToAave(uint256 amount) external {
        require(msg.sender == ROSCA, "only_rosca");
        require(amount > 0, "zero_amount");

        // Supply vào Aave (USDC đã có trong adapter từ Rosca.transfer)
        IAavePool(AAVE_POOL).supply(USDC, amount, address(this), 0);

        amountSent += amount;
        emit SuppliedToAave(amount);
    }

    /**
     * @notice Rút toàn bộ aUSDC từ Aave, tính yield, gửi lại Rosca, ghi nhận lãi.
     *         Chỉ Rosca gọi được.
     *
     * Flow:
     *   1. Rút từ Aave, nhận USDC (gốc + lãi)
     *   2. yield = usdcReceived - amountSent
     *   3. Transfer toàn bộ USDC lại Rosca
     *   4. Gọi Rosca.noteYield(yield) để tích lũy vào yieldAccrued
     *   5. Reset amountSent
     */
    function withdrawAndReport() external {
        require(msg.sender == ROSCA, "only_rosca");

        uint256 ausdc_balance = IERC20(AUSDC).balanceOf(address(this));
        require(ausdc_balance > 0, "no_ausdc");

        // Rút từ Aave
        uint256 usdc_received = IAavePool(AAVE_POOL).withdraw(USDC, ausdc_balance, address(this));

        // Tính yield = usdc_received - amountSent
        // (Nếu usdc_received < amountSent, nghĩa là lỗ → yield = 0)
        uint256 yield = usdc_received > amountSent ? usdc_received - amountSent : 0;

        // Gửi lại Rosca toàn bộ USDC
        require(IERC20(USDC).transfer(ROSCA, usdc_received), "transfer_failed");

        // Báo lại Rosca: yield đã kiếm được
        IRoscaCircle(ROSCA).noteYield(yield);

        // Reset
        amountSent = 0;

        emit WithdrewFromAave(usdc_received, yield);
    }

    /**
     * @notice Kiểm tra aUSDC đang giữ.
     */
    function ausdc_balance() external view returns (uint256) {
        return IERC20(AUSDC).balanceOf(address(this));
    }
}
