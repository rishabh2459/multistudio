"""Alembic environment: uses the engine handed over by ``multicam_api.db.migrate``."""

from __future__ import annotations

from alembic import context

from multicam_api.db.models import Base

config = context.config
engine = config.attributes["engine"]

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
