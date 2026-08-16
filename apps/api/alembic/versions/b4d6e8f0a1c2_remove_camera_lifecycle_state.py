"""remove_camera_lifecycle_state

Revision ID: b4d6e8f0a1c2
Revises: a3c4d5e6f7b8
Create Date: 2026-08-03 00:00:00.000000

Lifecycle (DRAFT/TESTING/VERIFIED/OPERATIONAL/MAINTENANCE/DISABLED) has
been removed as an architectural decision -- a registered camera always
connects, and AI eligibility is ``ai_enabled`` alone. This drops the
column and its check constraint added by 7a2c4e9d1b3f; that migration's
other change (``uq_cameras_name``) is untouched -- it is unrelated to
Lifecycle.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d6e8f0a1c2"
down_revision: str | Sequence[str] | None = "a3c4d5e6f7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIFECYCLE_VALUES = ("DRAFT", "TESTING", "VERIFIED", "OPERATIONAL", "MAINTENANCE", "DISABLED")


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_cameras_lifecycle_state", "cameras", type_="check")
    op.drop_column("cameras", "lifecycle_state")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "cameras",
        sa.Column("lifecycle_state", sa.String(), nullable=False, server_default="DRAFT"),
    )
    op.create_check_constraint(
        "ck_cameras_lifecycle_state",
        "cameras",
        f"lifecycle_state IN ({', '.join(repr(v) for v in _LIFECYCLE_VALUES)})",
    )
