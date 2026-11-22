from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.gold_math import premium
from app.ingestion.service import VN
from app.models import (
    DailyReferencePrice,
    FuturesSnapshot,
    FxSnapshot,
    GoldProduct,
    QuoteSnapshot,
    SpotSnapshot,
)
from app.providers.base import SAMPLE_LABEL


def quote_payload(quote: QuoteSnapshot, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    status = "stale" if now - quote.provider_timestamp > timedelta(hours=26) else "available"
    if quote.reference_type == "sample":
        status = "sample"
    return {
        "bid": quote.bid,
        "ask": quote.ask,
        "spread_vnd_per_luong": quote.ask - quote.bid,
        "business_date": quote.business_date,
        "source": quote.provider_id,
        "source_url": quote.source_url,
        "observed_at": quote.provider_timestamp,
        "time_basis": quote.time_basis,
        "fetched_at": quote.fetched_at,
        "data_status": status,
        "reference_type": quote.reference_type,
        "currency": quote.currency,
        "unit": quote.unit,
        "raw_payload_hash": quote.raw_payload_hash,
        "label": SAMPLE_LABEL if quote.reference_type == "sample" else "Giá niêm yết lý thuyết",
    }


def history(session: Session, product: GoldProduct, start: date, end: date, settings: Settings) -> list[dict]:
    rows = session.scalars(
        select(DailyReferencePrice)
        .where(
            DailyReferencePrice.product_id == product.id,
            DailyReferencePrice.business_date.between(start, end),
        )
        .order_by(DailyReferencePrice.business_date)
    ).all()
    by_day = {row.business_date: row for row in rows}
    data = []
    day = start
    while day <= end:
        row = by_day.get(day)
        quote = session.get(QuoteSnapshot, row.quote_snapshot_id) if row else None
        if quote is None or (settings.app_env == "production" and quote.reference_type == "sample"):
            data.append({"business_date": day, "data_status": "missing", "premium": None})
        else:
            payload = quote_payload(quote)
            payload.update(selection_method=row.selection_method, premium=None, premium_status="missing")
            spot = session.get(SpotSnapshot, row.spot_snapshot_id) if row.spot_snapshot_id else None
            fx = session.get(FxSnapshot, row.fx_snapshot_id) if row.fx_snapshot_id else None
            eligible = (
                spot
                and fx
                and product.purity == Decimal("0.9999")
                and (
                    settings.app_env != "production"
                    or (spot.reference_type != "sample" and fx.reference_type != "sample")
                )
            )
            if eligible:
                timestamps = [quote.provider_timestamp, spot.provider_timestamp, fx.provider_timestamp]
                skew_seconds = int((max(timestamps) - min(timestamps)).total_seconds())
                payload["premium"] = premium(quote.bid, quote.ask, spot.price, fx.rate)
                payload["premium_status"] = (
                    "aligned_daily"
                    if quote.time_basis == "provider" and skew_seconds <= settings.premium_tolerance_minutes * 60
                    else "indicative_daily"
                )
                payload["timestamp_skew_seconds"] = skew_seconds
                payload["premium_reference_type"] = "daily"
                payload["spot"] = {
                    "value": spot.price,
                    "source": spot.provider_id,
                    "observed_at": spot.provider_timestamp,
                    "unit": spot.unit,
                    "reference_type": spot.reference_type,
                    "source_url": spot.source_url,
                }
                payload["fx"] = {
                    "value": fx.rate,
                    "source": fx.provider_id,
                    "observed_at": fx.provider_timestamp,
                    "unit": fx.unit,
                    "convention": fx.convention,
                    "reference_type": fx.reference_type,
                    "source_url": fx.source_url,
                }
                if any(item.reference_type == "sample" for item in (quote, spot, fx)):
                    payload.update(data_status="sample", label=SAMPLE_LABEL)
            data.append(payload)
        day += timedelta(days=1)
    return data


def observed_on(session: Session, product_id: str, day: date, settings: Settings):
    row = session.scalar(
        select(DailyReferencePrice).where(
            DailyReferencePrice.product_id == product_id, DailyReferencePrice.business_date == day
        )
    )
    quote = session.get(QuoteSnapshot, row.quote_snapshot_id) if row else None
    if quote and settings.app_env == "production" and quote.reference_type == "sample":
        return None
    return quote


def vn_today() -> date:
    return datetime.now(UTC).astimezone(VN).date()


def hourly_history(session: Session, start: date, settings: Settings, *, end: date | None = None) -> list[dict]:
    """Last valid published observation in each Vietnam hour, within a single series."""
    products = {p.id: p for p in session.scalars(select(GoldProduct))}
    buckets = {}
    for model in (QuoteSnapshot, SpotSnapshot, FuturesSnapshot):
        statement = select(model).where(
            model.business_date.between(start, end or start), model.quality_flag == "valid"
        )
        if settings.app_env == "production":
            statement = statement.where(model.reference_type != "sample")
        snapshots = session.scalars(statement.order_by(model.provider_timestamp, model.id)
                                    .execution_options(yield_per=256))
        for snapshot in snapshots:
            hour = snapshot.provider_timestamp.astimezone(VN).replace(minute=0, second=0, microsecond=0)
            if isinstance(snapshot, QuoteSnapshot):
                product = products[snapshot.product_id]
                name = f"{product.name} · {product.location}"
                symbol = product.id
                kind = "gold"
            elif isinstance(snapshot, FuturesSnapshot):
                symbol = snapshot.contract
                name = "Gold Futures · " + symbol
                kind = "future"
            else:
                symbol = "XAU/USD"
                name = "Vàng giao ngay · " + snapshot.provider_id
                kind = "spot"
            buckets[(kind, snapshot.provider_id, symbol, hour)] = {
                "kind": kind, "source": snapshot.provider_id, "symbol": symbol, "name": name,
                "business_date": hour.date(),
                "hour": hour.hour, "observed_at": snapshot.provider_timestamp, "fetched_at": snapshot.fetched_at,
                "unit": snapshot.unit, "reference_type": snapshot.reference_type,
                "time_basis": snapshot.time_basis if kind == "gold" else "provider",
                "bid": snapshot.bid if kind == "gold" else None,
                "ask": snapshot.ask if kind == "gold" else None,
                "value": snapshot.price if kind != "gold" else None,
            }
    return [buckets[key] for key in sorted(buckets)]
