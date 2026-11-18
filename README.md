# Hụi On-Chain — ROSCA Demo (Avalanche Fuji)

Demo ứng dụng hụi (ROSCA) phi tập trung cho 4 người chơi trên Avalanche Fuji testnet.

**Đặc điểm nổi bật**:
- ✅ Sealed-bid auction (commit-reveal)
- ✅ Ký quỹ (deposit) tự động
- ✅ Late fee 2%, legal cap 20%/năm
- ✅ **Part 2**: Idle Funds Yield + HITL (Human-in-the-Loop)
- ✅ **Part 3**: Referral system (on-chain tracking)
- ✅ **Part 4**: Edu-KYC + Sybil Resistance 
- 🤖 AI chatbot tư vấn

---

## Quick Start

### 1. Install
```bash
cd huionchain-main
pip install -r requirements.txt
```

### 2. Setup Wallets
Tạo file `demo_wallets.json`:
```json
[
  {
    "name": "Alice",
    "address": "0x...",
    "key": "0x..."
  },
  {
    "name": "Bob",
    "address": "0x...",
    "key": "0x..."
  },
  {
    "name": "Carol",
    "address": "0x...",
    "key": "0x..."
  },
  {
    "name": "Dave",
    "address": "0x...",
    "key": "0x..."
  }
]
```

Hoặc dùng env vars:
```bash
export HUI_PK_1="0x..."
export HUI_PK_2="0x..."
export HUI_PK_3="0x..."
export HUI_PK_4="0x..."
```

**Lấy AVAX testnet**: https://faucet.avax.network/

### 3. Deploy Contracts (nếu chưa có)
```bash
export FUJI_RPC="https://api.avax-test.network/ext/bc/C/rpc"
export PRIVATE_KEY="0x..."

# Deploy MockUSDC + Factory
forge script contracts/script/Deploy.s.sol:DeployMockUSDC \
  --rpc-url $FUJI_RPC --broadcast

# Deploy MockYieldAdapter (0.5% mock yield)
forge script contracts/script/DeployMockYieldAdapter.s.sol \
  --rpc-url $FUJI_RPC --broadcast
```

Cập nhật `demo_config.py` với địa chỉ vừa deploy.

### 4. Run App
```bash
streamlit run app/main.py
```

Mở: http://localhost:8501

---

## Features

### Core ROSCA
- **Bidding mode**: Sealed-bid auction (commit-reveal pattern)
- **Fixed mode**: Rotating receiver (no bidding)
- **Deposit (ký quỹ)**: 1 period contribution, auto-refund after completion
- **Late fee**: 2% per contribution
- **Legal cap**: Max 20%/year (Vietnamese Civil Code Điều 468)

### Part 2: Idle Funds Yield + HITL 🏦
- **Pool gợi ý**: DefiLlama API (Aave, Benqi, Trader Joe)
- **Human-in-the-Loop**: Organizer bấm nút → gửi/rút tiền
- **Yield adapter**: YieldAdapter.sol (Aave v3) hoặc MockYieldAdapter.sol (0.5% demo)
- **Chia lãi**: Yield chia đều lúc close circle

**UI**: Tab "Tiền nhàn rỗi"
- Hiển thị 3 pools (APY, TVL, link)
- Button "📤 Chuyển tiền sang pool"
- Button "📥 Rút tiền + yield"
- Real-time aUSDC balance

### Part 3: Referral System 🎁
- **Link mời**: `http://localhost:8501/?ref=<địa_chỉ_organizer>`
- **Ghi nhận on-chain**: `join(address referrer)` → event `Referred`
- **Thưởng tách quỹ**: nền tảng trả từ phí 0.5% của factory, KHÔNG lấy từ quỹ hụi
- **Chống lạm dụng**: mỗi thành viên một người giới thiệu, chỉ organizer đủ tư cách

**UI**: Tab "🎁 Giới thiệu"
- Link mời copy-paste
- Số người bạn đã giới thiệu
- Bảng quan hệ giới thiệu trong dây

### Part 4: Edu-KYC + Sybil 🎓
- **Xác thực giáo dục**: Google, GitHub (OAuth)
- **Điểm thưởng**: +30 điểm tín dụng
- **Chống Sybil**: Một credential chỉ dùng cho một ví
- **Badge**: "✓ Đã xác thực qua Google"

**UI**: Tab "Điểm uy tín"
- Credit score (A-F)
- Lý do chi tiết
- Form xác thực (mock OAuth trong demo)

