from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timestamp phải có timezone")
        return value.astimezone(UTC) if value else value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(500))
    license_status: Mapped[str] = mapped_column(String(40), default="unverified")
    license_note: Mapped[str] = mapped_column(String(1000), default="Chưa xác minh quyền tự động hóa")
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    next_poll_after: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class GoldProduct(Base):
    __tablename__ = "gold_products"
    __table_args__ = (
        UniqueConstraint("provider_id", "product_code", "location"),
        CheckConstraint("purity > 0 AND purity <= 1"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    product_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(64))
    purity: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    unit: Mapped[str] = mapped_column(String(24), default="VND/luong")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SnapshotMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    source_url: Mapped[str] = mapped_column(String(500))
    provider_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    business_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh")
    raw_payload_hash: Mapped[str] = mapped_column(String(64))
    quality_flag: Mapped[str] = mapped_column(String(24), default="valid")
    reference_type: Mapped[str] = mapped_column(String(24))
    quality_reason: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class QuoteSnapshot(SnapshotMixin, Base):
    __tablename__ = "quote_snapshots"
    __table_args__ = (
        UniqueConstraint("provider_id", "product_id", "provider_timestamp"),
        CheckConstraint("ask >= bid AND bid >= 0 AND ask > 0 AND ask <= 1000000000000"),
        CheckConstraint("quality_flag IN ('valid','quarantined')"),
        CheckConstraint("reference_type IN ('manual','official','sample')"),
        Index("ix_quote_series_date", "product_id", "business_date", "quality_flag"),
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("gold_products.id"))
    time_basis: Mapped[str] = mapped_column(String(24), default="provider", server_default="provider")
    bid: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    ask: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    unit: Mapped[str] = mapped_column(String(24), default="VND/luong")


class SpotSnapshot(SnapshotMixin, Base):
    __tablename__ = "spot_snapshots"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_timestamp"),
        CheckConstraint("price > 0 AND price <= 1000000000000"),
        CheckConstraint("quality_flag IN ('valid','quarantined')"),
        CheckConstraint("reference_type IN ('manual','official','sample')"),
        Index("ix_spot_date", "business_date", "quality_flag"),
    )
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    unit: Mapped[str] = mapped_column(String(24), default="USD/troy_oz")


class FuturesSnapshot(SnapshotMixin, Base):
    __tablename__ = "futures_snapshots"
    __table_args__ = (
        UniqueConstraint("provider_id", "contract", "provider_timestamp"),
        CheckConstraint("price > 0 AND price <= 1000000000000"),
        CheckConstraint("quality_flag IN ('valid','quarantined')"),
        CheckConstraint("reference_type IN ('manual','official','sample')"),
        Index("ix_futures_date", "business_date", "quality_flag"),
    )
    contract: Mapped[str] = mapped_column(String(7))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    unit: Mapped[str] = mapped_column(String(24), default="USD/troy_oz")


class FxSnapshot(SnapshotMixin, Base):
    __tablename__ = "fx_snapshots"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_timestamp", "convention"),
        CheckConstraint("rate > 0 AND rate <= 1000000000000"),
        CheckConstraint("quality_flag IN ('valid','quarantined')"),
        CheckConstraint("reference_type IN ('manual','official','sample')"),
        CheckConstraint("convention = 'reference_mid'"),
        Index("ix_fx_date", "business_date", "quality_flag"),
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), default="VND")
    unit: Mapped[str] = mapped_column(String(24), default="VND/USD")
    convention: Mapped[str] = mapped_column(String(32), default="reference_mid")


class DailyReferencePrice(Base):
    __tablename__ = "daily_reference_prices"
    __table_args__ = (UniqueConstraint("product_id", "business_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("gold_products.id"))
    business_date: Mapped[date] = mapped_column(Date)
    quote_snapshot_id: Mapped[int] = mapped_column(ForeignKey("quote_snapshots.id"))
    spot_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("spot_snapshots.id"))
    fx_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("fx_snapshots.id"))
    selection_method: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), default="running")
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))


def immutable_snapshot(mapper, connection, target):
    raise ValueError("Snapshots là append-only; dùng snapshot mới hoặc quy trình reconciliation")


for snapshot_model in (QuoteSnapshot, SpotSnapshot, FxSnapshot, FuturesSnapshot):
    event.listen(snapshot_model, "before_update", immutable_snapshot)
    event.listen(snapshot_model, "before_delete", immutable_snapshot)
