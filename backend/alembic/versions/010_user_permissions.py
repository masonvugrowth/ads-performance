"""Create user_permissions table for per-branch + per-section access control

Revision ID: 010_user_permissions
Revises: 009_material_url_source
Create Date: 2026-04-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_user_permissions"
down_revision: Union[str, None] = "009_material_url_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Disable statement timeout (Supabase pooler default is aggressive)
    op.execute("SET LOCAL statement_timeout = 0")

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("branch", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
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
        sa.UniqueConstraint(
            "user_id",
            "branch",
            "section",
            name="uq_user_perm_user_branch_section",
        ),
    )
    op.create_index(
        "ix_user_permissions_user_id",
        "user_permissions",
        ["user_id"],
    )
    op.create_index(
        "ix_user_permissions_user_section",
        "user_permissions",
        ["user_id", "section"],
    )

    # branch: one of 'Saigon'|'Osaka'|'Taipei'|'1948'|'Oani'|'Bread' (enforced at app layer)
    # section: one of 'analytics'|'meta_ads'|'google_ads'|'budget'|'automation'|'ai'|'settings'
    # level: 'view' (read-only) or 'edit' (read + write). No row for (user, branch, section) = no access.
    # Admin role bypasses this table entirely — admins see everything.


def downgrade() -> None:
    op.drop_index("ix_user_permissions_user_section", table_name="user_permissions")
    op.drop_index("ix_user_permissions_user_id", table_name="user_permissions")
    op.drop_table("user_permissions")
