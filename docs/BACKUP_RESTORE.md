# Backup và phục hồi

Backup database ứng dụng khác backup Dokploy control plane. `compose.backup.yaml` thêm container không quyền root/runtime, chỉ có secret reader, network database + outbound, tmpfs và giới hạn tài nguyên. Script `infra/backup/backup.sh` chạy pg_dump custom format, pg_restore --list, SHA-256 rồi upload dump/hash lên S3 với **SSE-KMS bắt buộc**. Không ghi dump vào webroot; không log password/API key.

Đặt S3_BUCKET, S3_KMS_KEY_ID, AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY qua Dokploy Secrets Provider; ưu tiên workload role/short-lived credentials nếu hạ tầng hỗ trợ. Bucket private, chặn public ACL/access, bắt buộc TLS và key KMS cụ thể. Role backup chỉ PutObject vào prefix `gold/`, KMS GenerateDataKey/Encrypt theo key; role restore tách riêng có GetObject/Decrypt. Không cấp quyền S3 wildcard toàn account. Áp lifecycle [infra/s3-lifecycle.json](../infra/s3-lifecycle.json): 35 ngày, xóa noncurrent sau 7 ngày, abort multipart sau 1 ngày. Kiểm tra policy/KMS bằng tài khoản thật trước khi đặt lịch.

```bash
docker compose -f compose.yaml -f compose.backup.yaml config --quiet
docker compose -f compose.yaml -f compose.backup.yaml up -d --build backup
docker compose exec backup /usr/local/bin/gold-backup
```

Tạo Dokploy Compose Job cho container backup đang chạy, theo DOKPLOY_DEPLOYMENT. Alert khi job nonzero, không có object mới trong 26 giờ hoặc dung lượng bất thường. Retention do bucket lifecycle áp dụng, không có code xóa backup từ app.

Restore drill trên **database tạm riêng, không trỏ vào production**:

1. Dùng operator role có quyền đọc S3 và decrypt KMS, tải cả gold.dump và gold.dump.sha256 vào thư mục private.
2. `sha256sum -c gold.dump.sha256`; `pg_restore --list gold.dump` phải thành công.
3. Tạo database `gold_test_restore` hoặc cluster/volume mới ở network private, PostgreSQL major tương thích. Không phục hồi đè volume live. Truyền PGPASSFILE/secret, không đặt password trong argv.
4. `pg_restore --exit-on-error --no-owner --no-acl --dbname gold_test_restore gold.dump` bằng role đủ quyền cho DB tạm. Tạo/grant roles theo schema tương ứng sau restore; dump không chứa credentials/ACL.
5. Kiểm tra alembic_version, catalog, số rows theo bảng/ngày, raw hash, timestamps, latest/history, P&L cố định và append-only trigger. Chạy smoke app trỏ DB tạm. Ghi RPO/RTO thực đo, thời gian/digest backup và người thực hiện.
6. Chỉ chuyển app khi kết quả được xác minh; giữ volume cũ để rollback. Giới hạn quyền và dọn database test sau drill theo quy trình operator.

**Đã kiểm thử:** native PostgreSQL 18.6 pg_dump/pg_restore vào DB test, kiểm tra dữ liệu catalog và schema revision sau restore; xem artifacts/postgres-tests.xml. **Chưa kiểm thử:** upload/download S3, KMS, bucket policy, retention thực tế, restore full Compose volume và RPO/RTO trên VPS. Không gọi đây là backup production đã hoạt động.
