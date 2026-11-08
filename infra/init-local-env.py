"""Generate local secrets; never prints them and never overwrites an existing .env."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env đã tồn tại; không ghi đè cấu hình hoặc secret của bạn")
secret_dir = root / ".secrets"
secret_dir.mkdir(mode=0o700, exist_ok=True)
content = (root / ".env.example").read_text(encoding="utf-8")
for name in ("db_admin_password", "db_owner_password", "db_reader_password", "db_ingestor_password"):
    secret_file = secret_dir / name
    with secret_file.open("x", encoding="utf-8") as stream:
        stream.write(secrets.token_urlsafe(36))
    # Private parent directory protects host access; mounted files must be readable by UID 70 and 10001.
    secret_file.chmod(0o444)
with target.open("x", encoding="utf-8") as stream:
    stream.write(content)
target.chmod(0o600)
print("Đã tạo .env chỉ chứa cấu hình và .secrets private; không commit các file này.")
