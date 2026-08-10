"""camera_lifecycle_state

Revision ID: 7a2c4e9d1b3f
Revises: 1f216fe63fe1
Create Date: 2026-07-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a2c4e9d1b3f"
down_revision: str | Sequence[str] | None = "1f216fe63fe1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIFECYCLE_VALUES = ("DRAFT", "TESTING", "VERIFIED", "OPERATIONAL", "MAINTENANCE", "DISABLED")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cameras",
        sa.Column("lifecycle_state", sa.String(), nullable=False, server_default="DRAFT"),
    )
    op.create_check_constraint(
        "ck_cameras_lifecycle_state",
        "cameras",
        f"lifecycle_state IN ({', '.join(repr(v) for v in _LIFECYCLE_VALUES)})",
    )
    op.create_unique_constraint("uq_cameras_name", "cameras", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_cameras_name", "cameras", type_="unique")
    op.drop_constraint("ck_cameras_lifecycle_state", "cameras", type_="check")
    op.drop_column("cameras", "lifecycle_state")
