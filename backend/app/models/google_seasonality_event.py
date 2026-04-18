from sqlalchemy import Column, Integer, Numeric, SmallInteger, String, Text

from app.models.base import Base, TimestampMixin


class GoogleSeasonalityEvent(TimestampMixin, Base):
    """Static Vietnam-hotel seasonality calendar used by SEASONALITY_* detectors.

    Seeded in migration 011. Rows describe recurring annual events (Tet, summer
    peak, low season) along with SOP-recommended budget/tCPA adjustments.
    """

    __tablename__ = "google_seasonality_events"

    event_key = Column(String(40), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    start_month = Column(SmallInteger, nullable=False)
    start_day = Column(SmallInteger, nullable=False)
    end_month = Column(SmallInteger, nullable=False)
    end_day = Column(SmallInteger, nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    budget_bump_pct_min = Column(Numeric(5, 2), nullable=True)
    budget_bump_pct_max = Column(Numeric(5, 2), nullable=True)
    tcpa_adjust_pct_min = Column(Numeric(5, 2), nullable=True)
    tcpa_adjust_pct_max = Column(Numeric(5, 2), nullable=True)
    notes = Column(Text, nullable=True)
