# Gold Premium Tracker & Investment Simulator

Ứng dụng Vue 3 + TypeScript / FastAPI / PostgreSQL, tính toán tài chính bằng Decimal ở backend. Giao diện tiếng Việt gồm Tổng quan, Premium, Mô phỏng lịch sử, Phòng kịch bản và Dữ liệu & nguồn.

**Trạng thái:** source code đã được triển khai và có kiểm thử thực tế; chưa triển khai VPS. Database production khởi tạo không có báo giá. SJC/PNJ và FX tự động còn bị khóa vì chưa xác minh quyền sử dụng; Metals.Dev cần hợp đồng/subscription và API key. Xem [báo cáo kiểm chứng](docs/IMPLEMENTATION_STATUS.md) để phân biệt phần đã chạy và phần còn chờ.

Đã bổ sung **job crawl BTMH trên worker**, tắt mặc định: xem [hướng dẫn VPS/Dokploy](docs/BTMH_VPS_JOB.md) và [kết quả 130 tests Linux/PostgreSQL cùng final image scans](docs/BTMH_JOB_RESULTS.md). Lệnh riêng `python -m app.jobs.collect_daily --source btmh`; chỉ bật sau khi xác nhận quyền và convention đơn vị/timezone. Không có giá BTMH thật được seed vào database.

## Chạy local bằng Docker Compose

Cần Docker Engine/Desktop chạy Linux containers và Docker Compose. Secrets dùng file để tương thích root filesystem read-only. Chạy từ thư mục repository:

```bash
python infra/init-local-env.py
docker compose -f compose.yaml -f compose.local.yaml config --quiet
docker compose -f compose.yaml -f compose.local.yaml up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health/ready
```

Mở http://127.0.0.1:8080. Script tạo secrets ngẫu nhiên trong thư mục private `.secrets`, `.env` chỉ giữ đường dẫn/cấu hình và không ghi đè file cũ. Cả hai bị loại khỏi Git và Docker build context. API/DB không có host ports. Local chỉ bind frontend trên loopback. Không dùng `compose.local.yaml` trên Dokploy.

Migration chạy một lần qua service `migrate`; sau đó API dùng role `gold_reader`, CLI/job dùng `gold_ingestor`. CLI đọc `/run/secrets` trực tiếp cả khi được chạy bằng `docker compose exec`.

Nhập dữ liệu **thật có quyền sử dụng**, từ CSV đúng schema của [fixture](sample-data/quotes.sample.csv), nhưng đổi `reference_type=manual` và thay toàn bộ dữ liệu bằng quan sát thật:

```bash
docker compose cp ./prices.csv worker:/tmp/prices.csv
docker compose exec worker python -m app.jobs.import_csv /tmp/prices.csv --import-root /tmp --confirm-data-rights
docker compose exec worker python -m app.jobs.collect_daily
```

`collect_daily` hiện trả exit 2/3 và `source_unavailable` cho nguồn chưa sẵn sàng; không giả vờ đồng bộ đủ thị trường. Không nhập fixture `sample` vào production. Mọi báo giá dùng VND/lượng, kể cả sản phẩm đóng gói 1 chỉ; sản phẩm vẫn có series riêng.

## Chạy kiểm thử ngoài Docker

Python 3.15.2 và Node 24.22.1 là phiên bản đã dùng để kiểm chứng. Dependency được khóa chính xác; Python lockfiles có SHA-256 từ PyPI, npm có package-lock integrity.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux/macOS: source .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements-dev.lock
python -m pytest -q
cd frontend
npm ci --ignore-scripts
npm run lint
npm run typecheck
npm run build
```

Các test PostgreSQL chỉ chạy khi có `TEST_DATABASE_URL`, tên database phải bắt đầu `gold_test`. **Chỉ trỏ vào DB test dùng xong bỏ**; test sẽ truncate/drop schema trong DB đó.

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:TEST_PASSWORD@127.0.0.1:5432/gold_test_ci python -m pytest backend/tests/test_postgres.py -v
```

Windows có thể tải binary PostgreSQL chính thức từ EDB vào `.tools/postgresql/pgsql`, rồi chạy `./infra/test-postgres.ps1`. Script tạo DB tạm, bind 127.0.0.1:55432, chạy test và tắt server. Không cài Windows service.

QA bundle tĩnh chỉ trên loopback: `python infra/serve_preview.py` (http://127.0.0.1:8765). Thêm `--sample` chỉ cho QA có banner **SAMPLE DATA — NOT REAL MARKET DATA**. Không dùng script này trên VPS. Test trình duyệt ở `tests/browser_ui.cjs` nhận `PLAYWRIGHT_MODULE` và `BROWSER_EXECUTABLE` của máy test.

## Tài liệu vận hành

Security gate đã chạy trên Docker Linux: **75 tests, 9 smoke groups và 8 browser checks pass**; bốn final images có **0 High/Critical** tại thời điểm quét. Xem [báo cáo security gate](docs/SECURITY_GATE_RESULTS.md). Chưa triển khai VPS/HTTPS hay kiểm thử S3/KMS thực tế.

Chạy lại project test riêng, không dùng credentials production:

```bash
python infra/security_gate.py prepare
python infra/security_gate.py build
python infra/security_gate.py start
python infra/security_gate.py test
python infra/container_smoke.py --base-url http://127.0.0.1:18080 --project-name gold-security-gate --env-file .tools/security-gate/.env --compose-file compose.yaml --compose-file .tools/security-gate/compose.gate.yaml --report artifacts/security-gate/container-smoke.json
python infra/security_gate.py scan
python infra/security_gate.py stop
```

Trivy cần nằm trong `.tools/security/trivy` (Linux) hoặc `trivy.exe` (Windows); Windows có thể truyền `--docker` bằng đường dẫn Docker CLI khi chưa có trong PATH. Test giữ volume riêng `gold-security-gate_pgdata`, không xóa volume ứng dụng.

- [Kiến trúc và quyết định](docs/ARCHITECTURE.md)
- [Nguồn, quyền dữ liệu và blockers](docs/DATA_SOURCES.md)
- [Công thức và đối chiếu HTML](docs/CALCULATIONS.md)
- [Threat model](docs/SECURITY_THREAT_MODEL.md) và [security gates](docs/SECURITY_CHECKLIST.md)
- [Dokploy từng bước](docs/DOKPLOY_DEPLOYMENT.md)
- [Backup / restore](docs/BACKUP_RESTORE.md) và [runbook](docs/OPERATIONS_RUNBOOK.md)

Đây là mô phỏng lãi/lỗ lý thuyết theo báo giá, không phải giao dịch thật hoặc cam kết lợi nhuận.
