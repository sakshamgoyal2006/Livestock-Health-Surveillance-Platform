"""Add Checkpoint 2 analysis artifacts and retryable triage jobs.

Revision ID: 0002_checkpoint_2
Revises: 0001_checkpoint_1
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op
from app.db.base import Base
from app.domain import models  # noqa: F401

revision = "0002_checkpoint_2"
down_revision = "0001_checkpoint_1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("triage_jobs")
    op.drop_table("analysis_artifacts")
