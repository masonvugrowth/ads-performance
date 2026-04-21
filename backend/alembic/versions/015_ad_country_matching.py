"""Split metrics revenue into website/offline and add ad×country breakdown table

Revision ID: 015_ad_country_matching
Revises: 014_booking_rate_plan
Create Date: 2026-04-20

Adds the infrastructure for the new Booking from Ads matching methodology:
  - metrics_cache gets revenue_website + revenue_offline columns so each
    campaign/ad row tracks fb_pixel_purchase and offline_conversion.purchase
    separately (in addition to the existing omni_purchase total in `revenue`).
  - ad_country_metrics is a new per-(ad|campaign)×date×country breakdown
    table populated by a Meta insights fetch with breakdowns=country and by
    Google campaign metrics where country comes from the last 2 chars of the
    campaign name. Booking matching queries this table directly.
  - booking_matches gets ad_id / ad_name / purchase_kind so each match row
    records which ad was responsible and whether the revenue came from the
    website pixel or the offline upload.

Idempotent per project memory: all DDL uses IF NOT EXISTS and the alembic
version bump is conditional.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_ad_country_matching"
down_revision: Union[str, None] = "014_booking_rate_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("ALTER TABLE metrics_cache ADD COLUMN IF NOT EXISTS revenue_website NUMERIC(15,2) NOT NULL DEFAULT 0")
        op.execute("ALTER TABLE metrics_cache ADD COLUMN IF NOT EXISTS revenue_offline NUMERIC(15,2) NOT NULL DEFAULT 0")

        op.execute("""
            CREATE TABLE IF NOT EXISTS ad_country_metrics (
                id VARCHAR(36) PRIMARY KEY,
                platform VARCHAR(20) NOT NULL,
                campaign_id VARCHAR(36) NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                ad_id VARCHAR(36) REFERENCES ads(id) ON DELETE CASCADE,
                date DATE NOT NULL,
                country VARCHAR(4) NOT NULL,
                spend NUMERIC(15,2) NOT NULL DEFAULT 0,
                impressions INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                revenue_website NUMERIC(15,2) NOT NULL DEFAULT 0,
                revenue_offline NUMERIC(15,2) NOT NULL DEFAULT 0,
                conversions_website INTEGER NOT NULL DEFAULT 0,
                conversions_offline INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_date ON ad_country_metrics(date)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_platform_date ON ad_country_metrics(platform, date)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_ad_date ON ad_country_metrics(ad_id, date)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_country_metrics_campaign_date ON ad_country_metrics(campaign_id, date)")
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_ad_country_metrics_ad
            ON ad_country_metrics(ad_id, date, country) WHERE ad_id IS NOT NULL
        """)
        op.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_ad_country_metrics_campaign
            ON ad_country_metrics(campaign_id, date, country) WHERE ad_id IS NULL
        """)

        op.execute("ALTER TABLE booking_matches ADD COLUMN IF NOT EXISTS ad_id VARCHAR(36)")
        op.execute("ALTER TABLE booking_matches ADD COLUMN IF NOT EXISTS ad_name VARCHAR(500)")
        op.execute("ALTER TABLE booking_matches ADD COLUMN IF NOT EXISTS purchase_kind VARCHAR(20)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_booking_matches_ad_id ON booking_matches(ad_id)")

        op.execute(
            "UPDATE alembic_version SET version_num = '015_ad_country_matching' "
            "WHERE version_num = '014_booking_rate_plan'"
        )
    else:
        op.add_column("metrics_cache", sa.Column("revenue_website", sa.Numeric(15, 2), nullable=False, server_default="0"))
        op.add_column("metrics_cache", sa.Column("revenue_offline", sa.Numeric(15, 2), nullable=False, server_default="0"))

        op.create_table(
            "ad_country_metrics",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("platform", sa.String(20), nullable=False),
            sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ad_id", sa.String(36), sa.ForeignKey("ads.id", ondelete="CASCADE"), nullable=True),
            sa.Column("date", sa.Date, nullable=False),
            sa.Column("country", sa.String(4), nullable=False),
            sa.Column("spend", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
            sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
            sa.Column("revenue_website", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("revenue_offline", sa.Numeric(15, 2), nullable=False, server_default="0"),
            sa.Column("conversions_website", sa.Integer, nullable=False, server_default="0"),
            sa.Column("conversions_offline", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ad_country_metrics_date", "ad_country_metrics", ["date"])

        op.add_column("booking_matches", sa.Column("ad_id", sa.String(36), nullable=True))
        op.add_column("booking_matches", sa.Column("ad_name", sa.String(500), nullable=True))
        op.add_column("booking_matches", sa.Column("purchase_kind", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("booking_matches") as batch:
        batch.drop_column("purchase_kind")
        batch.drop_column("ad_name")
        batch.drop_column("ad_id")
    op.drop_table("ad_country_metrics")
    with op.batch_alter_table("metrics_cache") as batch:
        batch.drop_column("revenue_offline")
        batch.drop_column("revenue_website")
