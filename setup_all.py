#!/usr/bin/env python3
"""
Script tự động thiết lập từ A-Z cho người mới bắt đầu (Chưa có ví, chưa có contract):
1. Tạo 4 ví demo mới (`demo_wallets.json`) nếu chưa có.
2. Kiểm tra số dư AVAX của Người 1 (chỉ cần xin AVAX Faucet cho 1 ví duy nhất!).
3. Tự động chia AVAX từ Người 1 sang Người 2, 3, 4 để cả 4 ví đều có gas.
4. Tự động biên dịch (bằng py-solc-x, không cần cài Foundry) và deploy:
   - MockUSDC (và mint sẵn 1.000 USDC cho mỗi ví Người 1..4)
   - RoscaFactory
   - Dây hụi mẫu (RoscaCircle)
   - MockYieldAdapter (và gắn kết nối setYieldAdapter + nạp USDC dự phòng trả lãi)
5. Tự động cập nhật địa chỉ vào `app/chain.py` và `demo_config.py`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from eth_account import Account
from web3 import Web3

ROOT = Path(__file__).resolve().parent
WALLET_FILE = ROOT / "demo_wallets.json"
CHAIN_FILE = ROOT / "app" / "chain.py"
CONFIG_FILE = ROOT / "demo_config.py"
CONTRACTS_SRC = ROOT / "contracts" / "src"

FUJI_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
FUJI_CHAIN_ID = 43113


def ensure_wallets() -> list[dict]:
    if WALLET_FILE.exists():
        try:
            data = json.loads(WALLET_FILE.read_text(encoding="utf-8"))
            if len(data) >= 4 and all(item.get("private_key") for item in data[:4]):
                for i, item in enumerate(data[:4]):
                    acct = Account.from_key(item["private_key"])
                    item["address"] = acct.address
                WALLET_FILE.write_text(json.dumps(data[:4], indent=2, ensure_ascii=False), encoding="utf-8")
                return data[:4]
        except Exception:
            pass

    print("🔑 Đang khởi tạo 4 ví demo mới...")
    wallets = []
    for i in range(1, 5):
        acct = Account.create()
        wallets.append({
            "name": f"Người {i}",
            "address": acct.address,
            "private_key": "0x" + acct.key.hex().lstrip("0x"),
        })
    WALLET_FILE.write_text(json.dumps(wallets, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Đã lưu 4 ví vào {WALLET_FILE.name}")
    return wallets


def send_tx(w3: Web3, priv_key: str, tx_dict: dict, label: str = "Tx") -> dict:
    acct = Account.from_key(priv_key)
    sender = acct.address
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas") or w3.to_wei(25, "gwei")
    priority = w3.to_wei(2, "gwei")

    tx_dict["from"] = sender
    tx_dict["nonce"] = w3.eth.get_transaction_count(sender)
    tx_dict["chainId"] = FUJI_CHAIN_ID
    tx_dict["maxFeePerGas"] = base_fee * 2 + priority
    tx_dict["maxPriorityFeePerGas"] = priority
    tx_dict.setdefault("value", 0)

    if "gas" not in tx_dict:
        try:
            tx_dict["gas"] = int(w3.eth.estimate_gas(tx_dict) * 1.3)
        except Exception:
            tx_dict["gas"] = 4_000_000

    signed = w3.eth.account.sign_transaction(tx_dict, priv_key)
    raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt["status"] != 1:
        raise RuntimeError(f"{label} bị revert! Hash: {tx_hash.hex()}")
    return receipt


def distribute_avax(w3: Web3, wallets: list[dict]):
    p1 = wallets[0]
    bal1_wei = w3.eth.get_balance(p1["address"])
    bal1_avax = float(w3.from_wei(bal1_wei, "ether"))

    print("\n" + "=" * 65)
    print("KIỂM TRA SỐ DƯ AVAX TESTNET (PHÍ GAS)")
    print("=" * 65)
    for w in wallets:
        b = float(w3.from_wei(w3.eth.get_balance(w["address"]), "ether"))
        print(f"  {w['name']:10} ({w['address']}): {b:.4f} AVAX")

    if bal1_avax < 0.15:
        print("\n⚠️  Ví Người 1 chưa có đủ AVAX testnet để deploy và chia gas.")
        print("👉 BẠN CHỈ CẦN XIN AVAX CHO ĐÚNG 1 ĐỊA CHỈ NÀY:")
        print(f"\n    {p1['address']}\n")
        print("Cách lấy AVAX miễn phí (chọn 1 trong 2 link):")
        print("  1. https://core.app/tools/testnet-faucet/?subnet=c&token=c (Nhập mã coupon nếu có hoặc kết nối ví)")
        print("  2. https://faucet.quicknode.com/avalanche/fuji")
        print("\nSau khi nhận được AVAX vào ví Người 1, hãy chạy lại lệnh:")
        print("    python setup_all.py")
        sys.exit(0)

    # Chia AVAX cho Người 2, 3, 4 nếu các ví đó có dưới 0.03 AVAX
    target_avax = w3.to_wei("0.05", "ether")
    for w in wallets[1:]:
        b_wei = w3.eth.get_balance(w["address"])
        if b_wei < w3.to_wei("0.03", "ether"):
            send_amt = target_avax - b_wei
            print(f"💸 Đang chuyển {w3.from_wei(send_amt, 'ether'):.4f} AVAX từ Người 1 -> {w['name']}...")
            send_tx(
                w3,
                p1["private_key"],
                {"to": w["address"], "value": send_amt, "gas": 21000},
                label=f"Chuyển AVAX cho {w['name']}",
            )
            print(f"  ✓ Đã chuyển xong cho {w['name']}")


def compile_contracts() -> dict:
    print("\n📦 Đang cài đặt trình biên dịch Solidity 0.8.24 (py-solc-x)...")
    import solcx
    solcx.install_solc("0.8.24")

    sources = {}
    for name in ["MockUSDC.sol", "RoscaCircle.sol", "RoscaFactory.sol", "MockYieldAdapter.sol"]:
        path = CONTRACTS_SRC / name
        sources[name] = {"content": path.read_text(encoding="utf-8")}

    print("🔨 Đang biên dịch các Smart Contract...")
    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": sources,
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode.object"]}
                },
            },
        },
        solc_version="0.8.24",
    )

    out = {}
    for file_name, contracts_dict in compiled["contracts"].items():
        for contract_name, data in contracts_dict.items():
            if contract_name in ("MockUSDC", "RoscaFactory", "RoscaCircle", "MockYieldAdapter"):
                out[contract_name] = {
                    "abi": data["abi"],
                    "bytecode": "0x" + data["evm"]["bytecode"]["object"],
                }
    print("✓ Biên dịch thành công: MockUSDC, RoscaFactory, RoscaCircle, MockYieldAdapter")
    return out


def deploy_contract(w3: Web3, priv_key: str, artifact: dict, *args, label: str) -> str:
    contract = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx = contract.constructor(*args).build_transaction({"from": Account.from_key(priv_key).address})
    receipt = send_tx(w3, priv_key, tx, label=label)
    addr = receipt["contractAddress"]
    print(f"  ✓ {label}: {addr}")
    return addr


def update_files(usdc_addr: str, factory_addr: str, circle_addr: str, adapter_addr: str):
    # 1. Cập nhật USDC_FUJI trong app/chain.py
    chain_text = CHAIN_FILE.read_text(encoding="utf-8")
    chain_text = re.sub(
        r'USDC_FUJI\s*=\s*"0x[0-9a-fA-F]{40}"',
        f'USDC_FUJI = "{usdc_addr}"',
        chain_text,
    )
    CHAIN_FILE.write_text(chain_text, encoding="utf-8")

    # 2. Cập nhật demo_config.py
    cfg_text = CONFIG_FILE.read_text(encoding="utf-8")
    cfg_text = re.sub(
        r'DEMO_FACTORY\s*=\s*.*',
        f'DEMO_FACTORY = "{factory_addr}"',
        cfg_text,
    )
    cfg_text = re.sub(
        r'DEMO_CIRCLE\s*=\s*.*',
        f'DEMO_CIRCLE = "{circle_addr}"',
        cfg_text,
    )
    cfg_text = re.sub(
        r'DEMO_ADAPTER\s*=\s*.*',
        f'DEMO_ADAPTER = "{adapter_addr}"',
        cfg_text,
    )
    CONFIG_FILE.write_text(cfg_text, encoding="utf-8")


def main():
    print("🚀 BẮT ĐẦU THIẾT LẬP TỰ ĐỘNG VAULTRING (HỤI ON-CHAIN)")
    wallets = ensure_wallets()

    w3 = Web3(Web3.HTTPProvider(FUJI_RPC))
    try:
        blk = w3.eth.get_block_number()
        print(f"✓ Đã kết nối Avalanche Fuji Testnet (Block #{blk})")
    except Exception as e:
        print(f"✗ Không kết nối được Fuji RPC: {e}")
        sys.exit(1)

    distribute_avax(w3, wallets)
    artifacts = compile_contracts()

    p1 = wallets[0]
    pk1 = p1["private_key"]

    print("\n" + "=" * 65)
    print("TRIỂN KHAI SMART CONTRACTS LÊN AVALANCHE FUJI")
    print("=" * 65)

    # 1. Deploy MockUSDC
    usdc_addr = deploy_contract(w3, pk1, artifacts["MockUSDC"], label="Deploy MockUSDC")
    usdc = w3.eth.contract(address=usdc_addr, abi=artifacts["MockUSDC"]["abi"])

    # Mint 1,000 USDC cho mỗi ví
    mint_amount = 1_000 * 10**6
    for w in wallets:
        tx = usdc.functions.mint(w["address"], mint_amount).build_transaction({"from": p1["address"]})
        send_tx(w3, pk1, tx, label=f"Mint 1,000 USDC cho {w['name']}")
        print(f"  ✓ Đã cấp 1,000.00 USDC cho {w['name']} ({w['address'][:10]}...)")

    # 2. Deploy RoscaFactory
    factory_addr = deploy_contract(
        w3, pk1, artifacts["RoscaFactory"],
        usdc_addr, p1["address"], 50,
        label="Deploy RoscaFactory",
    )
    factory = w3.eth.contract(address=factory_addr, abi=artifacts["RoscaFactory"]["abi"])

    # 3. Tạo sẵn 1 Dây Hụi Mẫu (4 người, Đấu giá kín, góp 10 USDC, kỳ 30 ngày, commit 60s, reveal 60s, pay 600s)
    params = (1, 4, 10_000_000, 30 * 86400, 60, 60, 600)
    tx_create = factory.functions.createCircle(params).build_transaction({"from": p1["address"]})
    rcpt_create = send_tx(w3, pk1, tx_create, label="Tạo Dây Hụi Mẫu (RoscaCircle)")
    logs = factory.events.CircleCreated().process_receipt(rcpt_create)
    circle_addr = logs[0]["args"]["circle"]
    print(f"  ✓ Dây Hụi Mẫu (RoscaCircle): {circle_addr}")

    # 4. Deploy MockYieldAdapter cho Dây Hụi Mẫu & cấu hình setYieldAdapter
    adapter_addr = deploy_contract(
        w3, pk1, artifacts["MockYieldAdapter"],
        usdc_addr, circle_addr,
        label="Deploy MockYieldAdapter",
    )
    # Mint 100 USDC dự phòng vào MockYieldAdapter để trả lãi 0.5% khi rút
    tx_mint_adapter = usdc.functions.mint(adapter_addr, 100 * 10**6).build_transaction({"from": p1["address"]})
    send_tx(w3, pk1, tx_mint_adapter, label="Cấp quỹ lãi cho MockYieldAdapter")

    circle = w3.eth.contract(address=circle_addr, abi=artifacts["RoscaCircle"]["abi"])
    tx_set_adapter = circle.functions.setYieldAdapter(adapter_addr).build_transaction({"from": p1["address"]})
    send_tx(w3, pk1, tx_set_adapter, label="Liên kết YieldAdapter vào RoscaCircle")
    print("  ✓ Đã liên kết MockYieldAdapter vào Dây Hụi Mẫu")

    # 5. Cho cả 4 người tham gia (Join) sẵn vào Dây Hụi Mẫu để vào thẳng Pha Đấu Giá Kín!
    print("\n🤝 Đang cho 4 ví tham gia vào Dây Hụi Mẫu (Người 2 được Người 1 giới thiệu)...")
    deposit_amt = circle.functions.deposit().call()
    for idx, w in enumerate(wallets):
        w_pk = w["private_key"]
        w_addr = w["address"]
        tx_app = usdc.functions.approve(circle_addr, deposit_amt * 10).build_transaction({"from": w_addr})
        send_tx(w3, w_pk, tx_app, label=f"Approve USDC ({w['name']})")

        if idx == 1:
            # Người 2 dùng mã giới thiệu của Người 1 để tab Giới Thiệu có số liệu on-chain đẹp!
            tx_join = circle.functions.join(p1["address"]).build_transaction({"from": w_addr})
        else:
            tx_join = circle.functions.join().build_transaction({"from": w_addr})
        send_tx(w3, w_pk, tx_join, label=f"Join dây hụi ({w['name']})")
        print(f"  ✓ {w['name']} đã tham gia & đóng ký quỹ 10 USDC")

    update_files(usdc_addr, factory_addr, circle_addr, adapter_addr)

    print("\n" + "=" * 65)
    print("🎉 HOÀN TẤT 100%! HỆ THỐNG ĐÃ SẴN SÀNG ĐỂ TEST & QUAY VIDEO")
    print("=" * 65)
    print(f"• MockUSDC:          {usdc_addr}")
    print(f"• RoscaFactory:      {factory_addr}")
    print(f"• Dây Hụi Mẫu:       {circle_addr} (Đã có 4 người join, đang ở pha Đấu giá kín!)")
    print(f"• MockYieldAdapter:  {adapter_addr}")
    print("\n👉 Bây giờ bạn chỉ cần chạy lệnh sau để mở giao diện:")
    print(f'   $env:HUI_FACTORY="{factory_addr}"')
    print("   streamlit run app/main.py")


if __name__ == "__main__":
    main()
