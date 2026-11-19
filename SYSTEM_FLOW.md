# Hụi On-Chain — System Architecture & Flow Diagram
---

## 1. Tổng quan Hệ thống (System Overview)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HỤI ON-CHAIN SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐         ┌──────────────────┐                      │
│  │  User Interface  │         │   Smart Contract │                      │
│  │  (Streamlit)     │◄────────│   (Solidity)     │                      │
│  │                  │         │                  │                      │
│  │ • Login          │         │ • RoscaCircle    │                      │
│  │ • Create Circle  │         │ • YieldAdapter   │                      │
│  │ • Join / Pay     │         │ • Factory        │                      │
│  │ • Bid / Settle   │         │                  │                      │
│  │ • Referral       │         │                  │                      │
│  │ • Yield          │         │                  │                      │
│  │ • Credit Score   │         │                  │                      │
│  └────────┬─────────┘         └────────┬─────────┘                      │
│           │                           │                                 │
│           └───────web3.py (JSON-RPC)──┘                                │
│                                                                          │
│                    ┌─────────────────────────────┐                      │
│                    │   Avalanche Fuji C-Chain    │                      │
│                    │   chainId: 43113            │                      │
│                    │   USDC: 0x5425890...        │                      │
│                    │   Aave v3 Pool: 0x6Ae43d3..│                      │
│                    └─────────────────────────────┘                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. User Flow — Từ Login đến Close Circle

```
START
  │
  ├─► [Login Screen]
  │     Player 1-4 choose ví
  │
  ├─► [Tab "Tạo dây"] (Player 1 = Organizer)
  │     Input: Factory, mode, member_count, contribution, period, windows
  │     Action: createCircle() → RoscaFactory
  │     Output: circle_address
  │
  ├─► [Tab "Đóng hụi"] (All Players)
  │     ├─ Phase = OPEN
  │     │   ├─ Chưa join?
  │     │   │   ├─ Check ?ref query param (Part 3)
  │     │   │   ├─ join() or join(referrer)
  │     │   │   └─ emit Joined event
  │     │   │
  │     │   └─ Tất cả join xong
  │     │       └─ phase = Bidding (auto)
  │     │
  │     ├─ Phase = Bidding (4 rounds)
  │     │   ├─ [Part 2: Yield] (organizer only, phase = Bidding)
  │     │   │   ├─ setYieldAdapter(adapter_address)
  │     │   │   ├─ sendToAdapter(amount) → fundsInAdapter↑
  │     │   │   └─ withdrawFromAdapter() → yield recorded
  │     │   │
  │     │   ├─ [Tab "Đấu giá"]
  │     │   │   ├─ commitBid(hash) + receive event BidCommitted
  │     │   │   ├─ revealBid(bid, salt) → receive event BidRevealed
  │     │   │   ├─ settle() → winner decided, pot ready
  │     │   │   └─ payIn() → pot transferred to winner
  │     │   │
  │     │   └─ repeat for round 2, 3, 4
  │     │
  │     ├─ [Part 4: Edu-KYC] (any time)
  │     │   ├─ Tab "Điểm uy tín"
  │     │   ├─ "Xác thực ngay" → mock OAuth
  │     │   ├─ credential lưu → score +30
  │     │   └─ badge "✓ Đã xác thực"
  │     │
  │     └─ Phase = Closed
  │         ├─ yield chia đều = yieldAccrued / memberCount
  │         ├─ emit CircleClosed
  │         └─ end
  │
  └─► [Summary]
        ✓ 4 người tham gia
        ✓ 4 vòng đấu giá hoàn thành
        ✓ Yield kiếm được + chia đều
        ✓ Credit score tăng (Part 4)
        ✓ Referral tracked (Part 3)

END
```

---

## 3. Part 2: Idle Funds Yield + HITL Flow

