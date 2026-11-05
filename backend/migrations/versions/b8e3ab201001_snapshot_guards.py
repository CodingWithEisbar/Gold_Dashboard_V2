"""PostgreSQL append-only guards and provider/product consistency."""

from alembic import op

revision = "b8e3ab201001"
down_revision = "7255fd2938d9"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""CREATE FUNCTION reject_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'snapshots are append-only'; END $$""")
    for table in ("quote_snapshots", "spot_snapshots", "fx_snapshots"):
        # Table identifiers are code-owned constants, never request input.
        op.execute(
            f"CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_snapshot_mutation()"
        )
    op.execute("""CREATE FUNCTION validate_quote_product() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM gold_products WHERE id = NEW.product_id AND provider_id = NEW.provider_id) THEN
          RAISE EXCEPTION 'provider/product mismatch';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER quote_product_match BEFORE INSERT ON quote_snapshots
                  FOR EACH ROW EXECUTE FUNCTION validate_quote_product()""")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER quote_product_match ON quote_snapshots")
    op.execute("DROP FUNCTION validate_quote_product()")
    for table in ("quote_snapshots", "spot_snapshots", "fx_snapshots"):
        op.execute(f"DROP TRIGGER immutable_snapshot ON {table}")
    op.execute("DROP FUNCTION reject_snapshot_mutation()")
