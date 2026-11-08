# Security gate · 06/11/2026

**PASS trên môi trường kiểm thử Linux local.** Đã build/chạy Compose thật, quét final images và kiểm tra health, Nginx, quyền DB và network isolation. Đây không phải xác nhận đã triển khai VPS/HTTPS.

Môi trường: Docker Desktop engine **29.9.2**, Linux x86_64, kernel **6.18.54.1-microsoft-standard-WSL2**. Project riêng `gold-security-gate`; frontend chỉ bind `127.0.0.1:18080`. Không dùng credentials production hoặc dữ liệu thị trường thật.

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Linux pytest, có PostgreSQL 18.6 thật | **75 passed, 0 skipped** | [linux-tests.xml](../artifacts/security-gate/linux-tests.xml) |
| Production container smoke | **9 nhóm pass** | [container-smoke.json](../artifacts/security-gate/container-smoke.json) |
| Browser desktop/mobile qua Nginx thật | **8 nhóm pass**, không lỗi JS/CSP | [browser-tests.json](../artifacts/security-gate/browser-tests.json) |
| Final backend image | **0 High / 0 Critical** | [backend scan](../artifacts/security-gate/backend-scan.json) |
| Final frontend image | **0 High / 0 Critical** | [frontend scan](../artifacts/security-gate/frontend-scan.json) |
| Final PostgreSQL image | **0 High / 0 Critical** | [PostgreSQL scan](../artifacts/security-gate/postgres-scan.json) |
| Final backup image | **0 High / 0 Critical** | [backup scan](../artifacts/security-gate/backup-scan.json) |
| Git history + source secrets | Không thấy leak; đã quét 1 commit | [history](../artifacts/security-gate/gitleaks-history.json), [source](../artifacts/security-gate/gitleaks-source.json) |
| Source/config security | Không High/Critical trong phạm vi Trivy filesystem | [source scan](../artifacts/security-gate/trivy-source.json) |
| Backup image offline smoke | UID 70, AWS CLI 2.34.63, pg_dump 18.6 và script syntax pass | Chưa gọi S3/KMS |

Trivy **0.76.2** dùng advisory DB cập nhật trong lần chạy này. Không thêm ignore, không `ignore-unfixed`, không chấp nhận rủi ro hoặc đổi severity để qua gate. Kết quả “0” là **High/Critical** ở các final images đã quét; không phải tuyên bố không có mọi lỗ hổng/zero-day. SBOM CycloneDX riêng nằm cạnh từng report, tên `backend-sbom.json`, `frontend-sbom.json`, `postgres-sbom.json`, `backup-sbom.json`.

## Image identities đã kiểm chứng

| Image local | Digest SHA-256 |
|---|---|
| gold-backend:gate | `3d2643c1d499bc070a639c84427ce57cdf5366df15986e4a0feba60242619650` |
| gold-frontend:gate | `3a4149c5cd71ce60695f1196b645ed10818b8f7da3f5af01242ec24d42e46dd7` |
| gold-postgres:gate | `d610ff8574feeb486cba9c75b2d1df5f8234177e5879d913e8d308281cfde16f` |
| gold-backup:gate | `3a4809629cc5f31d677bfd714cab68908ae146e23adedcdd1e7e9159ac55ace2` |

Các digest này hiện ở Docker local, **chưa push registry**. Không sao chép nguyên thành remote production image rồi giả định VPS pull được. Release cần push đúng content vào registry, kiểm tra RepoDigest tại đó và dùng Compose release overlay. Nếu build lại hoặc upstream APK/image thay đổi, phải scan và smoke lại đúng images mới.

## Các lỗi phát hiện và sửa trong lần chạy

1. **Environment-backed Compose secrets lỗi khi service read-only.** Kiểm tra config trước đó không phát hiện được. Đổi sang `secrets.file` và bốn biến `DB_*_PASSWORD_FILE`. `init-local-env.py` tạo thư mục `.secrets` private, `.env` chỉ chứa paths/config. `.secrets` được loại khỏi Git/build context. App/DB vẫn non-root, read-only; không nới hardening để khởi động.
2. Container được tạo dở từ lần lỗi secret thiếu mounts. Runner dùng force-recreate trong **project test riêng**, giữ volume; không xóa volume hoặc container của project khác.
3. Bổ sung `.gitattributes` giữ LF để tránh shell scripts bị chuyển CRLF khi checkout trên Windows.
4. CI được cập nhật gọi cùng runner và smoke tests đã kiểm chứng, lưu raw scans/SBOM. Chưa tuyên bố có remote CI run thành công; kết quả ở đây là chạy local Docker Linux.

## Phạm vi smoke

Health API thực sự trả qua Nginx; CSP self không unsafe-inline và browser headers có mặt; `.env`, `.git`, source maps, public ingestion và API docs trả 404. Database trống trả missing, không có giá giả; CSV export và phép tính scenario Decimal hoạt động qua proxy.

Inspect mọi service: non-root UID, rootfs read-only, cap_drop ALL, no-new-privileges, memory/CPU/PID limits, không host network/PID/privileged/socket. DB/API/worker/migrate không publish ports, API và DB chỉ ở internal networks; frontend không chung DB network. Migration exit 0, API/DB/worker/frontend healthy. Nginx `-t` chạy được dưới runtime UID; API xác thực là `gold_reader` và bị từ chối câu DELETE không sửa row nào.

Linux regression chạy thêm trong verifier non-root, rootfs read-only, network private; DB `gold_test_gate` riêng để migration up/down và dump/restore không tác động schema ứng dụng. Project test đã dừng sau kiểm chứng; test volume riêng và image/report được giữ để review.

## Chưa thuộc lần kiểm chứng này

Domain/VPS/Dokploy UI, TLS/HSTS/firewall Internet thực tế, S3/KMS/IAM/retention, quyền nguồn dữ liệu và API credentials thật. Các phần này vẫn cần thực hiện trước khi vận hành production; security gate local không thay thế các bước đó.