```
┌────────────────────────────────────────────────────────────────────┐
│              IDLE FUNDS YIELD + HUMAN-IN-THE-LOOP                  │
└────────────────────────────────────────────────────────────────────┘

PRECONDITION:
  • depositsHeld = 40 USDC (4 người join × 10 USDC)
  • Phase = Bidding
  • Organizer = có quyền gửi/rút

FLOW:
  
  1. [SETUP] Organizer set adapter
     ┌─────────────────────────────┐
     │ organizer bấm "Setup Yield"  │
     │ input: yieldAdapter_address  │
     └────────────┬────────────────┘
                  │
                  ▼
     ┌─────────────────────────────┐
     │ setYieldAdapter(adapter)    │
     │ state: yieldAdapter ✓       │
     └────────────┬────────────────┘
                  │
  
  2. [SUPPLY] Organizer gửi tiền sang Aave
     ┌─────────────────────────────────┐
     │ Tab "Tiền nhàn rỗi"              │
     │ Input: 20 USDC (từ idle funds)   │
     │ Button: "📤 Chuyển tiền sang pool"│
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ supply_to_aave(w3, wallet,      │
     │                adapter, 20)     │
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ Rosca.sendToAdapter(20)         │
     │ • approve USDC to adapter       │
     │ • transfer 20 USDC to adapter   │
     │ • fundsInAdapter += 20          │
     │ • depositsHeld -= 20            │
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ YieldAdapter.supplyToAave(20)   │
     │ • amountSent += 20              │
     │ • Aave.supply(USDC, 20)         │
     │ • receive aUSDC (1:1 ratio)     │
     └────────────┬────────────────────┘
                  │
     ┌────────────┴────────────────┐
     │                             │
     ▼ (over time)                 ▼
  aUSDC balance                  Aave generates yield
  grows (pending)                (accrues interest)
     │                             │
     └────────────┬────────────────┘
                  │
  
  3. [HARVEST] Organizer rút tiền + yield
     ┌─────────────────────────────────┐
     │ Tab "Tiền nhàn rỗi"              │
     │ Check: aUSDC balance ≈ 20.10    │
     │ Button: "📥 Rút tiền + yield"    │
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ withdraw_and_report(w3, wallet) │
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ Rosca.withdrawFromAdapter()     │
     │ • fundsInAdapter = 0            │
     │ • call adapter.withdrawAndReport│
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ YieldAdapter.withdrawAndReport()│
     │ • ausdc_balance = 20.10         │
     │ • Aave.withdraw(20.10)          │
     │ • usdc_received = 20.10         │
     │ • yield = 20.10 - 20 = 0.10     │
     │ • transfer 20.10 back to Rosca  │
     │ • call Rosca.noteYield(0.10)    │
     └────────────┬────────────────────┘
                  │
                  ▼
     ┌─────────────────────────────────┐
     │ Rosca.noteYield(0.10)           │
     │ • yieldAccrued += 0.10          │
     │ • emit YieldAccrued(0.10)       │
     └────────────┬────────────────────┘
                  │
     ┌────────────┴────────────────┐
     │                             │
     ▼                             ▼
  UI shows:                    On close():
  "Yield: +0.10 USDC"          yield_per_member = 0.10 / 4
  gasUsed, link                = 0.025 USDC each

ACCOUNTING INVARIANT:
  balanceOf(Rosca) + fundsInAdapter
    == (depositsHeld - fundsInAdapter) + penaltyPool + potInFlight + yieldAccrued
  
  Before: 20 + 20 == 20 + 0 + 0 + 0  ✓
  After:  20.10 + 0 == 20 + 0 + 0 + 0.10  ✓

SECURITY:
  ✓ CEI: state update trước external calls
  ✓ Reentrancy guard: nonReentrant
  ✓ Authorization: adapter chỉ gọi từ Rosca
  ✓ Van an toàn: anyone gọi withdrawFromAdapter() được
```

---

## 4. Part 3: Referral System Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                      REFERRAL SYSTEM (Part 3)                      │
└────────────────────────────────────────────────────────────────────┘

