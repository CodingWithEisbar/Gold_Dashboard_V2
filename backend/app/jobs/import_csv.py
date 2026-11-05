import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.config import get_settings
from app.db import engine
from app.ingestion.service import VN, ingest, reconcile_day, record_run
from app.models import DataSource
from app.providers.csv_provider import read_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Nhập CSV quản trị; không có HTTP upload")
    parser.add_argument("file", type=Path)
    parser.add_argument("--import-root", type=Path, required=True)
    parser.add_argument("--confirm-data-rights", action="store_true")
    args = parser.parse_args()
    started_at = datetime.now(UTC)
    observations = read_csv(args.file, args.import_root)
    providers = {o.provider_id for o in observations}
    with Session(engine) as session:
        try:
            seed_catalog(session)
            counts = {"inserted": 0, "duplicates": 0, "quarantined": 0}
            provider_counts = {}
            for provider_id in sorted(providers):
                provider_counts[provider_id] = ingest(
                    session,
                    [o for o in observations if o.provider_id == provider_id],
                    get_settings(),
                    rights_confirmed=args.confirm_data_rights,
                )
                for key in counts:
                    counts[key] += provider_counts[provider_id][key]
            for day in sorted({o.provider_timestamp.astimezone(VN).date() for o in observations}):
                reconcile_day(session, day, get_settings())
            for provider_id in providers:
                record_run(
                    session,
                    provider_id,
                    "success",
                    counts=provider_counts[provider_id],
                    started_at=started_at,
                )
            session.commit()
        except Exception:
            session.rollback()
            for provider_id in providers:
                if session.get(DataSource, provider_id):
                    record_run(session, provider_id, "failed", error_code="csv_import_rejected")
            session.commit()
            raise SystemExit(
                "CSV bị từ chối; kiểm tra schema, quyền sử dụng, timestamp, duplicate hoặc sample production"
            ) from None
    print(json.dumps({"event": "csv_import", "status": "success", **counts}))


if __name__ == "__main__":
    main()
