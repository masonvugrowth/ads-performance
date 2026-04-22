"""Landing Pages feature: CMS, approvals, ad-link, Clarity snapshots

Revision ID: 017_landing_pages
Revises: 016_currency_rates
Create Date: 2026-04-22

Creates 5 tables for the Landing Page feature:

1. landing_pages               — one row per landing page (managed in CMS or
                                  imported from ads). Source is either
                                  'external' (discovered from Meta/Google ad
                                  final_urls) or 'managed' (built in our CMS).
2. landing_page_versions       — append-only snapshots of the module content
                                  for managed pages. Never UPDATE existing
                                  rows — follows the budget_allocations
                                  pattern. Latest published version points
                                  from landing_pages.current_version_id.
3. landing_page_approvals      — one approval record per version submit.
                                  ALL reviewers must approve. ANY reject = REJECTED.
                                  Pattern mirrors combo_approvals.
4. landing_page_approval_reviewers — per-reviewer decision rows (mirrors
                                  approval_reviewers table).
5. landing_page_ad_links       — link (landing_page, platform, campaign_id,
                                  ad_id) so ad-performance metrics can roll
                                  up to landing pages. UTM tags stored for
                                  cross-referencing Clarity URL data.
6. landing_page_clarity_snapshots — daily per-landing-page (+ optional UTM
                                  breakdown) snapshot from Microsoft Clarity
                                  Data Export API. Clarity only keeps 3 days
                                  of live data, so we pull daily and persist.

Idempotent per project memory: IF NOT EXISTS / ON CONFLICT, no manual
UPDATE alembic_version.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_landing_pages"
down_revision: Union[str, None] = "016_currency_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── landing_pages ───────────────────────────────────────────────────────
    op.create_table(
        "landing_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),  # external | managed
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("ad_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        # Public URL parts — the canonical live destination
        sa.Column("domain", sa.String(255), nullable=False),   # e.g. osk.staymeander.com
        sa.Column("slug", sa.String(255), nullable=False),     # e.g. couple-traveler-direct-zh
        sa.Column("language", sa.String(10), nullable=True),   # en | zh | vi | ja
        sa.Column("ta", sa.String(20), nullable=True),         # Solo | Couple | Friend | Group | Business
        # CMS lifecycle (managed pages only; external rows keep DISCOVERED)
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'DRAFT'")),
        #   DRAFT | PENDING_APPROVAL | APPROVED | PUBLISHED | REJECTED | DISCOVERED | ARCHIVED
        sa.Column("current_version_id", sa.String(36), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        # Clarity per-page config (overrides global project id if set)
        sa.Column("clarity_project_id", sa.String(50), nullable=True),
        # Ownership / audit
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", "slug", name="uq_landing_pages_domain_slug"),
    )
    op.create_index("idx_landing_pages_branch", "landing_pages", ["branch_id"])
    op.create_index("idx_landing_pages_status", "landing_pages", ["status"])
    op.create_index("idx_landing_pages_source", "landing_pages", ["source"])
    op.create_index("idx_landing_pages_is_active", "landing_pages", ["is_active"])

    # ── landing_page_versions (INSERT-only) ─────────────────────────────────
    op.create_table(
        "landing_page_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "landing_page_id",
            sa.String(36),
            sa.ForeignKey("landing_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_num", sa.Integer(), nullable=False),  # 1, 2, 3...
        sa.Column("content", sa.JSON(), nullable=False),         # 11 modules + theme + seo
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("landing_page_id", "version_num", name="uq_lp_versions_page_num"),
    )
    op.create_index("idx_lp_versions_page", "landing_page_versions", ["landing_page_id"])

    # Back-FK: landing_pages.current_version_id → landing_page_versions.id
    # Added after the versions table exists to avoid circular dependency.
    op.create_foreign_key(
        "fk_landing_pages_current_version",
        "landing_pages",
        "landing_page_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── landing_page_approvals ──────────────────────────────────────────────
    op.create_table(
        "landing_page_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "landing_page_id",
            sa.String(36),
            sa.ForeignKey("landing_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("landing_page_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'PENDING_APPROVAL'")),
        #   PENDING_APPROVAL | APPROVED | REJECTED | CANCELLED
        sa.Column(
            "submitted_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_lp_approvals_page", "landing_page_approvals", ["landing_page_id"])
    op.create_index("idx_lp_approvals_status", "landing_page_approvals", ["status"])
    op.create_index("idx_lp_approvals_submitted_by", "landing_page_approvals", ["submitted_by"])

    # ── landing_page_approval_reviewers ─────────────────────────────────────
    op.create_table(
        "landing_page_approval_reviewers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "approval_id",
            sa.String(36),
            sa.ForeignKey("landing_page_approvals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        #   PENDING | APPROVED | REJECTED
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_lp_appr_reviewers_approval", "landing_page_approval_reviewers", ["approval_id"])
    op.create_index("idx_lp_appr_reviewers_reviewer", "landing_page_approval_reviewers", ["reviewer_id"])

    # ── landing_page_ad_links ───────────────────────────────────────────────
    op.create_table(
        "landing_page_ad_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "landing_page_id",
            sa.String(36),
            sa.ForeignKey("landing_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(20), nullable=False),  # meta | google | tiktok
        sa.Column(
            "campaign_id",
            sa.String(36),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ad_id",
            sa.String(36),
            sa.ForeignKey("ads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("asset_group_id", sa.String(36), nullable=True),  # Google PMax
        # Destination URL as stored on the ad (with UTMs) — the canonical link
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(200), nullable=True),
        sa.Column("utm_content", sa.String(200), nullable=True),
        sa.Column("utm_term", sa.String(200), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_lp_ad_links_page", "landing_page_ad_links", ["landing_page_id"])
    op.create_index("idx_lp_ad_links_campaign", "landing_page_ad_links", ["campaign_id"])
    op.create_index("idx_lp_ad_links_ad", "landing_page_ad_links", ["ad_id"])
    op.create_index("idx_lp_ad_links_platform", "landing_page_ad_links", ["platform"])

    # ── landing_page_clarity_snapshots ──────────────────────────────────────
    op.create_table(
        "landing_page_clarity_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "landing_page_id",
            sa.String(36),
            sa.ForeignKey("landing_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        # UTM breakdown: NULL-NULL-NULL-NULL row = aggregate across all ads
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(200), nullable=True),
        sa.Column("utm_content", sa.String(200), nullable=True),
        sa.Column("url_raw", sa.Text(), nullable=True),  # sample raw URL observed
        # Clarity metrics (per docs: 9 metric types, sessions as integer, percentages as 0-100 float)
        sa.Column("sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("bot_sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("distinct_users", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pages_per_session", sa.Numeric(8, 4), nullable=True),
        sa.Column("avg_scroll_depth", sa.Numeric(6, 2), nullable=True),   # % 0-100
        sa.Column("total_time_sec", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active_time_sec", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("dead_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rage_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quickback_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("excessive_scrolls", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("script_errors", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # Keep raw Clarity payload for forward compat (per database-rules.md)
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "landing_page_id", "date", "utm_source", "utm_campaign", "utm_content",
            name="uq_lp_clarity_page_date_utm",
        ),
    )
    op.create_index("idx_lp_clarity_page", "landing_page_clarity_snapshots", ["landing_page_id"])
    op.create_index("idx_lp_clarity_date", "landing_page_clarity_snapshots", ["date"])


def downgrade() -> None:
    op.drop_table("landing_page_clarity_snapshots")
    op.drop_table("landing_page_ad_links")
    op.drop_table("landing_page_approval_reviewers")
    op.drop_table("landing_page_approvals")
    op.drop_constraint("fk_landing_pages_current_version", "landing_pages", type_="foreignkey")
    op.drop_table("landing_page_versions")
    op.drop_table("landing_pages")