FLOW:

  1. [GENERATE LINK] Organizer share
     ┌──────────────────────────────┐
     │ Player 1 (Organizer) login   │
     │ Tab "🎁 Giới thiệu"          │
     └────────────┬─────────────────┘
                  │
                  ▼
     ┌──────────────────────────────────────────┐
     │ Link hiển thị:                            │
     │ http://localhost:8501/?ref=0xPlayer1Addr │
     │                                          │
     │ [Copy button]                            │
     └────────────┬─────────────────────────────┘
                  │
  
  2. [OPEN LINK] Player 2-4 open link
     ┌──────────────────────────────────────────┐
     │ Player 2 opens:                          │
     │ http://localhost:8501/?ref=0xPlayer1Addr │
     └────────────┬─────────────────────────────┘
                  │
                  ▼
     ┌──────────────────────────────┐
     │ Streamlit parses URL          │
     │ st.query_params["ref"] = 0xP1 │
     └────────────┬─────────────────┘
                  │
  
  3. [JOIN WITH REFERRER]
     ┌──────────────────────────────┐
     │ Player 2 login                │
     │ Tab "Đóng góp"                │
     └────────────┬─────────────────┘
                  │
                  ▼
     ┌────────────────────────────────────────┐
     │ UI checks query param                   │
     │ if ref != me and ref == organizer:      │
     │   show: "🎁 Bạn được giới thiệu bởi    │
     │          0xPlayer1…"                    │
     │   referrer = 0xPlayer1                  │
     └────────────┬───────────────────────────┘
                  │
                  ▼
     ┌────────────────────────────────────────┐
     │ Player 2 bấm "Tham gia"                 │
     │ join(w3, wallet, circle, referrer)     │
     └────────────┬───────────────────────────┘
                  │
                  ▼
     ┌────────────────────────────────────────┐
     │ Contract:                               │
     │ join(address referrer)                  │
     │   → _join(0xPlayer1)                    │
     │   → members.push(player2)               │
     │   → isMember[player2] = true            │
     │   → referredBy[player2] = 0xPlayer1     │
     │   → referralCount++ (= 1)               │
     │   → emit Referred(player2, player1)     │
     │   → depositsHeld += 10                  │
     └────────────┬───────────────────────────┘
                  │
                  ▼
     ┌────────────────────────────────────────┐
     │ Receipt:                                │
     │ ✓ Event Referred phát                   │
     │ ✓ tx confirmed                          │
     └────────────┬───────────────────────────┘
                  │
  
  4. [CHECK STATS] Organizer kiểm tra
     ┌──────────────────────────────┐
     │ Player 1 Tab "🎁 Giới thiệu"  │
     └────────────┬─────────────────┘
                  │
                  ▼
     ┌────────────────────────────────────────┐
     │ Metric: "Số người bạn giới thiệu: 3"   │
     │                                        │
     │ Table:                                  │
     │ ┌──────────────┬──────────────────┐    │
     │ │ Thành viên   │ Người giới thiệu  │    │
     │ ├──────────────┼──────────────────┤    │
     │ │ 0xPlayer2… │ 0xPlayer1…       │    │
     │ │ 0xPlayer3… │ 0xPlayer1…       │    │
     │ │ 0xPlayer4… │ 0xPlayer1…       │    │
     │ └──────────────┴──────────────────┘    │
     └────────────┬───────────────────────────┘
                  │
  
  5. [REWARD] Platform off-chain (NOT in contract)
     ┌────────────────────────────────────────┐
     │ Platform service listens for events     │
     │ event Referred(member, referrer)       │
     │   → referrer = 0xPlayer1                │
     │   → reward = 1 USDC from treasury       │
     │   → transfer to 0xPlayer1               │
     │                                        │
     │ Quỹ hụi KHÔNG ĐỔI:                     │
     │   depositsHeld = 40 USDC                │
     │   totalPool = 40 USDC                   │
     └────────────────────────────────────────┘

ACCOUNTING INVARIANT:
  referralCount = số event Referred phát
  = 3 (player2, player3, player4)
  
  Quỹ hụi:
    sum(net) = 0  ✓
    không có USDC nào được tạo/xoá
    reward trả từ ngoài quỹ

