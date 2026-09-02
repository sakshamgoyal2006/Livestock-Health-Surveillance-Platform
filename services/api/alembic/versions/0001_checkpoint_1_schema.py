"""Create the Checkpoint 1 PostGIS domain schema.

Revision ID: 0001_checkpoint_1
Revises: None
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op
from app.db.base import Base
from app.domain import models  # noqa: F401

revision = "0001_checkpoint_1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
