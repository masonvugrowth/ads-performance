from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.models.base import Base, TimestampMixin, UUIDType

# Approval statuses (mirror combo_approvals)
APPROVAL_PENDING = "PENDING_APPROVAL"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"
APPROVAL_CANCELLED = "CANCELLED"

# Per-reviewer statuses
REVIEWER_PENDING = "PENDING"
REVIEWER_APPROVED = "APPROVED"
REVIEWER_REJECTED = "REJECTED"


class LandingPageApproval(TimestampMixin, Base):
    """One approval round per version submit.

    Rule: ALL reviewers must approve to mark APPROVED. ANY reject = REJECTED.
    Once APPROVED, the version can be published. Creator-only launch applies.
    """

    __tablename__ = "landing_page_approvals"

    landing_page_id = Column(
        UUIDType,
        ForeignKey("landing_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id = Column(
        UUIDType,
        ForeignKey("landing_page_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    round = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default=APPROVAL_PENDING, index=True)
    submitted_by = Column(
        UUIDType,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    deadline = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    reject_reason = Column(Text, nullable=True)


class LandingPageApprovalReviewer(TimestampMixin, Base):
    __tablename__ = "landing_page_approval_reviewers"

    approval_id = Column(
        UUIDType,
        ForeignKey("landing_page_approvals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id = Column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(20), nullable=False, default=REVIEWER_PENDING)
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
