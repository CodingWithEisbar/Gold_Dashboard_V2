# Nguồn và quyền dữ liệu

Khảo sát ban đầu **06/11/2026, Asia/Ho_Chi_Minh**; bổ sung Bảo Tín Mạnh Hải **08/11/2026**. Khả năng xem trang không phải quyền thu thập/lưu/tái phân phối. robots.txt không phải giấy phép.

| Nguồn | Live API | Historical API | CSV | Trạng thái |
|---|---|---|---|---|
| SJC | Chưa xác minh API được cấp phép | Chưa xác minh | Có, nếu được quyền | BLOCKED tự động |
| PNJ | Trang JS công khai; chưa xác minh API được cấp phép | Chưa xác minh | Có, nếu được quyền | BLOCKED tự động |
| Vietcombank | Trang niêm yết; chưa xác minh quyền tự động | Chưa xác minh | Có, phải ghi đúng convention | BLOCKED tự động |
| Metals.Dev spot | Adapter endpoint được tài liệu hóa, tắt mặc định | Timeseries có tài liệu, chưa tích hợp backfill | Có | Cần subscription, key và xác nhận quyền |
| FX reference_mid | Chưa chọn API có contract/đơn vị đã kiểm chứng | Chưa xác minh | Có | manual-fx |
| GiaVangVietNam.com | Có hướng dẫn widget; chưa xác minh API JSON được cấp phép | Có trang biểu đồ, chưa có historical API được xác minh | Chỉ khi có quyền | Chưa bật ingestion; [khảo sát chi tiết](SOURCE_RESEARCH_GIAVANGVIETNAM.md) |
| Bảo Tín Mạnh Hải | Adapter HTTP HTML Kim Gia Bảo 24K đã triển khai, tắt mặc định; chưa có xác nhận quyền của operator | Có biểu đồ/nhãn Export Excel, chưa xác minh tải và quyền backfill | Có, catalog BTMH riêng; yêu cầu quyền và chuẩn hóa đúng | Cần xác nhận quyền/đơn vị/timezone; [job VPS](BTMH_VPS_JOB.md), [khảo sát](SOURCE_RESEARCH_BAOTINMANHHAI.md) |

SJC [giá niêm yết](https://www.sjc.com.vn/gia-vang-online), PNJ [trang giá](https://giavang.pnj.com.vn/) truy cập được; PNJ chỉ trả shell JS qua công cụ đọc. Thử đọc robots tại ba host qua web tool không thành công. Không suy ra “được phép” hoặc “bị cấm” từ lỗi này. Không thử endpoint ẩn, CAPTCHA hoặc bot bypass. Chưa có bằng chứng hợp đồng của người dùng; adapter tự động cho các nguồn này không được bật.

Vietcombank [trang tỷ giá](https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-tien-ich/Ty-gia) phân biệt mua tiền mặt, chuyển khoản, bán. MVP chỉ nhận **reference_mid** qua CSV; không đổi tên tỷ giá bán VCB thành mid. Nếu cần bank_sell phải bổ sung convention/series, migration và kiểm thử trước khi dùng.

[Metals.Dev docs](https://www.metals.dev/docs) mô tả endpoint spot với USD/toz, price và timestamp. Adapter chỉ đọc spot gold, kiểm tra currency/unit/metal/schema, giữ Decimal và hash. [Terms](https://www.metals.dev/policy/terms) cho phép hiển thị rates trên website khi subscription còn hiệu lực, hạn chế bán lại/tạo API cạnh tranh. Người vận hành phải xác nhận quyền lưu dài hạn và việc API dashboard có phù hợp hợp đồng; không tự hiểu một API key là quyền sử dụng vô hạn.

[Pricing](https://www.metals.dev/pricing) có Bronze 2.000 requests/tháng, 4,99 USD/tháng tại lúc đọc; docs nói các endpoint được mở ở các gói và timeseries giới hạn 30 ngày/request. Đây là thông tin khảo sát, không đăng ký hoặc thanh toán. Chưa có key nên chưa xác minh entitlement/response/quota thực tế. Ví dụ FX trong docs có giá trị VND gây mơ hồ về scale/direction; không tích hợp FX tự động bằng cách suy đoán hoặc nghịch đảo.

Để bật spot sau khi có quyền:

```bash
docker compose exec worker python -m app.jobs.catalog --license-metals --license-note "Hợp đồng tham chiếu nội bộ; quyền lưu/hiển thị và kỳ hạn đã được xác minh"
```

Đặt `XAU_API_KEY` và `METALS_LICENSE_CONFIRMED=true` qua Secrets Provider của Dokploy, redeploy worker. Cần cả catalog approval và biến cấu hình; API reader không chứa key.

CSV UTF-8 header chính xác:

```csv
kind,provider_id,product_id,provider_timestamp,bid,ask,value,unit,reference_type
```

Không có ví dụ giá thật được tự điền. `gold`: bid/ask, product và unit VND/luong; `spot`: value USD/troy_oz, source manual-spot; `fx`: value VND/USD, source manual-fx, convention reference_mid. Timestamp bắt buộc có offset. Tiền dùng chuỗi số không dấu phân cách, tối đa 8 số lẻ. Giới hạn 2MiB/10.000 rows, import root chống traversal/symlink thoát root; toàn bộ batch atomic. `--confirm-data-rights` là xác nhận của operator về quyền lưu và hiển thị. Provenance nguồn gốc/chứng từ nên lưu ngoài repo trước khi nhập; URL catalog không chứng minh một CSV đã được nhà cung cấp xác nhận.

Không seed quotes, không backfill bằng nội suy. Lịch sử bắt đầu từ observation/import thật đầu tiên. Sample chỉ nằm trong sample-data, luôn gắn nhãn và bị chặn ở production; readiness cũng fail nếu production database chứa sample.
