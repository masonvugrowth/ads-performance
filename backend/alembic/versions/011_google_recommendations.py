"""Add Google Ads Power Pack recommendation engine tables

Revision ID: 011_google_recommendations
Revises: 010_user_permissions
Create Date: 2026-04-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_google_recommendations"
down_revision: Union[str, None] = "010_user_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("SET LOCAL statement_timeout = 0")

    # ── google_recommendations ────────────────────────────────
    op.create_table(
        "google_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rec_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "account_id",
            sa.String(length=36),
            sa.ForeignKey("ad_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.String(length=36),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ad_group_id",
            sa.String(length=36),
            sa.ForeignKey("ad_sets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ad_id",
            sa.String(length=36),
            sa.ForeignKey("ads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "asset_group_id",
            sa.String(length=36),
            sa.ForeignKey("google_asset_groups.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_level", sa.String(length=20), nullable=False),
        sa.Column("campaign_type", sa.String(length=20), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detector_finding", sa.JSON(), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=False),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("ai_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("suggested_action", sa.JSON(), nullable=False),
        sa.Column("auto_applicable", sa.Boolean(), nullable=False),
        sa.Column("warning_text", sa.Text(), nullable=False),
        sa.Column("sop_reference", sa.String(length=40), nullable=True),
        sa.Column("dedup_key", sa.String(length=180), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.String(length=36), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by", sa.String(length=36), nullable=True),
        sa.Column("dismiss_reason", sa.Text(), nullable=True),
        sa.Column(
            "action_log_id",
            sa.String(length=36),
            sa.ForeignKey("action_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_task_id", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_google_recs_rec_type", "google_recommendations", ["rec_type"])
    op.create_index("ix_google_recs_severity", "google_recommendations", ["severity"])
    op.create_index("ix_google_recs_status", "google_recommendations", ["status"])
    op.create_index("ix_google_recs_account_id", "google_recommendations", ["account_id"])
    op.create_index("ix_google_recs_campaign_id", "google_recommendations", ["campaign_id"])
    op.create_index("ix_google_recs_ad_group_id", "google_recommendations", ["ad_group_id"])
    op.create_index("ix_google_recs_ad_id", "google_recommendations", ["ad_id"])
    op.create_index("ix_google_recs_asset_group_id", "google_recommendations", ["asset_group_id"])
    op.create_index("ix_google_recs_campaign_type", "google_recommendations", ["campaign_type"])
    op.create_index("ix_google_recs_dedup_key", "google_recommendations", ["dedup_key"])
    op.create_index(
        "ix_google_recs_account_status_severity",
        "google_recommendations",
        ["account_id", "status", "severity"],
    )
    op.create_index(
        "ix_google_recs_campaign_status",
        "google_recommendations",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_google_recs_rec_type_status",
        "google_recommendations",
        ["rec_type", "status"],
    )
    # Partial unique index: one pending recommendation per dedup_key at a time.
    # Postgres only — SQLite dev falls back to the plain index above.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_google_recs_dedup_pending "
        "ON google_recommendations (dedup_key) WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_google_recs_expires_pending "
        "ON google_recommendations (expires_at) WHERE status = 'pending'"
    )

    # ── google_seasonality_events ─────────────────────────────
    op.create_table(
        "google_seasonality_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("start_month", sa.SmallInteger(), nullable=False),
        sa.Column("start_day", sa.SmallInteger(), nullable=False),
        sa.Column("end_month", sa.SmallInteger(), nullable=False),
        sa.Column("end_day", sa.SmallInteger(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("budget_bump_pct_min", sa.Numeric(5, 2), nullable=True),
        sa.Column("budget_bump_pct_max", sa.Numeric(5, 2), nullable=True),
        sa.Column("tcpa_adjust_pct_min", sa.Numeric(5, 2), nullable=True),
        sa.Column("tcpa_adjust_pct_max", sa.Numeric(5, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("event_key", name="uq_google_seasonality_event_key"),
    )

    # Seed Vietnam-hotel seasonality events per SOP Part 6.2
    op.execute(
        """
        INSERT INTO google_seasonality_events (
            id, event_key, name, start_month, start_day, end_month, end_day,
            lead_time_days, budget_bump_pct_min, budget_bump_pct_max,
            tcpa_adjust_pct_min, tcpa_adjust_pct_max, notes,
            created_at, updated_at
        ) VALUES
        ('11111111-0000-0000-0000-000000000001', 'tet', 'Lunar New Year (Tet)',
            1, 15, 2, 28, 21, 30, 50, 20, 30,
            'Book-ahead behavior peaks in January. Raise budget mid-January; do not wait for peak.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000002', 'lien_30_4', 'Reunification & Labor Day (30/4 - 1/5)',
            4, 15, 5, 3, 14, 20, 30, 15, 20,
            'Short peak around the long weekend. 2-week lead time is sufficient.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000003', 'he_summer', 'Summer Peak',
            5, 15, 8, 31, 30, 40, 60, 0, 10,
            'Family travel season. Start lifting budget early May; creative should emphasize pool / family rooms.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000004', 'le_2_9', 'National Day (2/9)',
            8, 20, 9, 4, 14, 20, 30, 10, 15,
            'Mid-length holiday. 2-week lead time.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000005', 'christmas', 'Christmas & Year-End',
            11, 15, 12, 31, 30, 20, 40, 10, 15,
            'Year-end peak with high ADR. Ramp budget from early November.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000006', 'low_spring', 'Low Season (Spring)',
            3, 1, 3, 31, 7, -15, -10, -15, -10,
            'Shift spend to Demand Gen for warm-up; tighten tCPA to protect ROAS.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('11111111-0000-0000-0000-000000000007', 'low_autumn', 'Low Season (Autumn)',
            9, 15, 10, 31, 7, -15, -10, -15, -10,
            'Shift spend to Demand Gen for warm-up; tighten tCPA to protect ROAS.',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )

    # ── google_search_term_patterns ───────────────────────────
    op.create_table(
        "google_search_term_patterns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("pattern", sa.String(length=160), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true" if is_postgres else "1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_google_search_term_patterns_locale",
        "google_search_term_patterns",
        ["locale"],
    )
    op.create_index(
        "ix_google_search_term_patterns_category",
        "google_search_term_patterns",
        ["category"],
    )
    op.create_index(
        "ix_google_search_term_patterns_is_active",
        "google_search_term_patterns",
        ["is_active"],
    )

    # Seed negative-keyword regex patterns per SOP Part 2.6
    op.execute(
        """
        INSERT INTO google_search_term_patterns (id, locale, category, pattern, is_active, created_at, updated_at) VALUES
        ('22222222-0000-0000-0000-000000000001', 'vi-VN', 'jobs', '(?i)(viec\\s*lam|tuyen\\s*dung|xin\\s*viec|nhan\\s*vien|cv)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000002', 'en', 'jobs', '(?i)(career|job|hiring|recruit|employ)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000003', 'vi-VN', 'press', '(?i)(bao\\s*chi|tin\\s*tuc|phong\\s*vien|thong\\s*cao)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000004', 'en', 'press', '(?i)(press|media\\s*kit|journalist|news\\s*release)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000005', 'vi-VN', 'academic', '(?i)(de\\s*tai|nghien\\s*cuu|luan\\s*van|luan\\s*an|case\\s*study)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000006', 'en', 'academic', '(?i)(thesis|research\\s*paper|case\\s*study|dissertation)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000007', 'vi-VN', 'free', '(?i)(mien\\s*phi|free|gratis|khong\\s*mat\\s*tien)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000008', 'en', 'free', '(?i)(\\bfree\\b|freebie|no\\s*cost|gratis)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000009', 'vi-VN', 'cancel', '(?i)(huy\\s*phong|refund|hoan\\s*tien|complaint|khieu\\s*nai)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
        ('22222222-0000-0000-0000-000000000010', 'en', 'cancel', '(?i)(cancel|refund|complaint|charge\\s*back)', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_google_search_term_patterns_is_active", table_name="google_search_term_patterns")
    op.drop_index("ix_google_search_term_patterns_category", table_name="google_search_term_patterns")
    op.drop_index("ix_google_search_term_patterns_locale", table_name="google_search_term_patterns")
    op.drop_table("google_search_term_patterns")

    op.drop_table("google_seasonality_events")

    op.execute("DROP INDEX IF EXISTS ix_google_recs_expires_pending")
    op.execute("DROP INDEX IF EXISTS uq_google_recs_dedup_pending")
    op.drop_index("ix_google_recs_rec_type_status", table_name="google_recommendations")
    op.drop_index("ix_google_recs_campaign_status", table_name="google_recommendations")
    op.drop_index("ix_google_recs_account_status_severity", table_name="google_recommendations")
    op.drop_index("ix_google_recs_dedup_key", table_name="google_recommendations")
    op.drop_index("ix_google_recs_campaign_type", table_name="google_recommendations")
    op.drop_index("ix_google_recs_asset_group_id", table_name="google_recommendations")
    op.drop_index("ix_google_recs_ad_id", table_name="google_recommendations")
    op.drop_index("ix_google_recs_ad_group_id", table_name="google_recommendations")
    op.drop_index("ix_google_recs_campaign_id", table_name="google_recommendations")
    op.drop_index("ix_google_recs_account_id", table_name="google_recommendations")
    op.drop_index("ix_google_recs_status", table_name="google_recommendations")
    op.drop_index("ix_google_recs_severity", table_name="google_recommendations")
    op.drop_index("ix_google_recs_rec_type", table_name="google_recommendations")
    op.drop_table("google_recommendations")