SECURITY GUARDS:
  ✓ referrer must be organizer (chỉ organizer được credit)
  ✓ referredBy[member] == address(0) (1 người 1 referrer)
  ✓ event Referred phát tùy điều kiện
```

---

## 5. Part 4: Edu-KYC + Sybil Resistance Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                 EDU-KYC + SYBIL RESISTANCE (Part 4)                │
└────────────────────────────────────────────────────────────────────┘

FLOW:

  1. [LOGIN & VIEW SCORE]
     ┌──────────────────────────┐
     │ Player login              │
     │ Tab "Điểm uy tín"         │
     └────────────┬──────────────┘
                  │
                  ▼
     ┌──────────────────────────────────────┐
     │ UI reads credit score from backend    │
     │                                      │
     │ Score = base + bonuses               │
     │ • Base: 400 (default)                │
     │ • Joined circle: +30                 │
     │ • Paid on time: +20/round            │
     │ • Edu-KYC: +30 (if verified)         │
     │                                      │
     │ Example: 400 + 30 (join) = 430       │
     │ Grade: D (400-499)                   │
     └────────────┬──────────────────────────┘
                  │
  
  2. [CHECK EDU-KYC STATUS]
     ┌──────────────────────────────┐
     │ Scroll to "🎓 Xác thực giáo dục"│
     │                              │
     │ If verified:                 │
     │   Show: "✓ Đã xác thực qua   │
     │          Google"             │
     │   Skip form                  │
     │                              │
     │ If NOT verified:             │
     │   Show: "🔐 Xác thực ngay"    │
     │   Provider choice:           │
     │   • Google                   │
     │   • GitHub                   │
     └────────────┬──────────────────┘
                  │
  
  3. [MOCK OAUTH VERIFICATION]
     ┌──────────────────────────────┐
     │ Player bấm "Xác thực ngay"     │
     │ Chọn provider: "Google"        │
     └────────────┬──────────────────┘
                  │
                  ▼
     ┌──────────────────────────────────────┐
     │ Backend: mock_oauth_flow("google")   │
     │   • simulate OAuth redirect          │
     │   • generate credential_id           │
     │   • mark_edu_verified(wallet)        │
     │   • store: {wallet, provider, id}    │
     │   • return: success                  │
     └────────────┬──────────────────────────┘
                  │
                  ▼
     ┌──────────────────────────────────────┐
     │ UI shows:                            │
     │ "✓ Xác thực thành công!" 🎈          │
     │ Refresh score                        │
     └────────────┬──────────────────────────┘
                  │
  
  4. [SCORE UPDATED]
     ┌──────────────────────────────────────┐
     │ Credit score recalculated:           │
     │                                      │
     │ Old: 430 (grade D)                   │
     │ New: 430 + 30 = 460 (grade C)        │
     │                                      │
     │ Reason shown:                        │
     │ • Tham gia dây hụi (+30)              │
     │ • Xác thực Edu-KYC (+30) ✓            │
     │ • Thanh toán đúng hạn (+0)            │
     │ = 460 tổng                           │
     │                                      │
     │ Grade: C (500-599) ✓                 │
     └────────────┬──────────────────────────┘
                  │
  
  5. [SYBIL DEFENSE]
     ┌──────────────────────────────────────┐
     │ Backend tracks:                      │
     │ credential_id → [wallet]              │
     │                                      │
     │ If same credential used for wallet2: │
     │   • Flag: Sybil detected              │
     │   • Action: reject or penalize        │
     │                                      │
     │ One person = one credential           │
     │ One credential = one wallet           │
     └────────────────────────────────────────┘

SCORING ALGORITHM (ai/credit_score.py):

  base_score = 400
  
  if hasJoined:
    base_score += 30
  
  if hasEduKyc:
    base_score += 30
  
  for each round:
    if paidOnTime:
      base_score += 20
    elif late:
      base_score -= 10
    elif defaulted:
      base_score -= 50
  
  final_score = max(0, min(1000, base_score))
  
  grade = {
    0-399: F,
    400-499: D,
    500-599: C,
    600-799: B,
    800-1000: A
  }

SYBIL DEFENSE LAYERS:
  ✓ Layer 1: One credential per provider
  ✓ Layer 2: One credential per wallet
  ✓ Layer 3: KYC + Liveness check (production)
  ✓ Layer 4: IP reputation (production)
  ✓ Layer 5: Combine with referral gating
```

