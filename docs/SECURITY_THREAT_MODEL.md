# Threat model MVP

Tài sản cần bảo vệ: tính đúng báo giá/P&L, DB lịch sử, provider keys, DB secrets, backups và host Docker. Ranh giới tin cậy: browser→proxy, proxy→API, admin CSV→ingestion, provider→parser, app→DB, backup→S3. Dữ liệu nguồn và CSV đều không đáng tin cho tới khi được kiểm định.

| Nguy cơ | Kiểm soát đã có | Giới hạn / kiểm chứng cần thêm |
|---|---|---|
| SQL injection | SQLAlchemy binds, ID/date/decimal validation, reader role SELECT | PG role test thật; CI chạy lại |
| XSS | Vue interpolation, không v-html, không raw provider HTML, CSP self | Nginx CSP cần smoke trong container/TLS |
| SSRF / DNS rebinding | Host/path cố định, HTTPS, kiểm tra toàn bộ DNS global IP, kết nối IP đã pin + Host/SNI TLS, cấm redirect/proxy env | Firewall egress bổ sung; parser fixtures chưa phải live API verification |
| RCE / command injection | Không shell từ input, không eval/exec/pickle, CLI nội bộ | Container image scans, kernel patches trên VPS |
| DoS | body 16KiB, dải ngày giới hạn, DB statement timeout, Nginx limit, backend limiter bounded, quota/retries | Limiter process-local; shared ingress peer giới hạn tổng có thể cần tune |
| Data poisoning | schema/unit/positive/precision checks, quarantine, hash collision rejection, append-only | Baseline đầu tiên vẫn cần operator xác minh |
| Secret exposure | secrets chỉ vào service cần thiết, gitignore/dockerignore, không VITE secrets, generic errors | Dokploy env có thể được materialize thành .env; cần permissions và Secrets Provider |
| Container escape | non-root, read-only, cap_drop ALL, no-new-privileges, pids/memory/cpu caps, no socket/host modes | Không bảo đảm chống kernel zero-day; cần host update và isolation |
| Dependency supply chain | exact pins, Python release hashes/npm integrity, audit, SBOM gates | Hash không tự bảo đảm package không độc hại; kiểm tra provenance khi upgrade |
| Backup loss / theft | pg_dump, SHA256, S3 SSE-KMS, private bucket, retention | S3 upload/KMS/IAM/restore drill cần tài khoản thật |

Không có login/PII trong MVP. Không có public route để sửa giá, upload file, tùy ý fetch URL, thực thi SQL/shell. Nếu bổ sung tài khoản phải bổ sung threat model cho auth/RBAC/session/CSRF, không dùng cấu hình public này như admin UI.

CSV import từ operator, không upload web. Chặn path thoát import root sau resolve, file/row limits, strict numeric grammar. Export escape cả prefix trắng trước `=+-@` và tab/CR/LF để giảm formula injection. Snapshot sửa/xóa bị DB trigger chặn; reconciliation dùng reference table, không viết đè raw observations.

Không log provider payload, query URL có key hoặc exception chứa DB DSN. Uvicorn access log tắt; log ingestion là JSON với error codes. Chưa có external alert receiver được cấu hình; operator cần kết nối failure notifications cho Schedule Jobs.
