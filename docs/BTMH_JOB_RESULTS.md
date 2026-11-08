# Kiểm chứng job BTMH · 08/11/2026

Đã triển khai adapter và CLI cho worker trên VPS/Dokploy; đã build và chạy kiểm chứng trên **Docker Linux local**, chưa triển khai lên VPS của người dùng. Nguồn vẫn tắt mặc định. [Hướng dẫn bật nguồn và đặt lịch](BTMH_VPS_JOB.md).

## Phần đã hoàn thành

- Adapter HTTP HTML chỉ lấy **Kim Gia Bảo 24K** vào source/product riêng, Decimal VND/lượng; tách bảng vàng/bạc, Gift, Tiểu Kim Cát và dòng thiếu ask. Sai header/cấu trúc, đơn vị, purity, timestamp hoặc giá sẽ dừng.
- CLI `python -m app.jobs.collect_daily --source btmh`: log JSON, tần suất tối thiểu, advisory transaction lock chống job chồng nhau, idempotency qua database, quarantine và daily reference trước 18:00 VN.
- Catalog ghi nhận/thu hồi quyền nguồn; ba flags BTMH chặn fetch trước khi có xác nhận quyền và convention. Giới hạn DNS/IP public, Host/SNI/TLS pin, fixed URLs, robots, response size/HTML complexity, timeout/retry/backoff/Retry-After; không thực thi JS của nguồn.
- Migration `c9d4ef202601`: cột nullable `data_sources.next_poll_after` giữ Retry-After qua restart. API source status công bố thời điểm này. Không sửa dữ liệu giá hoặc công thức tài chính.
- Compose chỉ đưa cấu hình crawler vào worker; PostgreSQL/API/worker không publish cổng. CI có smoke test CLI bị chặn đúng khi chưa có quyền nguồn. Runbook có cron UTC/VN, dừng nguồn, CSV fallback và lưu ý rollback migrator.

## Kết quả thực tế

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ tests trong Docker Linux + PostgreSQL 18.6 | **130 passed, 0 skipped, 0 failures/errors** |
| Tests trên host khi không đặt TEST_DATABASE_URL | **125 passed, 5 skipped**; 5 PostgreSQL tests đã chạy đầy đủ trên Linux |
| Nginx/API/container/CLI smoke | **10 nhóm pass**, gồm CLI chạy bằng gold_ingestor trong worker thật, nguồn unverified ghi trạng thái lỗi và không tạo market quote |
| Browser qua Nginx thật | **8 nhóm pass**, desktop 1440px / mobile 390px, không JS/CSP error |
| Ruff backend/tests/migrations/smoke | Pass |
| Compose production/local/backup/release | Pass; private networks/ports, flags chỉ ở worker, release digest-only |
| pip-audit runtime lockfile | **0 known vulnerabilities** tại thời điểm kiểm tra |
| Gitleaks source | **0 leaks** |
| Trivy 0.76.2 final images + SBOM | **4 images, 0 High/Critical**; không ignore/ignore-unfixed; SBOM cả 4 pass |
| Transport thật tới `/robots.txt` | Pass public-IP pin + TLS/Host/SNI; không gọi bảng giá trong phép kiểm tra này |
| Parser trên HTML công khai đã khảo sát | Trích đúng một quote; timestamp giữ nguyên; **không nhập vào database** |

Trivy database `UpdatedAt=2026-11-07T12:52:01Z`, tải ngày 08/11/2026 giờ Việt Nam; scan final revision sau build. Có một warning deprecation Starlette TestClient/httpx trong bộ test, không làm test thất bại. Không thay dependency theo warning này.

Test fixtures là dữ liệu tổng hợp có nhãn **SAMPLE DATA — NOT REAL MARKET DATA**, chỉ dùng trong database test riêng. Các kiểm thử cover parse/đơn vị, đổi thứ tự cột, HTML malformed/oversized, dữ liệu cũ/tương lai, thiếu giá, HTTP timeout/429/503/redirect/private DNS, retry cuối cùng và Retry-After dài, duplicate/conflict/quarantine, cutoff, PostgreSQL role/lock, migration up/down/dump-restore, API và same-day P&L theo ask/bid.

Các local image IDs được ghi trong [verification-summary.json](../artifacts/btmh-job/verification-summary.json). Đây không phải remote registry RepoDigests; chưa push images hoặc xác minh VPS pull. Raw scans, SBOM, JUnit, smoke, browser và source-parse evidence nằm trong `artifacts/btmh-job/`; bằng chứng security gate ngày 06/11 vẫn giữ riêng trong `artifacts/security-gate/`.

## Chạy lại

Trên máy có Docker Linux và các scanner theo CI, dùng runner hiện có (project test riêng, không cần credentials production):

```bash
python -m ruff check --config backend/pyproject.toml backend/app backend/tests backend/migrations
python infra/security_gate.py prepare
python infra/security_gate.py build
python infra/security_gate.py start
python infra/security_gate.py test
python infra/container_smoke.py --base-url http://127.0.0.1:18080 --project-name gold-security-gate --env-file .tools/security-gate/.env --compose-file compose.yaml --compose-file .tools/security-gate/compose.gate.yaml --check-btmh-job --report artifacts/security-gate/container-smoke.json
python infra/security_gate.py scan
python infra/security_gate.py stop
```

Phiên kiểm chứng này dùng tên riêng `gold-btmh-gate` cùng logic runner để giữ nguyên bằng chứng của lần trước. Container và network test được dừng sau kiểm chứng; giữ volume test để đối chiếu, không xóa volume ứng dụng.

## Chưa được xác minh

Chưa có quyền truy cập VPS/Dokploy/domain/registry, chưa có chứng từ quyền dữ liệu hoặc xác nhận đơn vị/timezone từ operator. Chưa bật lịch production hay thu thập thị trường định kỳ, chưa lấy lịch sử qua Export Excel, chưa xác minh HTTPS/S3 trên VPS. XAU/USD và FX vẫn cần nguồn/quyền/credentials riêng; chưa thể gọi premium là đồng bộ đầy đủ khi thiếu các nguồn đó. Không có lịch sử thị trường được bịa hoặc seed.
