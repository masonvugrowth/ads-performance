"""Add creative library tables: ad_materials, ad_angles, ad_copies, ad_combos, branch_keypoints

Revision ID: 002b_creative_library
Revises: 002_ad_sets_and_ads
Create Date: 2026-04-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002b_creative_library"
down_revision: Union[str, None] = "002_ad_sets_and_ads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ad_materials ---
    op.create_table(
        "ad_materials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("material_id", sa.String(10), nullable=False),
        sa.Column("material_type", sa.String(20), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_audience", sa.String(30), nullable=True),
        sa.Column("derived_verdict", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["branch_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("material_id"),
    )
    op.create_index("ix_ad_materials_branch_id", "ad_materials", ["branch_id"])
    op.create_index("ix_ad_materials_material_id", "ad_materials", ["material_id"])

    # --- ad_angles ---
    op.create_table(
        "ad_angles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=True),
        sa.Column("angle_id", sa.String(10), nullable=False),
        sa.Column("angle_type", sa.String(60), nullable=True),
        sa.Column("angle_explain", sa.Text(), nullable=True),
        sa.Column("hook_examples", sa.JSON(), nullable=True),
        sa.Column("target_audience", sa.String(30), nullable=True),
        sa.Column("angle_text", sa.Text(), nullable=False),
        sa.Column("hook", sa.String(60), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="TEST"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["branch_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("angle_id"),
    )
    op.create_index("ix_ad_angles_branch_id", "ad_angles", ["branch_id"])
    op.create_index("ix_ad_angles_angle_id", "ad_angles", ["angle_id"])

    # --- ad_copies ---
    op.create_table(
        "ad_copies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("copy_id", sa.String(10), nullable=False),
        sa.Column("target_audience", sa.String(30), nullable=False),
        sa.Column("angle_id", sa.String(10), nullable=True),
        sa.Column("headline", sa.String(500), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("cta", sa.String(200), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("derived_verdict", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["branch_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["angle_id"], ["ad_angles.angle_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("copy_id"),
    )
    op.create_index("ix_ad_copies_branch_id", "ad_copies", ["branch_id"])
    op.create_index("ix_ad_copies_copy_id", "ad_copies", ["copy_id"])

    # --- ad_combos ---
    op.create_table(
        "ad_combos",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("combo_id", sa.String(10), nullable=False),
        sa.Column("ad_name", sa.String(500), nullable=True),
        sa.Column("target_audience", sa.String(30), nullable=True),
        sa.Column("country", sa.String(10), nullable=True),
        sa.Column("keypoint_ids", sa.JSON(), nullable=True),
        sa.Column("angle_id", sa.String(10), nullable=True),
        sa.Column("copy_id", sa.String(10), nullable=False),
        sa.Column("material_id", sa.String(10), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("verdict_source", sa.String(10), nullable=False),
        sa.Column("verdict_notes", sa.Text(), nullable=True),
        sa.Column("spend", sa.Numeric(15, 2), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=True),
        sa.Column("conversions", sa.Integer(), nullable=True),
        sa.Column("revenue", sa.Numeric(15, 2), nullable=True),
        sa.Column("roas", sa.Numeric(8, 4), nullable=True),
        sa.Column("cost_per_purchase", sa.Numeric(15, 2), nullable=True),
        sa.Column("ctr", sa.Numeric(8, 6), nullable=True),
        sa.Column("engagement", sa.Integer(), nullable=True),
        sa.Column("engagement_rate", sa.Numeric(8, 6), nullable=True),
        sa.Column("video_plays", sa.Integer(), nullable=True),
        sa.Column("thruplay", sa.Integer(), nullable=True),
        sa.Column("video_p100", sa.Integer(), nullable=True),
        sa.Column("hook_rate", sa.Numeric(8, 6), nullable=True),
        sa.Column("thruplay_rate", sa.Numeric(8, 6), nullable=True),
        sa.Column("video_complete_rate", sa.Numeric(8, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["branch_id"], ["ad_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["angle_id"], ["ad_angles.angle_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["copy_id"], ["ad_copies.copy_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["ad_materials.material_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("combo_id"),
        sa.UniqueConstraint("copy_id", "material_id", name="uq_combo_copy_material"),
    )
    op.create_index("ix_ad_combos_branch_id", "ad_combos", ["branch_id"])
    op.create_index("ix_ad_combos_combo_id", "ad_combos", ["combo_id"])
    op.create_index("ix_ad_combos_campaign_id", "ad_combos", ["campaign_id"])

    # --- branch_keypoints ---
    op.create_table(
        "branch_keypoints",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("branch_id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["branch_id"], ["ad_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_branch_keypoints_branch_id", "branch_keypoints", ["branch_id"])


def downgrade() -> None:
    op.drop_table("branch_keypoints")
    op.drop_table("ad_combos")
    op.drop_table("ad_copies")
    op.drop_table("ad_angles")
    op.drop_table("ad_materials")
