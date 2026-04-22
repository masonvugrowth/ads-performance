from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text

from app.models.base import Base, JSONType, TimestampMixin, UUIDType


class LandingPageClaritySnapshot(TimestampMixin, Base):
    """Daily Microsoft Clarity metrics snapshot per landing page.

    Clarity Data Export API only keeps the last 3 days of live data, so we
    pull daily via the Zeabur cron job (`/api/internal/tasks/clarity-sync`)
    and persist one row per (landing_page_id, date, utm_source, utm_campaign,
    utm_content).

    The aggregate row for a page on a given day uses NULL for all UTM fields.
    Per-ad / per-campaign breakdowns use the specific UTM values observed.

    Metric columns map 1:1 to Clarity's 9 metric types plus the Traffic
    sub-fields:
      Traffic          → sessions, bot_sessions, distinct_users, pages_per_session
      EngagementTime   → total_time_sec, active_time_sec
      ScrollDepth      → avg_scroll_depth (%)
      DeadClickCount   → dead_clicks
      RageClickCount   → rage_clicks
      ErrorClickCount  → error_clicks
      QuickbackClick   → quickback_clicks
      ExcessiveScroll  → excessive_scrolls
      ScriptErrorCount → script_errors
    """

    __tablename__ = "landing_page_clarity_snapshots"

    landing_page_id = Column(
        UUIDType,
        ForeignKey("landing_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)
    utm_source = Column(String(100), nullable=True)
    utm_campaign = Column(String(200), nullable=True)
    utm_content = Column(String(200), nullable=True)
    url_raw = Column(Text, nullable=True)

    # Traffic
    sessions = Column(Integer, nullable=False, default=0)
    bot_sessions = Column(Integer, nullable=False, default=0)
    distinct_users = Column(Integer, nullable=False, default=0)
    pages_per_session = Column(Numeric(8, 4), nullable=True)

    # Engagement
    avg_scroll_depth = Column(Numeric(6, 2), nullable=True)
    total_time_sec = Column(Integer, nullable=False, default=0)
    active_time_sec = Column(Integer, nullable=False, default=0)

    # Friction signals (playbook: these are the UX-bug smoke detectors)
    dead_clicks = Column(Integer, nullable=False, default=0)
    rage_clicks = Column(Integer, nullable=False, default=0)
    error_clicks = Column(Integer, nullable=False, default=0)
    quickback_clicks = Column(Integer, nullable=False, default=0)
    excessive_scrolls = Column(Integer, nullable=False, default=0)
    script_errors = Column(Integer, nullable=False, default=0)

    # Forward-compat raw Clarity payload
    raw_data = Column(JSONType, nullable=True)
