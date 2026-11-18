"""
Hụi On-Chain — giao diện Streamlit.

Chạy:
    streamlit run app/main.py

Thiết kế: mọi phép tính và truy vấn nằm trong app/chain.py và
ai/credit_score.py. File này chỉ dựng giao diện. Nhờ vậy phần logic
test được mà không cần Streamlit.
"""
from __future__ import annotations

import hashlib
import os
import time

import streamlit as st

from app.chain import (
    FUJI_CHAIN_ID, FUJI_RPC, FUJI_EXPLORER, MODE_NAMES, PHASE_NAMES,
    USDC_FUJI, fmt_usdc, read_circle, read_history, read_members, read_rounds,
    etherscan_link
)
from app.wallet import (
    load_players, balances, create_circle, join, pay_in,
    commit_bid, reveal_bid, settle
)
from app.yield_backend import supply_to_aave, withdraw_and_report, get_ausdc_balance
from app.contract_abi import ROSCA_CIRCLE_ABI
from ai.credit_score import History, score
from app.agent_bridge import build_agent_context
from ai import agent as _agent
from ai.tools import defi_pools, bid_advice

st.set_page_config(page_title="Hụi On-Chain", page_icon="🪙", layout="wide")

CURRENT_PLAYER_KEY = "current_player"
CIRCLE_ADDRESS_KEY = "circle_address"


def _w3():
    """Kết nối Web3. Trả None nếu chưa cài web3."""
    try:
        from web3 import Web3
    except ImportError:
        return None
    return Web3(Web3.HTTPProvider(FUJI_RPC))


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


def _players():
    """Nạp 4 ví demo, cache trong session để không đọc file mỗi rerun."""
    if "_players" not in st.session_state:
        st.session_state["_players"] = load_players()
    return st.session_state["_players"]


def setup_panel():
    """Hướng dẫn khi chưa có ví."""
    st.title("🪙 Hụi On-Chain — Thiết lập ví")
    st.error("Chưa tìm thấy ví demo.")
    st.markdown(
        """
    Tạo file `demo_wallets.json` ở thư mục gốc dự án:

    ```json
    [
      {"name": "Người 1", "private_key": "0x..."},
      {"name": "Người 2", "private_key": "0x..."},
      {"name": "Người 3", "private_key": "0x..."},
      {"name": "Người 4", "private_key": "0x..."}
    ]
    ```

    Hoặc đặt biến môi trường `HUI_PK_1` … `HUI_PK_4`.

    **Lấy AVAX testnet**: https://faucet.avax.network/

    **Lấy USDC testnet**: dùng faucet của Circle, hoặc nhờ người deploy
    MockUSDC mint cho.
    """
    )
    st.warning(
        "`demo_wallets.json` chứa private key. Đây là ví TESTNET, "
        "không dùng cho tiền thật. File này không được commit."
    )


def login_screen():
    """
    Màn hình đăng nhập: chọn một trong 4 người chơi.
    Trả về địa chỉ ví được chọn, hoặc None nếu chưa chọn.
    """
    players = _players()
    if not players:
        setup_panel()
        return

    st.title("🪙 Hụi On-Chain — Chọn người chơi")
    st.markdown(
        """
    Hụi On-Chain là quỹ tiết kiệm chung trên **Avalanche Fuji Testnet**.
    Quỹ nằm trong contract, mọi dòng tiền công khai, không ai can thiệp được.
    """
    )

    w3 = _w3()
    if w3 is None:
        st.error("Chưa cài `web3`. Chạy: `pip install web3 eth-abi eth-utils`.")
        return

    st.divider()
    cols = st.columns(len(players))
    for i, player in enumerate(players):
        with cols[i]:
            bal = None
            try:
                bal = balances(w3, player.address)
            except Exception:
                pass
            st.markdown(f"**{player.name}**")
            st.caption(f"`{player.address[:8]}…{player.address[-6:]}`")
            if bal is not None:
                st.caption(
                    f"{bal['avax']:.4f} AVAX · "
                    f"{bal['usdc'] / 10**6:,.2f} USDC"
                )
            if st.button("Đăng nhập", key=f"login_{i}",
                         use_container_width=True, type="primary"):
                st.session_state[CURRENT_PLAYER_KEY] = player.address
                st.rerun()

    st.divider()
    st.info(
        "**Lưu ý**: Đây là bản demo trên Fuji testnet. "
        "Các ví được cấp USDC từ faucet; giao dịch không mất tiền thật."
    )


def logout_button():
    """Nút logout ở góc trên phải."""
    col1, col2 = st.columns([0.88, 0.12])
    with col2:
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state[CURRENT_PLAYER_KEY] = None
            st.session_state.pop("_players", None)
            st.rerun()


def _wallet(me: str):
    """Ví demo ứng với địa chỉ đang đăng nhập."""
    players = _players()
    return next(
        (p for p in players if p.address.lower() == (me or "").lower()), None
    )


def show_tx(res: dict, label: str = "Giao dịch thành công"):
    """
    Ghi nhận giao dịch vừa xong để hiển thị sau khi rerun.

    Không render trực tiếp: các nút gọi `show_tx()` rồi `st.rerun()`, mà
    rerun sẽ xoá sạch bản render hiện tại — receipt sẽ biến mất trước khi
    người dùng kịp thấy.
    """
    st.session_state["_pending_tx"] = {"res": res, "label": label}


def flush_tx():
    """Hiển thị receipt của giao dịch vừa xong (nếu có), rồi xoá."""
    item = st.session_state.pop("_pending_tx", None)
    if not item:
        return
    res, label = item["res"], item["label"]
    st.success(label)
    st.markdown(f"[Xem trên explorer]({res['link']})")
    c1, c2, c3 = st.columns(3)
    c1.metric("Block", f"{res['block']:,}")
    c2.metric("Gas dùng", f"{res['gasUsed']:,}")
    c3.metric("Phí", f"{res['gasCostAvax'] / 1e18:.6f} AVAX")
    st.caption(f"`{res['hash']}`")


