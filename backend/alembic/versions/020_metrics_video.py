"""Add per-ad video funnel columns to metrics_cache

Revision ID: 020_metrics_video
Revises: 019_link_clicks
Create Date: 2026-04-23

The /export/ads/metrics endpoint needs to surface the full video engagement
funnel per ad: video_views (plays) → video_3s_views → video_thru_plays →
p25/p50/p75/p100. These come from Meta Insights (video_play_actions,
video_3_sec_watched_actions, video_thruplay_watched_actions,
video_pXX_watched_actions) and are already aggregated in the combo-level
ad_combos table; this migration mirrors them at the per-day / per-ad grain
in metrics_cache so the export can slice by date_from/date_to.

Non-video ads (Google search, TikTok for now) leave these at their 0 default.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_metrics_video"
down_revision: Union[str, None] = "019_link_clicks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIDEO_COLUMNS = [
    "video_views",
    "video_3s_views",
    "video_thru_plays",
    "video_p25_views",
    "video_p50_views",
    "video_p75_views",
    "video_p100_views",
]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        for col in VIDEO_COLUMNS:
            op.execute(
                f"""
                ALTER TABLE metrics_cache
                ADD COLUMN IF NOT EXISTS {col} INTEGER NOT NULL DEFAULT 0
                """
            )
    else:
        with op.batch_alter_table("metrics_cache") as batch:
            for col in VIDEO_COLUMNS:
                batch.add_column(
                    sa.Column(col, sa.Integer(), nullable=False, server_default="0")
                )


def downgrade() -> None:
    with op.batch_alter_table("metrics_cache") as batch:
        for col in VIDEO_COLUMNS:
            batch.drop_column(col)
