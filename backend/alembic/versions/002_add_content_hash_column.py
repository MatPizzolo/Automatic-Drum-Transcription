"""Add content_hash column to jobs table for upload idempotency

Revision ID: 002_add_content_hash_column
Revises: 001_add_cancelling_cancelled
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "002_add_content_hash_column"
down_revision = "001_add_cancelling_cancelled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_jobs_content_hash",
        "jobs",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_content_hash", table_name="jobs")
    op.drop_column("jobs", "content_hash")
