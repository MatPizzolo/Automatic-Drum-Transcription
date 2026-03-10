"""Add CANCELLING and CANCELLED to job_status enum

Revision ID: 001_add_cancelling_cancelled
Revises:
Create Date: 2026-02-24
"""
from alembic import op

revision = "001_add_cancelling_cancelled"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'cancelling'")
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # To roll back: recreate the enum without these values and migrate the column.
    pass
