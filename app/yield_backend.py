"""
Backend cho Part 2: Idle Funds Yield + HITL.

Các hàm này gọi RoscaCircle để điều khiển YieldAdapter.
HITL: organizer bấm nút → backend gọi contract → adapter gửi/rút tiền.
"""
from typing import Dict

from app.contract_abi import ROSCA_CIRCLE_ABI, YIELD_ADAPTER_ABI
from app.wallet import DemoWallet, send


def supply_to_aave(
    w3,
    wallet: DemoWallet,
    rosca_addr: str,
    adapter_addr: str,
    amount: int,
    gas: int = 500_000
) -> Dict:
    """
    Gửi idle funds sang adapter để kiếm lãi.
    Gọi Rosca.sendToAdapter(amount) → Rosca transfer USDC + gọi adapter.supplyToAave().

    Args:
        amount: USDC base units (1 USDC = 10^6)

    Returns:
        Receipt dict: {hash, link, block, gasUsed, gasCostAvax}
    """
    rosca = w3.eth.contract(address=rosca_addr, abi=ROSCA_CIRCLE_ABI)
    fn = rosca.functions.sendToAdapter(amount)
    return send(w3, wallet, fn, gas)


def withdraw_and_report(
    w3,
    wallet: DemoWallet,
    rosca_addr: str,
    gas: int = 500_000
) -> Dict:
    """
    Rút tiền (gốc + lãi) từ adapter về Rosca.
    Gọi Rosca.withdrawFromAdapter() → Rosca reset fundsInAdapter, gọi adapter.withdrawAndReport()
    → adapter rút từ Aave, tính yield, gửi lại Rosca, gọi noteYield().

    Bất kỳ thành viên nào cũng gọi được (van an toàn).

    Returns:
        Receipt dict: {hash, link, block, gasUsed, gasCostAvax}
    """
    rosca = w3.eth.contract(address=rosca_addr, abi=ROSCA_CIRCLE_ABI)
    fn = rosca.functions.withdrawFromAdapter()
    return send(w3, wallet, fn, gas)


def get_ausdc_balance(w3, adapter_addr: str) -> int:
    """
    Lấy aUSDC balance hiện tại (USDC base units).
    Dùng để polling xem lãi đang tăng dần.
    """
    adapter = w3.eth.contract(address=adapter_addr, abi=YIELD_ADAPTER_ABI)
    return adapter.functions.ausdc_balance().call()


def get_funds_in_adapter(w3, rosca_addr: str) -> int:
    """
    Lấy số tiền đang nằm ở adapter (tracked by Rosca).
    """
    rosca = w3.eth.contract(address=rosca_addr, abi=ROSCA_CIRCLE_ABI)
    return rosca.functions.fundsInAdapter().call()


def get_yield_accrued(w3, rosca_addr: str) -> int:
    """
    Lấy yield đã kiếm được (USDC base units).
    Được cập nhật mỗi lần adapter gọi noteYield().
    """
    rosca = w3.eth.contract(address=rosca_addr, abi=ROSCA_CIRCLE_ABI)
    return rosca.functions.yieldAccrued().call()
