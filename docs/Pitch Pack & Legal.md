# Hụi On-Chain — Pitch Pack + Phân tích pháp lý

---

### 1. Vì sao phải dùng blockchain?

Hụi truyền thống sập vì một lý do đơn giản: **chủ hụi nắm tiền**. Người chơi không có cách nào kiểm tra số dư, không có cách nào ngăn chủ ôm tiền bỏ trốn, và khi xảy ra tranh chấp, không có **bằng chứng nào có giá trị pháp lý**.

Blockchain giải quyết đúng ba điểm này cùng lúc:

Thứ nhất, **Hợp đồng thông minh nắm tiền, không phải con người**: `RoscaCircle.sol` không có hàm nào cho phép chủ hụi rút tiền của người khác. Mọi luồng tiền đều theo quy tắc được lập trình cứng, code đã được deploy thì không ai sửa được.

Thứ hai, **Tất cả dòng tiền đều công khai và tái lập được**: Mọi kỳ góp, mọi pot nhận được, mọi lần cáo đều là sự kiện on-chain, ai cũng đọc được từ explorer. Không có "sổ chủ hụi" mà chỉ chủ hụi mới thấy.

Thứ ba, **Không cần tin tưởng bất kỳ ai**. Người chơi xa lạ hoàn toàn có thể cùng chơi vì quy tắc được cưỡng chế bởi mã, không phải bởi uy tín cá nhân.

Nếu dùng cơ sở dữ liệu tập trung thay vì blockchain, bạn chỉ dời vấn đề: vẫn phải tin tưởng người quản lý server. Blockchain loại bỏ điểm tin tưởng đó.

### 2. Vì sao chọn Avalanche?

Ba lý do có số liệu:

**Phí thấp**: Lấy ví dụ một dây hụi 10 người đóng hàng tuần sẽ tạo ra khoảng 100 giao dịch trong 10 tuần. Trên Ethereum mainnet, 100 giao dịch có thể tốn hàng trăm đô phí gas tuỳ trạng thái mạng. Trên Avalanche C-Chain, con số tương tự dưới 1 đô - Điều này đặc biệt quan trọng với thị trường Việt Nam

**Thời gian hoàn tất giao dịch**: Avalanche xác nhận trong vài giây, không phải vài phút. Điều này quan trọng cho trải nghiệm: người dùng bấm "đóng hụi", chờ 2-3 giây thấy xác nhận, không phải chờ 15-30 giây rồi không biết giao dịch đã vào chưa.

**USDC bản địa**: Circle phát hành USDC trực tiếp trên Avalanche C-Chain (không phải wrapped từ chuỗi khác). Điều này loại bỏ rủi ro de-peg từ bridge và đơn giản hoá kế toán. Hụi Việt Nam vốn tính bằng VND; USDC là lớp trung gian ổn định nhất hiện có on-chain.


### 3. Tiền lãi / Yield đến từ đâu?

Có hai nguồn hoàn toàn tách biệt:

**Nguồn 1 — lãi đấu giá (nằm trong contract)**. Người cần tiền sớm kêu giá (bidding), tức là chấp nhận nhận ít hơn `n×A`. Khoản chiết khấu đó không biến mất — nó được phân bổ cho những người nhận muộn hơn dưới dạng họ chỉ phải đóng `A - d` thay vì `A`. Hệ thống là zero-sum: tổng lợi nhuận ròng của tất cả thành viên cộng lại bằng 0. Đây không phải lãi từ bên ngoài vào — đây là sự phân bổ lại trong nhóm.

Mức tối đa của `d` bị chặn bởi trần 20%/năm (Quy định của Bộ luật Dân sự và Nghị định 19/2019/NĐ-CP), được cưỡng chế trong `maxBid()` ngay trong contract.

**Nguồn 2 — Yield trên số dư nhàn rỗi (ngoài contract, bonus)**. Giữa các kỳ, tiền trong contract chưa được phân phối. Nếu gửi vào lending protocol như Aave hay Benqi trên Avalanche, phần đó sinh yield. Hiện tại contract có hàm `noteYield()` để ghi nhận yield từ adapter bên ngoài, nhưng không tự đầu tư — đó là quyết định thiết kế có chủ đích (giảm rủi ro, đơn giản hoá audit).

