"""Linux regression tests against a dedicated DB in the isolated security-gate project."""
import os
from pathlib import Path
from urllib.parse import quote

import psycopg
import pytest

password = Path("/run/secrets/db_admin_password").read_text().strip()
with psycopg.connect(host="db", dbname="postgres", user="postgres", password=password, autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_database WHERE datname = 'gold_test_gate'").fetchone():
        connection.execute("CREATE DATABASE gold_test_gate")
os.environ["TEST_DATABASE_URL"] = f"postgresql+psycopg://postgres:{quote(password, safe='')}@db/gold_test_gate"
os.environ["DATABASE_URL"] = "sqlite://"
code = pytest.main(["-c", "pytest.ini", "backend/tests", "-q", "--basetemp=/tmp/pytest-gate",
                    "-o", "cache_dir=/tmp/pytest-cache", "--junitxml=/reports/linux-tests.xml"])
raise SystemExit(code)
