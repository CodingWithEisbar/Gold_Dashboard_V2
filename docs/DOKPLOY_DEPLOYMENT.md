# Triển khai Dokploy từng bước

Chưa có domain, VPS, quyền Dokploy hoặc registry của người dùng. Các bước sau cần thực hiện trên hạ tầng thật và lưu bằng chứng. Không có deployment được xác minh trong phiên này.

1. Chuẩn bị VPS Linux đang được hỗ trợ, Docker/Dokploy đã vá, DNS A/AAAA trỏ domain đến IP VPS. Chỉ mở ingress 80/443 cần thiết, SSH key-only qua IP tin cậy/VPN; bảo vệ UI Dokploy bằng 2FA/passkeys, RBAC và private access. Không public Traefik dashboard, DB hoặc Docker socket. Kiểm tra firewall cho Docker-published ports, không chỉ UFW thông thường.
2. Đẩy repository vào Git của bạn. Trong Dokploy tạo Project → Docker Compose → kết nối repository/branch. Chọn `compose.yaml`, không thêm `compose.local.yaml`. Kiểm tra UI của phiên bản Dokploy hiện có trước khi cấu hình; chưa có quyền truy cập UI để kiểm chứng từ phiên này.
3. Chạy pipeline CI trên commit định release. Phải có Docker build, PostgreSQL tests, container smoke, dependency/secret/image scans và SBOM. Nếu scan có High/Critical chưa xử lý hoặc chưa chạy được, dừng release. Push các image đã scan vào private registry, lấy RepoDigest rồi đặt `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `POSTGRES_IMAGE`, `BACKUP_IMAGE` theo `registry/image@sha256:...`. Build trên Dokploy chỉ là phương án bootstrap; release phải cố định digest, không dùng `latest`.
4. Tạo bốn password độc lập ít nhất 24 ký tự: DB_ADMIN/OWNER/READER/INGESTOR_PASSWORD. Compose hardened hiện dùng **file-backed secrets**, vì environment-backed secrets không tương thích container read-only trong môi trường đã kiểm tra. Materialize từng secret từ Dokploy Secrets Provider thành file riêng ngoài webroot trên VPS; đặt bốn biến `DB_*_PASSWORD_FILE` là đường dẫn file, không phải mật khẩu. Thư mục cha chỉ operator được truy cập (0700); file phải đọc được bởi UID container 70/10001 qua secret mount, chẳng hạn 0444 trong thư mục cha private, hoặc ownership/ACL phù hợp. `.env.example` chỉ chứa tên biến/đường dẫn. Nếu Dokploy ghi Environment vào `.env` cạnh compose, giới hạn quyền đọc/backup thư mục này; không mount nó vào webroot hoặc đưa secrets vào Git. `infra/init-local-env.py` tạo cấu hình local theo cùng mô hình.
5. Đặt APP_ENV=production; để XAU_API_KEY trống và METALS_LICENSE_CONFIRMED=false cho đến khi có quyền hợp lệ. Không cần license để chạy phần mềm với database trống. Đừng dùng fixture làm market data.
6. Bật Isolated Deployments khi phiên bản Dokploy tương thích. Frontend cần network do Dokploy/Traefik quản lý, API chỉ `application`+`database`, DB chỉ `database`, worker `database`+`outbound`. Kiểm tra compose cuối do Dokploy sinh; không cho API/DB vào ingress mặc định. Volume `pgdata` phải là named volume, không xóa trong update. Postgres 18 mount `/var/lib/postgresql` theo layout major version mới.
7. Deploy. Service `migrate` chạy Alembic, seed catalog metadata và grant role; chỉ thành công mới khởi động API/worker, rồi frontend. Xem logs và health status. Reader không giữ key/API/migration secret. Worker không chạy lịch bên trong container.
8. Trong tab **Domains** thêm domain → service `frontend` → port **8080**, HTTPS Let's Encrypt, redirect HTTP→HTTPS. Dokploy tự thêm routing labels; **không thêm labels Traefik thủ công trùng lặp**. Hướng dẫn dựa trên [Compose Domains chính thức](https://docs.dokploy.com/docs/core/docker-compose/domains), chưa phải bằng chứng UI trên VPS của bạn.
9. Kiểm tra HTTPS trước khi bật HSTS. Thêm middleware HSTS tại Traefik/Dokploy: `max-age=31536000`; chỉ includeSubDomains nếu mọi subdomain đều có HTTPS. Không bật preload tùy tiện. Chỉ tin forwarded headers từ proxy CIDR đã kiểm chứng; app không tin header từ Internet. Limiter hiện có thể nhìn toàn bộ traffic sau proxy như một peer; tune tại ingress theo IP tin cậy nếu có nhu cầu lớn hơn.
10. Tạo [Schedule Job](https://docs.dokploy.com/docs/core/schedule-jobs), loại Compose, chọn worker đang chạy. Command `python -m app.jobs.collect_daily`. Cron **0 11 * * *** nếu scheduler UTC, tương ứng 18:00 Việt Nam. Nếu UI hỗ trợ timezone được xác minh thì dùng Asia/Ho_Chi_Minh và **0 18 * * ***. Không đặt cả hai. Xác nhận Next run trong UI; log JSON/exit 2 hoặc 3 hiện chỉ ra nguồn thiếu, không phải sync thành công. Bật failure notifications. CLI có advisory transaction lock để tránh import/job đua nhau.
11. Sau khi có license, bật Metals.Dev theo DATA_SOURCES. Adapter BTMH đã có trong worker, tắt mặc định: làm theo [BTMH VPS Job](BTMH_VPS_JOB.md) để xác nhận quyền/đơn vị/timezone, chạy thử `--source btmh` rồi tạo lịch riêng mỗi 30 phút nếu nguồn cho phép. Không bật đồng thời hai lịch BTMH. SJC/PNJ/FX còn dùng CSV có quyền; BTMH không tự cung cấp nguồn thế giới hoặc tỷ giá cho app.
12. Bật backup sidecar bằng merge `compose.backup.yaml`, cung cấp S3/KMS/IAM theo BACKUP_RESTORE. Tạo Compose Job trên service backup, command `/usr/local/bin/gold-backup`, cron `30 19 * * *` UTC (02:30 hôm sau ở Việt Nam). Bật bucket policy private/TLS/KMS và lifecycle retention. Thực hiện restore drill trước khi coi là production-ready.

Sau khi đã có image digests qua CI, dùng Compose release overlay để bỏ toàn bộ build tại production:

```bash
docker compose -f compose.yaml -f compose.release.yaml config --quiet
docker compose -f compose.yaml -f compose.release.yaml up -d --no-build
# Có backup: thêm -f compose.backup.yaml -f compose.backup-release.yaml
```

Trong Dokploy chọn cùng tổ hợp file, không gọi build khi image chứa `@sha256`. Overlay yêu cầu Compose >=2.24 hỗ trợ `!reset`. `infra/validate-compose.ps1` kiểm tra mọi service release đều không có build và dùng digest. Các digest mẫu trong validator chỉ phục vụ kiểm tra cấu hình, không trỏ tới release đã tồn tại.

Kiểm tra từ máy ngoài VPS:

```bash
curl --fail https://YOUR_DOMAIN/api/v1/health/live
curl --fail https://YOUR_DOMAIN/api/v1/health/ready
curl -I https://YOUR_DOMAIN/
curl -i https://YOUR_DOMAIN/.env
curl -i 'https://YOUR_DOMAIN/.env?raw'
curl -i https://YOUR_DOMAIN/api/v1/ingest
curl -i https://YOUR_DOMAIN/docs
```

Health phải 200; CSP/nosniff/referrer/permissions ở frontend phải có; `.env` 404, public ingest 404. `/docs` có thể trả SPA index vì frontend fallback, nhưng `/openapi.json` và `/api/v1/openapi.json` không được trả schema production; backend không tạo docs route. Kiểm tra nội dung, không chỉ HTTP status của SPA.

Trên VPS: `docker compose ps` chỉ frontend nhận ingress; `docker inspect` kiểm tra PortBindings DB/API rỗng; `ss -lntp` và kiểm tra từ ngoài phải không thấy 5432/8000. Inspect networks của container thực tế và xác nhận database network internal. Kiểm tra process user, read-only mounts, cap drop, no privileged/host modes/socket. `docker compose exec api ...` truy cập DB chỉ đọc; không đưa password vào lệnh shell/history.

Rollback: lưu commit + image digests + schema revision + backup trước release. Với thay đổi schema tương thích, chọn deployment/image digest trước và health/smoke lại. Với migration phá vỡ tương thích, dừng writers và restore backup vào volume/database mới, kiểm tra rồi chuyển traffic; không tự downgrade schema production hoặc xóa volume. [Runbook](OPERATIONS_RUNBOOK.md) nêu thao tác chi tiết.
