# Khảo sát Bảo Tín Mạnh Hải · 08/11/2026

**Cập nhật triển khai:** adapter và CLI job đã được thêm vào worker, tắt mặc định; xem [hướng dẫn VPS](BTMH_VPS_JOB.md). Các đoạn dưới ghi lại kết quả khảo sát trước khi viết adapter, không phải trạng thái runtime mới hoặc bằng chứng VPS đã deploy.

## Kết luận

Có thể xây dựng adapter HTTP đọc [bảng giá chính thức](https://baotinmanhhai.vn/bang-gia-vang) để cung cấp giá nội địa cho tracker. Không bắt buộc có API JSON: response HTML công khai đã chứa tên sản phẩm, hàm lượng, mua vào, bán ra và thời điểm cập nhật. Đây là kiểm chứng tính khả thi, chưa phải nguồn ingestion production đã được triển khai hoặc được xác nhận quyền sử dụng.

## Bằng chứng truy cập

Đọc một lần mỗi URL bằng HTTP GET, không đăng nhập, không theo redirect, không gọi endpoint nội bộ hoặc vượt cơ chế chống bot:

| URL | Kết quả |
|---|---|
| `https://baotinmanhhai.vn/robots.txt` | HTTP 200, text/plain, 69 bytes; `User-agent: *`, `Allow: /` |
| `https://baotinmanhhai.vn/bang-gia-vang` | HTTP 200, text/html, 235.517 bytes; có giá và timestamp trong HTML |

Parser HTML chuẩn Python đã đọc được phần giá, đơn vị và timestamp mà không thực thi JavaScript. Bản đọc có mốc **2026-11-07 18:43:38.0**, không có offset timezone. Giữ nguyên timestamp gốc và thời điểm fetch riêng; xác minh quy ước giờ của nhà cung cấp trước khi chuẩn hóa thành Asia/Ho_Chi_Minh. Ngày fetch không thay thế ngày giá.

Bản kiểm tra HTTP, HTML và kết quả trích xuất nằm trong `.tools/source-research/btmh/`, được gitignore. Không nhập các giá khảo sát vào database ứng dụng. robots Allow không phải giấy phép lưu, tái phân phối hoặc sử dụng thương mại. Chưa tìm thấy tài liệu API công khai hay điều kiện cấp quyền dữ liệu trong những trang đã khảo sát; không suy ra rằng API không tồn tại hoặc việc tái sử dụng đã được cho phép. Xác nhận phạm vi sử dụng qua [kênh chính thức](https://baotinmanhhai.vn/ve-chung-toi) trước khi bật thu thập định kỳ và công bố lại.

## Kiểm soát ý nghĩa dữ liệu

- Bảng ghi **Đơn giá (nghìn VNĐ)** và **ĐVT: chỉ**. Dòng Kim Gia Bảo 24K có mua `13.650`, bán `14.050`: quy đổi lần lượt thành 13.650.000 và 14.050.000 VND/chỉ, sau đó nhân 10 để lưu VND/lượng. Đây là bản quan sát mang timestamp trên, không tuyên bố là giá hiện tại.
- Dòng Tiểu Kim Cát có mức thấp hơn 10 lần; cùng trang liên kết sản phẩm **0,1 chỉ** có giá tương ứng. Có dấu hiệu đơn vị theo sản phẩm khác nhãn chung: loại khỏi MVP đến khi xác minh denominator, không tự suy luận multiplier bằng tỷ lệ giá.
- Một số dòng nguyên liệu/trang sức chỉ có giá mua vào. Giữ thiếu giá bán; không điền 0 hoặc lấy giá của dòng kế bên.
- Kim Gia Bảo Gift, Kim Gia Bảo, Tiểu Kim Cát và trang sức là các series riêng. SJC bán tại BTMH phải có provenance BTMH, không nối vào series giá trực tiếp SJC/HCM hiện tại.
- [Chính sách thu mua lại](https://baotinmanhhai.vn/chinh-sach-doi-tra) mô tả điều kiện theo dòng sản phẩm, tình trạng và tiền công. Mô phỏng phải nêu giả định sản phẩm đủ điều kiện áp dụng giá niêm yết và tính thêm chi phí thực tế; giá bảng không đảm bảo số tiền thanh lý của mọi món vàng.
- Trang có biểu đồ và nhãn **Export Excel**. Chưa thử chức năng tải hoặc xác minh nội dung, timestamp, phạm vi lịch sử và quyền sử dụng; không coi đây là historical API đã kiểm chứng.
- Trang có mục XAUUSD; chưa xác minh feed gốc, timestamp, đơn vị và quyền tái sử dụng. Không lấy một biểu đồ nhúng làm nguồn world spot đã được xác nhận.

## Phương án tích hợp vào dự án

1. Thêm source `btmh` và product Kim Gia Bảo 24K riêng, tắt mặc định cho đến khi operator xác nhận quyền và đơn vị/timezone. Không thay thế catalog hoặc series đã có.
2. Worker tải duy nhất URL HTTPS được cấu hình cố định. Dùng DNS/public-IP validation và kết nối pin IP như adapter hiện có; không mở arbitrary-URL fetch. Giới hạn kích thước, thời gian, retry/backoff và tôn trọng 429/Retry-After. Đề xuất ban đầu 15–30 phút trong khung theo dõi nếu nhà cung cấp cho phép; giảm theo quota và yêu cầu nguồn.
3. Parser dựa trên nhãn sản phẩm/cột và phạm vi phần vàng, không dựa vị trí số toàn trang hoặc thực thi script. Dừng và cảnh báo nếu schema, đơn vị, timestamp, số cột hoặc mapping thay đổi. Kiểm tra Decimal, `ask >= bid`, trùng observation và biến động bất thường bằng ingestion hiện có.
4. Lưu timestamp nguồn, timestamp thu thập, URL, đơn vị gốc/chuẩn hóa, hash và phiên bản parser. Giữ missing/stale rõ ràng. Snapshot sau 18:00 không được đưa ngược vào daily reference 18:00 theo chính sách hiện tại; cần thu thập trước cutoff và ghép XAU/FX đúng cửa sổ.
5. Ghép spot XAU/USD từ nguồn có quyền (adapter Metals.Dev đã có nhưng cần key và xác nhận quyền) và FX **VND/USD reference_mid** đúng convention. Thiếu nguồn hoặc lệch thời điểm thì không công bố premium đồng bộ; không đổi tên bank sell thành mid.
6. Backend tiếp tục tính bằng Decimal: `world_reference = XAU_USD_per_troy_oz * USDVND * 37.5 / 31.1034768`; `premium_pct = (domestic_ask / world_reference - 1) * 100`. Spread là ask trừ bid; P&L dùng ask ngày mua, bid ngày bán và chi phí. Đây là premium tham chiếu, không phải giá nhập khẩu đã bao gồm thuế/phí.
7. Lịch sử bắt đầu từ observation hợp lệ đầu tiên; chỉ backfill nếu có dữ liệu lịch sử thật và quyền phù hợp. Nếu crawl lỗi, ghi thất bại và hỗ trợ CSV; không dùng giá cũ dưới timestamp mới.

Khi triển khai cần test parser với fixture đã được phép lưu: định dạng nghìn, denominator, thiếu ask, sản phẩm lạ, HTML đổi layout, timestamp lỗi/lệch ngày; test HTTP 429, timeout, redirect, oversized response và SSRF; test idempotency, daily cutoff và API provenance. Khảo sát này chỉ thêm tài liệu, không sửa runtime, bật scheduler hoặc tuyên bố đã crawl production.
