from sqlalchemy import Boolean, Column, String

from app.models.base import Base, TimestampMixin


class GoogleSearchTermPattern(TimestampMixin, Base):
    """Regex patterns for SEARCH_NEGATIVES_MISSING detector.

    Seeded in migration 011 with the six SOP negative-keyword categories:
    jobs, press, academic, free, cancel, competitor. Vietnamese + English
    locales covered.
    """

    __tablename__ = "google_search_term_patterns"

    locale = Column(String(8), nullable=False, index=True)  # vi-VN | en
    category = Column(String(30), nullable=False, index=True)
    pattern = Column(String(160), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
