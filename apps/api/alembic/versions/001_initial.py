"""Initial schema: regions, events, alert_subscriptions

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # regions table
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "geom",
            sa.Text(),  # stored as WKT; GeoAlchemy2 handles serialisation
            nullable=False,
        ),
        sa.Column("detection_types", JSONB(), nullable=False, server_default="[]"),
        sa.Column("cadence", sa.Integer(), nullable=False, server_default="24"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Use raw SQL for the PostGIS geometry column (GeoAlchemy2 DDL)
    op.execute(
        """
        ALTER TABLE regions
        ADD COLUMN IF NOT EXISTS geom_postgis geometry(Polygon, 4326)
        """
    )
    op.execute("ALTER TABLE regions DROP COLUMN IF EXISTS geom")
    op.execute("ALTER TABLE regions RENAME COLUMN geom_postgis TO geom")
    op.execute("CREATE INDEX idx_regions_geom ON regions USING GIST (geom)")

    # events table
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("detected_type", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("before_tile_url", sa.Text(), nullable=True),
        sa.Column("after_tile_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_events_region_id", "events", ["region_id"])
    op.create_index("idx_events_first_seen", "events", ["first_seen"])
    op.create_index("idx_events_detected_type", "events", ["detected_type"])

    # alert_subscriptions table
    op.create_table(
        "alert_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("slack_webhook", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["region_id"], ["regions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_alert_subscriptions_region_id",
        "alert_subscriptions",
        ["region_id"],
    )


def downgrade() -> None:
    op.drop_table("alert_subscriptions")
    op.drop_table("events")
    op.drop_table("regions")
    op.execute("DROP EXTENSION IF EXISTS postgis")
