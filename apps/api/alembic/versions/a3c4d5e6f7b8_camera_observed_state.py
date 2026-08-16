"""camera_observed_state

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
Create Date: 2026-07-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c4d5e6f7b8"
down_revision: str | Sequence[str] | None = "f2b3c4d5e6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cameras", sa.Column("fps", sa.Float(), nullable=True))
    op.add_column("cameras", sa.Column("latency_ms", sa.Float(), nullable=True))
    op.add_column("cameras", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "cameras",
        sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("cameras", sa.Column("last_stream_error", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cameras", "last_stream_error")
    op.drop_column("cameras", "reconnect_count")
    op.drop_column("cameras", "last_seen_at")
    op.drop_column("cameras", "latency_ms")
    op.drop_column("cameras", "fps")
