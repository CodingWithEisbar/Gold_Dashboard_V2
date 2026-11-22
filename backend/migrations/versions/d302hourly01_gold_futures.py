"""Keep gold futures and their delivery contracts separate from spot prices."""

import sqlalchemy as sa
from alembic import op

revision = "d302hourly01"
down_revision = "c9d4ef202601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "futures_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.String(64), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("contract", sa.String(7), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date, nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("raw_payload_hash", sa.String(64), nullable=False),
        sa.Column("quality_flag", sa.String(24), nullable=False),
        sa.Column("reference_type", sa.String(24), nullable=False),
        sa.Column("quality_reason", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_id", "contract", "provider_timestamp"),
        sa.CheckConstraint("price > 0 AND price <= 1000000000000"),
        sa.CheckConstraint("quality_flag IN ('valid','quarantined')"),
        sa.CheckConstraint("reference_type IN ('manual','official','sample')"),
    )
    op.create_index("ix_futures_date", "futures_snapshots", ["business_date", "quality_flag"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON futures_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation()"
        )


def downgrade():
    op.drop_table("futures_snapshots")
