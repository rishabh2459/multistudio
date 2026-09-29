"""camera layout, custom switch settings, user presets (PL1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from multicam_api.db.models import UTCDateTime

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old projects keep NULL: their layout is derived from clip roles, exactly as before.
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("layout", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("switch", sa.JSON(), nullable=True))
    op.create_table(
        "user_presets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("user_presets")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("switch")
        batch.drop_column("layout")
