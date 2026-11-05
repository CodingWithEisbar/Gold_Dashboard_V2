# Gold Premium Tracker & Investment Simulator

Ứng dụng Vue 3 + TypeScript / FastAPI / PostgreSQL, tính toán tài chính bằng Decimal ở backend. Giao diện tiếng Việt gồm Tổng quan, Premium, Mô phỏng lịch sử, Phòng kịch bản và Dữ liệu & nguồn.

**Trạng thái:** source code đã được triển khai và có kiểm thử thực tế; chưa triển khai VPS. Database production khởi tạo không có báo giá. SJC/PNJ và FX tự động còn bị khóa vì chưa xác minh quyền sử dụng; Metals.Dev cần hợp đồng/subscription và API key. Xem [báo cáo kiểm chứng](docs/IMPLEMENTATION_STATUS.md) để phân biệt phần đã chạy và phần còn chờ.

## Chạy local bằng Docker Compose

Cần Docker Engine/Desktop và Docker Compose hỗ trợ secrets từ environment. Chạy từ thư mục repository:

```bash
python infra/init-local-env.py
docker compose -f compose.yaml -f compose.local.yaml config --quiet
docker compose -f compose.yaml -f compose.local.yaml up -d --build
docker compose ps
curl --fail http://127.0.0.1:8080/api/v1/health/ready
```

Mở http://127.0.0.1:8080. Script tạo `.env` bằng secrets ngẫu nhiên, không ghi đè file cũ. API/DB không có host ports. Local chỉ bind frontend trên loopback. Không dùng `compose.local.yaml` trên Dokploy.

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

Ba test PostgreSQL chỉ chạy khi có `TEST_DATABASE_URL`, tên database phải bắt đầu `gold_test`. **Chỉ trỏ vào DB test dùng xong bỏ**; test sẽ truncate/drop schema trong DB đó.

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:TEST_PASSWORD@127.0.0.1:5432/gold_test_ci python -m pytest backend/tests/test_postgres.py -v
```

Windows có thể tải binary PostgreSQL chính thức từ EDB vào `.tools/postgresql/pgsql`, rồi chạy `./infra/test-postgres.ps1`. Script tạo DB tạm, bind 127.0.0.1:55432, chạy test và tắt server. Không cài Windows service.

QA bundle tĩnh chỉ trên loopback: `python infra/serve_preview.py` (http://127.0.0.1:8765). Thêm `--sample` chỉ cho QA có banner **SAMPLE DATA — NOT REAL MARKET DATA**. Không dùng script này trên VPS. Test trình duyệt ở `tests/browser_ui.cjs` nhận `PLAYWRIGHT_MODULE` và `BROWSER_EXECUTABLE` của máy test.

## Tài liệu vận hành

- [Kiến trúc và quyết định](docs/ARCHITECTURE.md)
- [Nguồn, quyền dữ liệu và blockers](docs/DATA_SOURCES.md)
- [Công thức và đối chiếu HTML](docs/CALCULATIONS.md)
- [Threat model](docs/SECURITY_THREAT_MODEL.md) và [security gates](docs/SECURITY_CHECKLIST.md)
- [Dokploy từng bước](docs/DOKPLOY_DEPLOYMENT.md)
- [Backup / restore](docs/BACKUP_RESTORE.md) và [runbook](docs/OPERATIONS_RUNBOOK.md)

Đây là mô phỏng lãi/lỗ lý thuyết theo báo giá, không phải giao dịch thật hoặc cam kết lợi nhuận.
