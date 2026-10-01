"""plugin sessions (PL2, Plugin API v1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from multicam_api.db.models import UTCDateTime

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("host_app", sa.String(length=20), nullable=False),
        sa.Column("host_version", sa.String(length=40), nullable=False),
        sa.Column("host_os", sa.String(length=20), nullable=False),
        sa.Column("host_sequence_id", sa.String(length=200), nullable=True),
        sa.Column("already_synced", sa.Boolean(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("clip_refs", sa.JSON(), nullable=False),
        sa.Column("host_start_frame", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host_app", "host_sequence_id"),
    )
    with op.batch_alter_table("plugin_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_plugin_sessions_project_id"), ["project_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("plugin_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plugin_sessions_project_id"))
    op.drop_table("plugin_sessions")
