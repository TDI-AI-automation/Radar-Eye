"""camera_connection_fields

Revision ID: e1a2b3c4d5f6
Revises: 9c1f6b4a2e7d
Create Date: 2026-07-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5f6"
down_revision: str | Sequence[str] | None = "9c1f6b4a2e7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BRANDS = ("HIKVISION", "DAHUA", "UNIVIEW", "AXIS", "HANWHA")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("camera_stream_profiles", sa.Column("brand", sa.String(), nullable=True))
    op.add_column("camera_stream_profiles", sa.Column("ip_address", sa.String(), nullable=True))
    op.add_column("camera_stream_profiles", sa.Column("port", sa.Integer(), nullable=True))
    op.add_column("camera_stream_profiles", sa.Column("stream_path", sa.String(), nullable=True))
    op.add_column("camera_stream_profiles", sa.Column("username", sa.String(), nullable=True))
    op.add_column(
        "camera_stream_profiles", sa.Column("password_encrypted", sa.String(), nullable=True)
    )
    op.create_check_constraint(
        "ck_camera_stream_profiles_brand",
        "camera_stream_profiles",
        "brand IS NULL OR brand IN (" + ", ".join(repr(b) for b in _BRANDS) + ")",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_camera_stream_profiles_brand", "camera_stream_profiles", type_="check")
    op.drop_column("camera_stream_profiles", "password_encrypted")
    op.drop_column("camera_stream_profiles", "username")
    op.drop_column("camera_stream_profiles", "stream_path")
    op.drop_column("camera_stream_profiles", "port")
    op.drop_column("camera_stream_profiles", "ip_address")
    op.drop_column("camera_stream_profiles", "brand")
