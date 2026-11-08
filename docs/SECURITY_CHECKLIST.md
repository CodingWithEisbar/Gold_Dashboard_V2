# Security gate · 06/11/2026

Không coi file checklist này là chứng nhận ASVS. Mục tiêu là các kiểm soát phù hợp OWASP ASVS 5.0 MVP; tham chiếu [ASVS](https://asvs.owasp.org/).

- [x] Vue SPA; không React/Next/RSC trong dependency graph.
- [x] Đọc [React2Shell/RSC advisory](https://react.dev/blog/2025/12/03/critical-security-vulnerability-in-react-server-components), gồm các CVE follow-up được liên kết. Không có server-dom packages nên đường khai thác này không tồn tại trong stack hiện tại.
- [x] Đọc [Vite advisory hiện hành](https://github.com/vitejs/vite/security/advisories), [CVE-2026-39364](https://github.com/vitejs/vite/security/advisories/GHSA-v2wj-q39q-566r), GHSA-rq7h-c2jc-7f22 và GHSA-vfpm-58rq-9qcg tháng 10/2026. Đã chọn Vite 8.3.6, production không cài/chạy Vite.
- [x] Sửa [minimatch GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) bằng override 11.0.1; lint/build kiểm tra tương thích.
- [x] npm audit full và runtime, pip-audit: xem artifacts thực tế.
- [x] Decimal/precision/input/SQLi/XSS/SSRF/CSV/rate tests; PostgreSQL append-only và least privilege tests.
- [x] Pin dependencies/lockfiles/hash; Compose config checks; source không có secrets thật được chủ động tạo.
- [x] Gitleaks source/history / OSV lockfiles / Trivy filesystem đã chạy; xem IMPLEMENTATION_STATUS. Base image findings ban đầu được giữ để đối chiếu.
- [x] Docker build/up/health/Nginx smoke trên Linux daemon: 9 nhóm pass và browser QA thực tế.
- [x] Scan final backend/frontend/PostgreSQL/backup images và OS packages: 0 High/Critical, có image SBOM. Không ignore hoặc tự chấp nhận rủi ro; xem SECURITY_GATE_RESULTS.
- [ ] Pin release images bằng sha256 digest sau khi build và scan (tags hiện tại là baseline có phiên bản).
- [ ] TLS/HSTS, IP/firewall/isolated network thực tế, ingress timeout, Dokploy 2FA/VPN, SSH keys-only, không public DB/API/dashboard.
- [ ] Kiểm tra `.env`/source maps/hidden files trả 404 qua HTTPS; API docs không tồn tại production.
- [ ] Backup S3/KMS/retention/IAM và restore drill thực tế.

`npm audit`/`pip-audit` không bao phủ OS/kernel/base images và không chứng minh không có zero-day. CI gate phải chạy trên đúng commit/image release; không publish production khi gate còn thiếu hoặc lỗi.