### AI Chatbot 🤖
- Tư vấn tham gia/rút lui
- Giải thích bidding strategy
- Dự đoán yield (advisory only, không can thiệp contract)

---

## Demo Flow

1. **Login** → Player 1-4 (tab "Đăng nhập")
2. **Create Circle** → 4 người, Bidding, 10 USDC, 30 ngày
3. **Join** → 4 người join + ký quỹ (Player 2-4 dùng link giới thiệu của Player 1)
4. **Tab "🎁 Giới thiệu"** → xem số người đã giới thiệu ✓
5. **Tab "Điểm uy tín"** → xác thực Edu-KYC → điểm +30 ✓
6. **Tab "Tiền nhàn rỗi"** → gửi/rút tiền Aave → yield ✓
7. **Bidding** → commit/reveal/settle (4 vòng)
8. **Close** → yield chia đều

Chi tiết: [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md)

---

## Project Structure

```
huionchain-main/
├── contracts/              # Solidity contracts (Foundry)
│   ├── src/
│   │   ├── RoscaCircle.sol           # Core ROSCA logic
│   │   ├── RoscaFactory.sol          # Circle factory
│   │   ├── YieldAdapter.sol          # Aave v3 adapter
│   │   └── MockYieldAdapter.sol      # Mock 0.5% yield
│   ├── script/
│   │   ├── Deploy.s.sol              # Deploy scripts
│   │   ├── DeployYieldAdapter.s.sol
│   │   └── DeployMockYieldAdapter.s.sol
│   └── test/
│
├── app/                    # Streamlit frontend
│   ├── main.py                       # Main UI (1010 lines)
│   ├── chain.py                      # Web3 read functions
│   ├── wallet.py                     # Web3 write functions
│   ├── contract_abi.py               # ABIs
│   ├── yield_backend.py              # Part 2 backend
│   └── edu_kyc_backend.py            # Part 4 backend
│
├── ai/                     # AI agent + credit scoring
│   ├── agent.py                      # Chatbot logic
│   ├── credit_score.py               # Scoring algorithm
│   └── tools.py                      # Agent tools
│
├── demo_config.py          # Demo constants
├── demo_run.py             # CLI demo runner
├── demo_wallets.json       # Demo wallets
├── requirements.txt        # Python dependencies
│
└── docs/
    ├── IMPLEMENTATION_STATUS.md      # Progress tracker
    ├── PART2_IMPLEMENTATION.md       # Part 2 details
    ├── PART4_IMPLEMENTATION.md       # Part 4 details
    └── DEMO_CHECKLIST.md             # Test checklist
```

---

## Tech Stack

**Blockchain**:
- Avalanche Fuji C-Chain (EVM-compatible)
- Solidity 0.8.24
- Foundry (forge, cast)
- USDC: `0x5425890298aed601595a70AB815c96711a31Bc65`

**Frontend**:
- Python 3.10+
- Streamlit
- web3.py
- eth_abi

**AI**:
- Anthropic Claude (via API)
- Credit scoring (deterministic, no LLM randomness)

**DeFi**:
- Aave v3 (Avalanche)
- DefiLlama API

---

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Contract address invalid"
Check `demo_config.py` có đúng địa chỉ deployed.

### "Insufficient AVAX"
 https://faucet.avax.network/

### "Insufficient USDC"
Mint từ MockUSDC:
```bash
cast send $USDC "mint(address,uint256)" $WALLET 100000000 \
  --rpc-url $FUJI_RPC --private-key $PRIVATE_KEY
```

### "Commit window expired"
Windows ngắn (300s), phải commit ngay sau join.

Xem thêm: [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md) (section "Troubleshooting")

---

## Roadmap

### ✅ Completed
- Core ROSCA (Bidding + Fixed)
- Commit-reveal bidding
- Deposit + late fee + legal cap
- **Part 2**: Idle Funds Yield + HITL
- **Part 3**: Referral (on-chain tracking)
- **Part 4**: Edu-KYC + Sybil

### 🚀 Production TODO
- Real OAuth provider (Google, GitHub)
- Store credential in DB (PostgreSQL, Firebase)
- Deploy to Avalanche Mainnet
- Security audit
- Gas optimization

---

## Team

**BK Hackday S15** — VaultRing
Lê Đức Anh - PO & LeadTech
Lường Trung Dũng - Blockchain Dev
Nguyễn Đức Hiếu - AI Dev
Nguyễn Ngọc Tú - AI Dev

**Contact**: 0975088628 / ducanh592006@gmail.com

---