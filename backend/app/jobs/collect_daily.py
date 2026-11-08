"""Finite CLI jobs for Dokploy Compose Schedule Jobs; never an API scheduler."""

import argparse
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog import seed_catalog
from app.config import Settings, get_settings
from app.db import engine
from app.ingestion.service import VN, ingest, reconcile_day, record_run
from app.models import DataSource, IngestionRun
from app.providers.btmh import PARSER_VERSION, BtmhGoldProvider
from app.providers.metals_dev import MetalsDevSpotProvider
from app.providers.safe_http import SourceUnavailable

PROVIDERS = {"btmh": BtmhGoldProvider, "metals-dev": MetalsDevSpotProvider}
# Stable transaction locks serialize each source's HTTP request + write + run accounting.
SOURCE_LOCKS = {"btmh": 74198015, "metals-dev": 74198016}


def collect_source(
    session: Session, source_id: str, settings: Settings, *, now: datetime | None = None
) -> dict:
    started_at = now or datetime.now(UTC)
    result = {"provider_id": source_id, "started_at": started_at.isoformat()}
    if source_id == "btmh":
        result["parser_version"] = PARSER_VERSION
    try:
        if session.bind.dialect.name == "postgresql":
            locked = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SOURCE_LOCKS[source_id]}
            )
            if not locked:
                session.rollback()
                return {**result, "status": "skipped", "reason": "source_job_already_running"}
        if source_id == "btmh":
            previous = session.scalar(
                select(IngestionRun)
                .where(IngestionRun.provider_id == source_id)
                .order_by(IngestionRun.started_at.desc())
                .limit(1)
            )
            if previous and started_at - previous.started_at < timedelta(
                minutes=settings.btmh_min_interval_minutes
            ):
                session.rollback()
                return {**result, "status": "skipped", "reason": "poll_interval_not_elapsed"}
        source = session.get(DataSource, source_id)
        if source is None or source.license_status != "licensed":
            raise SourceUnavailable("license_not_approved_in_catalog")
        if source.next_poll_after and source.next_poll_after > started_at:
            until = source.next_poll_after.isoformat()
            session.rollback()
            return {
                **result,
                "status": "skipped",
                "reason": "provider_retry_after_active",
                "next_poll_after": until,
            }
        observations = PROVIDERS[source_id](settings).fetch()
        if not observations or any(obs.provider_id != source_id for obs in observations):
            raise SourceUnavailable("provider_schema_changed")
        counts = ingest(session, observations, settings, now=started_at)
        days = {obs.provider_timestamp.astimezone(VN).date() for obs in observations}
        days.add(started_at.astimezone(VN).date())
        for day in sorted(days):
            reconcile_day(session, day, settings)
        if counts["quarantined"]:
            record_run(
                session,
                source_id,
                "quarantined",
                counts=counts,
                error_code="price_jump_requires_review",
                started_at=started_at,
            )
            session.commit()
            return {**result, "status": "quarantined", "error_code": "price_jump_requires_review", **counts}
        record_run(session, source_id, "success", counts=counts, started_at=started_at)
        source.next_poll_after = None
        session.commit()
        return {
            **result,
            "status": "success",
            **counts,
            "observed_at": max(obs.provider_timestamp for obs in observations).isoformat(),
        }
    except (SourceUnavailable, ValueError) as exc:
        # Never print raw provider content, HTTP URLs with keys, or database errors.
        session.rollback()
        code = str(exc) if isinstance(exc, SourceUnavailable) else "quality_validation_failed"
        record_run(session, source_id, "source_unavailable", error_code=code, started_at=started_at)
        if isinstance(exc, SourceUnavailable) and exc.retry_after_seconds is not None:
            source = session.get(DataSource, source_id)
            try:
                # Use the failure time, not job start; never shorten an upstream retry window.
                source.next_poll_after = (now or datetime.now(UTC)) + timedelta(
                    seconds=exc.retry_after_seconds
                )
            except OverflowError:
                source.next_poll_after = datetime.max.replace(tzinfo=UTC)
            result["next_poll_after"] = source.next_poll_after.isoformat()
        session.commit()
        return {**result, "status": "source_unavailable", "error_code": code}


def run_collection(session: Session, settings: Settings, source_id: str = "all") -> tuple[list[dict], int]:
    seed_catalog(session)
    session.commit()
    results = []
    if source_id == "all":
        for missing in ("sjc", "pnj", "manual-fx"):
            record_run(session, missing, "source_unavailable", error_code="use_licensed_csv")
            results.append({"provider_id": missing, "status": "source_unavailable", "action": "import_csv"})
        session.commit()
    for selected in PROVIDERS if source_id == "all" else (source_id,):
        results.append(collect_source(session, selected, settings))
    if any(
        item["status"] in ("source_unavailable", "quarantined") and item.get("action") != "import_csv"
        for item in results
    ):
        return results, 2
    return results, 3 if source_id == "all" else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("all", *PROVIDERS), default="all")
    args = parser.parse_args()
    try:
        settings = get_settings()
        with Session(engine) as session:
            results, code = run_collection(session, settings, args.source)
        for result in results:
            print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(code)
    except SQLAlchemyError:
        print(
            json.dumps({"provider_id": args.source, "status": "failed", "error_code": "database_unavailable"})
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