---

## 6. Complete Transaction Flow — Example (4-round Demo)

```
TIME   ROUND  PHASE        ACTION                POOL    YIELD   EVENT
────────────────────────────────────────────────────────────────────────
T=0    -      OPEN         4 join()              40      0       Joined×4
                           • each deposit 10
                           • Part 3: referral tracked
                           • Part 4: base score 430

T=1h   -      OPEN         Part 4: Edu-KYC      40      0       none
                           • Player 1,2,3: verify
                           • score +30 each

T=2h   1      BIDDING      Part 2: Yield setup  40      0       none
                           • sendToAdapter(20)
                           • fundsInAdapter=20
                           • pool idle=20

T=2h30 1      BIDDING      Yield harvest        40      0.10    YieldAccrued
                           • yield acrued 0.10
                           • yieldAccrued+=0.10

T=3h   1      BIDDING      Commit phase         40      0.10    BidCommitted×4
                           • 4 players commit bid
                           • locked

T=3:30h 1     BIDDING      Reveal phase         40      0.10    BidRevealed×4
                           • 4 players reveal
                           • highest bid: player1=2.0

T=4h   1      PAYING       Settle & pay         40      0.10    Settled
                           • player1 wins pot 10
                           • potInFlight → player1.received
                           • player1: net = +10 - 10 = 0

T=4:30h 1     PAYING       Other 3 pay in       38.10   0.10    PaidIn×3
                           • each pay 10 (contribution)
                           • pool back to 40

T=5h   2      BIDDING      Round 2: Commit      38.10   0.10    BidCommitted×4
T=5:30h 2     BIDDING      Round 2: Reveal      38.10   0.10    BidRevealed×4
T=6h   2      PAYING       Round 2: Settle      38.10   0.10    Settled
T=6:30h 2     PAYING       Round 2: Pay in      36.20   0.10    PaidIn×3

T=7h   3      BIDDING      Round 3: Commit      36.20   0.10    BidCommitted×4
...
T=10h  4      PAYING       Round 4 complete     34.30   0.10    Settled

T=11h  -      CLOSED       Close circle         0       0       CircleClosed
                           • yield ÷ 4 = 0.025 each
                           • penalty paid
                           • depositsHeld refunded
                           • final net = 0 ✓

ACCOUNTING CHECK:
  sum(paid_total) = 40 USDC input
  sum(received_total) = 40 USDC output
  sum(net) = 0 ✓
  yield distributed = 0.10 USDC
```

---

## 7. Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (Streamlit UI)                       │
├──────────────────────────────────────────────────────────┤
│ • Login screen                                            │
│ • 8 tabs: Overview, Create, Pay, Bid, History,           │
│           Credit, Yield, Referral                        │
│ • Form validation, display results                       │
└─────────┬──────────────────────────────────────────────┬─┘
          │                                              │
┌─────────▼────────────────────────────────────────────┐ │
│ APPLICATION LAYER (Python Backend)                  │ │
├────────────────────────────────────────────────────┤ │
│ • wallet.py: sign txs, manage allowance             │ │
│ • chain.py: read contract state                    │ │
│ • yield_backend.py: supply/withdraw Aave           │ │
│ • edu_kyc_backend.py: credential management        │ │
│ • contract_abi.py: contract interfaces             │ │
│ • credit_score.py: calculate score                 │ │
│ • agent.py: AI chatbot                             │ │
└─────────┬────────────────────────────────────────┬─┘ │
          │                                        │ │
          │ web3.py (JSON-RPC)                    │ │
          │ EIP-1559 signing                       │ │
          │                                        │ │
