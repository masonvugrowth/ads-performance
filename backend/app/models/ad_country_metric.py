from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String

from app.models.base import Base, TimestampMixin, UUIDType


class AdCountryMetric(TimestampMixin, Base):
    """Per-(ad|campaign) × date × country metrics broken down into
    website vs offline purchases — used by the Booking from Ads matcher.

    For Meta we store one row per (ad_id, date, country) using insights
    fetched with breakdowns=country. For Google we store one row per
    (campaign_id, date, country) with ad_id NULL; country comes from the
    last two characters of the campaign name.
    """

    __tablename__ = "ad_country_metrics"

    platform = Column(String(20), nullable=False, index=True)
    campaign_id = Column(
        UUIDType,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ad_id = Column(
        UUIDType,
        ForeignKey("ads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    date = Column(Date, nullable=False, index=True)
    country = Column(String(4), nullable=False)
    spend = Column(Numeric(15, 2), nullable=False, default=0)
    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    revenue_website = Column(Numeric(15, 2), nullable=False, default=0)
    revenue_offline = Column(Numeric(15, 2), nullable=False, default=0)
    conversions_website = Column(Integer, nullable=False, default=0)
    conversions_offline = Column(Integer, nullable=False, default=0)
