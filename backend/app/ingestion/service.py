from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    DailyReferencePrice,
    DataSource,
    FxSnapshot,
    GoldProduct,
    IngestionRun,
    QuoteSnapshot,
    SpotSnapshot,
)
from app.providers.base import Observation

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MODELS = {"gold": QuoteSnapshot, "spot": SpotSnapshot, "fx": FxSnapshot}


def lock_ingestion(session: Session) -> None:
    if session.bind.dialect.name == "postgresql":
        # Serializes all writers, including imports and scheduled jobs. Released on transaction end.
        session.execute(text("SELECT pg_advisory_xact_lock(74198014)"))


def ingest(
    session: Session,
    observations: list[Observation],
    settings: Settings,
    *,
    rights_confirmed: bool = False,
    now: datetime | None = None,
) -> dict:
    """Caller owns commit; all rows in one batch are atomic. Never mutates an existing snapshot."""
    lock_ingestion(session)
    now = now or datetime.now(UTC)
    counts = {"inserted": 0, "duplicates": 0, "quarantined": 0}
    threshold = Decimal(settings.outlier_threshold_pct)
    if not threshold.is_finite() or not Decimal("0") < threshold <= Decimal("100"):
        raise ValueError("Ngưỡng quarantine không hợp lệ")
    for obs in sorted(observations, key=lambda item: item.provider_timestamp):
        source = session.get(DataSource, obs.provider_id)
        if source is None:
            raise ValueError("provider_id chưa có trong catalog")
        if obs.reference_type == "sample" and settings.app_env == "production":
            raise ValueError("Cấm SAMPLE DATA trong production")
        if obs.reference_type == "manual" and not rights_confirmed:
            raise ValueError("CSV cần xác nhận quyền sử dụng dữ liệu")
        if obs.reference_type == "official" and source.license_status != "licensed":
            raise ValueError("Nguồn official chưa được cấp phép")
        if obs.provider_timestamp > now + timedelta(minutes=5):
            raise ValueError("Timestamp nằm trong tương lai")
        model = MODELS[obs.kind]
        filters = [model.provider_id == obs.provider_id]
        if obs.kind == "gold":
            product = session.get(GoldProduct, obs.product_id)
            if product is None or product.provider_id != obs.provider_id:
                raise ValueError("Sai provider/product/region")
            filters.append(model.product_id == obs.product_id)
        existing = session.scalar(
            select(model).where(*filters, model.provider_timestamp == obs.provider_timestamp)
        )
        if existing:
            if existing.raw_payload_hash != obs.raw_payload_hash:
                raise ValueError("Conflicting duplicate: cần reconciliation, không ghi đè snapshot")
            counts["duplicates"] += 1
            counts["quarantined"] += int(existing.quality_flag == "quarantined")
            continue
        previous = session.scalar(
            select(model)
            .where(*filters, model.quality_flag == "valid", model.provider_timestamp < obs.provider_timestamp)
            .order_by(model.provider_timestamp.desc())
            .limit(1)
        )
        current_value = obs.ask if obs.kind == "gold" else obs.value
        previous_value = None
        if previous:
            previous_value = (
                previous.ask
                if obs.kind == "gold"
                else (previous.price if obs.kind == "spot" else previous.rate)
            )
        outlier = bool(previous_value and abs(current_value / previous_value - 1) * 100 > threshold)
        if obs.kind == "gold" and previous and previous.bid > 0:
            outlier = outlier or abs(obs.bid / previous.bid - 1) * 100 > threshold
        payload = dict(
            provider_id=obs.provider_id,
            source_url=source.source_url,
            provider_timestamp=obs.provider_timestamp,
            fetched_at=now,
            business_date=obs.provider_timestamp.astimezone(VN).date(),
            raw_payload_hash=obs.raw_payload_hash,
            reference_type=obs.reference_type,
            quality_flag="quarantined" if outlier else "valid",
            quality_reason="price_jump_requires_review" if outlier else None,
        )
        if obs.kind == "gold":
            payload.update(product_id=obs.product_id, bid=obs.bid, ask=obs.ask)
        else:
            payload["price" if obs.kind == "spot" else "rate"] = obs.value
        session.add(model(**payload))
        session.flush()
        counts["inserted"] += 1
        counts["quarantined"] += int(outlier)
    return counts


def record_run(
    session: Session,
    provider_id: str,
    status: str,
    *,
    counts=None,
    error_code=None,
    started_at: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        IngestionRun(
            provider_id=provider_id,
            status=status,
            started_at=started_at or now,
            finished_at=now,
            error_code=error_code,
            **(counts or {}),
        )
    )
    source = session.get(DataSource, provider_id)
    if source:
        if status == "success":
            source.last_success_at = now
            source.last_error_code = None
        else:
            source.last_error_code = error_code or status


def select_snapshot(session: Session, model, day: date, settings: Settings, **filters):
    cutoff = datetime.combine(day, time(settings.daily_close_hour), VN).astimezone(UTC)
    statement = (
        select(model)
        .filter_by(**filters)
        .where(
            model.business_date == day,
            model.quality_flag == "valid",
            model.provider_timestamp <= cutoff,
            model.provider_timestamp >= cutoff - timedelta(minutes=settings.daily_max_lag_minutes),
        )
    )
    if settings.app_env == "production":
        statement = statement.where(model.reference_type != "sample")
    return session.scalar(statement.order_by(model.provider_timestamp.desc(), model.id.desc()).limit(1))


def reconcile_day(session: Session, day: date, settings: Settings) -> int:
    lock_ingestion(session)
    # Only these explicitly defined reference series are eligible. No silent source switching.
    spot = select_snapshot(session, SpotSnapshot, day, settings, provider_id="manual-spot")
    if spot is None:
        spot = select_snapshot(session, SpotSnapshot, day, settings, provider_id="metals-dev")
    fx = select_snapshot(
        session, FxSnapshot, day, settings, provider_id="manual-fx", convention="reference_mid"
    )
    count = 0
    for product in session.scalars(select(GoldProduct).order_by(GoldProduct.id)):
        quote = select_snapshot(session, QuoteSnapshot, day, settings, product_id=product.id)
        if quote is None:
            continue
        row = session.scalar(
            select(DailyReferencePrice).where(
                DailyReferencePrice.product_id == product.id, DailyReferencePrice.business_date == day
            )
        )
        if row is None:
            row = DailyReferencePrice(product_id=product.id, business_date=day)
            session.add(row)
        row.quote_snapshot_id = quote.id
        row.spot_snapshot_id = spot.id if spot else None
        row.fx_snapshot_id = fx.id if fx else None
        row.selection_method = f"last_at_or_before_{settings.daily_close_hour:02d}:00_VN_max_lag_{settings.daily_max_lag_minutes}m"
        count += 1
    session.flush()
    return count
