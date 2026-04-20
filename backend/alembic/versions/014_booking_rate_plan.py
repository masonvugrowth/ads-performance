"""Add rate_plan_name to reservations and rate_plans to booking_matches

Revision ID: 014_booking_rate_plan
Revises: 013_meta_recommendations
Create Date: 2026-04-20

Adds a new column to surface the PMS "rate plan" (the room-type pricing plan,
e.g. "Flexible Rate", "Non-refundable") on both reservations and on the
aggregated booking_matches rows so the Booking from Ads dashboard and the
external export API can break down matched bookings by rate plan.

Idempotent per project memory: uses IF NOT EXISTS / conditional alembic_version
bump so re-pasting over a Supabase editor run is safe.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_booking_rate_plan"
down_revision: Union[str, None] = "013_meta_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("ALTER TABLE reservations ADD COLUMN IF NOT EXISTS rate_plan_name VARCHAR(300)")
        op.execute("ALTER TABLE booking_matches ADD COLUMN IF NOT EXISTS rate_plans VARCHAR(1000)")
        op.execute(
            "UPDATE alembic_version SET version_num = '014_booking_rate_plan' "
            "WHERE version_num = '013_meta_recommendations'"
        )
    else:
        op.add_column(
            "reservations",
            sa.Column("rate_plan_name", sa.String(300), nullable=True),
        )
        op.add_column(
            "booking_matches",
            sa.Column("rate_plans", sa.String(1000), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("booking_matches") as batch:
        batch.drop_column("rate_plans")
    with op.batch_alter_table("reservations") as batch:
        batch.drop_column("rate_plan_name")
