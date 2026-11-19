"""
Cầu nối giữa dữ liệu on-chain (app/chain.py) và AI agent (ai/agent.py).
Tách khỏi app/main.py để unit test được mà không cần Streamlit.
"""
from __future__ import annotations

from typing import Dict, List

from ai.agent import AgentContext
from ai.credit_score import History
from app.chain import CircleView, read_circle, read_history


# Giả lập hồ sơ lịch sử từ các dây trước (dùng để test kịch bản Ban / Điểm xấu)
# Lưu trên builtins để không bị mất khi importlib.reload(app.agent_bridge)
import builtins as _builtins
if not hasattr(_builtins, "_VAULTRING_SIM_PRIOR"):
    _builtins._VAULTRING_SIM_PRIOR = {}
_SIMULATED_PRIOR: Dict[str, Dict] = _builtins._VAULTRING_SIM_PRIOR


def set_simulated_prior(address: str, **kwargs) -> None:
    """Gán hoặc xoá lịch sử giả lập của một ví (phục vụ demo/test)."""
    key = address.lower()
    if not kwargs:
        _SIMULATED_PRIOR.pop(key, None)
    else:
        _SIMULATED_PRIOR[key] = kwargs


def get_simulated_prior(address: str) -> Dict:
    return _SIMULATED_PRIOR.get(address.lower(), {})


def _history_for(me: str, c: CircleView, events: List[Dict], w3=None) -> History:
    """Dựng History của MỘT ví từ log — cùng công thức với tab Điểm uy tín."""
    from app.edu_kyc_backend import is_edu_verified
    from app.chain import read_wallet_anomalies

    paid = [e for e in events if e["type"] == "pay"]
    defaulted = [e for e in events if e["type"] == "default"]
    revealed = [e for e in events if e["type"] == "reveal"]
    settled = [e for e in events if e["type"] == "settle"]
    paid_out = [e for e in events if e["type"] == "payout"]

    me_low = me.lower()
    mine_paid = [e for e in paid if e["member"].lower() == me_low]
    mine_def = [e for e in defaulted if e["member"].lower() == me_low]
    mine_rev = [e for e in revealed if e["member"].lower() == me_low]
    mine_settled = [e for e in settled if e["receiver"].lower() == me_low]
    mine_all_ev = [e for e in events if e.get("member", "").lower() == me_low]
    late = sum(1 for e in mine_paid if e.get("fee", 0) > 0)

    prior = get_simulated_prior(me)
    p_on_time = prior.get("paidOnTime", 0)
    p_late = prior.get("paidLate", 0)
    p_def = prior.get("defaults", 0)
    p_won = prior.get("bidsWon", 0)
    p_circles = prior.get("circlesDone", 0)
    p_age = prior.get("walletAgeDays", 0)
    p_ratio = prior.get("avgBidRatio", None)
    p_anom = prior.get("anomalousTxs", 0)

    on_time_total = (len(mine_paid) - late) + p_on_time
    late_total = late + p_late
    def_total = len(mine_def) + p_def
    rounds_total = on_time_total + late_total + def_total

    if p_ratio is not None:
        avg_ratio = float(p_ratio)
    elif mine_rev and c.max_bid:
        avg_ratio = sum(e["bid"] for e in mine_rev) / (len(mine_rev) * c.max_bid)
    else:
        avg_ratio = 0.0

    # DEMO: Ví 1, 2, 3 luôn có hồ sơ sạch (Hạng A - 855 điểm, 0 giao dịch bất thường)
    # Ví 4 luôn bị Ban (Hạng F - 0 điểm, 4 giao dịch Wash Trading + lịch sử cáo hụi)
    from app.chain import CLEAN_DEMO_WALLETS, BANNED_DEMO_WALLETS
    if me_low in CLEAN_DEMO_WALLETS:
        return History(
            address=me,
            roundsJoined=12 + (len(mine_paid) - late),
            paidOnTime=12 + (len(mine_paid) - late),
            paidLate=0,
            defaults=0,
            bidsWon=2 + len(mine_settled),
            avgBidRatio=0.35,
            circlesDone=3,
            walletAgeDays=90,
            hasEduKyc=is_edu_verified(me),
            anomalousTxs=0,
        )
    if me_low in BANNED_DEMO_WALLETS:
        anom_cnt = 6
        if w3 is not None:
            try:
                anom_cnt = max(4, read_wallet_anomalies(w3, me, c.address).get("count", 6))
            except Exception:
                pass
        return History(
            address=me,
            roundsJoined=6,
            paidOnTime=2,
            paidLate=2,
            defaults=2,
            bidsWon=2,
            avgBidRatio=0.95,
            circlesDone=0,
            walletAgeDays=15,
            hasEduKyc=False,
            anomalousTxs=anom_cnt,
        )

    anom_count = p_anom
    if w3 is not None:
        try:
            anom_info = read_wallet_anomalies(
                w3, me, c.address,
                legitimate_rosca_events=max(1, len(mine_all_ev)),
            )
            anom_count += anom_info.get("count", 0)
        except Exception:
            pass

    return History(
        address=me,
        roundsJoined=rounds_total,
        paidOnTime=on_time_total,
        paidLate=late_total,
        defaults=def_total,
        bidsWon=len(mine_settled) + p_won,
        avgBidRatio=avg_ratio,
        circlesDone=(len(paid_out) // c.member_count if c.member_count else 0) + p_circles,
        walletAgeDays=p_age,
        hasEduKyc=is_edu_verified(me),
        anomalousTxs=anom_count,
    )


def build_agent_context_from_data(
    c: CircleView,
    events: List[Dict],
    me: str = "",
    w3=None,
) -> AgentContext:
    """Dựng AgentContext từ CircleView và danh sách sự kiện đã đọc."""
    paid = [e for e in events if e["type"] == "pay"]
    settled = [e for e in events if e["type"] == "settle"]
    paid_out = [e for e in events if e["type"] == "payout"]

    received = [e["receiver"] for e in (settled or paid_out)]
    paid_this = [e["member"] for e in paid
                 if e.get("round") == c.current_round]

    history = _history_for(me, c, events, w3=w3) if me else None

    # Điểm của TẤT CẢ thành viên (và cả 4 ví demo), để AI trả lời được
    # kể cả khi ví bị Ban chưa nằm trong danh sách join của dây 3 người.
    addr_set = {e["member"].lower() for e in events if e["type"] == "join"}
    try:
        from app.wallet import load_players
        for p in load_players():
            addr_set.add(p.address.lower())
    except Exception:
        pass

    histories = {
        a: _history_for(a, c, events, w3=w3)
        for a in addr_set
    }

    return AgentContext(
        history=history,
        histories=histories,
        member_count=c.member_count,
        contribution=c.contribution,
        period=c.period,
        current_round=c.current_round,
        mode=c.mode_name,
        received=received,
        paid_this_round=paid_this,
        penalty_pool=c.penalty_pool,
    )


def build_agent_context(w3, addr: str, me: str = "") -> AgentContext:
    """
    Gom dữ liệu thật từ contract thành AgentContext cho agent.
    Không có kết nối thì trả về context rỗng — agent sẽ tự nói là thiếu dữ liệu.
    """
    if not (w3 and addr):
        return AgentContext()

    try:
        c = read_circle(w3, addr)
        events = read_history(w3, addr)
    except Exception:
        return AgentContext()

    return build_agent_context_from_data(c, events, me, w3=w3)
