"""Widen ad_sets.country from VARCHAR(2) to VARCHAR(8)

Revision ID: 021_ad_set_country_widen
Revises: 020_metrics_video
Create Date: 2026-04-23

Adsets with 'All_*' names are now parsed as country='ALL' (3 chars), a
multi-country marker that doesn't fit in VARCHAR(2). Widening to VARCHAR(8)
also gives headroom for possible future markers without another migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_ad_set_country_widen"
down_revision: Union[str, None] = "020_metrics_video"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        # Idempotent: ALTER TYPE is safe to re-run and has no IF NOT EXISTS form.
        op.execute("ALTER TABLE ad_sets ALTER COLUMN country TYPE VARCHAR(8)")
    else:
        with op.batch_alter_table("ad_sets") as batch:
            batch.alter_column(
                "country",
                existing_type=sa.String(length=2),
                type_=sa.String(length=8),
                existing_nullable=True,
            )


def downgrade() -> None:
    # Truncates any value longer than 2 chars — data loss for 'ALL' rows.
    with op.batch_alter_table("ad_sets") as batch:
        batch.alter_column(
            "country",
            existing_type=sa.String(length=8),
            type_=sa.String(length=2),
            existing_nullable=True,
        )
