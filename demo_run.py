#!/usr/bin/env python3
"""
Demo script: chạy trọn một dây hụi 4 người trên Fuji testnet.

Cách chạy:
    python3 demo_run.py [--factory ADDRESS] [--circle ADDRESS] [--fast]

Hoặc để tạo dây mới:
    python3 demo_run.py --create

Lưu ý:
  - Cần 4 ví demo trong demo_wallets.json với private key và USDC
  - Cần tối thiểu ~50 USDC trên Fuji (=40 deposit + 10 góp kỳ 1)
  - Khoảng thời gian: phụ thuộc vào windows (mặc định = 300/300/600s)
  - Thích hợp quay video demo
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time

from web3 import Web3

from app.chain import FUJI_RPC, fmt_usdc, read_circle, read_members
from app.wallet import (
    load_players, join, pay_in, commit_bid, reveal_bid,
    settle, phase_of, balances, create_circle
)
from app.contract_abi import ROSCA_FACTORY_ABI
from demo_config import (
    DEMO_FACTORY, DEMO_CIRCLE, DEMO_MODE, DEMO_CONTRIBUTION,
    DEMO_PERIOD, DEMO_COMMIT_WINDOW, DEMO_REVEAL_WINDOW,
    DEMO_PAY_WINDOW,
)


def connect():
    """Kết nối Fuji."""
    return Web3(Web3.HTTPProvider(FUJI_RPC))


def show_balances(w3, players):
    print("\n" + "=" * 70)
    print("SỐ DƯ HIỆN TẠI")
    print("=" * 70)
    for p in players:
        bal = balances(w3, p.address)
        usdc_decimal = bal['usdc'] / 10**6
        print(f"{p.name:15} {bal['avax']:>10.4f} AVAX  {usdc_decimal:>15,.2f} USDC")


def create_circle_demo(w3, players, factory_addr):
    """Tạo dây mới."""
    print("\n" + "=" * 70)
    print("TẠO DÂY HỤI MỚI")
    print("=" * 70)
    print(f"Mode: {DEMO_MODE} (Bidding=1)")
    print(f"Contribution: {fmt_usdc(DEMO_CONTRIBUTION)} USDC/period")
    print(f"Period: {DEMO_PERIOD} seconds")
    print(f"Windows: commit {DEMO_COMMIT_WINDOW}s, reveal {DEMO_REVEAL_WINDOW}s, "
          f"pay {DEMO_PAY_WINDOW}s")

    factory = w3.eth.contract(
        address=w3.to_checksum_address(factory_addr),
        abi=ROSCA_FACTORY_ABI
    )

    organizer = players[0]
    print(f"\nOrganizer: {organizer.name}")

    try:
        res = create_circle(
            w3, organizer, factory_addr,
            member_count=4,
            contribution=DEMO_CONTRIBUTION,
            period=DEMO_PERIOD,
            commit_window=DEMO_COMMIT_WINDOW,
            reveal_window=DEMO_REVEAL_WINDOW,
            pay_window=DEMO_PAY_WINDOW,
            mode=DEMO_MODE,
        )
        print(f"✓ Dây tạo thành công")
        print(f"  Tx: {res['link']}")
        gas_cost_avax = w3.from_wei(res['gasCostAvax'], 'ether')
        print(f"  Gas: {res['gasUsed']} ({gas_cost_avax:.6f} AVAX)")

        # Tìm address dây mới từ event
        time.sleep(5)
        try:
            logs = factory.events.CircleCreated.create_filter(
                fromBlock=res["block"] - 1, toBlock="latest").get_all_entries()
            if logs:
                circle = logs[0]["args"]["circle"]
                print(f"\n🎯 Dây mới: {circle}")
                return circle
        except Exception as e:
            print(f"Lỗi tìm dây: {e}")
    except Exception as e:
        print(f"✗ Lỗi tạo dây: {e}")
    return None


def _hash_bid(bid: int, salt: str, address: str, round_idx: int) -> str:
    """
    Cam kết giá kêu. Phải khớp CHÍNH XÁC với Solidity:
        keccak256(abi.encode(bid, salt, msg.sender, currentRound))
    """
    from eth_abi import encode
    from eth_utils import keccak
    payload = encode(
        ["uint256", "bytes32", "address", "uint16"],
        [
            bid,
            bytes.fromhex(salt.lstrip("0x").ljust(64, "0")[:64]),
            address,
            round_idx,
        ],
    )
    return "0x" + keccak(payload).hex()


def run_round(w3, circle_addr, players, round_num, fast=False):
    """Chạy một vòng: join/pay → commit → reveal → settle → payout."""
    print("\n" + "=" * 70)
    print(f"VÒNG {round_num}")
    print("=" * 70)

    c = read_circle(w3, circle_addr)
    members = read_members(w3, circle_addr)

    if round_num == 1 and c.current_round == 0:
        print("🔗 Bước 1: 4 người tham gia + đóng ticket")
        for p in players:
            try:
                res = join(w3, p, circle_addr)
                print(f"  ✓ {p.name} join: gas {res['gasUsed']}")
            except Exception as e:
                print(f"  ✗ {p.name} join lỗi: {e}")
                return False

        time.sleep(3)
        members = read_members(w3, circle_addr)
    else:
        print("💳 Bước 1: Đóng tiền")
        for p in players:
            m = next((m for m in members if m.address.lower() == p.address.lower()), None)
            if m and m.amount_due > 0:
                try:
                    res = pay_in(w3, p, circle_addr)
                    print(f"  ✓ {p.name} pay {fmt_usdc(m.amount_due)}: gas {res['gasUsed']}")
                except Exception as e:
                    print(f"  ✗ {p.name} pay lỗi: {e}")

    phase = phase_of(w3, circle_addr)
    print(f"Phase: {phase} (0=Open, 1=Bidding, 2=Paying, 3=Closed)")

    if c.mode == 0:
        print("→ Chế độ Cố định, không có đấu giá. Đã chốt vòng tự động khi join.")
        return True

    print("🎯 Bước 2: Cam kết giá")
    commitments = {}
    for p in players:
        # Mỗi người kêu giá khác nhau (0, 0.1×, 0.2×, 0.3× của max_bid)
        bid = int(c.max_bid * (players.index(p) / 10))
        salt = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        h = _hash_bid(bid, salt, p.address, c.current_round)
        commitments[p.name] = (bid, salt)

        try:
            res = commit_bid(w3, p, circle_addr, h)
            print(f"  ✓ {p.name} commit (bid {fmt_usdc(bid)}): gas {res['gasUsed']}")
        except Exception as e:
            print(f"  ✗ {p.name} commit lỗi: {e}")

    print(f"⏳ Chờ hết commit window ({DEMO_COMMIT_WINDOW}s)…")
    _sleep_with_progress(DEMO_COMMIT_WINDOW, fast)

    print("📖 Bước 3: Mở giá")
    for p in players:
        if p.name in commitments:
            bid, salt = commitments[p.name]
            try:
                res = reveal_bid(w3, p, circle_addr, bid, salt)
                print(f"  ✓ {p.name} reveal: gas {res['gasUsed']}")
            except Exception as e:
                print(f"  ✗ {p.name} reveal lỗi: {e}")

    print(f"⏳ Chờ hết reveal window ({DEMO_REVEAL_WINDOW}s)…")
    _sleep_with_progress(DEMO_REVEAL_WINDOW, fast)

    print("✅ Bước 4: Chốt vòng")
    try:
        res = settle(w3, players[0], circle_addr)
        print(f"  ✓ Settle: gas {res['gasUsed']}")
    except Exception as e:
        print(f"  ✗ Settle lỗi: {e}")
        return False

    time.sleep(3)
    c = read_circle(w3, circle_addr)
    print(f"Vòng tiếp: {c.current_round + 1}")
    return True


def _sleep_with_progress(seconds, fast=False):
    """Sleep với countdown, tránh giả sử window chia hết cho 10."""
    if fast:
        print("   (fast mode: bỏ qua chờ)")
        return
    remaining = seconds
    while remaining > 0:
        chunk = min(10, remaining)
        if remaining <= 10:
            print(f"   {remaining}s")
        time.sleep(chunk)
        remaining -= chunk


def main():
    parser = argparse.ArgumentParser(description="Demo 4-player Hui On-Chain")
    parser.add_argument("--create", action="store_true", help="Tạo dây mới")
    parser.add_argument("--factory", default=DEMO_FACTORY, help="Factory address")
    parser.add_argument("--circle", default=DEMO_CIRCLE, help="Circle address")
    parser.add_argument("--fast", action="store_true", help="Bỏ qua sleep dài")
    args = parser.parse_args()

    print("🔗 Kết nối Fuji…")
    w3 = connect()
    try:
        _ = w3.eth.get_block_number()
        print(f"✓ Kết nối Fuji thành công. Block hiện tại: {_}")
    except Exception as e:
        print(f"✗ Lỗi kết nối: {e}")
        return 1

    print("🎭 Nạp 4 ví demo…")
    players = load_players()
    if not players:
        print("✗ Không tìm thấy ví demo. Kiểm tra demo_wallets.json hoặc env HUI_PK_1..4")
        return 1
    print(f"✓ Nạp {len(players)} ví:")
    for p in players:
        print(f"  - {p.name}: {p.address}")

    show_balances(w3, players)

    circle_addr = args.circle
    if args.create:
        circle_addr = create_circle_demo(w3, players, args.factory)
        if not circle_addr:
            return 1
    elif not circle_addr or circle_addr == "0x" + "0" * 40:
        print("✗ Chưa có địa chỉ dây. Dùng --circle ADDRESS hoặc --create.")
        return 1

    print(f"\n🎯 Dây hụi: {circle_addr}")

    try:
        c = read_circle(w3, circle_addr)
        print(f"Mode: {c.mode_name}, Phase: {c.phase_name}, "
              f"Vòng: {c.current_round + 1}/{c.member_count}")
    except Exception as e:
        print(f"✗ Lỗi đọc dây: {e}")
        return 1

    print("\n" + "=" * 70)
    print("CHẠY 4 VÒNG DEMO")
    print("=" * 70)

    for rnd in range(1, 5):
        if not run_round(w3, circle_addr, players, rnd, args.fast):
            print(f"✗ Vòng {rnd} lỗi, dừng.")
            return 1

    print("\n" + "=" * 70)
    print("✅ HOÀN THÀNH 4 VÒNG!")
    print("=" * 70)
    show_balances(w3, players)

    print("\n🎬 Dây đã đóng. Sẵn sàng quay video demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
