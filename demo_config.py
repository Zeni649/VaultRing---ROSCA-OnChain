"""
Cấu hình cho demo script (demo_run.py).

Các hằng số này định nghĩa tham số của dây hụi demo:
  - Factory address: nơi tạo contract dây
  - Circle address: dây hụi (hoặc "" để auto-create)
  - Mode: 1 = Bidding (đấu giá), 0 = Fixed (cố định)
  - Contribution: tiền góp mỗi kỳ (base units USDC, 1 USDC = 10^6)
  - Period: thời gian mỗi kỳ (giây)
  - Windows: commit/reveal/pay (giây, phải chia hết cho 10 để script sleep đúng)
"""

# ──────────────────────────────────────────────────────────────────
# Địa chỉ Factory và Circle trên Fuji
# ──────────────────────────────────────────────────────────────────
# Thay bằng địa chỉ thật sau khi deploy
DEMO_FACTORY = "0x16b1797Bc96CdA5911F31516f62c1B2a86b395ed"
DEMO_CIRCLE = "0x2B5fcCef6BEEdFF669Bfdf61208B4460dC17b6fb"
DEMO_ADAPTER = "0xeCf9CF3d5A2f0d831EA0d193dE8b8D01ece929B5"

# ──────────────────────────────────────────────────────────────────
# Tham số dây hụi
# ──────────────────────────────────────────────────────────────────
DEMO_MODE = 1                           # 1 = Bidding, 0 = Fixed
DEMO_CONTRIBUTION = 10_000_000          # 10 USDC (10^6 per USDC)
DEMO_PERIOD = 30 * 86400                # 30 ngày (để maxBid = 0.164 USDC)

# ──────────────────────────────────────────────────────────────────
# Cửa sổ thời gian (giây)
# Lưu ý: script dùng loop sleep(10) nên phải chia hết cho 10
# ──────────────────────────────────────────────────────────────────
DEMO_COMMIT_WINDOW = 300                # 5 phút = 300 s (phù hợp quay video)
DEMO_REVEAL_WINDOW = 300                # 5 phút = 300 s
DEMO_PAY_WINDOW = 600                   # 10 phút = 600 s (thế chủ có thời gian)
