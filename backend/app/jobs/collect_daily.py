import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.config import get_settings
from app.db import engine
from app.ingestion.service import VN, ingest, reconcile_day, record_run
from app.models import DataSource
from app.providers.metals_dev import MetalsDevSpotProvider
from app.providers.safe_http import SourceUnavailable


def main() -> None:
    settings = get_settings()
    failed = False
    with Session(engine) as session:
        seed_catalog(session)
        session.commit()
        for source_id in ("sjc", "pnj", "manual-fx"):
            record_run(session, source_id, "source_unavailable", error_code="use_licensed_csv")
            print(
                json.dumps({"provider_id": source_id, "status": "source_unavailable", "action": "import_csv"})
            )
        session.commit()
        started_at = datetime.now(UTC)
        try:
            source = session.get(DataSource, "metals-dev")
            if source.license_status != "licensed":
                raise SourceUnavailable("license_not_approved_in_catalog")
            observations = MetalsDevSpotProvider(settings).fetch()
            counts = ingest(session, observations, settings)
            for day in {o.provider_timestamp.astimezone(VN).date() for o in observations}:
                reconcile_day(session, day, settings)
            record_run(session, "metals-dev", "success", counts=counts, started_at=started_at)
            session.commit()
            print(json.dumps({"provider_id": "metals-dev", "status": "success", **counts}))
        except (SourceUnavailable, ValueError) as exc:
            session.rollback()
            code = str(exc) if isinstance(exc, SourceUnavailable) else "quality_validation_failed"
            record_run(session, "metals-dev", "source_unavailable", error_code=code, started_at=started_at)
            session.commit()
            failed = True
            print(
                json.dumps({"provider_id": "metals-dev", "status": "source_unavailable", "error_code": code})
            )
        reconcile_day(session, datetime.now(UTC).astimezone(VN).date(), settings)
        session.commit()
    # Exit nonzero so monitoring alerts on incomplete sources, including domestic/FX blockers.
    raise SystemExit(2 if failed else 3)


if __name__ == "__main__":
    main()
