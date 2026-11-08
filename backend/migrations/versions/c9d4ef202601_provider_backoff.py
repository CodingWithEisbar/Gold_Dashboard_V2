"""Persist provider Retry-After across scheduled processes and container restarts."""

import sqlalchemy as sa
from alembic import op

revision = "c9d4ef202601"
down_revision = "b8e3ab201001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("data_sources", sa.Column("next_poll_after", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("data_sources", "next_poll_after")
