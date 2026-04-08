"""Add Google Ads tables: google_asset_groups, google_assets

Revision ID: 006_google_ads
Revises: 005_approval_system
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_google_ads"
down_revision: Union[str, None] = "005_approval_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── google_asset_groups (PMax) ──────────────────────────
    op.create_table(
        "google_asset_groups",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("platform_asset_group_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("final_urls", sa.JSON(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("platform_asset_group_id"),
    )
    op.create_index("ix_google_asset_groups_campaign_id", "google_asset_groups", ["campaign_id"])
    op.create_index("ix_google_asset_groups_account_id", "google_asset_groups", ["account_id"])
    op.create_index("ix_google_asset_groups_status", "google_asset_groups", ["status"])

    # ── google_assets ───────────────────────────────────────
    op.create_table(
        "google_assets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("asset_group_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("platform_asset_id", sa.String(100), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("text_content", sa.String(500), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("performance_label", sa.String(30), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["asset_group_id"], ["google_asset_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("asset_group_id", "platform_asset_id", name="uq_asset_group_asset"),
    )
    op.create_index("ix_google_assets_asset_group_id", "google_assets", ["asset_group_id"])
    op.create_index("ix_google_assets_account_id", "google_assets", ["account_id"])
    op.create_index("ix_google_assets_asset_type", "google_assets", ["asset_type"])


def downgrade() -> None:
    op.drop_table("google_assets")
    op.drop_table("google_asset_groups")
