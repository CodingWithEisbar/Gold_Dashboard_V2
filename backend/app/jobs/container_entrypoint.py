"""Inject only the current service's DB password from a read-only secret file."""

import os
import sys
from pathlib import Path
from urllib.parse import quote


def main():
    password_file = os.environ.get("DATABASE_PASSWORD_FILE")
    role = os.environ.get("DATABASE_ROLE")
    if password_file:
        if role not in {"gold_reader", "gold_ingestor", "gold_owner"}:
            raise SystemExit("Unsupported database role")
        password = Path(password_file).read_text().strip()
        if len(password) < 24:
            raise SystemExit("Database secret must contain at least 24 characters")
        os.environ["DATABASE_URL"] = f"postgresql+psycopg://{role}:{quote(password, safe='')}@db:5432/gold"
    if not sys.argv[1:]:
        raise SystemExit("Missing entrypoint command")
    # argv is fixed by Compose/operator, never exposed via an API.
    os.execvp(sys.argv[1], sys.argv[1:])  # noqa: S606


if __name__ == "__main__":
    main()