def sidebar_circle_input():
    """Nhập địa chỉ dây hụi ở thanh bên."""
    st.sidebar.title("Hụi On-Chain")
    st.sidebar.caption("ROSCA trên Avalanche Fuji")
    st.sidebar.markdown(f"**Chain ID**: {FUJI_CHAIN_ID}")
    st.sidebar.markdown(f"**RPC**: `{FUJI_RPC[:30]}…`")
    st.sidebar.markdown(f"**USDC**: `{USDC_FUJI[:8]}…{USDC_FUJI[-6:]}`")
    st.sidebar.markdown(f"**Explorer**: {FUJI_EXPLORER}")
    st.sidebar.divider()

    addr = st.sidebar.text_input(
        "Địa chỉ dây hụi",
        key=CIRCLE_ADDRESS_KEY,
        placeholder="0x...",
        help="Sao chép từ tab 'Tạo dây' sau khi khởi tạo",
    )

    # Số dư ví đang đăng nhập
    me = st.session_state.get(CURRENT_PLAYER_KEY)
    w = _wallet(me) if me else None
    if w is not None:
        st.sidebar.divider()
        st.sidebar.markdown(f"**Ví**: {w.name}")
        st.sidebar.caption(f"`{w.address[:8]}…{w.address[-6:]}`")
        try:
            w3 = _w3()
            if w3 is not None:
                bal = balances(w3, w.address)
                st.sidebar.metric("AVAX", f"{bal['avax']:.4f}")
                st.sidebar.metric("USDC", f"{bal['usdc'] / 10**6:,.2f}")
        except Exception:
            st.sidebar.caption("Không đọc được số dư.")

    st.sidebar.divider()
    st.sidebar.caption(
        "**Mạng Avalanche Fuji**\n\n"
        "- Faucet AVAX: https://faucet.avax.network/\n"
        "- Explorer: https://subnets-test.avax.network/c-chain\n\n"
        "Mọi giao dịch đều cần bạn ký trong ví — "
        "contract không tự chuyển tiền thay bạn."
    )
    return addr