┌─────────▼────────────────────────────────────────┐ │
│ SMART CONTRACT LAYER (Solidity)                  │ │
├────────────────────────────────────────────────┤ │
│ • RoscaCircle.sol (2500 lines, core logic)      │ │
│ • RoscaFactory.sol (factory pattern)            │ │
│ • YieldAdapter.sol (Aave v3 integration)        │ │
│ • MockYieldAdapter.sol (0.5% demo)              │ │
│ • Libraries: CEI, reentrancy guards              │ │
└─────────┬────────────────────────────────────┬─┘ │
          │                                    │ │
┌─────────▼────────────────────────────────────┐ │
│ BLOCKCHAIN LAYER (Avalanche Fuji)            │ │
├───────────────────────────────────────────┤ │
│ • EVM-compatible C-Chain                  │ │
│ • RPC: https://api.avax-test.network/...  │ │
│ • chainId: 43113                          │ │
│ • USDC token: 0x5425890...                 │ │
│ • Aave v3 Pool: 0x6Ae43d3...               │ │
└───────────────────────────────────────────┘ │
                                              │
└──────────────────────────────────────────────┘
```

---

## 8. Data Flow — Single Transaction

```
User Input (Streamlit)
    │
    ├─ if tab_pay & join button clicked
    │
    ▼
Extract referrer from query param
    │
    ├─ if ?ref=organizer_address
    │   └─ referrer = validated address
    │ else
    │   └─ referrer = None
    │
    ▼
wallet.join(w3, wallet, circle_addr, referrer=referrer)
    │
    ▼
get deposit amount from contract
    │
    ▼
ensure_allowance(USDC, circle, deposit)
    │
    ├─ if allowance < deposit
    │   └─ send approve() tx
    │ else
    │   └─ skip
    │
    ▼
if referrer:
    call c.functions.join(referrer)  ← calls join(address referrer)
else:
    call c.functions.join()          ← calls join()
    │
    ▼
send(wallet_key, tx)  ← sign & broadcast
    │
    ├─ build tx dict (EIP-1559)
    ├─ sign with private key
    ├─ send raw tx via RPC
    ├─ wait_for_receipt (180s timeout)
    │
    ▼
On-chain: RoscaCircle._join(referrer)
    │
    ├─ check phase == OPEN
    ├─ check !isMember[msg.sender]
    ├─ check members.length < memberCount
    ├─ members.push(msg.sender)
    ├─ isMember[msg.sender] = true
    │
    ├─ if referrer && referrer==organizer && referredBy[msg.sender]==0
    │   ├─ referredBy[msg.sender] = referrer
    │   ├─ referralCount++
    │   ├─ emit Referred(msg.sender, referrer)
    │
    ├─ depositsHeld += deposit
    ├─ USDC.transferFrom(msg.sender, address(this), deposit)
    ├─ emit Joined(msg.sender, index)
    │
    ├─ if all members joined
    │   ├─ phase = Bidding
    │   └─ commitDeadline = now + commitWindow
    │
    ▼
Receipt returned to Python
    │
    ▼
show_tx(receipt)  ← display on UI
    │
    ├─ success banner
    ├─ tx hash link
    ├─ block, gas used, fee
    │
    ▼
st.rerun()
    │
    ▼
UI refresh with new state
    ├─ members count updated
    ├─ phase changed (if last member)
    ├─ referralCount visible in Tab "Giới thiệu"
