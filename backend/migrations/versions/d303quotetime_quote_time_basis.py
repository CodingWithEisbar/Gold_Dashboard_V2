"""Identify domestic quotes timed by reading the public board."""

import sqlalchemy as sa
from alembic import op

revision = "d303quotetime"
down_revision = "d302hourly01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "quote_snapshots", sa.Column("time_basis", sa.String(24), nullable=False, server_default="provider")
    )


def downgrade():
    op.drop_column("quote_snapshots", "time_basis")
