"""human_review_open_dedup

Revision ID: c5d6e7f8a9b0
Revises: 5e336d6ed50e
Create Date: 2026-08-09 00:00:00.000000

Mirrors ``ux_incidents_active_camera_track``'s own pattern (same
migration, initial_schema): at most one OPEN human review item per
(camera_id, track_id) at a time -- the DB-level backstop for
``ThreatEngine``'s in-memory ``review_signaled`` dedup, which resets on
process restart.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "5e336d6ed50e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ux_human_review_items_open_camera_track",
        "human_review_items",
        ["camera_id", "track_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ux_human_review_items_open_camera_track", table_name="human_review_items")
