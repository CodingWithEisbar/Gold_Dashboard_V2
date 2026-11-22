"""Local Compose worker. Poll on startup and at each full hour while the VM is running."""

import json
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import engine
from app.jobs.collect_daily import collect_source


def main():
    settings = get_settings()
    enabled = {
        "sjc": settings.sjc_enabled,
        "btmh": settings.btmh_enabled,
        "doji": settings.doji_enabled,
        "investing-gold": settings.investing_enabled,
        "metals-dev": settings.metals_license_confirmed,
    }
    print(json.dumps({"event": "hourly_worker_started", "sources": [k for k, v in enabled.items() if v]}))
    while True:
        for source, active in enabled.items():
            if active:
                try:
                    with Session(engine) as session:
                        report = collect_source(session, source, settings, hourly=True)
                except SQLAlchemyError:
                    report = {"provider_id": source, "status": "failed", "error_code": "database_unavailable"}
                print(json.dumps(report), flush=True)
        now = datetime.now(UTC)
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        time.sleep((next_hour - now).total_seconds())


if __name__ == "__main__":
    main()
