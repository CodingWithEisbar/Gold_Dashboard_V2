# Vận hành

## Mỗi ngày

Kiểm tra health/ready, worker/backup health, Dokploy Schedule Job exit status, nguồn lỗi và latest_observed_at. Job hiện trả nonzero nếu nguồn thiếu; `source_unavailable` phải hiện rõ với người vận hành. Không tạo dữ liệu để làm health xanh. DB/app health tách biệt freshness của nguồn.

CSV import là atomic: schema, số lượng, quyền, timestamps, sản phẩm và đơn vị phải đúng. Trùng khóa/cùng hash → duplicates, không thêm snapshot. Khóa cũ/hash khác → reject toàn batch, source ingestion_run failed. Kiểm tra chứng từ/source trước khi nhập lại. Không đổi timestamp giả để né duplicate hoặc quarantine.

Quarantine giá nhảy >20%: đối chiếu chứng từ, đơn vị và báo giá gốc; không tự release vào analytics. Snapshot bất biến. Nếu nhà cung cấp công bố correction có timestamp thực khác thì nhập correction theo timestamp thật. Nếu cần cho phép snapshot quarantine sau review, phải bổ sung bảng quyết định/reviewer và migration/audit trail trước; MVP chủ động fail closed, chưa có public admin release.

Daily selection chạy lại cho các ngày CSV vừa nhập; không chạy vòng lặp scheduler trong API. Ranh giới Việt Nam 00:00 được kiểm thử. Dữ liệu sau giờ chốt hoặc quá sớm vẫn lưu snapshot nhưng không thành daily reference, UI báo missing nếu không có candidate hợp lệ.

## Khi nguồn thay đổi hoặc lỗi

BTMH: xem [job VPS/Dokploy](BTMH_VPS_JOB.md). Dùng `python -m app.jobs.collect_daily --source btmh` trong worker cho lịch riêng; `status=skipped` không phải đã fetch thành công. Parser kiểm tra đúng bảng vàng, thứ tự cột, sản phẩm, purity, đơn vị và timestamp; sai cấu trúc thì dừng. Giá quá cũ không được gắn ngày mới. Source license trong catalog và ba cờ xác nhận phải đầy đủ trước HTTP; tắt lịch/flag hoặc `catalog --revoke-btmh` để dừng những lần chạy tiếp theo. Giữ failure alert cả khi duplicate vẫn thuộc quarantine.

Parser Metals.Dev sai status/unit/schema → source_unavailable, không ghi số. Retry tối đa 3 lần, backoff+jitter, timeout 10s, response cap 256KiB, redirect tắt. Nếu quota sắp hết: giảm lịch ở Dokploy hoặc tạm tắt provider; không thêm vòng retry vô hạn. Domestic/FX vẫn import CSV có quyền. Không bypass robots/CAPTCHA để “sửa” lỗi nguồn.

## Update / rollback

1. Lưu source commit, image digests, schema revision và backup trước deploy. Tạo backup mới và kiểm tra list/hash.
2. Chạy CI đầy đủ, quét lockfile + final image; không chấp nhận High/Critical chưa được xử lý. Đọc release notes base image/PostgreSQL.
3. Deploy vào môi trường staging riêng, migration và smoke; kiểm tra nguồn thiếu/sample/observed/scenario đúng nhãn, CSV export, TLS/CSP.
4. Deploy production theo digest; `migrate` hoàn tất trước API. Recreate service migrate nếu Compose/Dokploy reuse container đã completed từ release trước; kiểm tra schema revision, không chỉ container cũ exit 0.
5. Lỗi app/schema tương thích → rollback image digest và smoke. Schema không tương thích → dừng ingestion, restore vào DB/volume mới, kiểm tra và chuyển traffic theo kế hoạch. Không `docker compose down -v`, không downgrade DB major tự động.

## Sự cố secrets / host

Thu hồi và rotate key/password ở nguồn quản lý, redeploy service có liên quan, audit access/logs. Quét Git history bằng gitleaks khi có commits; repo ban đầu chưa có commit nên không thể chứng nhận lịch sử từ xa. Không đưa secret vào issue, screenshot hay support message. Cập nhật host/kernel/Docker/Dokploy thường xuyên, SSH keys-only, Dokploy 2FA/VPN, disk alerts cho PG volume và backups.

## Lệnh kiểm tra

```bash
docker compose ps
docker compose logs --tail=100 api worker migrate
docker compose exec worker python -m app.jobs.collect_daily
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready').status)"
```

Không chạy `docker compose config` không filter trong log public vì output có thể chứa environment/secrets. Dùng `config --quiet`; kiểm tra nội bộ config đã redacted khi cần.
