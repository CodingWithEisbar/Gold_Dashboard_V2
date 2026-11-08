# Khảo sát GiaVangVietNam.com · 06/11/2026

Theo hai URL người dùng cung cấp: [giá vàng nội địa](https://giavangvietnam.com/gia-vang/) và [giá vàng thế giới](https://giavangvietnam.com/gia-vang-the-gioi/). Mục tiêu là tìm feed hợp lệ cho tracker và simulator, không lấy HTML làm dữ liệu lịch sử tự động.

## Kết quả

| Nhu cầu | Bằng chứng | Kết luận hiện tại |
|---|---|---|
| Hiển thị giá động | Website có [hướng dẫn widget miễn phí](https://giavangvietnam.com/huong-dan-chen-gia-vang-bieu-do-gia-vang-vao-website/) và [demo](https://cls.giavangvietnam.com/demo.html), loader được công bố `https://cls.giavangvietnam.com/js/widget.js` | Có phương án nhúng theo hướng dẫn; chưa tích hợp vào CSP của app |
| API JSON backend | Chưa tìm thấy tài liệu API developer, authentication, quota hoặc hợp đồng lưu trữ | Không coi endpoint mà trang tự gọi là public API được cấp phép |
| Lưu snapshot/backtest | [Điều khoản mục 3](https://giavangvietnam.com/dieu-khoan-su-dung/) giới hạn việc tái sử dụng và lưu nội dung ngoài truy cập dịch vụ thông thường | Cần xác nhận quyền bằng văn bản hoặc hợp đồng cho nghiệp vụ này |
| Robots | GET /robots.txt trả 200, Allow / và Disallow /wp-admin/ | Khả năng crawl không thay thế quyền dùng dữ liệu |
| Lịch sử | Có các trang biểu đồ lịch sử được liên kết | Không chứng minh có API lịch sử/export hoặc quyền backfill |

Đã đọc một lần HTML của hai trang và robots để kiểm tra khả năng truy cập, không gọi endpoint nội bộ, không chạy scheduler hoặc ghi market quotes vào database. Trong HTML nội địa nhận được, bảng giá mang nhãn cập nhật **13:10:04 07/05/2025**, trong khi nội dung khác trên cùng trang có mốc mới hơn. Kết quả search/cache cũng khác bản đọc trực tiếp. Không coi mọi giá trong HTML là giá realtime. Cần xác minh timestamp của từng series từ feed được cho phép; đồng hồ của phần crypto/footer không phải timestamp giá vàng.

Kiểm tra riêng loader được công bố: GET `https://cls.giavangvietnam.com/js/widget.js` trả **HTTP 200**, `application/javascript`, 20.457 bytes, không redirect. Đây là bằng chứng script còn truy cập được, chưa chứng minh mọi feed bên trong widget có dữ liệu mới hoặc ổn định.

Trang thế giới có XAU/USD và tỷ giá dùng để quy đổi, nhưng chưa xác minh được timestamp riêng và convention FX. Không dùng giá quy đổi/premium hiển thị sẵn làm source of truth; backend vẫn cần spot USD/troy oz, FX VND/USD và bid/ask nội địa đúng sản phẩm/vùng để tính Decimal.

## Phương án cho dự án

1. Nếu chỉ cần xem giá: widget theo hướng dẫn của họ là lựa chọn hiển thị. Widget không tự cung cấp quyền lấy số, lưu PostgreSQL hoặc backtest. Không chèn script bên thứ ba trực tiếp vào app đang có CSP chặt trước khi review; cần kiểm tra tải script, upstream domains, timestamp và phương án cô lập iframe/origin nếu thực hiện.
2. Để hoàn tất tracker/simulator: xin API/feed JSON và quyền lưu/hiển thị/lịch sử từ nhà cung cấp. Ghi provenance là GiaVangVietNam tổng hợp, không giả danh feed trực tiếp từ SJC/PNJ. Không trộn dữ liệu qua aggregator với series SJC/PNJ hiện có nếu chưa được định danh và reconciliation.
3. Nếu chưa có thỏa thuận: giá domestic/FX dùng CSV có quyền; spot có thể dùng adapter Metals.Dev đã có sau khi xác nhận subscription/key/quyền sử dụng. Không tự mở backfill hoặc production ingestion từ website này.

## Nội dung yêu cầu API có thể gửi thủ công

Liên hệ qua [trang liên hệ chính thức](https://giavangvietnam.com/lien-he/):

> Tôi xây dựng ứng dụng theo dõi vàng và mô phỏng đầu tư. Bên bạn có API/feed JSON cho bid/ask từng sản phẩm SJC/PNJ theo vùng, XAU/USD và USD/VND không? Tôi cần timestamp có timezone, định nghĩa đơn vị và FX, quota/chi phí, quyền lưu snapshot lâu dài, hiển thị lại và dùng dữ liệu lịch sử/backtest. Xin cung cấp tài liệu và điều kiện cấp phép.

Chưa gửi tin nhắn hoặc liên hệ thay người dùng. Kết quả khảo sát này không bật nguồn mới, không thay đổi runtime đã qua security gate.
