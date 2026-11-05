# Báo cáo kiểm chứng · 06/11/2026

Repository ban đầu rỗng, nhánh main chưa có commit. Đã đọc master prompt đầy đủ và infographic kiến trúc; calculator HTML cũ được nhắc trong yêu cầu chưa có trong tập file. Diff ở artifacts/implementation.patch thể hiện các file được thêm vào; không thay đổi Git config global, không tạo commit hoặc tuyên bố đã push/deploy.

| Phase | Đầu ra | Bằng chứng / giới hạn |
|---|---|---|
| 0 Discovery | Kiến trúc, ma trận nguồn/quyền, công thức, threat model | docs/ARCHITECTURE, DATA_SOURCES, CALCULATIONS, SECURITY_THREAT_MODEL |
| 1 Math | Decimal library, validation, premium/spread/P&L/scenario, fees/break-even | Tests cố định + property test pass |
| 2 Storage/ingestion | 7 bảng, 2 migrations, catalog metadata, append-only triggers, providers, CSV CLI, collect CLI, quarantine/daily reference/source status | 3 integration tests PostgreSQL 18.6 thật pass; fixtures và API tests pass; live provider chưa chạy do thiếu quyền/key |
| 3 UI/API | 5 màn hình Vue, API read/calculate, history/missing/provenance, charts/CSV, backtest, scenario | Build/typecheck/lint pass; browser QA desktop/mobile và sample có nhãn |
| 4 Security/production | Hardened Compose, role separation, secret mounts, Nginx CSP/rate, CI gates, Dokploy/backup/rollback docs | Config validation pass; Docker daemon/final image build+scan, HTTPS và S3 chưa được chạy |
| 5 Handover | README, runbooks, artifacts, source manifest/diff | Chưa có domain/VPS/Dokploy/repo credentials nên không deploy |

## Lệnh đã chạy và kết quả

| Lệnh / kiểm tra | Kết quả |
|---|---|
| `python -m pytest -q --junitxml=artifacts/backend-tests.xml` | **72 passed, 3 skipped**; skipped là PG suite khi không đặt TEST_DATABASE_URL; bao gồm chạy CLI thật, import hai lần và job source_unavailable |
| `infra/test-postgres.ps1` trên PostgreSQL 18.6 portable | **3 passed**, gồm Numeric/idempotency/append-only, migration up/down, reader role và pg_dump/pg_restore; server đã tắt và temp directory được dọn |
| `ruff check backend/app backend/tests backend/migrations` | Pass |
| `npm run lint`, `npm run typecheck`, `npm run build` | Pass; Vite 8.3.6; bundle static |
| `tests/browser_ui.cjs` | 8 checks pass, Edge headless, desktop 1440px/mobile 390px; thiếu dữ liệu không trả số giả |
| `tests/browser_sample.cjs` | Xem artifacts/browser-sample-tests.json; sample được gắn nhãn, kiểm tra P&L/backtest |
| `infra/validate-compose.ps1` + Compose 5.7.0 | Production/local/backup config hợp lệ; kiểm tra private ports, internal networks, hardening và tmpfs uid/gid |
| `pip install --dry-run --require-hashes -r backend/requirements-dev.lock` | Pass trên môi trường hiện có |
| `pip download --require-hashes --only-binary ...` cho CPython 3.15 Linux musllinux 1.1 + 1.2 | **26 runtime packages** tải được, hashes hợp lệ; không cần compiler trong image |
| npm audit full + omit=dev | 0 vulnerabilities, artifacts/npm-audit*.json |
| pip-audit | 0 known vulnerabilities, artifacts/pip-audit.json |
| OSV Scanner 2.7.0 | Pass cho frontend/package-lock.json và Python requirements.lock |
| Dependency SBOM | artifacts/dependency-sbom.json, CycloneDX 1.6 từ lockfiles; chưa phải final image SBOM |
| Gitleaks 8.30.1 source directory | Không thấy leaks; Git history chưa có commit để quét |
| Trivy 0.76.2 filesystem | Không có High/Critical trong phần source/config/dependency được scanner nhận diện; không thay thế final image scan |
| Trivy remote base images | **Phát hiện High/Critical; xem phần dưới. Không coi release gate là pass.** |

Có một warning của Starlette: TestClient dùng httpx bị deprecate để chuyển dần sang httpx2. Tests vẫn pass; chưa đổi HTTP client production theo warning của test helper.

## Base image findings và sửa đổi

Raw reports được giữ để review: `artifacts/base-*-scan.json`. Không che bằng ignore-unfixed, không hạ severity hoặc chấp nhận rủi ro thay người vận hành.

- Python 3.15.2 **slim/Debian 13.7** khảo sát ban đầu có nhiều High OS và các packages Python đi kèm; không được dùng làm runtime cuối. Đã đổi Dockerfile sang **Python 3.15.2 Alpine**, scan base này không phát hiện High/Critical ở OS nhưng có msgpack/setuptools/urllib3 đi kèm. Runtime mới chỉ dùng /opt/venv dependency đã audit, bỏ global site-packages và pip không dùng. Bước loại bỏ này **chưa được build/scan final image**.
- Nginx unprivileged 1.30.6 Alpine base có **CVE-2026-111497 Critical** brotli-libs; curl/libcurl/libexpat có High và bản vá trong repository Alpine. Đã thêm `apk upgrade --no-cache`; final image cần quét để xác nhận bản thực sự được cài.
- PostgreSQL 18.6 Alpine base có brotli/libcurl và Go runtime trong **gosu** cũ. Đã tạo custom Dockerfile cập nhật APK và bỏ gosu; container được cấu hình chạy UID 70 nên không dùng nhánh entrypoint chuyển từ root qua gosu. Chưa xác minh final image/runtime này bằng Docker.
- Node 24.22.1 Alpine build base có packages npm/corepack bị advisory. Đã nâng npm build tool lên 12.2.2, bỏ corepack; Node không nằm trong final frontend runtime. Cần scan build stage nếu policy CI yêu cầu, không coi nâng npm là bằng chứng đã hết mọi package của base.
- Backup image cũng cập nhật APK, bỏ gosu; AWS CLI/OS dependencies phát sinh cần quét sau build.

**Release đang bị chặn** cho đến khi build và quét final backend/frontend/PostgreSQL/backup images thành công, xử lý mọi Critical/High còn lại và chạy container smoke trên Linux. CI đã cấu hình fail gate; chưa có CI run từ remote được xác minh. Không dùng việc source scans pass để bỏ qua gate này.

## Phần cần người dùng cung cấp

1. File `Gold_Premium_Infographic_Calculator.html` cũ để hoàn tất đối chiếu với đúng source ban đầu. Hiện đã đối chiếu được infographic kiến trúc và master prompt.
2. Quyền/contract cho dữ liệu domestic và FX, hoặc CSV thật có quyền lưu/hiển thị; subscription/API key Metals.Dev nếu dùng spot tự động.
3. Git/registry và Docker Linux build environment để chạy CI, scan final images, ghi digests và kiểm thử Compose runtime.
4. Domain/DNS, VPS/Dokploy access để kiểm tra HTTPS, firewall, ingress/network thực tế và deploy.
5. S3 bucket, region, KMS key và IAM phù hợp để kiểm chứng backup upload, retention và restore drill trên VPS.

Không có giá thị trường thật nào được tạo hoặc lịch sử được nội suy. `sample-data` chỉ dành cho tests/QA, bị chặn production. Ứng dụng với nguồn chưa cấu hình hiển thị missing/source_unavailable có chủ đích.
