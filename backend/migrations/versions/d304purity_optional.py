"""Some public feed products do not specify their fineness."""

import sqlalchemy as sa
from alembic import op

revision = "d304purity"
down_revision = "d303quotetime"
branch_labels = None
depends_on = None


def change(nullable):
    # Preserve the unnamed fineness constraint when SQLite recreates the table.
    constraints = (sa.CheckConstraint("purity > 0 AND purity <= 1"),) if op.get_bind().dialect.name == "sqlite" else ()
    with op.batch_alter_table("gold_products", table_args=constraints) as batch:
        batch.alter_column("purity", existing_type=sa.Numeric(8, 6), nullable=nullable)


def upgrade():
    change(True)


def downgrade():
    # The previous schema cannot represent unknown purity. Remove only unreferenced
    # feed catalog entries. Never alter an existing observation to allow rollback.
    op.execute("""DELETE FROM gold_products WHERE provider_id = 'vang-today' AND purity IS NULL
        AND NOT EXISTS (SELECT 1 FROM quote_snapshots WHERE product_id = gold_products.id)
        AND NOT EXISTS (SELECT 1 FROM daily_reference_prices WHERE product_id = gold_products.id)""")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM gold_products WHERE purity IS NULL")):
        raise RuntimeError("Verify fineness for products with unknown purity before downgrading.")
    change(False)
