from sqlalchemy import Column, ForeignKey, String, UniqueConstraint, Index

from app.models.base import Base, TimestampMixin, UUIDType


class UserPermission(Base, TimestampMixin):
    """Per-user, per-branch, per-section access level.

    level='view' allows reading that branch's data in that section.
    level='edit' allows both read and write.
    No row = no access. Admin role bypasses this table entirely.
    """

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "branch", "section", name="uq_user_perm_user_branch_section"),
        Index("ix_user_permissions_user_section", "user_id", "section"),
    )

    user_id = Column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch = Column(String(20), nullable=False)  # e.g. 'Saigon', 'Osaka', 'Taipei', '1948', 'Oani', 'Bread'
    section = Column(String(20), nullable=False)  # analytics|meta_ads|google_ads|budget|automation|ai|settings
    level = Column(String(10), nullable=False)  # 'view' | 'edit'
