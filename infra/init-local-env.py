"""Generate local secrets; never prints them and never overwrites an existing .env."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (root / ".env.example").read_text(encoding="utf-8")
for name in ("DB_ADMIN_PASSWORD", "DB_OWNER_PASSWORD", "DB_READER_PASSWORD", "DB_INGESTOR_PASSWORD"):
    content = content.replace(f"{name}=\n", f"{name}={secrets.token_urlsafe(36)}\n")
with target.open("x", encoding="utf-8") as stream:
    stream.write(content)
target.chmod(0o600)
print("Đã tạo .env local; không commit hoặc đưa vào bundle.")
