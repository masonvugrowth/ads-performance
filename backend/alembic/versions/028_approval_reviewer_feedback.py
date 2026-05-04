"""Add feedback column to approval_reviewers for per-reviewer ad-copy feedback.

Revision ID: 028_approval_reviewer_feedback
Revises: 027_budget_yearly_plans
Create Date: 2026-05-04

Reviewers can now leave free-text feedback alongside their decision so the
creator can see exactly what to revise on the ad copy / combo.

Idempotent: ADD COLUMN IF NOT EXISTS on Postgres, batch_alter_table on SQLite
test path.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_approval_reviewer_feedback"
down_revision: Union[str, None] = "027_budget_yearly_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            """
            ALTER TABLE approval_reviewers
            ADD COLUMN IF NOT EXISTS feedback TEXT;
            """
        )
    else:
        with op.batch_alter_table("approval_reviewers") as batch:
            batch.add_column(sa.Column("feedback", sa.Text(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE approval_reviewers DROP COLUMN IF EXISTS feedback;")