def tab_overview(w3, addr, me: str):
    st.subheader("Tổng quan dây hụi")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")

    if not addr:
        st.info("Nhập địa chỉ dây hụi ở thanh bên để bắt đầu.")
        return
    if w3 is None:
        st.warning("Chưa cài `web3`. Chạy: `pip install web3 eth-abi eth-utils`.")
        return

    try:
        c = read_circle(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(f"Không đọc được contract: {e}")
        return

    col = st.columns(5)
    col[0].metric("Chế độ", c.mode_name)
    col[1].metric("Trạng thái", c.phase_name)
    col[2].metric("Vòng", f"{c.current_round + 1}/{c.member_count}")
    col[3].metric("Góp mỗi kỳ", fmt_usdc(c.contribution))
    col[4].metric("Ký quỹ", fmt_usdc(c.deposit))

    col2 = st.columns(4)
    col2[0].metric("Trong contract", fmt_usdc(c.total_pool))
    col2[1].metric("Ký quỹ đang giữ", fmt_usdc(c.deposits_held))
    col2[2].metric("Quỹ phạt", fmt_usdc(c.penalty_pool))
    col2[3].metric("Thiếu hụt (cáo)", fmt_usdc(c.shortfall))

    if c.shortfall > 0:
        st.error(
            f"Đã có {fmt_usdc(c.shortfall)} USDC thiếu hụt do có người cáo. "
            "Khoản này được ghi công khai, không giấu."
        )

    st.divider()
    st.markdown("#### Thành viên")
    rows = []
    for m in members:
        rows.append(
            {
                "#": m.index + 1,
                "Ví": f"{m.address[:6]}…{m.address[-4:]}",
                "Trạng thái": m.status,
                "Đã đóng": fmt_usdc(m.paid_total),
                "Đã nhận": fmt_usdc(m.received_total),
                "Lãi/lỗ": fmt_usdc(m.net),
                "Ký quỹ còn": fmt_usdc(m.deposit_left),
                "Trễ": m.late_count,
                "Kỳ này phải đóng": fmt_usdc(m.amount_due),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Avalanche specifics
    st.divider()
    st.markdown("#### 🏔️ Avalanche Fuji")
    st.caption(
        f"Chain ID {FUJI_CHAIN_ID} • ~2 giây finality • "
        f"Gas ghi khoảng 0.002 AVAX/txn trên testnet"
    )


def tab_create_circle(w3, addr, me: str):
    st.subheader("Tạo dây hụi mới")
    st.caption(
        "Khởi tạo một dây mới với 4 người chơi. "
        "Lưu địa chỉ contract để chia cho các thành viên khác."
    )

    if w3 is None:
        st.warning("Chưa cài `web3`. Chạy: `pip install web3 eth-abi eth-utils`.")
        return

    wallet = _wallet(me)
    if wallet is None:
        st.error(
            "Ví đang đăng nhập không nằm trong danh sách demo — "
            "không ký được giao dịch."
        )
        return
    if not wallet.can_sign:
        st.error(
            f"Ví {wallet.name} không có private key, không ký được. "
            "Kiểm tra `demo_wallets.json`."
        )
        return

    st.markdown("#### Cấu hình")

    mode = st.radio("Chế độ", ["Cố định (chia theo thứ tự)", "Đấu giá kín"], index=1)
    mode_val = 1 if "Đấu giá" in mode else 0

    col1, col2 = st.columns(2)
    with col1:
        contribution = st.number_input(
            "Góp mỗi kỳ (USDC)", min_value=1.0, value=10.0, step=1.0
        )
        commitment_window_sec = st.number_input(
            "Thời gian cam kết (giây)", min_value=60, value=300, step=60
        )
    with col2:
        period_days = st.number_input(
            "Chu kỳ (ngày)", min_value=1, value=30, step=1
        )
        reveal_window_sec = st.number_input(
            "Thời gian mở giá (giây)", min_value=60, value=300, step=60
        )

    pay_window_sec = st.number_input(
        "Thời gian đóng tiền (giây)", min_value=60, value=600, step=60
    )

    # ── Kiểm tra giới hạn pháp lý (NĐ 19/2019, Điều 14) ────────────
    MEMBER_COUNT = 4                       # dây demo cố định 4 người
    MAX_POOL_USDC = 3_500.0                # trần trên contract
    VND_PER_USDC = 25_000                  # tỷ giá tham chiếu
    LEGAL_LIMIT_VND = 100_000_000          # 100 triệu VND

    total_pool = MEMBER_COUNT * contribution
    total_pool_vnd = total_pool * VND_PER_USDC
    exceeds = total_pool > MAX_POOL_USDC

    st.markdown("---")
    st.markdown("#### Tóm tắt")
    st.info(
        f"**Chế độ**: {mode}\n\n"
        f"**Góp mỗi kỳ**: {contribution:.2f} USDC\n\n"
        f"**Chu kỳ**: {period_days} ngày\n\n"
        f"**Máy chủ**: Bidding window {commitment_window_sec}s → "
        f"Reveal window {reveal_window_sec}s → Pay window {pay_window_sec}s\n\n"
        f"**{MEMBER_COUNT} người chơi sẽ xoay vòng nhận hụi trong {period_days} ngày × {MEMBER_COUNT}."
    )

    # Hiển thị giá trị dây + kiểm tra ngưỡng
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Giá trị dây (pot mỗi vòng)", f"{total_pool:,.2f} USDC")
    col_b.metric("Quy ra VND", f"{total_pool_vnd:,.0f} ₫")
    col_c.metric(
        "Ngưỡng khai báo",
        f"{LEGAL_LIMIT_VND:,} ₫",
        help="Dây hụi ≥ 100 triệu VND phải thông báo UBND xã "
             "(NĐ 19/2019, Điều 14)"
    )

    if exceeds:
        st.error(
            f"⛔ **Dây hụi quá lớn**\n\n"
            f"Tổng giá trị dây **{total_pool:,.2f} USDC** vượt trần "
            f"**{MAX_POOL_USDC:,.0f} USDC** (≈ 100 triệu VND).\n\n"
            f"Contract sẽ revert với lỗi `ExceedsLegalLimit()`. "
            f"Giảm góp mỗi kỳ xuống tối đa "
            f"**{MAX_POOL_USDC / MEMBER_COUNT:,.2f} USDC/người** để không phải khai báo."
        )
    else:
        margin_vnd = LEGAL_LIMIT_VND - total_pool_vnd
        st.success(
            f"✓ Dây **{total_pool:,.2f} USDC** ≈ **{total_pool_vnd:,.0f} ₫** "
            f"— dưới ngưỡng 100 triệu VND. "
            f"Không cần khai báo UBND (còn dư {margin_vnd:,.0f} ₫)."
        )

    factory_addr = st.text_input(
        "Địa chỉ Factory",
        value=os.environ.get("HUI_FACTORY", ""),
        placeholder="0x... (địa chỉ RoscaFactory đã deploy trên Fuji)",
    )

    if st.button("📝 Dựng contract", type="primary",
                 use_container_width=True, disabled=exceeds):
        if not factory_addr:
            st.error("Nhập địa chỉ Factory trước.")
            return
        try:
            w3.to_checksum_address(factory_addr)
        except Exception:
            st.error("Địa chỉ Factory không hợp lệ.")
            return

        with st.spinner("Đang ký và gửi giao dịch…"):
            try:
                res = create_circle(
                    w3, wallet, factory_addr,
                    member_count=4,
                    contribution=int(contribution * 1e6),
                    period=int(period_days * 86400),
                    commit_window=int(commitment_window_sec),
                    reveal_window=int(reveal_window_sec),
                    pay_window=int(pay_window_sec),
                    mode=mode_val,
                )
            except Exception as e:
                st.error(f"Tạo dây thất bại: {e}")
                return

        show_tx(res, "Dây đã tạo trên chain")

        # Lấy địa chỉ từ event CircleCreated
        circle_addr = None
        try:
            from app.contract_abi import ROSCA_FACTORY_ABI
            factory = w3.eth.contract(
                address=w3.to_checksum_address(factory_addr),
                abi=ROSCA_FACTORY_ABI,
            )
            logs = factory.events.CircleCreated.create_filter(
                fromBlock=res["block"] - 1, toBlock="latest"
            ).get_all_entries()
            if logs:
                circle_addr = logs[0]["args"]["circle"]
        except Exception as e:
            st.warning(f"Không đọc được địa chỉ từ event: {e}")

        if circle_addr:
            st.session_state[CIRCLE_ADDRESS_KEY] = circle_addr
            st.success(f"Địa chỉ dây mới: `{circle_addr}`")
            st.caption("Đã điền sẵn vào thanh bên — chuyển sang tab «Đóng hụi».")
        else:
            st.info(
                "Giao dịch thành công nhưng không lấy được địa chỉ từ event. "
                "Xem log trên explorer, hoặc đọc `factory.circles(n)::call()`."
            )


def tab_pay(w3, addr, me: str):
    st.subheader("Đóng hụi kỳ này")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")

    if not (w3 and addr):
        st.info("Nhập địa chỉ dây hụi ở thanh bên để bắt đầu.")
        return

    wallet = _wallet(me)
    if wallet is None or not wallet.can_sign:
        st.error("Ví đang đăng nhập không ký được giao dịch.")
        return

    try:
        c = read_circle(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(f"Không đọc được contract: {e}")
        return

    mv = next((m for m in members if m.address.lower() == me.lower()), None)

    # ── Chưa tham gia: hiện nút join ─────────────────────────────
    if mv is None:
        if c.phase != 0:
            st.warning("Dây đã đóng đăng ký — bạn không còn tham gia được.")
            return
        if len(members) >= c.member_count:
            st.warning("Dây đã đủ người.")
            return

        st.markdown("#### Bạn chưa tham gia dây này")
        st.info(
            f"Tham gia sẽ khoá ký quỹ **{fmt_usdc(c.deposit)} USDC** "
            f"(= 1 kỳ góp). Số này được giữ trong contract và bù vào pot "
            f"nếu sau này bạn cáo."
        )

        # Kiểm tra referrer từ query param
        referrer = None
        try:
            query_params = st.query_params
            ref_param = query_params.get("ref")
            if ref_param and ref_param != me:
                # Validate referrer là organizer
                if ref_param.lower() == c.organizer.lower():
                    referrer = ref_param
                    st.success(
                        f"🎁 Bạn được giới thiệu bởi: `{referrer[:8]}…{referrer[-6:]}`"
                    )
        except Exception:
            pass

        bal = balances(w3, wallet.address)
        st.caption(f"Số dư hiện tại: {bal['usdc'] / 10**6:,.2f} USDC")
        if bal["usdc"] < c.deposit:
            st.error("Không đủ USDC để ký quỹ. Nạp thêm rồi thử lại.")
            return

        if st.button("🔗 Tham gia dây (ký quỹ)", type="primary",
                     use_container_width=True):
            with st.spinner("Đang approve USDC và gửi giao dịch join…"):
                try:
                    res = join(w3, wallet, addr, referrer=referrer)
                except Exception as e:
                    st.error(f"Tham gia thất bại: {e}")
                    return
            show_tx(res, "Đã tham gia dây")
            time.sleep(1)
            st.rerun()
        return

    # ── Đã tham gia ───────────────────────────────────────────────
    st.metric("Bạn phải đóng kỳ này", fmt_usdc(mv.amount_due))
    if mv.amount_due == 0:
        if mv.won_round:
            st.success("Kỳ này bạn là người nhận hụi — không phải đóng.")
        else:
            st.info("Bạn không phải đóng kỳ này.")
        return

    bal = balances(w3, wallet.address)
    st.caption(
        f"Số dư: {bal['usdc'] / 10**6:,.2f} USDC · "
        f"Ký quỹ còn: {fmt_usdc(mv.deposit_left)} USDC"
    )

    if st.button("💳 Ký và gửi giao dịch `payIn`", type="primary",
                 use_container_width=True):
        with st.spinner("Đang approve USDC và gửi giao dịch…"):
            try:
                res = pay_in(w3, wallet, addr)
            except Exception as e:
                st.error(f"Đóng hụi thất bại: {e}")
                return
        show_tx(res, "Đã đóng hụi kỳ này")
        time.sleep(1)
        st.rerun()


def tab_bidding(w3, addr, me: str):
    st.subheader("Đấu giá kín")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")

    if not (w3 and addr):
        return

    try:
        c = read_circle(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    if c.mode != 1:
        st.info("Dây này chia theo thứ tự cố định, không đấu giá.")
        return

    wallet = _wallet(me)
    if wallet is None or not wallet.can_sign:
        st.error("Ví đang đăng nhập không ký được giao dịch.")
        return

    st.metric("Trần giá kêu kỳ này", fmt_usdc(c.max_bid))
    st.caption(
        "Trần này là 20%/năm trên khoản góp, theo Bộ luật Dân sự 2015 "
        "Điều 468. Contract từ chối mọi giá kêu vượt trần — không cắt "
        "âm thầm, mà revert."
    )

    # Bid advice
    advice = bid_advice(c.contribution, c.period, c.member_count)
    st.markdown("#### Gợi ý kêu giá")
    for rec in advice["cacMuc"]:
        st.write(
            f"**{rec['muc'].title()}**: {fmt_usdc(rec['giaKeu'])} "
            f"({rec.get('apr', 0):.1f}% APR) → "
            f"lãi/lỗ {fmt_usdc(rec['laiLoRong']) if rec.get('laiLoRong') else '?'}"
        )

    st.divider()

    # ── Đếm ngược theo phase ─────────────────────────────────────
    rounds = []
    try:
        rounds = read_rounds(w3, addr)
    except Exception:
        pass
    current = rounds[c.current_round] if c.current_round < len(rounds) else None

    now = int(time.time())
    if c.phase == 1 and current:
        left = max(0, current["commit_deadline"] - now)
        st.metric("Còn lại để cam kết", f"{left}s")
    elif c.phase == 2 and current:
        left = max(0, current["pay_deadline"] - now)
        st.metric("Còn lại để đóng tiền", f"{left}s")

    # ── Bước 1: commit ──────────────────────────────────────────
    st.markdown("#### Bước 1 — Cam kết (không ai thấy giá)")
    if c.phase != 1:
        st.info("Chưa tới cửa sổ cam kết, hoặc đã qua.")
    else:
        bid_usdc = st.number_input(
            "Giá kêu (USDC)", min_value=0.0,
            max_value=c.max_bid / 1e6, step=0.01,
            help=f"Tối đa {fmt_usdc(c.max_bid)} USDC (trần luật định)",
        )
        salt = st.text_input(
            "Chuỗi bí mật (ghi nhớ — mất là mất nửa ký quỹ)",
            value=hashlib.sha256(os.urandom(16)).hexdigest()[:16],
        )

        if st.button("🔐 Cam kết giá", type="primary",
                     use_container_width=True):
            bid_units = int(round(bid_usdc * 1e6))
            if bid_units > c.max_bid:
                st.error("Giá kêu vượt trần luật định.")
                return
            try:
                h = _hash_bid(bid_units, salt, me, c.current_round)
            except Exception as e:
                st.error(f"Không tính được hash: {e}")
                return

            with st.spinner("Đang ký và gửi cam kết…"):
                try:
                    res = commit_bid(w3, wallet, addr, h)
                except Exception as e:
                    st.error(f"Cam kết thất bại: {e}")
                    return

            # Lưu lại để bước reveal dùng lại
            st.session_state["pending_bid"] = {
                "circle": addr,
                "round": c.current_round,
                "bid": bid_units,
                "salt": salt,
            }
            show_tx(res, "Đã gửi cam kết")
            time.sleep(1)
            st.rerun()

        st.caption(
            f"Hash cam kết = keccak256(abi.encode(bid, salt, bạn, vòng "
            f"{c.current_round})). Contract chỉ lưu hash — giá của bạn "
            f"kín cho tới bước mở giá."
        )

    # ── Bước 2: reveal ──────────────────────────────────────────
    st.markdown("#### Bước 2 — Mở giá")
    pending = st.session_state.get("pending_bid")
    pending_ok = bool(
        pending
        and pending.get("circle") == addr
        and pending.get("round") == c.current_round
    )
    if c.phase != 1:
        st.info("Cửa sổ mở giá đã đóng.")
    elif current and now < current["commit_deadline"]:
        st.info(
            f"Chưa tới giờ mở giá. Còn "
            f"{current['commit_deadline'] - now}s. "
            "Contract revert nếu reveal sớm — đó là điều kiện để đấu giá kín."
        )
    elif not pending_ok:
        st.warning(
            "Không có cam kết nào của bạn ở vòng này. Nếu đã commit từ "
            "thiết bị khác, nhập tay giá và chuỗi bí mật bên dưới."
        )
        manual_bid = st.number_input(
            "Giá đã cam kết (USDC)", min_value=0.0,
            max_value=c.max_bid / 1e6, step=0.01, key="manual_bid",
        )
        manual_salt = st.text_input("Chuỗi bí mật đã dùng", key="manual_salt")
        if st.button("📖 Mở giá", type="primary", use_container_width=True):
            if not manual_salt:
                st.error("Nhập chuỗi bí mật.")
                return
            with st.spinner("Đang gửi reveal…"):
                try:
                    res = reveal_bid(
                        w3, wallet, addr,
                        int(round(manual_bid * 1e6)), manual_salt,
                    )
                except Exception as e:
                    st.error(f"Mở giá thất bại: {e}")
                    return
            show_tx(res, "Đã mở giá")
            time.sleep(1)
            st.rerun()
    else:
        st.caption(
            f"Bạn đã cam kết giá {fmt_usdc(pending['bid'])} USDC ở vòng "
            f"{pending['round'] + 1}."
        )
        if st.button("📖 Mở giá ngay", type="primary",
                     use_container_width=True):
            with st.spinner("Đang gửi reveal…"):
                try:
                    res = reveal_bid(
                        w3, wallet, addr, pending["bid"], pending["salt"],
                    )
                except Exception as e:
                    st.error(f"Mở giá thất bại: {e}")
                    return
            st.session_state.pop("pending_bid", None)
            show_tx(res, "Đã mở giá")
            time.sleep(1)
            st.rerun()

    # ── Bước 3: settle ──────────────────────────────────────────
    st.markdown("#### Bước 3 — Chốt vòng (ai cũng gọi được)")
    if c.phase != 1:
        st.info("Không ở cửa sổ đấu giá.")
    elif current and now <= current["commit_deadline"] + c.reveal_window:
        left = max(0, current["commit_deadline"] + c.reveal_window - now)
        st.info(f"Chưa hết cửa sổ mở giá. Còn {left}s.")
    else:
        if st.button("✅ Chốt vòng", type="primary",
                     use_container_width=True):
            with st.spinner("Đang chốt vòng…"):
                try:
                    res = settle(w3, wallet, addr)
                except Exception as e:
                    st.error(f"Chốt vòng thất bại: {e}")
                    return
            show_tx(res, "Đã chốt vòng")
            time.sleep(1)
            st.rerun()


def tab_history(w3, addr, me: str):
    st.subheader("Lịch sử giao dịch")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")

    if not (w3 and addr):
        return
    try:
        events = read_history(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    if not events:
        st.info("Chưa có sự kiện nào.")
        return

    labels = {
        "join": "Tham gia",
        "pay": "Đóng hụi",
        "commit": "Cam kết giá",
        "reveal": "Mở giá",
        "settle": "Chốt vòng",
        "payout": "Nhận hụi",
        "default": "Cáo",
    }
    rows = []
    for e in events:
        row = {"Block": e["block"], "Loại": labels.get(e["type"], e["type"])}
        if "member" in e:
            row["Ví"] = f"{e['member'][:6]}…{e['member'][-4:]}"
        if "round" in e:
            row["Vòng"] = e["round"] + 1
        if e["type"] == "pay":
            row["Số tiền"] = fmt_usdc(e["due"])
            row["Phạt trễ"] = fmt_usdc(e["fee"])
        if e["type"] in ("reveal", "settle"):
            row["Giá kêu"] = fmt_usdc(e["bid"])
        if e["type"] in ("settle", "payout"):
            row["Pot"] = fmt_usdc(e["pot"])
        if e["type"] == "default":
            row["Ký quỹ bù"] = fmt_usdc(e["covered"])
            row["Thiếu"] = fmt_usdc(e["short"])
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def tab_score(w3, addr, me: str):
    st.subheader("Điểm uy tín")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")
    st.markdown(
        "Điểm tính bằng công thức cố định trên dữ liệu on-chain — "
        "không dùng mô hình ngôn ngữ. Ai cũng tính lại được từ log. "
        "**Điểm chỉ là gợi ý, contract không chặn ai dựa trên điểm.**"
    )

    if not (w3 and addr):
        return

    try:
        events = read_history(w3, addr)
        members = read_members(w3, addr)
        c = read_circle(w3, addr)
    except Exception as e:
        st.error(str(e))
        return

    paid = [e for e in events if e["type"] == "pay"]
    defaulted = [e for e in events if e["type"] == "default"]
    revealed = [e for e in events if e["type"] == "reveal"]
    settled = [e for e in events if e["type"] == "settle"]  # receiver là người thắng
    paid_out = [e for e in events if e["type"] == "payout"]  # dấu hiệu dây đã xong 1 vòng

    mine_paid = [e for e in paid if e["member"].lower() == me.lower()]
    mine_def = [e for e in defaulted if e["member"].lower() == me.lower()]
    mine_rev = [e for e in revealed if e["member"].lower() == me.lower()]
    mine_settled = [e for e in settled if e["receiver"].lower() == me.lower()]

    late = sum(1 for e in mine_paid if e.get("fee", 0) > 0)

    # Part 4: check Edu-KYC verification
    from app.edu_kyc_backend import is_edu_verified
    has_edu = is_edu_verified(me)

    h = History(
        address=me,
        roundsJoined=len(mine_paid) + len(mine_def),
        paidOnTime=len(mine_paid) - late,
        paidLate=late,
        defaults=len(mine_def),
        bidsWon=len(mine_settled),  # số lần thắng settlement
        avgBidRatio=(
            (sum(e["bid"] for e in mine_rev) / (len(mine_rev) * c.max_bid))
            if mine_rev and c.max_bid
            else 0.0
        ),
        circlesDone=len(paid_out) // c.member_count if c.member_count else 0,
        walletAgeDays=0,
        hasEduKyc=has_edu,
    )
    r = score(h)

    col = st.columns(3)
    col[0].metric("Điểm", r.score)
    col[1].metric("Hạng", r.band)
    col[2].metric("Trần góp đề xuất", fmt_usdc(r.maxContribution))

    st.markdown("**Vì sao có điểm này**")
    for reason in r.reasons:
        st.write(f"· {reason}")

    with st.expander("Thành phần điểm (để kiểm toán)"):
        st.json(r.components)

    st.divider()
    st.markdown("#### 🎓 Xác thực giáo dục (Edu-KYC)")

    from app.edu_kyc_backend import (
        get_edu_credential,
        get_edu_providers,
        mock_oauth_flow
    )

    cred = get_edu_credential(me)

    if cred:
        st.success(
            f"✓ Đã xác thực qua **{cred.provider}** "
            f"(credential: `{cred.credential_id}`)"
        )
        st.info("**Lợi ích**: +30 điểm tín dụng, chống Sybil (multi-account)")
    else:
        st.warning("Chưa xác thực giáo dục. Xác thực để tăng +30 điểm.")

        with st.form("edu_kyc_form"):
            st.write("Chọn nhà cung cấp để xác thực:")
            provider = st.selectbox(
                "Provider",
                get_edu_providers(),
                format_func=lambda x: {
                    "google": "🎓 Google (Gmail edu)",
                    "github": "💻 GitHub (Student pack)",
                }.get(x, x.title())
            )

            submitted = st.form_submit_button("🔐 Xác thực ngay")

            if submitted:
                with st.spinner(f"Đang xác thực qua {provider}..."):
                    try:
                        new_cred = mock_oauth_flow(provider, me)
                        st.success(
                            f"✓ Xác thực thành công! Credential: `{new_cred.credential_id}`"
                        )
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi xác thực: {str(e)}")

        st.caption(
            "**Demo mode**: Xác thực giả (mock) để test. "
            "Trong production, sẽ redirect đến OAuth provider thật."
        )


def tab_idle_funds(w3, addr, me: str):
    st.subheader("💰 Tiền nhàn rỗi — gợi ý gửi đâu")
    st.caption(
        "Khi vòng hiện tại đang chờ (pha Bidding), tiền của bạn trong contract có thể gửi "
        "sang các pool lending trên Avalanche để kiếm lãi. "
        "**Quyết định gửi đâu hoàn toàn của bạn — contract không tự chuyển tiền (HITL).**"
    )

    # Load circle & funds state
    c = read_circle(w3, addr)
    wallet = _wallet(me)
    if not wallet or not wallet.can_sign:
        st.warning("Chỉ organizer mới có thể quản lý yield")
        return

    if c.organizer.lower() != me.lower():
        st.info(f"Bạn không phải organizer. Chỉ organizer (`{c.organizer[:8]}…`) mới quản lý yield.")
        return

    # Show current state
    st.markdown("#### Trạng thái hiện tại")
    col1, col2, col3 = st.columns(3)
    col1.metric("Tiền ở adapter", fmt_usdc(c.funds_in_adapter))
    col2.metric("Yield tích lũy", fmt_usdc(c.yield_accrued))
    col3.metric("Phase", c.phase_name)

    st.markdown("#### Pool gợi ý từ DefiLlama")
    with st.spinner("Đang lấy dữ liệu từ DefiLlama…"):
        pools_result = defi_pools(top=3, min_tvl=1_000_000)

    if "loi" in pools_result:
        st.warning(f"Không lấy được dữ liệu: {pools_result['loi']}")
        return

    pools = pools_result.get("pools", [])
    if not pools:
        st.info("Không tìm thấy pool phù hợp trên Avalanche lúc này.")
        return

    st.info(
        f"**{pools_result.get('tongSoPoolAvalanche', '?')}** pool lending trên Avalanche "
        f"(lọc TVL > $1M, APY 0-60%). Dưới đây là **top 3 có lãi suất cao nhất**:"
    )

    for i, pool in enumerate(pools, 1):
        with st.expander(
            f"**{i}. {pool['project']} · {pool['pool']} — {pool['apy']:.1f}% APY**"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("TVL", f"${pool['tvlUsd']:,.0f}")
                st.metric("APY", f"{pool['apy']:.2f}%")
            with col2:
                st.metric("Stablecoin", "Có" if pool.get("stablecoin") else "Không")
                if pool.get("ilRisk"):
                    st.metric("Rủi ro IL", pool["ilRisk"])

    st.divider()
    st.markdown("#### HITL (Human-in-the-Loop) — Organizer bấm nút")
    st.markdown(
        """
    **Quy trình**:
    1. **Pha Bidding**: Tiền nhàn rỗi (không còn nợ gì cho vòng)
    2. **Bấm "📤 Gửi tiền sang pool"**: Chuyển số tiền bạn chọn vào adapter
    3. **Adapter gửi lên Aave**: Kiếm lãi từng block
    4. **Bấm "🔄 Rút lãi"**: Gọi tiền và yield về, ghi nhận lãi vào yieldAccrued
    5. **Lúc đóng hụi**: Mọi người nhận lại deposit + chia đều yield

    **Rủi ro**: Nếu pool gặp sự cố (hack, IL, token mất giá), quỹ hụi sẽ chịu tổn thất.
    """
    )

    # HITL controls
    col_send, col_withdraw = st.columns(2)

    with col_send:
        st.markdown("##### 📤 Gửi tiền sang pool")
        amount_to_send = st.number_input(
            "Số USDC gửi (tính bằng $, sẽ nhân với 10^6)",
            min_value=0.0,
            max_value=float(c.deposits_held - c.funds_in_adapter) / 1e6,
            step=0.01,
            value=0.0,
            key="amount_to_send"
        )

        if st.button("📤 Gửi sang adapter"):
            if amount_to_send <= 0:
                st.warning("Nhập số tiền > 0")
            elif c.phase != 1:  # Phase.Bidding = 1
                st.error(f"Chỉ gửi được trong pha Bidding. Hiện tại: {c.phase_name}")
            else:
                amount_base = int(amount_to_send * 1e6)
                with st.spinner("Đang gửi tiền…"):
                    try:
                        from demo_config import DEMO_ADAPTER
                        res = supply_to_aave(
                            w3, wallet, addr,
                            DEMO_ADAPTER,
                            amount_base
                        )
                        show_tx(res, "✓ Gửi tiền sang adapter thành công")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")

    with col_withdraw:
        st.markdown("##### 🔄 Rút lãi từ adapter")
        st.write(f"Tiền đang ở adapter: **{fmt_usdc(c.funds_in_adapter)}**")
        st.write(f"Yield tích lũy: **{fmt_usdc(c.yield_accrued)}**")

        if st.button("🔄 Rút lãi về"):
            if c.funds_in_adapter == 0:
                st.info("Không có tiền ở adapter")
            else:
                with st.spinner("Đang rút lãi từ Aave…"):
                    try:
                        res = withdraw_and_report(w3, wallet, addr)
                        show_tx(res, "✓ Rút lãi thành công")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")

    st.divider()
    st.warning(
        "**⚠️ Điều cần biết**:\n"
        "• Quỹ hụi chỉ **gợi ý** các pool, không tự động gửi tiền.\n"
        "• Organizer phải **tự bấm nút** — duy trì kiểm soát hoàn toàn.\n"
        "• Nếu pool bị hack hoặc token mất giá, quỹ hụi sẽ chịu tổn thất.\n"
        "• **Phải rút tiền về trước `settle()`**: nếu quên, bất kỳ thành viên nào cũng có thể bấm "
        "'🔄 Rút lãi về' để kéo tiền — van an toàn để dây hụi không bị kẹt."
    )


def tab_assistant(w3, addr, me: str):
    st.subheader("🤖 Trợ lý AI")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")
    st.markdown(
        "Trợ lý đọc dữ liệu on-chain qua bộ công cụ cố định rồi diễn giải. "
        "Mọi con số đều lấy từ hợp đồng — nếu model nói một số không có "
        "trong dữ liệu, câu trả lời đó bị thay bằng bản tính trực tiếp."
    )

    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []

    provider_ok = bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )
    if not provider_ok:
        st.info(
            "Chưa đặt `GEMINI_API_KEY` — trợ lý vẫn trả lời được bằng số liệu "
            "trực tiếp, nhưng không có phần diễn giải tự nhiên. "
            "Lấy key miễn phí tại aistudio.google.com/app/apikey."
        )

    # Quick suggestions
    st.markdown("**Hỏi nhanh**")
    suggestions = [
        "Điểm uy tín của tôi thế nào?",
        "Nên kêu giá bao nhiêu?",
        "Tình hình dây hụi này ra sao?",
        "Nhận sớm hay nhận muộn có lợi hơn?",
        "Tiền nhàn rỗi gửi đâu được?",
    ]
    cols = st.columns(len(suggestions))
    picked = None
    for i, s in enumerate(suggestions):
        if cols[i].button(s, key=f"sug_{i}", use_container_width=True):
            picked = s

    question = st.chat_input("Hỏi về dây hụi, điểm uy tín, hoặc mức kêu giá…")
    question = picked or question

    # Display chat history
    for turn in st.session_state.chat_log:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    if question:
        st.session_state.chat_log.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Đang đọc dữ liệu on-chain…"):
                ctx = build_agent_context(w3, addr, me)
                history = [
                    {"role": t["role"], "content": t["content"]}
                    for t in st.session_state.chat_log[:-1][-6:]
                ]
                res = _agent.ask(question, ctx, history=history)

            st.markdown(res["answer"])

            if res["toolCalls"]:
                with st.expander("Công cụ đã dùng"):
                    st.write(", ".join(res["toolCalls"]))
            if res["fallback"] and res.get("error") == "ungrounded_numbers_replaced":
                st.caption(
                    "⚠️ Model đưa ra con số không khớp dữ liệu hợp đồng, nên "
                    "câu trả lời đã được thay bằng bản tính trực tiếp. "
                    "Đây là guardrail hoạt động đúng."
                )

        st.session_state.chat_log.append({"role": "assistant", "content": res["answer"]})

    if st.session_state.chat_log and st.button("Xoá hội thoại"):
        st.session_state.chat_log = []
        st.rerun()


def tab_referral(w3, addr, me: str):
    """
    Part 3 — Giới thiệu (Referral).

    Kế toán: contract chỉ GHI NHẬN quan hệ giới thiệu on-chain (event
    `Referred`). Thưởng do nền tảng trả từ phí 0.5% của factory, KHÔNG
    lấy từ quỹ hụi — nếu lấy từ quỹ thì bất biến "tổng net mọi thành
    viên = 0" bị phá và contract tự sinh tiền.
    """
    st.subheader("🎁 Giới thiệu bạn bè")
    st.caption(f"Bạn: `{me[:8]}…{me[-6:]}`")

    # ── Link giới thiệu ────────────────────────────────────────────
    st.markdown("#### Link mời của bạn")
    link = f"http://localhost:8501/?ref={me}"
    st.code(link, language="text")
    st.caption(
        "Người mở link này rồi tham gia dây, contract sẽ ghi nhận bạn "
        "là người giới thiệu. Thưởng do nền tảng chi trả từ phí tạo dây, "
        "không lấy từ quỹ hụi."
    )

    st.divider()

    # ── Thống kê on-chain ──────────────────────────────────────────
    if not (w3 and addr):
        st.info("Nhập địa chỉ dây hụi ở thanh bên để xem thống kê giới thiệu.")
        return

    try:
        c = read_circle(w3, addr)
        members = read_members(w3, addr)
    except Exception as e:
        st.error(f"Không đọc được contract: {e}")
        return

    circle_contract = w3.eth.contract(
        address=w3.to_checksum_address(addr),
        abi=ROSCA_CIRCLE_ABI,
    )

    c1, c2 = st.columns(2)
    c1.metric("Số người bạn giới thiệu vào dây này", c.referral_count)
    c2.metric(
        "Bạn được giới thiệu bởi",
        "Có" if circle_contract.functions.referredBy(
            w3.to_checksum_address(me)).call() !=
        "0x0000000000000000000000000000000000000000" else "Không",
    )

    # ── Bảng ai do ai giới thiệu ───────────────────────────────────
    rows = []
    for m in members:
        ref = circle_contract.functions.referredBy(m.address).call()
        is_ref = ref != "0x0000000000000000000000000000000000000000"
        rows.append({
            "Thành viên": f"{m.address[:8]}…{m.address[-6:]}",
            "Người giới thiệu": (
                f"{ref[:8]}…{ref[-6:]}" if is_ref else "—"
            ),
        })
    if rows:
        st.markdown("#### Quan hệ giới thiệu trong dây")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Dây chưa có thành viên nào.")

    # ── Tổng kết ───────────────────────────────────────────────────
    st.divider()
    st.markdown(
        """
    #### Cách hoạt động
    - **On-chain**: `RoscaCircle.join(address referrer)` ghi cặp
      `(thành viên → người giới thiệu)` và phát event `Referred`.
    - **Reward**: nền tảng trả từ phí 0.5% khi tạo dây — tách biệt hoàn
      toàn khỏi quỹ hụi, nên không ảnh hưởng dòng tiền của 4 người chơi.
    - **Chống lạm dụng**: mỗi thành viên chỉ ghi nhận một người giới thiệu,
      và chỉ người tổ chức dây mới đủ tư cách nhận referral.
    """
    )


def main():
    # Check login
    current_player = st.session_state.get(CURRENT_PLAYER_KEY)
    if not current_player:
        login_screen()
        return

    # Logged in: show main app
    logout_button()
    st.title("🪙 Hụi On-Chain")
    flush_tx()

    addr = sidebar_circle_input()
    w3 = _w3()

    # Tabs for logged-in user
    t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(
        [
            "Tổng quan",
            "Tạo dây",
            "Đóng hụi",
            "Đấu giá",
            "Lịch sử",
            "Điểm uy tín",
            "💰 Tiền nhàn",
            "🎁 Giới thiệu",
        ]
    )

    with t1:
        tab_overview(w3, addr, current_player)
    with t2:
        tab_create_circle(w3, addr, current_player)
    with t3:
        tab_pay(w3, addr, current_player)
    with t4:
        tab_bidding(w3, addr, current_player)
    with t5:
        tab_history(w3, addr, current_player)
    with t6:
        tab_score(w3, addr, current_player)
    with t7:
        tab_idle_funds(w3, addr, current_player)
    with t8:
        tab_referral(w3, addr, current_player)

    # Assistant in sidebar
    with st.sidebar:
        st.divider()
        st.markdown("#### 🤖 Trợ lý AI")
        showing = bool(st.session_state.get("show_assistant"))
        if st.button(
            "Đóng trợ lý" if showing else "Mở trợ lý",
            use_container_width=True,
        ):
            st.session_state["show_assistant"] = not showing
            st.rerun()

    if st.session_state.get("show_assistant"):
        st.divider()
        tab_assistant(w3, addr, current_player)


if __name__ == "__main__":
    main()
