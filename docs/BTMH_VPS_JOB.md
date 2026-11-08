# Chạy job Bảo Tín Mạnh Hải trên VPS / Dokploy

Code nằm cùng repository, chạy trong service `worker` bằng Dokploy Compose Schedule Job. Không có scheduler trong FastAPI, không dùng Colab và không mở cổng ghi dữ liệu ra Internet. Hướng dẫn này không phải bằng chứng đã triển khai lên VPS của bạn.

## 1. Chuẩn bị và bật nguồn

Deploy theo [hướng dẫn Dokploy](DOKPLOY_DEPLOYMENT.md). Release mới phải chạy lại service `migrate` để nâng schema tới `c9d4ef202601` (thêm `data_sources.next_poll_after`) và seed catalog metadata BTMH, không seed giá. Migration thêm cột nullable, tương thích code cũ khi rollback image; không cần downgrade/xóa lịch sử. Worker phải đang running/healthy vì Dokploy thực thi job bằng Docker exec. Không thay `COMPOSE_PROJECT_NAME` do Dokploy quản lý.

Xác nhận quyền thu thập tự động, lưu lịch sử và hiển thị/phân tích lại với nhà cung cấp. Xác minh **riêng Kim Gia Bảo 24K**: đơn giá nghìn VND/chỉ, timestamp dùng giờ Việt Nam. Không coi robots Allow là giấy phép, không bật flags theo phỏng đoán. Các cấu hình dưới đây là bước operator chỉ thực hiện sau khi đã có xác nhận.

Ghi nhận xác nhận trong catalog bằng CLI nội bộ (ghi tham chiếu chứng từ, không ghi secrets):

```bash
docker compose exec -T worker python -m app.jobs.catalog \
  --license-btmh --license-note "THAY_BANG_THAM_CHIEU_XAC_NHAN_QUYEN_LUU_VA_HIEN_THI"
```

Nếu quản trị bằng Dokploy Terminal của worker thì bỏ tiền tố `docker compose exec -T worker`. Dùng đúng project/file/env do Dokploy quản lý khi chạy SSH; không vô tình tạo một Compose project mới. Lệnh trên chỉ ghi nhận của operator, không tự cấp quyền từ BTMH.

Đặt các biến sau trong Environment của Compose trên Dokploy, rồi redeploy worker:

```dotenv
BTMH_ENABLED=true
BTMH_LICENSE_CONFIRMED=true
BTMH_CONVENTIONS_CONFIRMED=true
BTMH_MIN_INTERVAL_MINUTES=30
BTMH_MAX_AGE_HOURS=24
SOURCE_ALLOWLIST=api.metals.dev,baotinmanhhai.vn
REQUEST_TIMEOUT_SECONDS=10
```

Ba cờ BTMH mặc định false; catalog mặc định unverified. Thiếu bất kỳ xác nhận nào sẽ chặn network fetch. Không cần API key cho adapter HTML BTMH. XAU_API_KEY vẫn chỉ cần nếu dùng nguồn thế giới Metals.Dev; không đưa key vào `VITE_*` hoặc commit `.env`.

## 2. Chạy thử trước khi đặt lịch

```bash
docker compose exec -T worker python -m app.jobs.collect_daily --source btmh
```

Chỉ coi lần đồng bộ là thành công nếu exit **0**, log `status=success` và kiểm tra được `provider_id=btmh`, `observed_at` nguồn, `inserted/duplicates/quarantined` cùng giá chuẩn hóa. Exit **2** báo nguồn/database lỗi hoặc quarantine. `status=skipped` exit 0 nghĩa là một job khác đang chạy hoặc chưa đủ khoảng cách giữa hai lần poll; không phải một lần lấy giá mới thành công. Chờ hết interval trước khi thử lại; không đổi timestamp hoặc xóa run để ép gọi nguồn.

Default `python -m app.jobs.collect_daily` kiểm tra toàn bộ nguồn và vẫn có thể exit 2/3 vì SJC/PNJ/FX/Metals còn thiếu. Dùng `--source btmh` cho lịch BTMH để không nhầm thiếu nguồn khác với lỗi crawler BTMH.

## 3. Tạo Schedule Job trên Dokploy

