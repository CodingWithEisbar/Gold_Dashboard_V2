# Gold Premium Tracker & Investment Simulator

Ứng dụng Vue 3 + TypeScript / FastAPI / PostgreSQL, tính toán tài chính bằng Decimal ở backend. Giao diện tiếng Việt gồm Tổng quan, Premium, Mô phỏng lịch sử, Phòng kịch bản và Dữ liệu & nguồn.

Worker local lấy giá trong nước và giá thế giới XAU/USD từ API công khai Vàng.Today. Hướng dẫn bật và kiểm tra dữ liệu nằm trong phần [Giá vàng theo giờ trên local](#giá-vàng-theo-giờ-trên-local).

## Chạy local bằng Docker Compose

Cần Docker Engine/Desktop chạy Linux containers và Docker Compose. Trên Linux, chạy từ thư mục gốc của repo:

```bash
./start.sh
```

Script dùng Python 3 để tạo cấu hình lần đầu, khởi động các service và dùng curl để kiểm tra dashboard cùng API tại http://127.0.0.1:8080. Sau khi sửa code hoặc Dockerfile, chạy `./start.sh --build` để build lại image. Nếu dùng VS Code Remote SSH, mở địa chỉ chuyển tiếp của cổng `8080` trong tab **Ports**.

Để chạy thủ công:

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

### Giá vàng theo giờ trên local

Chạy `./start.sh --build`. Worker đọc [API Vàng.Today](https://www.vang.today/api/prices) lúc khởi động và đầu mỗi giờ khi máy đang chạy. API công khai dùng HTTPS, không cần API key hoặc trình duyệt để lấy giá. Khi nâng cấp từ cấu hình cũ có `SOURCE_ALLOWLIST` trong `.env`, thêm `www.vang.today` vào danh sách. Đặt `VANG_TODAY_ENABLED=false` để tắt nếu cần.

Mục **Giá vàng trong nước** hiển thị 11 mã theo thương hiệu. Giá mua/bán có đơn vị VND/lượng. Mỗi báo giá giữ timestamp của bảng do API trả về. Khi timestamp và giá không đổi, worker ghi nhận lượt kiểm tra và giữ một bản giá duy nhất. Mục **Dữ liệu & nguồn** hiển thị trạng thái và lỗi gần nhất. Kiểm tra log bằng `docker compose logs --tail 20 worker`. Các báo giá cũ vẫn giữ nguồn ban đầu.

Mục **Giá vàng thế giới** hiển thị giá giao ngay từ [API XAUUSD của Vàng.Today](https://www.vang.today/api/prices?type=XAUUSD), tính bằng USD/ounce troy. Biểu đồ và bảng theo giờ dùng báo giá đã lưu từ API này. Bảng lịch sử trong nước và XAU/USD mặc định hiển thị 7 ngày gần nhất, có thể lọc từ 1 đến 31 ngày. Dữ liệu đã lưu nằm trong PostgreSQL và được giữ qua các lần khởi động lại. Worker giữ thời điểm cập nhật do nguồn cung cấp.

Chuỗi vàng thế giới giao ngay dùng nguồn spot đã cấu hình và tỷ giá USD/VND để tính premium. Dữ liệu kỳ hạn đã lưu vẫn có trong lịch sử chung theo giờ.

### Nhật ký API Gateway

Mở **API Gateway** để lọc GET/POST theo mã HTTP và xem các lượt worker thu thập giá. Nhật ký yêu cầu giữ 10.000 lượt gần nhất trong volume `api_logs` trên máy chạy API. Mỗi dòng lưu phương thức, mẫu endpoint, thời điểm, mã HTTP và thời lượng. Dữ liệu nhạy cảm như query string, nội dung yêu cầu và token nằm ngoài nhật ký.

`./start.sh --build` mở trang theo dõi trên loopback local. Khi deploy, đặt `API_GATEWAY_TOKEN` bằng một token riêng trong môi trường server, rồi nhập token vào trang để xem. Với Dokploy đang dùng **Patches**, cập nhật patch bằng `compose.dokploy.yaml` trên máy và thêm token trong **Environment**.

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