Phần này được tích hợp vào frontend qua DefiLlama API: dashboard hiển thị top 3 pool trên Avalanche theo APY, **gợi ý**, và người dùng hoặc admin **bấm nút** để đẩy tiền đi (HITL — Human in the Loop). Quyết định đầu tư không được tự động hoá.

---

## Phân tích pháp lý Việt Nam

### 1.Khung pháp lý về hụi

**Nghị định 19/2019/NĐ-CP** (ngày 19/02/2019, hiệu lực 01/04/2019) quy định về hụi, họ, biêu, phường. Đây là văn bản pháp lý chính điều chỉnh hoạt động này.

Các điểm quan trọng nhất với dự án:

**Quy định về hình thức**: Điều 6 Nghị định 19/2019 yêu cầu dây hụi có giá trị từ 100 triệu đồng trở lên phải lập thành văn bản, có chữ ký của tất cả thành viên, và phải được công chứng hoặc chứng thực trong một số trường hợp. Với hụi on-chain, smart contract thay thế văn bản, và chữ ký số (giao dịch blockchain) thay thế chữ ký tay — nhưng hiện tại pháp luật Việt Nam chưa công nhận tường minh sự tương đương này.

**Giới hạn lãi suất**: Bộ luật Dân sự 2015, Điều 468 chặn lãi suất thỏa thuận ở mức 20%/năm (tính trên dư nợ thực tế). Dự án cưỡng chế giới hạn này ngay trong hàm `maxBid()`:

```
d ≤ A × 20% × period / YEAR
```

Tức là `maxBid() = contribution × 2000 × period / (10_000 × YEAR)`. Mọi giá kêu vượt trần bị `revert` ngay tại contract, không để người dùng vô tình vi phạm pháp luật.

**Quy định về khai báo**: Theo Điều 14 Nghị định 19/2019, dây hụi từ 100 triệu đồng trở lên phải được thông báo với UBND cấp xã nơi chủ hụi cư trú. Chúng tôi đưa ra phương án: **hệ thống chỉ cung cấp dịch vụ hụi với tổng giá trị ở mức trần 3.500 USDC**, được cưỡng chế ngay trong contract.

```
totalPool = memberCount × contribution        (pot mỗi vòng)
trần:     totalPool ≤ 3.500 USDC
quy đổi:  3.500 × 25.000 = 87.500.000 VND < 100.000.000 VND  ✓
```

Mọi dây vượt trần bị `revert ExceedsLegalLimit()` ngay khi khởi tạo, nên không dây nào vận hành qua hệ thống chạm ngưỡng phải khai báo. Frontend hiển thị giá trị quy ra VND và cảnh báo trước khi tạo.


### Giới hạn pháp lý rõ ràng của dự án


Thứ nhất, **Hợp đồng thông minh chưa được công nhận tường minh trong luật hụi Việt Nam**. Nếu xảy ra tranh chấp, toà án có thể không công nhận smart contract thay thế hợp đồng văn bản theo Nghị định 19/2019.

Thứ hai, **USDC chưa phải đồng VND**. Quy định về hụi viết bằng VND; hụi bằng USDC là vùng pháp lý xám.

Thứ ba, **Nghị định 19/2019 yêu cầu khai báo dây ≥ 100 triệu VND**. Chúng tôi xử lý bằng cách đặt trần hard trong contract: tối đa 3.500 USDC per dây (≈ 87.5 triệu VND). Nếu người dùng muốn dây lớn hơn (khi deploy mainnet), khai báo là trách nhiệm của họ — contract không can thiệp vì UBND không có API.

Thứ tư, **Không có cơ chế giải quyết tranh chấp off-chain**. Nếu có lỗi kỹ thuật trong contract, không có cơ quan nào can thiệp được — đây vừa là ưu điểm (không ai kiểm soát) vừa là rủi ro (không ai sửa được). Tuy nhiên các giao dịch hoàn toàn có thể được truy xuất bằng Trình duyệt khối Snowtrace của Avalanche

---