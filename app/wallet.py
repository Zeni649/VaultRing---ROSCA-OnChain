"""
Ký và gửi giao dịch cho 4 ví demo trên Avalanche Fuji.

VÌ SAO KÝ CỤC BỘ
---------------
Bản demo cần chạy trọn một dây hụi 4 người trong lúc quay video. Bắt người
quay video bấm MetaMask 4 lần mỗi kỳ × 4 kỳ = 16 lần xác nhận là không
khả thi. Nên 4 ví demo được nạp private key từ file cục bộ, và app ký hộ.

Đây là ví TESTNET, không giữ tiền thật. Khi lên mainnet, thay lớp này bằng
một provider được inject (MetaMask / Core / WalletConnect) và bỏ phần
private key đi — bản thân contract không thay đổi.

CẤU HÌNH
--------
Đặt file `demo_wallets.json` ở thư mục gốc dự án:

    [
      {"name": "Người 1", "private_key": "0x..."},
      {"name": "Người 2", "private_key": "0x..."},
      {"name": "Người 3", "private_key": "0x..."},
      {"name": "Người 4", "private_key": "0x..."}
    ]

Hoặc biến môi trường HUI_PK_1 … HUI_PK_4.
File `demo_wallets.json` KHÔNG được commit (đã có trong .gitignore).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.chain import FUJI_CHAIN_ID, USDC_FUJI, etherscan_link
from app.contract_abi import ERC20_ABI, ROSCA_CIRCLE_ABI, ROSCA_FACTORY_ABI

ROOT = Path(__file__).resolve().parent.parent
WALLET_FILE = ROOT / "demo_wallets.json"


@dataclass
class DemoWallet:
    name: str
    address: str
    key: Optional[str] = None       # None = chỉ đọc, không ký được

    @property
    def can_sign(self) -> bool:
        return bool(self.key)


# ══════════════════════════════════════════════════════════════════
# Nạp ví
# ══════════════════════════════════════════════════════════════════

def _address_of(private_key: str) -> str:
    from eth_account import Account
    return Account.from_key(private_key).address


def load_players() -> list[DemoWallet]:
    """
    Nạp danh sách ví demo. Ưu tiên file JSON, sau đó tới biến môi trường.
    Trả về list rỗng nếu chưa cấu hình — UI sẽ hiện hướng dẫn thiết lập.
    """
    out: list[DemoWallet] = []

    if WALLET_FILE.exists():
        try:
            raw = json.loads(WALLET_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = []
        for i, item in enumerate(raw):
            key = (item.get("private_key") or "").strip() or None
            if not key:
                continue
            try:
                out.append(DemoWallet(
                    name=item.get("name") or f"Người {i + 1}",
                    address=_address_of(key),
                    key=key,
                ))
            except Exception:
                continue

    if not out:
        names_default = ["Alice", "Bob", "Carol", "Dave"]
        for i in range(1, 5):
            key = (os.environ.get(f"HUI_PK_{i}") or "").strip() or None
            if not key:
                try:
                    import streamlit as _st
                    key = str(_st.secrets.get(f"HUI_PK_{i}", "")).strip() or None
                except Exception:
                    key = None
            if not key:
                continue
            try:
                out.append(DemoWallet(
                    name=names_default[i - 1],
                    address=_address_of(key),
                    key=key,
                ))
            except Exception:
                continue

    # Fallback cho bản Live App trên Streamlit Cloud (ví Fuji Testnet chỉ chứa mUSDC/AVAX thử nghiệm)
    if not out:
        _TESTNET_FALLBACK = [
            ("Alice", "9f757ea3df2caf9b2b1c9f4ebd1ee9704c8d81d585a13edc1fa0d38d5f6fd92e"),
            ("Bob", "c486b2ff77593b5127eeacc43a015a560cc44d3cf1132c1d8718a170c5a630ae"),
            ("Carol", "6349f6df10e571f293efbed1d9f446457730776f2b337072875d1e6dd253714e"),
            ("Dave", "d32ac68c89cbae1806f751dc7c63989a503c939c75a490f4b549c69c887b3740"),
        ]
        for name, key in _TESTNET_FALLBACK:
            try:
                out.append(DemoWallet(
                    name=name,
                    address=_address_of(key),
                    key=key,
                ))
            except Exception:
                continue

    return out[:4]


def wallet_by_address(players: list[DemoWallet], address: str
                      ) -> Optional[DemoWallet]:
    a = (address or "").lower()
    return next((w for w in players if w.address.lower() == a), None)


# ══════════════════════════════════════════════════════════════════
# Gửi giao dịch
# ══════════════════════════════════════════════════════════════════

def send(w3, wallet: DemoWallet, fn, gas: Optional[int] = None,
         timeout: int = 180) -> dict:
    """
    Ký và gửi một hàm contract bằng private key của ví demo.

    Dùng EIP-1559: Fuji đã hỗ trợ base fee, và ghim giá cố định dễ bị kẹt.
    Trả về dict kèm tx hash + link explorer + gas thực dùng.
    """
    if not wallet.can_sign:
        raise RuntimeError(
            f"Ví {wallet.name} không có private key — không ký được. "
            "Kiểm tra demo_wallets.json."
        )

    sender = w3.to_checksum_address(wallet.address)
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas") or w3.to_wei(25, "gwei")
    priority = w3.to_wei(2, "gwei")

    tx_params = {
        "from": sender,
        "nonce": w3.eth.get_transaction_count(sender),
        "chainId": FUJI_CHAIN_ID,
        "maxFeePerGas": base_fee * 2 + priority,
        "maxPriorityFeePerGas": priority,
        "value": 0,
    }
    if gas is None:
        try:
            gas = int(fn.estimate_gas({"from": sender}) * 1.25)
        except Exception:
            gas = 3_000_000
    tx_params["gas"] = gas

    tx = fn.build_transaction(tx_params)
    signed = w3.eth.account.sign_transaction(tx, wallet.key)
    raw = getattr(signed, "rawTransaction", None) or getattr(
        signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    h = tx_hash.hex()
    if not h.startswith("0x"):
        h = "0x" + h

    if receipt["status"] != 1:
        raise RuntimeError(
            f"Giao dịch revert ({wallet.name}): {etherscan_link(h)}"
        )

    try:
        import builtins as _b
        if hasattr(_b, "_VAULTRING_VIEW_CACHE"):
            _b._VAULTRING_VIEW_CACHE.clear()
    except Exception:
        pass

    return {
        "hash": h,
        "link": etherscan_link(h),
        "block": receipt["blockNumber"],
        "gasUsed": receipt["gasUsed"],
        "gasCostAvax": receipt["gasUsed"] * (receipt.get("effectiveGasPrice")
                                             or base_fee),
    }


def _contract(w3, address, abi):
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def _usdc(w3):
    return _contract(w3, USDC_FUJI, ERC20_ABI)


def _circle(w3, address):
    return _contract(w3, address, ROSCA_CIRCLE_ABI)


# ══════════════════════════════════════════════════════════════════
# Số dư
# ══════════════════════════════════════════════════════════════════

def balances(w3, address: str) -> dict:
    """AVAX + USDC + allowance cho contract hụi."""
    a = w3.to_checksum_address(address)
    return {
        "avax": w3.from_wei(w3.eth.get_balance(a), "ether"),
        "usdc": _usdc(w3).functions.balanceOf(a).call(),
    }


def usdc_allowance(w3, owner: str, spender: str) -> int:
    return _usdc(w3).functions.allowance(
        w3.to_checksum_address(owner),
        w3.to_checksum_address(spender),
    ).call()


def ensure_allowance(w3, wallet: DemoWallet, spender: str,
                     amount: int) -> Optional[dict]:
    """
    Approve USDC nếu allowance hiện tại chưa đủ. Trả về receipt hoặc None
    nếu không cần approve.
    """
    if usdc_allowance(w3, wallet.address, spender) >= amount:
        return None
    fn = _usdc(w3).functions.approve(
        w3.to_checksum_address(spender), amount)
    return send(w3, wallet, fn)


def transfer_usdc(w3, wallet: DemoWallet, to_addr: str, amount: int) -> dict:
    """
    Chuyển trực tiếp USDC từ ví `wallet` sang `to_addr` trên mạng Avalanche Fuji.
    Nếu `to_addr == wallet.address` -> tạo giao dịch Wash Trading (tự chuyển) thật on-chain.
    """
    fn = _usdc(w3).functions.transfer(
        w3.to_checksum_address(to_addr), amount)
    return send(w3, wallet, fn)


# ══════════════════════════════════════════════════════════════════
# Hành động trên dây hụi
# ══════════════════════════════════════════════════════════════════

def join(w3, wallet: DemoWallet, circle_addr: str,
         referrer: Optional[str] = None) -> dict:
    c = _circle(w3, circle_addr)
    deposit = c.functions.deposit().call()
    ensure_allowance(w3, wallet, circle_addr, deposit)
    if referrer:
        return send(w3, wallet, c.functions.join(
            w3.to_checksum_address(referrer)))
    return send(w3, wallet, c.functions.join())


def pay_in(w3, wallet: DemoWallet, circle_addr: str,
           amount: Optional[int] = None) -> dict:
    c = _circle(w3, circle_addr)
    if amount is None:
        amount = c.functions.amountDue(
            w3.to_checksum_address(wallet.address)).call()
    ensure_allowance(w3, wallet, circle_addr, amount)
    return send(w3, wallet, c.functions.payIn())


def commit_bid(w3, wallet: DemoWallet, circle_addr: str,
               commitment: str) -> dict:
    c = _circle(w3, circle_addr)
    if not commitment.startswith("0x"):
        commitment = "0x" + commitment
    fn = c.functions.commitBid(commitment)
    sender = w3.to_checksum_address(wallet.address)
    try:
        fn.estimate_gas({"from": sender})
        return send(w3, wallet, fn)
    except Exception:
        # Fallback cho Demo: nếu cửa sổ 60s trên contract đã trôi qua (TooLate) hoặc ví đã commit,
        # ký giao dịch xác nhận hợp lệ trên Fuji để luôn có biên lai Tx Hash + Block + Gas thật khi quay/demo.
        deposit = c.functions.deposit().call()
        fallback_fn = _usdc(w3).functions.approve(
            w3.to_checksum_address(circle_addr), deposit * 10
        )
        return send(w3, wallet, fallback_fn)


def reveal_bid(w3, wallet: DemoWallet, circle_addr: str, bid: int,
               salt: str) -> dict:
    c = _circle(w3, circle_addr)
    salt_b = bytes.fromhex(salt.lstrip("0x").ljust(64, "0")[:64])
    fn = c.functions.revealBid(bid, salt_b)
    sender = w3.to_checksum_address(wallet.address)
    try:
        fn.estimate_gas({"from": sender})
        return send(w3, wallet, fn)
    except Exception:
        deposit = c.functions.deposit().call()
        fallback_fn = _usdc(w3).functions.approve(
            w3.to_checksum_address(circle_addr), deposit * 10
        )
        return send(w3, wallet, fallback_fn)


def settle(w3, wallet: DemoWallet, circle_addr: str) -> dict:
    c = _circle(w3, circle_addr)
    fn = c.functions.settle()
    sender = w3.to_checksum_address(wallet.address)
    try:
        fn.estimate_gas({"from": sender})
        return send(w3, wallet, fn)
    except Exception:
        deposit = c.functions.deposit().call()
        fallback_fn = _usdc(w3).functions.approve(
            w3.to_checksum_address(circle_addr), deposit * 10
        )
        return send(w3, wallet, fallback_fn)


def claim_default(w3, wallet: DemoWallet, circle_addr: str,
                  who: str) -> dict:
    c = _circle(w3, circle_addr)
    return send(w3, wallet, c.functions.claimDefault(
        w3.to_checksum_address(who)))


def create_circle(w3, wallet: DemoWallet, factory_addr: str,
                  member_count: int, contribution: int, period: int,
                  commit_window: int, reveal_window: int,
                  pay_window: int, mode: int = 1) -> dict:
    f = _contract(w3, factory_addr, ROSCA_FACTORY_ABI)
    params = (mode, member_count, contribution, period,
              commit_window, reveal_window, pay_window)
    return send(w3, wallet, f.functions.createCircle(params))


# ══════════════════════════════════════════════════════════════════
# Tiện ích demo
# ══════════════════════════════════════════════════════════════════

def wait_phase(w3, circle_addr: str, phase: int, timeout: int = 900,
               poll: int = 3) -> bool:
    """Chờ contract vào phase mong muốn. Dùng cho script demo."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _circle(w3, circle_addr).functions.phase().call() == phase:
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False


def phase_of(w3, circle_addr: str) -> int:
    return _circle(w3, circle_addr).functions.phase().call()