Theo [tài liệu Schedule Jobs chính thức](https://docs.dokploy.com/docs/core/schedule-jobs):

| Trường | Giá trị |
|---|---|
| Tên | `collect-btmh` |
| Loại | Compose Job |
| Compose/service | Project của ứng dụng / `worker` đang running |
| Command | `python -m app.jobs.collect_daily --source btmh` |
| Cron nếu scheduler UTC | `*/30 1-11 * * *` |
| Cron nếu chọn được timezone Asia/Ho_Chi_Minh | `*/30 8-18 * * *` |

Chọn **một** cách theo timezone đã xác minh trong UI; xem **Next run** phải khớp giờ Việt Nam. Lịch gợi ý chạy mỗi 30 phút, 08:00–18:30 VN, 22 lượt/ngày nếu mọi lượt đều được chạy. Tần suất phải nằm trong quyền/quota nguồn; tăng interval và giảm lịch nếu nhà cung cấp yêu cầu. Biến `BTMH_INGESTION_CRON` trong `.env.example` chỉ là tham chiếu, không tự tạo Schedule Job.

Giữ job thế giới/FX riêng theo quyền và quota. Không cần cài cron/systemd hoặc thêm vòng lặp Python trong worker khi đã dùng Dokploy. Chỉ tạo một lịch BTMH; job có khóa transaction PostgreSQL chống chạy đồng thời và kiểm tra run gần nhất để hạn chế gọi quá dày, kể cả sau restart hoặc lần thất bại.

## 4. Dữ liệu và giám sát

- Source `btmh`, product `btmh-kgb-24k-listed`, location `BTMH_LISTED` nghĩa là giá bảng niêm yết chưa tách vùng; không giả định là HCM/Hà Nội hoặc gộp với SJC/PNJ trực tiếp.
- Chỉ nhập Kim Gia Bảo 24K, purity 99.99%, đủ bid/ask. Không nhập Gift, Tiểu Kim Cát, bạc hoặc dòng thiếu giá bán. Giá chuẩn hóa VND/lượng bằng Decimal; 1 đơn vị nghìn VND/chỉ nhân 10.000.
- Timestamp gốc không có offset: adapter chỉ gắn Asia/Ho_Chi_Minh sau cờ xác nhận convention. Giữ provider timestamp khác fetched_at; dữ liệu quá `BTMH_MAX_AGE_HOURS` hoặc tương lai hơn 5 phút bị từ chối.
- `raw_payload_hash` là SHA-256 của các trường báo giá gốc được trích xuất cùng đơn vị/timezone và giá chuẩn hóa, **không phải toàn trang HTML**. Tin tức, quảng cáo hoặc sản phẩm khác đổi sẽ không gây duplicate conflict giả. Sửa giá tại cùng timestamp vẫn bị chặn để đối chiếu. Parser version có trong log mỗi run; không lưu hoặc thực thi HTML/JavaScript vào database.
- Daily reference vẫn lấy snapshot hợp lệ cuối cùng tại/trước 18:00 VN trong cửa sổ 120 phút. Báo giá sau 18:00 vẫn được lưu nhưng không dùng thay giá chốt. Không lấy timestamp fetch để lách cutoff, không carry ngày cũ sang ngày mới.
- Giá nhảy bất thường bị quarantine và job exit 2. Khi gọi lại đúng snapshot quarantine, vẫn báo quarantine, không chuyển thành thành công vì duplicate.
- Theo dõi log JSON, Schedule Job failure notifications, `GET /api/v1/data-sources/status`, và `GET /api/v1/quotes/latest?product_id=btmh-kgb-24k-listed`. API read-only có thể public theo cấu hình HTTPS hiện có; DB/worker không có host port.
- Snapshot được lưu trong volume PostgreSQL. Backup/restore và retention dùng [runbook hiện có](BACKUP_RESTORE.md); không dùng Git làm kho lịch sử thị trường.
- Nếu nguồn lỗi, có thể nhập CSV đã được quyền: `provider_id=btmh`, `product_id=btmh-kgb-24k-listed`, `unit=VND/luong`, `reference_type=manual`; giá đã chuẩn hóa, timestamp có offset. Dùng CLI import và xác nhận quyền theo [DATA_SOURCES](DATA_SOURCES.md), không đưa HTML/JSON tùy ý vào database.

HTTP chỉ gọi robots và `/bang-gia-vang` trên hostname cố định: kiểm tra public DNS, pin IP/Host/SNI và TLS, không redirect/proxy môi trường. Mỗi request tối đa 3 lần thử; có timeout, giới hạn response 2MiB cho HTML / 16KiB cho robots, giới hạn độ phức tạp HTML, backoff+jitter. `Retry-After` quá ngân sách 10 giây làm job dừng và lưu `next_poll_after` vào PostgreSQL; các lịch tiếp theo và container sau restart vẫn phải chờ hết thời hạn này. Trạng thái chờ hiện qua API source status và log `skipped/provider_retry_after_active`. Kiểm tra robots mỗi lần chạy; robots cấm hoặc không đọc được thì không tải bảng giá.

Các lỗi đáng chú ý: `license_not_approved_in_catalog`, `source_disabled`, `data_rights_not_confirmed`, `units_or_timezone_not_confirmed`, `robots_disallowed`, `provider_schema_changed`, `provider_data_stale`, `price_jump_requires_review`. Kiểm tra nguồn, đơn vị và điều khoản; không bypass CAPTCHA hoặc tự nới parser để làm job xanh.

## 5. Dừng và rollback

Disable lịch `collect-btmh` trước, đặt `BTMH_ENABLED=false` và redeploy worker. Thu hồi xác nhận catalog khi cần:

```bash
docker compose exec -T worker python -m app.jobs.catalog --revoke-btmh
```

Run đang thực thi có thể hoàn tất trước khi thu hồi; muốn dừng ngay cần dừng worker theo quy trình vận hành. Thu hồi không xóa lịch sử đã có. Rollback image digest đã quét, giữ volume, chạy health/smoke; không `down -v`. Khi rollback runtime về trước migration mới, giữ migrator mới hoặc không chạy migrator cũ: Alembic trong image cũ không biết revision `c9d4ef202601`, dù cột nullable mới vẫn tương thích API/worker cũ. Không redeploy toàn bộ Compose cũ rồi mặc định migration sẽ thành công. Chưa có domain/VPS/Dokploy credentials nên chưa xác minh HTTPS, lịch thực tế hoặc quyền nguồn từ phiên triển khai này.
