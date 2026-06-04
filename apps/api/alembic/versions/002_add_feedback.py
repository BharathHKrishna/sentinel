"""add is_false_positive to events

Revision ID: 002
Revises: 001
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("is_false_positive", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_events_is_false_positive", "events", ["is_false_positive"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_events_is_false_positive", table_name="events")
    op.drop_column("events", "is_false_positive")