```

---

## 9. State Machine — Circle Lifecycle

```
                    ┌─────────────┐
                    │    OPEN     │
                    │  phase = 0  │
                    └──────┬──────┘
                           │
                    join() for 4 members
                           │
                           ▼
                    ┌─────────────┐
                    │   BIDDING   │
                    │  phase = 1  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    [Round 1]         [Round 2-3]       [Round 4]
  ┌─────────┐        ┌─────────┐       ┌─────────┐
  │Commit   │        │Commit   │       │Commit   │
  │300s     │        │300s     │       │300s     │
  └────┬────┘        └────┬────┘       └────┬────┘
       │                  │                 │
       ▼                  ▼                 ▼
  ┌─────────┐        ┌─────────┐       ┌─────────┐
  │Reveal   │        │Reveal   │       │Reveal   │
  │300s     │        │300s     │       │300s     │
  └────┬────┘        └────┬────┘       └────┬────┘
       │                  │                 │
       ▼                  ▼                 ▼
  ┌─────────┐        ┌─────────┐       ┌─────────┐
  │Settle   │        │Settle   │       │Settle   │
  │600s     │        │600s     │       │600s     │
  └────┬────┘        └────┬────┘       └────┬────┘
       │                  │                 │
       ▼                  ▼                 ▼
  ┌─────────┐        ┌─────────┐       ┌─────────┐
  │PayIn    │        │PayIn    │       │PayIn    │
  │(4-1)    │        │(4-2)    │       │(4-3)    │
  │players  │        │players  │       │players  │
  └────┬────┘        └────┬────┘       └────┬────┘
       │                  │                 │
       └──────────────────┼─────────────────┘
                          │
                    All rounds done
                          │
                          ▼
                    ┌──────────────┐
                    │   PAYING     │
                    │  phase = 2   │
                    │              │
                    │ (temporary)  │
                    └────┬─────────┘
                         │
                    payIn() all
                         │
                         ▼
                    ┌──────────────┐
                    │   CLOSED     │
                    │  phase = 3   │
                    │              │
                    │ • yield ÷    │
                    │ • deposits   │
                    │   refund     │
                    │ • close()    │
                    │   event      │
                    └──────────────┘

TRANSITIONS:
  • join() when phase==0 (members < count)
  • commitBid() when phase==1 (commit window open)
  • revealBid() when phase==1 (reveal window open)
  • settle() when phase==1 (pay window open)
  • payIn() when phase==1 or 2
  • auto to PAYING after settle
  • auto to CLOSED after payIn count == memberCount
```

---

## 10. Production Deployment Checklist

```
✅ COMPLETED

Part 2: Idle Funds Yield + HITL
  ✅ Contract: YieldAdapter.sol + RoscaCircle yield state
  ✅ Backend: supply_to_aave(), withdraw_and_report()
  ✅ UI: tab_idle_funds with pool suggestions
  ✅ Docs: PART2_IMPLEMENTATION.md
  ✅ Test: Python syntax check ✓

Part 3: Referral System
  ✅ Contract: join(address referrer), referredBy, referralCount
  ✅ Backend: wallet.join(referrer), chain.py referral_count
  ✅ UI: tab_referral, query param ?ref=
  ✅ Docs: PART3_IMPLEMENTATION.md, PART3_SUMMARY.md
  ✅ Test: Python syntax check ✓

Part 4: Edu-KYC + Sybil
  ✅ Contract: credit_score.py hasEduKyc +30
  ✅ Backend: edu_kyc_backend.py mock OAuth
  ✅ UI: tab_score with verification form
  ✅ Docs: PART4_IMPLEMENTATION.md
  ✅ Test: Python syntax check ✓

⏳ PENDING (USER ACTION)

Core Blockchain:
  ⏳ forge build --via-ir (compile check)
  ⏳ deploy to Fuji
  ⏳ update demo_config.py with addresses
  ⏳ verify on Snowtrace

App:
  ⏳ streamlit run app/main.py
  ⏳ test all 8 tabs
  ⏳ test referral link flow
  ⏳ test yield harvest
  ⏳ test credit score +30

Demo:
  ⏳ record 2-3 min video
  ⏳ test end-to-end flow
  ⏳ verify all parts working

🚀 PRODUCTION

Mainnet:
  • Deploy to Avalanche Mainnet (chainId 43114)
  • Real OAuth (Google, GitHub)
  • Database (PostgreSQL/Firebase)
  • Monitor gas cost
  • Audit contract (security review)
  • Set up reward payout service

Platform:
  • Referral reward service (listen to Referred events)
  • KYC backend (store credentials securely)
  • Dashboard (organizer, admin)
  • Analytics (daily active users, etc.)
```

---