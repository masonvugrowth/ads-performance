"""007 – Video transcripts table for AI-powered angle/keypoint classification.

Revision ID: 007_video_transcripts
Revises: 006_google_ads
"""

from alembic import op
import sqlalchemy as sa

revision = "007_video_transcripts"
down_revision = "006_google_ads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_transcripts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("material_id", sa.Text(), sa.ForeignKey("ad_materials.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("combo_id", sa.Text(), sa.ForeignKey("ad_combos.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("video_url", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("ai_analysis", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING", index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_time_seconds", sa.Float(), nullable=True),
        sa.Column("triggered_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("video_transcripts")
