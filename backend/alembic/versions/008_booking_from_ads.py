"""Add reservations and booking_matches tables

Revision ID: 008_booking_from_ads
Revises: 007_video_transcripts
Create Date: 2026-04-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_booking_from_ads"
down_revision: Union[str, None] = "007_video_transcripts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── reservations ──────────────────────────────────────
    op.create_table(
        "reservations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("reservation_number", sa.String(50), nullable=False),
        sa.Column("reservation_date", sa.Date(), nullable=True),
        sa.Column("check_in_date", sa.Date(), nullable=True),
        sa.Column("check_out_date", sa.Date(), nullable=True),
        sa.Column("grand_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("name", sa.String(300), nullable=True),
        sa.Column("email", sa.String(300), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("room_type", sa.String(200), nullable=True),
        sa.Column("branch", sa.String(100), nullable=False),
        sa.Column("nights", sa.Integer(), nullable=True),
        sa.Column("adults", sa.Integer(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_number"),
    )
    op.create_index("ix_reservations_reservation_number", "reservations", ["reservation_number"])
    op.create_index("ix_reservations_reservation_date", "reservations", ["reservation_date"])
    op.create_index("ix_reservations_source", "reservations", ["source"])
    op.create_index("ix_reservations_branch", "reservations", ["branch"])
    op.create_index("ix_reservations_status", "reservations", ["status"])
    op.create_index("ix_reservations_country", "reservations", ["country"])

    # ── booking_matches ───────────────────────────────────
    op.create_table(
        "booking_matches",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("ads_revenue", sa.Numeric(15, 2), nullable=False),
        sa.Column("ads_bookings", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ads_country", sa.String(100), nullable=True),
        sa.Column("ads_channel", sa.String(20), nullable=True),
        sa.Column("campaign_name", sa.String(500), nullable=True),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("reservation_ids", sa.String(1000), nullable=True),
        sa.Column("reservation_numbers", sa.String(1000), nullable=True),
        sa.Column("guest_names", sa.String(1000), nullable=True),
        sa.Column("guest_emails", sa.String(1000), nullable=True),
        sa.Column("reservation_statuses", sa.String(500), nullable=True),
        sa.Column("room_types", sa.String(1000), nullable=True),
        sa.Column("reservation_sources", sa.String(500), nullable=True),
        sa.Column("matched_country", sa.String(200), nullable=True),
        sa.Column("branch", sa.String(100), nullable=True),
        sa.Column("match_result", sa.String(50), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_booking_matches_match_date", "booking_matches", ["match_date"])
    op.create_index("ix_booking_matches_campaign_id", "booking_matches", ["campaign_id"])
    op.create_index("ix_booking_matches_branch", "booking_matches", ["branch"])
    op.create_index("ix_booking_matches_match_result", "booking_matches", ["match_result"])


def downgrade() -> None:
    op.drop_table("booking_matches")
    op.drop_table("reservations")
