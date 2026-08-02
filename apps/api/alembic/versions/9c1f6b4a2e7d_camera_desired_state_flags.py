"""camera_desired_state_flags

Revision ID: 9c1f6b4a2e7d
Revises: 7a2c4e9d1b3f
Create Date: 2026-07-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c1f6b4a2e7d"
down_revision: str | Sequence[str] | None = "7a2c4e9d1b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cameras",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "cameras",
        sa.Column("recording_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cameras", "recording_enabled")
    op.drop_column("cameras", "ai_enabled")
