"""camera_media_distribution

Revision ID: 5e336d6ed50e
Revises: b4d6e8f0a1c2
Create Date: 2026-08-04 16:49:09.112958

Media Architecture Reset (ADR-028), Phase 1. Two new tables, both keyed
by (camera_id, subsystem) with a unique constraint -- one row per
publishing/reporting subsystem per camera, matching this repo's
existing "separate processes, Postgres is the only shared state"
pattern (the same reasoning already documented on ``Camera``'s Observed
State columns).

``camera_media_endpoints``: how to reach a subsystem's currently
published media (Media Distribution Interface, ``shared/
media_transport``) -- ``transport``/``address`` are opaque outside
``build_source_element()``.

``camera_subsystem_health``: a subsystem's own independently-reported
health fact for a camera -- replaces the single overloaded
``cameras.status`` column's future role as "the" health signal once
more than one subsystem reports health for the same camera.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e336d6ed50e"
down_revision: str | Sequence[str] | None = "b4d6e8f0a1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "camera_media_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("camera_id", sa.UUID(), nullable=False),
        sa.Column("subsystem", sa.String(), nullable=False),
        sa.Column("transport", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "camera_id", "subsystem", name="uq_camera_media_endpoints_camera_subsystem"
        ),
    )
    op.create_index(
        op.f("ix_camera_media_endpoints_camera_id"),
        "camera_media_endpoints",
        ["camera_id"],
        unique=False,
    )
    op.create_table(
        "camera_subsystem_health",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("camera_id", sa.UUID(), nullable=False),
        sa.Column("subsystem", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "camera_id", "subsystem", name="uq_camera_subsystem_health_camera_subsystem"
        ),
    )
    op.create_index(
        op.f("ix_camera_subsystem_health_camera_id"),
        "camera_subsystem_health",
        ["camera_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_camera_subsystem_health_camera_id"), table_name="camera_subsystem_health"
    )
    op.drop_table("camera_subsystem_health")
    op.drop_index(op.f("ix_camera_media_endpoints_camera_id"), table_name="camera_media_endpoints")
    op.drop_table("camera_media_endpoints")
